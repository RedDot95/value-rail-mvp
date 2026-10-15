# SFS Gateway — security, authorization and resource controls

Date: 2026-10-15. This document describes what exists, not hypothetical security guarantees.

## Verified boundaries

The ChatGPT GitHub connector authenticated as `RedDot95`, with admin and push permission on the PUBLIC `value-rail-mvp` repository. Explicit issue assignment to `copilot-swe-agent[bot]` succeeded. Copilot created a draft PR on its own `copilot/` branch, rather than editing `master`. The smoke-test diff included only a documentation file.

The issue's text is UNTRUSTED input to the AI agent. No sensitive content or tokens belong in public issues. Explicit assignment in the authenticated ChatGPT workflow is the currently used authorization decision; text labels or titles alone must not trigger coding.

GitHub Cloud Agent has its own platform restrictions: separate branch and PR, limited repository access, and default blocking of CI on agent PRs until authorized human approval. Do not turn off human CI approval as a convenience.

## Protections not yet implemented

- No verified trigger-independent software authorization gate for autonomous issue events.
- No validated independently enforced global AI-credit budget, atomic reservation ledger or per-run AI cap for Copilot Cloud Agent.
- No custom protected-file allowlist embedded in the execution engine (only platform controls and review).
- No tested private-repository deployment, private identity boundary or secret rotation.
- No verified per-task ability to select Copilot model or cap cloud-agent tokens.
- No verified automated cancellation after quota exhaustion.
- No trusted measurement of Copilot Student model entitlement attribution. Successful agent assignment is evidence of agent access, not billing attribution.

A security prompt is not a substitute for a technical enforcement boundary. Do not label these items IMPLEMENTED.

## Existing CI observation

For smoke PR #3, GitHub Actions run [38668144984](https://github.com/RedDot95/value-rail-mvp/actions/runs/38668144984) was reported as `action_required`; no jobs were returned through the connector. Therefore automated regression tests are **not claimed to have passed**. A repository maintainer should inspect the PR and approve workflow execution in GitHub.

## Economic policy

- ChatGPT Work/Codex: do not invoke for routine development.
- Copilot Cloud Agent: one explicit task assignment per authorized task; no automatic retry or follow-on task.
- GitHub Actions: short-lived jobs and existing CI; never turn off credit/usage safeguards.
- External services: no new paid API keys, no overages, no continuous servers.
- No assumption that GitHub Student benefits imply unlimited inference or Actions minutes.
- No guaranteed numerical budget cap is currently in force for cloud-agent usage.

## Conditional hardening path

For fully autonomous issue-triggered execution with robust hard limits, evaluate official `gh-aw` with compiled and pinned workflows, safe-output PR creation, protected files, trusted event identity checks, concurrency limits, and audit logs. Confirm the exact Copilot seat-authentication path and billing before enabling. Alternatively implement a narrowly scoped direct CLI runner only if equivalent protections and caps can be demonstrated. Neither is deployed here.

Keep the public Value Rail proof of concept isolated from future private SGS code and artifacts.
