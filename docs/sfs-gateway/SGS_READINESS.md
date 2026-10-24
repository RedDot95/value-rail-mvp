# SGS Private Repository — Phase B onboarding blueprint

**Status:** PLANNED. No SGS repository has been created or initialized.

A private SGS repository is a separate proprietary software asset. The existing public Value Rail repository must NOT become its source or issue tracker.

## Required steps after explicit Phase B authorization

1. Create a private repository under the explicitly approved owner. Verify visibility, branch protection, security settings, Actions policy, and Copilot availability.
2. Verify the GitHub connector is installed with appropriate read/write scope for that repository. Do not assume connector access from `value-rail-mvp` automatically extends to the new private repository.
3. Verify Copilot Cloud Agent can be assigned to a harmless test Issue and can create a draft PR in the private repository. Obtain real evidence for private-target operation and billing before transferring SGS requirements.
4. Keep all SGS Issues, specifications, model context, logs, code and artifacts in the private repository or other explicitly approved private storage. No cross-posts to public Value Rail.
5. Configure least-privilege repository-scoped tokens and short-lived credentials. Agent code does not receive long-lived repo write credentials or unrelated secrets. Never post tokens to ChatGPT.
6. Review Copilot data processing, model provider terms, training and retention settings, and artifact/log retention before sharing proprietary code.
7. Create only approved requirements, architecture decisions, code ownership conventions, tests, and issue backlog. Record product requirements from the user; do not invent business logic.
8. Validate the first end-to-end private pull request and actual CI; enforce manual merge/review and operational budgets.
9. Reassess whether existing direct Copilot assignment is sufficient or whether an independently gated gh-aw execution plane is needed for scale.

## Readiness conditions

The current proof of concept establishes one iPhone-to-GitHub-to-Copilot pathway, but **does not** empirically verify private repo portability, SGS confidentiality controls, controlled monthly usage or autonomous hard resource ceilings. These must be closed before treating Phase B as production ready.
