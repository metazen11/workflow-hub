# Refactor Plan: Simplify to Core

## Target: Projects → Tasks → Work Cycles with Claims Validation

---

## Current State (18 models, 14 services, 186 routes)

### Models
| Model | Purpose | KEEP/KILL/MERGE |
|-------|---------|-----------------|
| Project | Container for work | **KEEP** |
| Task | Unit of work | **KEEP** |
| Run | Pipeline execution | **KILL** - merge into Task work cycles |
| Handoff | Agent work session | **KEEP** - rename to WorkCycle |
| Claim | Falsifiable statement | **KEEP** |
| ClaimTest | Test definition | **KEEP** |
| ClaimEvidence | Test results | **KEEP** |
| Proof | Evidence artifacts | **MERGE** into ClaimEvidence |
| AgentReport | Agent output | **KILL** - results go in WorkCycle |
| Requirement | High-level specs | **KILL** - use Claims instead |
| BugReport | External bug intake | **KEEP** (separate concern) |
| Credential | Secrets storage | **KEEP** |
| Environment | Deploy targets | **KEEP** |
| DeploymentHistory | Deploy log | **KEEP** |
| Webhook | n8n integration | **KEEP** |
| ThreatIntel | Security feeds | **KILL** - not used |
| RoleConfig | Agent prompts | **KEEP** |
| LLMSession | Chat history | **KEEP** |
| Attachment | Task files | **KEEP** |
| Audit | Event log | **KEEP** |

### Services to KILL
- `run_service.py` - Run concept eliminated
- `director_service.py` - Was orchestrating Runs
- `docs_service.py` - Speculative

### Services to KEEP
- `claim_service.py` - Core
- `ledger_service.py` - Core
- `handoff_service.py` → rename to `work_cycle_service.py`
- `task_queue_service.py` - Useful
- `llm_service.py` - Useful
- `proof_service.py` → merge into claim_service
- `deployment_service.py` - Keep for now
- `webhook_service.py` - Integration
- `crypto_service.py` - Security
- `agent_service.py` - Core

---

## New Simplified Model

```
Project
  └── Tasks (units of work)
        └── Claims (falsifiable statements about this task)
              └── Tests (how to validate)
              └── Evidence (results)
        └── WorkCycles (agent work sessions)
              └── artifacts/proofs
        └── Attachments
```

### Core Flow

1. **Project** has **Tasks**
2. **Tasks** have **Claims** (what must be true when done)
3. **Claims** have **Tests** (how to validate)
4. **Agent** picks up Task → creates **WorkCycle**
5. Agent works → produces artifacts
6. Agent runs claim tests → produces **Evidence**
7. If tests pass → Task advances
8. If tests fail → **Ledger entry** + new Tasks auto-generated

### Task States (simplified)
```
BACKLOG → IN_PROGRESS → VALIDATING → DONE
              ↓              ↓
          BLOCKED      FAILED (creates ledger entry + tasks)
```

No more: PM, DEV, QA, SEC, DOCS stages
Instead: Claims define what must be validated

---

## URL Simplification

### Current: 186 routes
### Target: ~50 routes

**Keep (standardize to plural nouns):**
```
/api/projects
/api/projects/{id}
/api/projects/{id}/tasks
/api/projects/{id}/claims

/api/tasks/{id}
/api/tasks/{id}/claims
/api/tasks/{id}/work-cycles
/api/tasks/{id}/start  (create work cycle)
/api/tasks/{id}/complete (validate claims)

/api/claims/{id}
/api/claims/{id}/tests
/api/claims/{id}/evidence

/api/work-cycles/{id}
/api/work-cycles/{id}/artifacts

/api/ledger
/api/ledger/{id}

/api/bugs (external intake)
/api/webhooks
/api/llm/* (keep as-is)
```

**Kill all Run endpoints**

---

## API Layer: PostgREST + Minimal Python Service

### Option: Replace Django API with PostgREST

**PostgREST** auto-generates REST API from PostgreSQL schema. No route handlers needed for CRUD.

```
Architecture:
┌─────────────────┐     ┌─────────────────┐
│   Next.js UI    │────▶│   PostgREST     │──▶ PostgreSQL
└─────────────────┘     └─────────────────┘       (CRUD)
         │
         │ (business logic only)
         ▼
┌─────────────────┐
│  Python Service │──▶ Claim execution, Ledger automation
└─────────────────┘
```

**PostgREST handles (~90% of requests):**
- All CRUD: Projects, Tasks, Claims, Evidence, WorkCycles, etc.
- Filtering: `/tasks?status=eq.BACKLOG&priority=gte.5`
- Pagination, sorting, joins
- RLS-based auth (Postgres Row Level Security)

**Python service handles (~10% of requests):**
- `/api/claims/{id}/run-test` - Execute claim tests
- `/api/tasks/{id}/start` - Create WorkCycle with logic
- `/api/tasks/{id}/complete` - Validate claims, create ledger entries
- Agent orchestration, webhooks

**Benefits:**
- Kill most of `views/api.py` (186 routes → ~10 custom endpoints)
- Schema = API (no drift)
- Auto-generated OpenAPI docs
- Standard REST filtering built-in

**Docker setup:**
```yaml
services:
  postgrest:
    image: postgrest/postgrest
    environment:
      PGRST_DB_URI: postgres://...
      PGRST_DB_ANON_ROLE: web_anon
      PGRST_JWT_SECRET: ${JWT_SECRET}
    ports:
      - "3000:3000"
```

---

## Frontend

Current: Django templates + vanilla JS
Target: Next.js + TypeScript (as per CLAUDE.md)

### Phase 1: Simplify backend + add PostgREST
### Phase 2: Build Next.js frontend consuming PostgREST + Python endpoints

---

## Migration Strategy

1. Create new simplified models alongside old
2. Write migration script: Run → Tasks, Handoff → WorkCycle
3. Update services one by one
4. Update routes
5. Delete old code
6. Frontend rebuild

---

## Questions Before Proceeding

1. **PostgREST** - Use PostgREST for auto-generated CRUD API? (Recommended: Yes)
2. **WorkCycle naming** - Keep "Handoff" or rename to "WorkCycle"?
3. **Bug reports** - Keep as separate intake or merge into Tasks?
4. **Environments/Credentials** - Keep for deployment or simplify?
5. **LLM sessions** - Keep or defer to future?

---

## Estimated Scope

- Kill: ~8 models, ~4 services, ~100+ routes (mostly replaced by PostgREST)
- Keep/Modify: ~10 models, ~3 services (claim, ledger, agent), ~10 custom endpoints
- The core becomes: Project → Task → Claim → Evidence → Ledger
- Stack: PostgreSQL + PostgREST + Minimal Python + Next.js
