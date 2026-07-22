# Upgrade and rollback

AgentKit 1.0 supports migration from 0.4.0 through 0.11.0.

```bash
agentkit migrate check
agentkit migrate apply
agentkit self-test
```

`check` is read-only. Its JSON report classifies each resource as `create`, `update`, `unchanged`, or `preserve`. `apply` acquires an exclusive migration lock and performs only safe operations.

## Preservation rules

- `AGENT.md` is user-owned after installation.
- Existing configuration values and unknown TOML sections are preserved.
- AgentKit-managed blocks in Make and Git ignore files are additive.
- An unchanged managed resource can be replaced.
- A customized or unrecognized legacy resource is retained. The 1.0 version is written under `.agent/update-candidates/` for manual comparison.
- Replaced files are copied to `.agent/backups/<migration-id>/` first.

Running `migrate apply` repeatedly is safe. Files marked `preserved-customization` remain protected on later migrations.

## Manual rollback

1. Stop AgentKit processes and inspect `.agent/state/migration.lock`.
2. Restore the required files from the latest `.agent/backups/<migration-id>/` directory.
3. Reinstall the previous AgentKit package version.
4. Restore the previous `.agent/installation.json` from version control.
5. Run `agentkit self-test` and review `agentkit migrate check` before another attempt.

Rollback never resets application source code or discards a working-tree diff.
