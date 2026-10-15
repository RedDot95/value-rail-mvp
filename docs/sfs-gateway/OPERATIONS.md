# SFS Gateway — normal ChatGPT iPhone runbook

**Status:** bounded direct connector-to-Copilot route verified on 2026-10-15; broader gateway not yet deployed.

## Submit a task

Use normal ChatGPT with the already connected GitHub app. Specify the **exact authorized repository**, acceptance criteria, excluded files, test commands, and cost scope. Ask ChatGPT to inspect the current repository and open a GitHub Issue. Only then, as a separate explicit step, assign that Issue to `copilot-swe-agent[bot]` with the connector's `add_issue_assignees` action. Do not allow Issue titles, external comments, labels or speculative agent instructions to authorize Copilot automatically.

**Proven example:** [Issue #2](https://github.com/RedDot95/value-rail-mvp/issues/2) assigned to Copilot by ChatGPT; [draft PR #3](https://github.com/RedDot95/value-rail-mvp/pull/3).

## Review and verify

1. Retrieve the issue and its PR in ordinary ChatGPT using the GitHub connector.
2. Check actor, branch, base, draft status, precise changed paths and unified diff. Verify protected files and secrets were not changed.
3. Run or obtain deterministic tests. In repositories that require manual approval of Copilot PR Actions, a user with write access must inspect the diff and select **Approve and run workflows** before those workflows execute. Keep this protective default enabled; do not silently disable it.
4. Only mark the work TESTED after examining actual run conclusions and jobs. Do not infer success from a PR, commit or agent narrative.
5. Manually review before merging. This gateway never authorizes an unattended application-code merge.

## Status, retries, stopping

- Status: ask normal ChatGPT to retrieve the Issue, PR, current changed files, Actions runs and checks.
- Failures: inspect specific error, compare expected vs actual changes, and request at most one bounded correction after identifying the cause.
- Retry: explicit issue/PR revision only; avoid reassigning the same issue blindly. Comments mentioning Copilot may start further billable work.
- Cancel: do not create additional assignments. Stop or cancel an active Copilot agent session through GitHub controls if available; closing an issue alone is not evidence the running agent stopped.
- Shut down gateway: stop issuing Copilot assignments; cancel remaining sessions where supported. The present bootstrap has no independent scheduled gateway workflow to disable.

## Cost

The direct ChatGPT/GitHub path does not start a separate ChatGPT Work or Codex task. Copilot usage and GitHub Actions usage are distinct resources. The GitHub connector available here does not expose trustworthy AI-credit balances or hard usage caps. Monitor GitHub Copilot and Actions billing/usage in account settings, and confirm that paid overages remain disabled. Manual approval and task scoping are **not** a technical hard budget ceiling.

## Copy-ready request pattern

"Use the connected GitHub app in this normal ChatGPT conversation. Inspect repository RedDot95/value-rail-mvp first, create one tightly scoped issue with the requested change and deterministic acceptance tests, and explicitly assign it to GitHub Copilot only after verifying the repository and exclusions. Do not invoke Work/Codex; do not change workflow, auth, security or dependency-manifest files; do not merge. Afterwards retrieve the Copilot draft PR and verify its real diff and test results. If budget attribution or authorization cannot be verified, report the limitation."

For SGS, replace the repository only after an authorized Phase B rollout and repository-specific access verification.
