# AI Development Instructions

## Repository workflow

Before changing code:
1. Read `README.md`.
2. Read `DEVELOPMENT.md`.
3. Read relevant design, TODO, roadmap, release, phase and audit documents.
4. Inspect the existing implementation before proposing replacement architecture.

## Development completion evidence

For every meaningful feature or bug fix, create or update its entry in `DEVELOPMENT.md`.

Use only these states where applicable: PLANNED, IN PROGRESS, BLOCKED, AWAITING ACCEPTANCE, COMPLETE, DEFERRED.

Never mark a coding task COMPLETE merely because an agent says it is complete. Verify repository evidence:
- implementation exists;
- relevant files changed;
- a non-empty diff or equivalent evidence exists;
- tests exist or the reason for no test is recorded;
- relevant tests pass;
- CI passes where available;
- commit/PR evidence is recorded;
- merge status is recorded where required;
- external/user acceptance is kept separate.

An empty result, no write/edit action, unchanged branch HEAD, empty diff, or missing requested validation means the task is not complete.

When documentation conflicts with code, tests, Git history or CI, repository evidence wins.
