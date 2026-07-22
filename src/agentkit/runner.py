from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .adapters import AgentAdapter, CommandAgentAdapter
from .commands import CommandPolicy
from .config import AgentKitConfig, load_config
from .git import changed_files, current_head, diff_text, is_git_repository
from .graphify import GraphContext, GraphifyClient
from .models import CommandResult, CompletionReport, ReviewReport, RunMode, Stage
from .prompts import fix_prompt, implementation_prompt, review_prompt
from .review import parse_review
from .state import RunState
from .telemetry import BudgetController, BudgetStatus, UsageLedger
from .triage import classify_task
from .verification import run_checks

_INTERNAL_ARTIFACT_PREFIXES = (".agent/state/", ".agent/cache/", ".agent/evals/")


def _workflow_changed_files(project_root: Path) -> list[str]:
    return [
        path
        for path in changed_files(project_root)
        if not path.startswith(_INTERNAL_ARTIFACT_PREFIXES)
    ]


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
    route_override: str | None = None
    resume_run_id: str | None = None


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

    def _provider_for(self, platform_override: str | None) -> str:
        return (platform_override or self.config.agent.platform).lower()

    def _ledger_provider(self, request: RunRequest) -> str:
        return self._provider_for(request.agent_override)

    def _adapter_for(self, platform_override: str | None) -> AgentAdapter:
        if self._adapter_override is not None:
            return self._adapter_override
        platform = self._provider_for(platform_override)
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
            provider=platform,
        )

    def _execution_for_phase(
        self,
        phase: str,
        *,
        request: RunRequest,
        triage: object,
    ) -> tuple[AgentAdapter, str]:
        """Resolve one executor per phase while preserving the legacy fixed-CLI default."""
        del phase, triage
        return (
            self._adapter_for(request.agent_override),
            self._provider_for(request.agent_override),
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
                "hard_input_tokens": self.config.budget.hard_input_tokens,
                "hard_output_tokens": self.config.budget.hard_output_tokens,
                "hard_agent_calls": self.config.budget.hard_agent_calls,
                "hard_duration_seconds": self.config.budget.hard_duration_seconds,
            },
        }

    def _persist_telemetry(
        self,
        state: RunState,
        ledger: UsageLedger,
        controller: BudgetController,
    ) -> BudgetStatus:
        ledger.save(state.directory / "usage.json")
        status = controller.evaluate(ledger)
        state.write_json("budget.json", status.to_dict())
        return status

    def _tool_observer(
        self,
        state: RunState,
        ledger: UsageLedger,
        controller: BudgetController,
    ):
        def observe(phase: str, result: CommandResult) -> None:
            ledger.record(phase=phase, kind="tool", result=result, provider="local")
            self._persist_telemetry(state, ledger, controller)

        return observe

    def _execute_agent(
        self,
        *,
        adapter: AgentAdapter,
        prompt: str,
        phase: str,
        state: RunState,
        ledger: UsageLedger,
        controller: BudgetController,
        provider: str,
        mutating: bool = False,
    ) -> tuple[CommandResult | None, BudgetStatus, str]:
        allowed, reason = controller.can_start_agent_call(ledger, phase)
        if not allowed:
            status = self._persist_telemetry(state, ledger, controller)
            return None, status, reason
        if mutating:
            state.mark_mutation_started(phase)
        result = adapter.execute(prompt, phase=phase, cwd=self.project_root)
        if mutating:
            state.mark_mutation_completed(diff_text(self.project_root))
        ledger.record(phase=phase, kind="agent", result=result, provider=provider)
        status = self._persist_telemetry(state, ledger, controller)
        reason = "; ".join(status.hard_limits_exceeded)
        return result, status, reason

    def _budget_outcome(
        self,
        *,
        state: RunState,
        mode: RunMode,
        baseline_files: list[str],
        reason: str,
        status: BudgetStatus,
    ) -> RunOutcome:
        task_files = sorted(set(_workflow_changed_files(self.project_root)) - set(baseline_files))
        completion = CompletionReport(
            status="budget_exceeded",
            mode=mode,
            changed_files=task_files,
            checks_passed=False,
            review_passed=False,
            blocking_findings=0,
            scope_passed=len(task_files) <= self.config.scope.max_changed_files,
            budget_passed=False,
            residual_risks=[reason or "Configured hard budget was exceeded"],
        )
        payload = completion.to_dict()
        payload["budget"] = status.to_dict()
        state.write_json("completion.json", payload)
        return RunOutcome(
            5,
            Stage.BUDGET_EXCEEDED,
            state.run_id,
            completion,
            reason or "Configured hard budget was exceeded",
        )

    def run(self, request: RunRequest) -> RunOutcome:
        if not request.task.strip():
            raise AgentKitError("Task cannot be empty")
        if not is_git_repository(self.project_root):
            raise AgentKitError("AgentKit requires a Git repository for change isolation")

        baseline_files = _workflow_changed_files(self.project_root)
        if baseline_files and self.config.workflow.require_clean_tree:
            raise AgentKitError(
                "Working tree is not clean. Commit/stash current work or set "
                "workflow.require_clean_tree=false after reviewing the risk."
            )

        state = RunState(
            self.project_root,
            run_id=request.resume_run_id,
            resume=bool(request.resume_run_id),
        )
        provider = self._ledger_provider(request)
        ledger = UsageLedger(run_id=state.run_id, provider=provider)
        controller = BudgetController(self.config.budget)
        self._persist_telemetry(state, ledger, controller)
        observer = self._tool_observer(state, ledger, controller)

        baseline_head = current_head(self.project_root)
        triage = classify_task(request.task, request.mode)
        state.write_json("triage.json", triage.to_dict())
        state.checkpoint("triage", triage.to_dict())

        graph = GraphContext(False, False, "", "", "Graph step skipped")
        if not request.skip_graph:
            graph = GraphifyClient(
                self.project_root,
                self.config.graphify,
                self.policy,
                observer=observer,
            ).build_context(request.task)
        state.write_json("graph.json", graph.to_dict())
        state.checkpoint("graph_context", graph.to_dict())

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

        initial_phase = "plan" if request.plan_only else "implementation"
        read_only_files = _workflow_changed_files(self.project_root) if request.plan_only else []
        read_only_diff_hash = (
            hashlib.sha256(diff_text(self.project_root).encode("utf-8")).hexdigest()
            if request.plan_only
            else ""
        )
        adapter, phase_provider = self._execution_for_phase(
            initial_phase,
            request=request,
            triage=triage,
        )
        implementation, budget_status, budget_reason = self._execute_agent(
            adapter=adapter,
            prompt=prompt,
            phase=initial_phase,
            state=state,
            ledger=ledger,
            controller=controller,
            provider=phase_provider,
            mutating=not request.plan_only,
        )
        if implementation is None or budget_status.hard_limits_exceeded:
            return self._budget_outcome(
                state=state,
                mode=triage.mode,
                baseline_files=baseline_files,
                reason=budget_reason,
                status=budget_status,
            )
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
            if (
                _workflow_changed_files(self.project_root) != read_only_files
                or hashlib.sha256(diff_text(self.project_root).encode("utf-8")).hexdigest()
                != read_only_diff_hash
            ):
                return RunOutcome(
                    2,
                    Stage.FAILED,
                    state.run_id,
                    None,
                    "Plan phase modified the working tree",
                )
            return RunOutcome(0, Stage.COMPLETE, state.run_id, None, "Plan completed; no implementation requested")

        checks = run_checks(
            self.project_root,
            self.config.verification,
            self.policy,
            observer=observer,
        )
        state.write_json("verification.json", [item.to_dict() for item in checks])
        state.checkpoint("verification", [item.to_dict() for item in checks])
        checks_passed = bool(checks) and all(item.passed for item in checks)

        review = ReviewReport(verdict="skipped")
        review_passed = not self.config.workflow.require_review
        if self.config.workflow.require_review:
            review, budget_status, budget_reason = self._run_review(
                request,
                triage,
                state,
                ledger=ledger,
                controller=controller,
            )
            if review is None or budget_status.hard_limits_exceeded:
                return self._budget_outcome(
                    state=state,
                    mode=triage.mode,
                    baseline_files=baseline_files,
                    reason=budget_reason,
                    status=budget_status,
                )
            review_passed = review.verdict in {
                "approved",
                "approved_with_non_blocking_findings",
            } and not review.blocking_findings
            state.checkpoint("review", review.to_dict())

        fixes_used = 0
        while review.blocking_findings and fixes_used < self.config.workflow.max_fix_iterations:
            fixes_used += 1
            fix_adapter, fix_provider = self._execution_for_phase(
                "targeted_fix",
                request=request,
                triage=triage,
            )
            correction, budget_status, budget_reason = self._execute_agent(
                adapter=fix_adapter,
                prompt=fix_prompt(task=request.task, review=review),
                phase="targeted_fix",
                state=state,
                ledger=ledger,
                controller=controller,
                provider=fix_provider,
                mutating=True,
            )
            if correction is None or budget_status.hard_limits_exceeded:
                return self._budget_outcome(
                    state=state,
                    mode=triage.mode,
                    baseline_files=baseline_files,
                    reason=budget_reason,
                    status=budget_status,
                )
            state.write_json(f"fix-{fixes_used}-command.json", correction.to_dict())
            if not correction.passed:
                break
            checks = run_checks(
                self.project_root,
                self.config.verification,
                self.policy,
                observer=observer,
            )
            state.write_json(
                f"verification-after-fix-{fixes_used}.json",
                [item.to_dict() for item in checks],
            )
            checks_passed = bool(checks) and all(item.passed for item in checks)
            review, budget_status, budget_reason = self._run_review(
                request,
                triage,
                state,
                ledger=ledger,
                controller=controller,
                suffix=f"-after-fix-{fixes_used}",
            )
            if review is None or budget_status.hard_limits_exceeded:
                return self._budget_outcome(
                    state=state,
                    mode=triage.mode,
                    baseline_files=baseline_files,
                    reason=budget_reason,
                    status=budget_status,
                )
            review_passed = review.verdict in {
                "approved",
                "approved_with_non_blocking_findings",
            } and not review.blocking_findings

        final_files = _workflow_changed_files(self.project_root)
        task_files = sorted(set(final_files) - set(baseline_files))
        scope_passed = len(task_files) <= self.config.scope.max_changed_files
        final_budget = self._persist_telemetry(state, ledger, controller)
        budget_passed = final_budget.allowed
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
        residual_risks.extend(final_budget.soft_limits_reached)
        residual_risks.extend(final_budget.hard_limits_exceeded)

        ready = checks_passed and review_passed and scope_passed and budget_passed
        completion = CompletionReport(
            status="ready_for_review" if ready else "needs_attention",
            mode=triage.mode,
            changed_files=task_files,
            checks_passed=checks_passed,
            review_passed=review_passed,
            blocking_findings=len(review.blocking_findings),
            scope_passed=scope_passed,
            budget_passed=budget_passed,
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
        request: RunRequest,
        triage: object,
        state: RunState,
        *,
        ledger: UsageLedger,
        controller: BudgetController,
        suffix: str = "",
    ) -> tuple[ReviewReport | None, BudgetStatus, str]:
        before = _workflow_changed_files(self.project_root)
        before_diff_hash = hashlib.sha256(diff_text(self.project_root).encode("utf-8")).hexdigest()
        adapter, provider = self._execution_for_phase(
            "review",
            request=request,
            triage=triage,
        )
        result, budget_status, budget_reason = self._execute_agent(
            adapter=adapter,
            prompt=review_prompt(
                task=request.task,
                diff=diff_text(self.project_root),
                triage=triage,
            ),
            phase="review",
            state=state,
            ledger=ledger,
            controller=controller,
            provider=provider,
        )
        if result is None:
            return None, budget_status, budget_reason
        state.write_json(f"review-command{suffix}.json", result.to_dict())
        state.write_text(f"review{suffix}.stdout.txt", result.stdout)
        state.write_text(f"review{suffix}.stderr.txt", result.stderr)
        after = _workflow_changed_files(self.project_root)
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
            report = ReviewReport(
                verdict="changes_required",
                findings=parse_review(
                    '{"verdict":"changes_required","findings":[{"severity":"P1",'
                    '"issue":"Review phase modified the working tree",'
                    '"evidence":"Git status changed during a read-only review",'
                    '"smallest_fix":"Revert review-only mutations and rerun review"}]}'
                ).findings,
                raw_output=result.stdout,
            )
            return report, budget_status, budget_reason
        report = parse_review(result.stdout if result.passed else result.stdout + "\n" + result.stderr)
        state.write_json(f"review{suffix}.json", report.to_dict())
        return report, budget_status, budget_reason
