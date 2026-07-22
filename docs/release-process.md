# Release process

1. Start `release/agentkit-1.0` from the tested `main` commit.
2. Run skill validation, release contract validation, the complete test suite, compileall, and the secret scan.
3. Run the Linux/Windows Python 3.11–3.14 matrix.
4. Build wheel and sdist twice with `SOURCE_DATE_EPOCH` set to the commit timestamp, normalize sdist ownership and archive timestamps, and compare SHA-256 digests.
5. Install the wheel in a clean environment and initialize a project whose path contains spaces.
6. Run the deterministic offline evaluation smoke suite and confirm no correctness regression.
7. Run one explicit opt-in OpenAI comparison against the CLI baseline. Never persist the API key or raw sensitive output.
8. Confirm no known P0/P1 findings and review dependency and secret scans.
9. Merge the release PR, tag the exact commit as `v1.0.0`, and require approval in the GitHub `pypi` environment.
10. Publish through PyPI trusted publishing and attach distributions plus checksums to the GitHub release.

The release workflow cannot publish from an ordinary branch. Tag publication is separate from project runtime; AgentKit never merges or deploys user repositories.
