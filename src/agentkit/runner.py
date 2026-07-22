from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .adapters import AgentAdapter, CommandAgentAdapter
from .commands import CommandPolicy
from .config import AgentKitConfig, load_config
from .git import changed_files, current_head, diff_text, is_git_repository
from .graphify import GraphContext, GraphifyClient
from .models import CompletionReport, ReviewReport, RunMode, Stage
from .prompts import fix_prompt, implementation_prompt, review_prompt
from .review import parse_review
from .state import RunState
from .triage import classify_task
from .verification import run_checks


class AgentKitError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunRequest:
    task: str
    mode: RunMode = RunMode.AUTO
    agent_override: str | None = None
    plan_only: bool = False
    dry_run: bool = False
    approve_deep: bool = False
    skip_graph: bool = False


@dataclass(frozen=True)
class RunOutcome:
    exit_code: int
    stage: Stage
    run_id: str
    completion: CompletionReport | None
    message: str


class AgentKitRunner:
    def __init__(
        self,
        project_root: Path,
        *,
        config: AgentKitConfig | None = None,
        adapter: AgentAdapter | None = None,
    ) -> None:
        self.project_root = project_root
        self.config = config or load_config(project_root)
        self.policy = CommandPolicy(
            self.config.security.allowed_executables,
            self.config.security.denied_substrings,
        )
        self._adapter_override = adapter

    def _adapter_for(self, platform_override: str | None) -> AgentAdapter:
        if self._adapter_override is not None:
            return self._adapter_override
        platform = (platform_override or self.config.agent.platform).lower()
        presets = {
            "codex": ["codex", "exec", "{prompt}"],
            "claude": ["claude", "-p", "{prompt}"],
            "gemini": ["gemini", "-p", "{prompt}"],
            "aider": ["aider", "--message", "{prompt}"],
        }
        if platform == self.config.agent.platform.lower():
            command_template = self.config.agent.command
        elif platform in presets:
            command_template = presets[platform]
        else:
            raise AgentKitError(
                f"Unknown agent platform '{platform}'. Configure [agent].command in .agent/agentkit.toml."
            )
        return CommandAgentAdapter(
            command_template,
            timeout_seconds=self.config.agent.timeout_seconds,
            policy=self.policy,
        )

    def _task_packet(
        self,
        request: RunRequest,
        triage: object,
        graph: GraphContext,
        baseline_head: str,
    ) -> dict[str, object]:
        return {
            "task": request.task,
            "mode": triage.mode.value,
            "risk_reasons": triage.risk_reasons,
            "selected_skills": triage.selected_skills,
            "graph": graph.to_dict(),
            "git_head": baseline_head,
            "limits": {
                "max_changed_files": self.config.scope.max_changed_files,
                "max_fix_iterations": self.config.workflow.max_fix_iterations,
            },
        }

    def run(self, request: RunRequest) -> RunOutcome:
        if not request.task.strip():
            raise AgentKitError("Task cannot be empty")
        if not is_git_repository(self.project_root):
            raise AgentKitError("AgentKit requires a Git repository for change isolation")

        baseline_files = changed_files(self.project_root)
        if baseline_files and self.config.workflow.require_clean_tree:
            raise AgentKitError(
                "Working tree is not clean. Commit/stash current work or set "
                "workflow.require_clean_tree=false after reviewing the risk."
            )

        state = RunState(self.project_root)
        adapter = self._adapter_for(request.agent_override)
        baseline_head = current_head(self.project_root)
        triage = classify_task(request.task, request.mode)
        state.write_json("triage.json", triage.to_dict())

        graph = GraphContext(False, False, "", "", "Graph step skipped")
        if not request.skip_graph:
            graph = GraphifyClient(
                self.project_root,
                self.config.graphify,
                self.policy,
            ).build_context(request.task)
        state.write_json("graph.json", graph.to_dict())

        packet = self._task_packet(request, triage, graph, baseline_head)
        state.write_json("task-packet.json", packet)

        if (
            triage.mode is RunMode.DEEP
            and self.config.workflow.deep_requires_approval
            and not request.approve_deep
        ):
            state.write_json(
                "completion.json",
                {"status": "approval_required", "reason": "deep mode requires --approve-deep"},
            )
            return RunOutcome(
                3,
                Stage.APPROVAL_REQUIRED,
                state.run_id,
                None,
                "Deep mode selected. Review task-packet.json and rerun with --approve-deep.",
            )

        prompt = implementation_prompt(
            project_root=self.project_root,
            task=request.task,
            triage=triage,
            graph=graph,
            plan_only=request.plan_only,
        )
        state.write_text("implementation-prompt.md", prompt)
        if request.dry_run:
            return RunOutcome(0, Stage.TRIAGE, state.run_id, None, "Dry run created task packet and prompt")

        implementation = adapter.execute(prompt, phase="implementation", cwd=self.project_root)
        state.write_json("implementation-command.json", implementation.to_dict())
        state.write_text("implementation.stdout.txt", implementation.stdout)
        state.write_text("implementation.stderr.txt", implementation.stderr)
        if not implementation.passed:
            return RunOutcome(
                2,
                Stage.FAILED,
                state.run_id,
                None,
                f"Agent implementation command failed with exit code {implementation.returncode}",
            )
        if request.plan_only:
            return RunOutcome(0, Stage.COMPLETE, state.run_id, None, "Plan completed; no implementation requested")

        checks = run_checks(self.project_root, self.config.verification, self.policy)
        state.write_json("verification.json", [item.to_dict() for item in checks])
        checks_passed = bool(checks) and all(item.passed for item in checks)

        review = ReviewReport(verdict="skipped")
        review_passed = not self.config.workflow.require_review
        if self.config.workflow.require_review:
            review = self._run_review(request.task, triage, state, adapter=adapter)
            review_passed = review.verdict == "approved" and not review.blocking_findings

        fixes_used = 0
        while review.blocking_findings and fixes_used < self.config.workflow.max_fix_iterations:
            fixes_used += 1
            correction = adapter.execute(
                fix_prompt(task=request.task, review=review),
                phase="targeted-fix",
                cwd=self.project_root,
            )
            state.write_json(f"fix-{fixes_used}-command.json", correction.to_dict())
            if not correction.passed:
                break
            checks = run_checks(self.project_root, self.config.verification, self.policy)
            state.write_json(
                f"verification-after-fix-{fixes_used}.json",
                [item.to_dict() for item in checks],
            )
            checks_passed = bool(checks) and all(item.passed for item in checks)
            review = self._run_review(
                request.task,
                triage,
                state,
                adapter=adapter,
                suffix=f"-after-fix-{fixes_used}",
            )
            review_passed = review.verdict == "approved" and not review.blocking_findings

        final_files = changed_files(self.project_root)
        task_files = sorted(set(final_files) - set(baseline_files))
        scope_passed = len(task_files) <= self.config.scope.max_changed_files
        residual_risks: list[str] = []
        if not graph.available:
            residual_risks.append(graph.warning or "Graphify context was unavailable")
        if not checks:
            residual_risks.append("No verification commands were discovered or configured")
        if not checks_passed:
            residual_risks.append("One or more verification commands failed")
        if not review_passed:
            residual_risks.append("Adversarial review did not produce an approved blocking-free result")
        if not scope_passed:
            residual_risks.append("Changed-file count exceeded configured scope limit")

        ready = checks_passed and review_passed and scope_passed
        completion = CompletionReport(
            status="ready_for_review" if ready else "needs_attention",
            mode=triage.mode,
            changed_files=task_files,
            checks_passed=checks_passed,
            review_passed=review_passed,
            blocking_findings=len(review.blocking_findings),
            scope_passed=scope_passed,
            residual_risks=residual_risks,
        )
        state.write_json("completion.json", completion.to_dict())
        return RunOutcome(
            0 if completion.ready else 4,
            Stage.COMPLETE if completion.ready else Stage.FAILED,
            state.run_id,
            completion,
            "Task is ready for human review" if completion.ready else "Task needs attention",
        )

    def _run_review(
        self,
        task: str,
        triage: object,
        state: RunState,
        *,
        adapter: AgentAdapter,
        suffix: str = "",
    ) -> ReviewReport:
        before = changed_files(self.project_root)
        before_diff_hash = hashlib.sha256(diff_text(self.project_root).encode("utf-8")).hexdigest()
        result = adapter.execute(
            review_prompt(task=task, diff=diff_text(self.project_root), triage=triage),
            phase="review",
            cwd=self.project_root,
        )
        state.write_json(f"review-command{suffix}.json", result.to_dict())
        state.write_text(f"review{suffix}.stdout.txt", result.stdout)
        state.write_text(f"review{suffix}.stderr.txt", result.stderr)
        after = changed_files(self.project_root)
        after_diff_hash = hashlib.sha256(diff_text(self.project_root).encode("utf-8")).hexdigest()
        if before != after or before_diff_hash != after_diff_hash:
            report = ReviewReport(
                verdict="changes_required",
                findings=[],
                raw_output=result.stdout,
            )
            payload = report.to_dict()
            payload["runner_error"] = "Review phase modified the working tree"
            state.write_json(f"review{suffix}.json", payload)
            return ReviewReport(
                verdict="changes_required",
                findings=parse_review(
                    '{"verdict":"changes_required","findings":[{"severity":"P1",'
                    '"issue":"Review phase modified the working tree",'
                    '"evidence":"Git status changed during a read-only review",'
                    '"smallest_fix":"Revert review-only mutations and rerun review"}]}'
                ).findings,
                raw_output=result.stdout,
            )
        report = parse_review(result.stdout if result.passed else result.stdout + "\n" + result.stderr)
        state.write_json(f"review{suffix}.json", report.to_dict())
        return report
