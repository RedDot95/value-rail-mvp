# SFS AI Development Gateway — verified initial architecture

Date: 2026-10-15. Scope: **Phase A only**. SGS creation and development are prohibited until separately authorized.

## Selected bootstrap: ChatGPT GitHub Connector + Copilot Cloud Agent

The following minimal path has been **observed** in the personally owned repository `RedDot95/value-rail-mvp`:

`Normal ChatGPT → authenticated GitHub Connector → GitHub Issue → explicit Copilot assignment → Copilot-generated draft PR → normal ChatGPT reads PR and diff`

Real smoke-test evidence: [Issue #2](https://github.com/RedDot95/value-rail-mvp/issues/2), [PR #3](https://github.com/RedDot95/value-rail-mvp/pull/3). The issue was authored by `RedDot95` through the connected GitHub app; the Copilot assignee was accepted; Copilot opened a draft PR on its isolated `copilot/` branch and added `docs/sfs-gateway-e2e-smoke.md`.

This is **not** a claim that the complete development gateway is deployed. It is a working, bounded ChatGPT-to-Copilot coding path. No custom automation or independent budget-gate currently controls the assignment.

## Architecture boundaries

**Control plane (currently operational subset):** ChatGPT requests one task; the GitHub connector writes the Issue and explicitly assigns the Copilot agent. GitHub stores the task record. There is no implicit `[AI-BUILD]` or issue-edit auto-trigger.

**Execution plane (currently operational subset):** GitHub Copilot Cloud Agent runs remotely in GitHub infrastructure and works on a separate branch and draft PR. Ordinary repository tests are already defined in `.github/workflows/tests.yml`. Their execution for Copilot PRs requires human approval by default.

**Target repository:** `value-rail-mvp` is public and is only the bootstrap demonstration. Neither confidential gateway secrets nor SGS source belong here.

**Future architecture:** dedicated private gateway infrastructure repository and separately authorized private target repository. Prefer repository-local Copilot execution with independently scoped GitHub permissions; do not presume the control-plane token has cross-repository access.

## Alternative evaluation

1. **Copilot Cloud Agent — selected for bootstrap:** successful authenticated GitHub connector assignment and real draft PR; no manual Copilot token provisioning; lower implementation and operational complexity. Missing: externally enforceable hard per-run and aggregate credit caps, automatically approved CI, independent authorization workflow.
2. **GitHub Agentic Workflows (gh-aw) — candidate for hardened gateway:** strong safe-output and protected-file controls, but requires compiling workflow sources and verifying personal-seat authentication/billing in this account. No gh-aw deployment or inference test has occurred.
3. **Direct Copilot CLI + GitHub Actions:** GitHub documents personal-repository `GITHUB_TOKEN` Copilot-seat attribution, but warns of a broader agent execution surface than gh-aw. Not enabled here.
4. **Copilot SDK / custom GitHub App / MCP:** unnecessary at bootstrap, and no compatible deployed integration has been verified.

## Non-goals and phase boundaries

No SGS repository; no SGS features; no auto-merge; no public intellectual property. Existing Value Rail application logic and its scheduled workflow remain unchanged.

## Acceptance status

- Verified: connector authentication, repository access, issue creation, Copilot assignment, Copilot-created draft PR and file diff retrieval.
- Independently observed: `SFS-GATEWAY-E2E-PASS` in the resulting new document.
- Incomplete: full CI execution; hard quota enforcement; separate private gateway repository; private-target portability; repeatable automation policy and secured trigger semantics.

Do not describe this operating subset as a finished, secured, fully autonomous gateway.
