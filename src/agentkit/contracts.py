from __future__ import annotations

from dataclasses import dataclass

from .exit_codes import STABLE_EXIT_CODES

PACKAGE_VERSION = "1.0.3"
CONFIG_VERSION = 1
INSTALLATION_MANIFEST_VERSION = 1
RUN_STATE_VERSION = 1
DIAGNOSTICS_VERSION = 1
MIGRATION_REPORT_VERSION = 1

MODEL_PHASES = ("plan", "implementation", "review", "targeted_fix")

CORE_COMMANDS = (
    "init",
    "run",
    "plan",
    "graph",
    "profile",
    "context",
    "cache",
    "check",
    "doctor",
    "status",
    "usage",
    "budget",
    "report",
    "models",
    "providers",
    "migrate",
    "self-test",
    "diagnostics",
    "version",
)

STABLE_MAKE_TARGETS = (
    "ai-upgrade-check",
    "ai-migrate",
    "ai-self-test",
    "ai-diagnostics",
    "ai-release-check",
)

ARTIFACT_SCHEMAS = (
    "agent-capabilities.schema.json",
    "compiled-context.schema.json",
    "completion.schema.json",
    "diagnostics-manifest.schema.json",
    "eval-comparison.schema.json",
    "eval-run.schema.json",
    "eval-summary.schema.json",
    "eval-task.schema.json",
    "hotspot-context.schema.json",
    "installation-manifest.schema.json",
    "migration-report.schema.json",
    "model-attempts.schema.json",
    "model-route.schema.json",
    "plan.schema.json",
    "project-profile.schema.json",
    "prompt-prefix.schema.json",
    "quality-ci-result.schema.json",
    "quality-diff.schema.json",
    "quality-gate.schema.json",
    "quality-hotspots.schema.json",
    "quality-provider.schema.json",
    "quality-route.schema.json",
    "quality-snapshot.schema.json",
    "review.schema.json",
    "run-state.schema.json",
    "self-test.schema.json",
    "task-packet.schema.json",
    "triage.schema.json",
    "usage.schema.json",
    "verification-plan.schema.json",
)


@dataclass(frozen=True)
class PublicContracts:
    package_version: str = PACKAGE_VERSION
    config_version: int = CONFIG_VERSION
    run_state_version: int = RUN_STATE_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "package_version": self.package_version,
            "config_version": self.config_version,
            "run_state_version": self.run_state_version,
            "commands": list(CORE_COMMANDS),
            "make_targets": list(STABLE_MAKE_TARGETS),
            "model_phases": list(MODEL_PHASES),
            "exit_codes": STABLE_EXIT_CODES,
            "artifact_schemas": list(ARTIFACT_SCHEMAS),
        }
