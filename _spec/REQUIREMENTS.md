# Requirements (MVP)

## R1: Project management
- Create/edit Projects
- Each Project has: name, description, repo_path (local path), stack tags

## R2: Requirements
- Create/edit Requirements with IDs (R1, R2…)
- Each requirement has acceptance criteria
- Requirements can be linked to tasks and test cases

## R3: Tasks
- Create/edit Tasks (T1, T2…)
- Task has status: backlog / in_progress / blocked / done
- Task links to one or more requirements

## R4: Runs
- Create a Run for a project (e.g., "Run 2025-12-24_01")
- Run has stage/state: PM → DEV → QA → SEC → READY_FOR_COMMIT → MERGED → READY_FOR_DEPLOY → DEPLOYED
- Run stores artifacts: pm_result/dev_result/qa_result/sec_result JSON

## R5: Gate enforcement
- If QA result status != pass → run state becomes QA_FAILED
- If Security result status != pass → run state becomes SEC_FAILED
- Only when QA + Sec pass can state advance to READY_FOR_COMMIT

## R6: QA writes tests
- QA report can include:
  - tests added/changed
  - commands run
  - failing tests list
  - link to requirement IDs covered

## R7: Security threat intel
- Security can add Threat Intel entries:
  - date, source, summary, affected tech, action, status
- Security report can reference intel entries and required controls

## R8: Human approval
- Transition READY_FOR_DEPLOY → DEPLOYED requires a human "Approve deploy" action in UI

## R9: Audit log
- Every state change is logged with timestamp and actor (human or agent role)
