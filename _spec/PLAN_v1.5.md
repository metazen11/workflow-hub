# Workflow Hub v1.5 - Local Agent Orchestration Platform

## Vision

A **local-first** development orchestration system where you manage a team of AI agents through a visual kanban pipeline. No cloud dependencies. You watch agents work, see tasks created, observe testing, and interject with feedback at any stage.

**Core Principle**: Asana-like workflow + local AI agents + human oversight = your personal dev team

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                        AGENT DASHBOARD (Local UI :8000)                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────────────────────┐ │
│  │  Agent Activity  │  │  Live Agent      │  │   Human Oversight               │ │
│  │  (what's running)│  │  Output Stream   │  │   Pause / Feedback / Approve    │ │
│  └──────────────────┘  └──────────────────┘  └─────────────────────────────────┘ │
└────────────────────────────────────┬─────────────────────────────────────────────┘
                                     │
                        ┌────────────▼────────────┐
                        │   ORCHESTRATOR CORE     │
                        │   (Agent Manager)       │
                        └────────────┬────────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          │                          │                          │
          ▼                          ▼                          ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  TASK ADAPTERS   │      │     AGENTS       │      │   LLM ADAPTERS   │
│  (pluggable)     │      │                  │      │   (pluggable)    │
├──────────────────┤      │  PM → DEV → QA   │      ├──────────────────┤
│ • Local (default)│      │  → SEC → DOCS    │      │ • Ollama (local) │
│ • Asana          │      │  → TESTING       │      │ • Claude API     │
│ • Jira           │      │                  │      │ • OpenAI API     │
│ • Linear         │      └──────────────────┘      │ • Groq           │
│ • GitHub Issues  │                                └──────────────────┘
└──────────────────┘
```

### Plugin Architecture

**Default: Runs 100% locally** - No external services required.
**Optional: Sync with Asana/Jira** - If you want your work team to see tasks too.

#### Task Backend Adapters

```python
# app/adapters/base.py
class TaskAdapter(ABC):
    """Abstract interface for task management backends."""

    @abstractmethod
    def get_tasks_by_stage(self, stage: str) -> List[Task]: ...

    @abstractmethod
    def move_task_to_stage(self, task_id: str, stage: str): ...

    @abstractmethod
    def add_comment(self, task_id: str, text: str): ...

    @abstractmethod
    def create_task(self, title: str, description: str, stage: str) -> Task: ...

    @abstractmethod
    def get_task_history(self, task_id: str) -> List[Event]: ...


# app/adapters/local.py (DEFAULT - works offline)
class LocalAdapter(TaskAdapter):
    """PostgreSQL/SQLite - full control, offline capable."""
    def __init__(self, db_session):
        self.db = db_session

    def get_tasks_by_stage(self, stage: str) -> List[Task]:
        return self.db.query(Task).filter(Task.current_stage == stage).all()

    def move_task_to_stage(self, task_id: str, stage: str):
        task = self.db.query(Task).get(task_id)
        task.current_stage = stage
        self.db.commit()


# app/adapters/asana.py (OPTIONAL - sync with work)
class AsanaAdapter(TaskAdapter):
    """Two-way sync with Asana - see tasks in both places."""
    def __init__(self, access_token: str, project_gid: str):
        self.client = asana.Client.access_token(access_token)
        self.project_gid = project_gid
        self.section_map = {}  # stage -> section_gid


# app/adapters/jira.py (OPTIONAL)
class JiraAdapter(TaskAdapter):
    """Sync with Jira for enterprise teams."""
    def __init__(self, url: str, email: str, api_token: str):
        self.jira = JIRA(server=url, basic_auth=(email, api_token))
```

#### LLM Backend Adapters

```python
# app/llm/base.py
class LLMAdapter(ABC):
    @abstractmethod
    def complete(self, prompt: str, system: str = None) -> str: ...

    @abstractmethod
    def stream(self, prompt: str, system: str = None) -> Iterator[str]: ...


# app/llm/ollama.py (DEFAULT - runs offline)
class OllamaAdapter(LLMAdapter):
    def __init__(self, model: str = "llama3.2:8b", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host

    def complete(self, prompt: str, system: str = None) -> str:
        response = requests.post(f"{self.host}/api/generate", json={
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False
        })
        return response.json()["response"]

    def stream(self, prompt: str, system: str = None) -> Iterator[str]:
        response = requests.post(f"{self.host}/api/generate", json={
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": True
        }, stream=True)
        for line in response.iter_lines():
            if line:
                yield json.loads(line)["response"]


# app/llm/claude.py (OPTIONAL - better quality, requires internet)
class ClaudeAdapter(LLMAdapter):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Client(api_key=api_key)
        self.model = model
```

#### Configuration

```yaml
# config.yaml - Minimal local setup (DEFAULT)
task_backend:
  adapter: local  # Uses PostgreSQL, works offline

llm_backend:
  adapter: ollama
  model: llama3.2:8b
  host: http://localhost:11434
```

```yaml
# config.yaml - Hybrid setup (sync with Asana)
task_backend:
  adapter: local
  sync_to:  # Optional: mirror tasks to external system
    - adapter: asana
      access_token: ${ASANA_TOKEN}
      project_gid: "1234567890"

llm_backend:
  adapter: ollama
  model: llama3.2:8b
  fallback: claude  # Use Claude if Ollama unavailable
```

---

## What We Have (v1.0)

### Working
- Django API at `:8000` with PostgreSQL (Docker)
- Kanban board UI with stages: PM → DEV → QA → Failed → SEC → DOCS → Deploy → Testing
- Run state machine with transitions and gates
- Task model with attachments, blocked_by, priority
- Bug tracking with soft delete (kill)
- Webhook system for external triggers
- Agent runner script (`scripts/agent_runner.py`) with Goose prompts
- Goose installed, Ollama running locally

### Not Yet Connected
- Agents don't auto-execute on state changes
- No real-time kanban movement
- No human feedback/interjection panel
- PM doesn't break down ideas into tasks automatically

---

## v1.5 Features

### 1. Local Agent Orchestrator (Replace n8n)

**New Component**: `app/orchestrator/`

```python
# Agent Orchestrator - runs as a background process
class AgentOrchestrator:
    """Watches for state changes, dispatches agents."""

    def __init__(self, llm_client):
        self.llm = llm_client  # Ollama
        self.agents = {
            'pm': PMAgent(),
            'dev': DevAgent(),
            'qa': QAAgent(),
            'sec': SecurityAgent(),
            'docs': DocsAgent(),
            'testing': TestingAgent()
        }

    def process_run(self, run_id):
        """Execute current stage's agent for this run."""
        run = get_run(run_id)
        agent = self.agents[run.state.value]
        result = agent.execute(run, self.llm)
        self.handle_result(run, result)
```

**Key Features**:
- Polls database for runs in actionable states
- Dispatches to appropriate agent
- Handles pass/fail results and state transitions
- Pauses for human review when configured

### 2. Agent Implementations

Each agent has a specialized role:

| Agent | Stage | Responsibility |
|-------|-------|----------------|
| **PM** | Planning | Break idea into tasks, set priorities, define acceptance criteria |
| **DEV** | Development | Write code, create files, implement features |
| **QA** | Testing | Write tests, run test suite, verify acceptance criteria |
| **SEC** | Security | Scan code, check dependencies, OWASP review |
| **DOCS** | Documentation | Update README, API docs, changelogs |
| **TESTING** | E2E Testing | Run Playwright, browser tests, verify deployed app |

### 3. Real-Time Kanban Updates

**WebSocket Integration**:
```
Browser ←──WebSocket──→ Django Channels ←──→ Orchestrator
```

- Cards animate when moving between columns
- Agent activity indicator (spinning, typing animation)
- Live log output in card detail view
- Notification badges for completed/failed stages

### 4. Human Oversight Panel

**New UI Component**: Appears as a slide-out panel or modal

- **Watch Mode**: See agent thoughts/actions in real-time
- **Pause Button**: Stop agent mid-execution
- **Feedback Input**: Add notes/corrections before agent continues
- **Approve/Reject**: Gate certain transitions (like deploy)
- **Edit Tasks**: Modify agent-created tasks before they proceed

### 5. Project Workspace

Each project gets a local workspace:

```
/Users/mz/Dropbox/_CODING/Agentic/workspaces/
├── listsnap/                 # Project workspace
│   ├── .git/                 # Version controlled
│   ├── src/                  # Source code
│   ├── tests/                # Test files
│   ├── docs/                 # Documentation
│   └── .workflow/            # Workflow metadata
│       ├── tasks.json        # Task breakdowns
│       ├── agent_logs/       # Agent execution logs
│       └── checkpoints/      # Save points for rollback
```

### 6. Pipeline Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│ USER: Submits idea/feature request                                       │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ PM AGENT:                                                                 │
│ • Analyzes requirement                                                    │
│ • Creates tasks with acceptance criteria                                  │
│ • Sets priorities and dependencies                                        │
│ • [HUMAN REVIEW POINT - approve task breakdown]                          │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ DEV AGENT (per task):                                                     │
│ • Reads task requirements                                                 │
│ • Writes code in workspace                                                │
│ • Commits changes to git                                                  │
│ • Reports what was implemented                                            │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ QA AGENT:                                                                 │
│ • Writes/runs unit tests                                                  │
│ • Verifies acceptance criteria                                            │
│ • If FAIL → creates bug, returns to DEV                                  │
│ • If PASS → advances to SEC                                              │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ SEC AGENT:                                                                │
│ • Scans for vulnerabilities                                               │
│ • Reviews dependencies                                                    │
│ • Checks OWASP Top 10                                                     │
│ • If FAIL → creates security bug, returns to DEV                         │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ DOCS AGENT:                                                               │
│ • Updates README                                                          │
│ • Generates API documentation                                             │
│ • Updates CHANGELOG                                                       │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ DEPLOY (Human Approval Required):                                         │
│ • Review changes in git diff                                              │
│ • Approve deployment                                                      │
│ • System commits and pushes                                               │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ TESTING AGENT (Post-Deploy):                                              │
│ • Runs Playwright E2E tests                                               │
│ • Verifies production behavior                                            │
│ • If FAIL → creates bug, returns to DEV                                  │
│ • If PASS → marks DEPLOYED                                               │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Core Orchestrator (Week 1)
1. Create `app/orchestrator/` module
2. Implement base Agent class with LLM integration
3. Build PMAgent that breaks ideas into tasks
4. Add orchestrator daemon that polls for work
5. Connect to Ollama for local LLM

### Phase 2: Agent Suite (Week 2)
1. DevAgent - code generation in workspace
2. QAAgent - test writing and execution
3. SecurityAgent - code scanning
4. DocsAgent - documentation generation
5. TestingAgent - Playwright integration

### Phase 3: Real-Time UI (Week 3)
1. Add Django Channels for WebSocket
2. Implement live kanban updates
3. Add agent activity indicators
4. Build oversight panel with pause/resume
5. Add feedback input system

### Phase 4: Polish & Workflow (Week 4)
1. Git integration for commits
2. Rollback/checkpoint system
3. Agent execution logs viewer
4. Dashboard metrics
5. Bug loop handling

---

---

## Database Schema (Senior-Level Design)

Elegant, normalized, and simple. Each table has a clear purpose.

### Entity Relationship

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│   Project    │──────<│     Task     │──────<│  Execution   │
└──────────────┘       └──────────────┘       └──────────────┘
                              │                      │
                              │                      │
                              ▼                      ▼
                       ┌──────────────┐       ┌──────────────┐
                       │   Handoff    │<──────│    Agent     │
                       └──────────────┘       └──────────────┘
```

### Tables

```sql
-- Agent roles and their configurations (lookup table)
CREATE TABLE agents (
    id              SERIAL PRIMARY KEY,
    role            VARCHAR(20) UNIQUE NOT NULL,  -- 'pm', 'dev', 'qa', 'sec', 'docs', 'testing'
    display_name    VARCHAR(50) NOT NULL,
    prompt_template TEXT NOT NULL,                 -- Base prompt for this role
    principles      TEXT,                          -- Role-specific principles
    timeout_seconds INTEGER DEFAULT 300,           -- Max execution time
    can_create_tasks BOOLEAN DEFAULT FALSE,        -- PM can, others cannot
    can_create_bugs  BOOLEAN DEFAULT FALSE,        -- QA, SEC, TESTING can
    active          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Agent execution sessions (the "run" of an agent on a task)
CREATE TABLE executions (
    id              SERIAL PRIMARY KEY,
    task_id         INTEGER NOT NULL REFERENCES tasks(id),
    agent_id        INTEGER NOT NULL REFERENCES agents(id),

    -- Execution state
    status          VARCHAR(20) DEFAULT 'pending',  -- pending, running, completed, failed, paused
    cwd             TEXT,                           -- Working directory for this execution

    -- Timing
    queued_at       TIMESTAMPTZ DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,

    -- Handoff data (JSONB for flexibility)
    incoming_handoff JSONB,                         -- What previous agent passed
    outgoing_handoff JSONB,                         -- What to pass to next agent

    -- Results
    result_status   VARCHAR(20),                    -- pass, fail, blocked
    result_summary  TEXT,
    result_details  JSONB,

    -- Logs and artifacts
    log_path        TEXT,                           -- Path to execution log file
    artifacts       JSONB,                          -- Files created, modified, etc.

    -- Human feedback (if paused for review)
    feedback        TEXT,
    feedback_at     TIMESTAMPTZ,

    CONSTRAINT valid_status CHECK (status IN ('pending', 'running', 'completed', 'failed', 'paused'))
);

-- Simplified task table (extends existing)
CREATE TABLE tasks (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id),

    -- Identity
    task_key        VARCHAR(20) NOT NULL,           -- "T-001", auto-generated
    title           VARCHAR(255) NOT NULL,
    description     TEXT,
    acceptance_criteria TEXT,

    -- Workflow state
    current_stage   VARCHAR(20) DEFAULT 'backlog',  -- backlog, pm, dev, qa, sec, docs, deploy, testing, done
    current_execution_id INTEGER REFERENCES executions(id),

    -- Priority and dependencies
    priority        INTEGER DEFAULT 5,              -- 1-10
    blocked_by      INTEGER[],                      -- Array of task IDs

    -- Metadata
    created_by      VARCHAR(50) DEFAULT 'human',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,

    UNIQUE(project_id, task_key)
);

-- Handoff records (audit trail of agent-to-agent transitions)
CREATE TABLE handoffs (
    id              SERIAL PRIMARY KEY,
    task_id         INTEGER NOT NULL REFERENCES tasks(id),

    -- From/To
    from_execution_id INTEGER REFERENCES executions(id),  -- NULL if from human
    to_execution_id   INTEGER REFERENCES executions(id),  -- NULL if to human
    from_stage      VARCHAR(20) NOT NULL,
    to_stage        VARCHAR(20) NOT NULL,

    -- Handoff content
    payload         JSONB NOT NULL,                 -- Data passed between agents
    notes           TEXT,                           -- Human-readable summary

    -- Timing
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    -- Was this handoff approved by human?
    requires_approval BOOLEAN DEFAULT FALSE,
    approved_at     TIMESTAMPTZ,
    approved_by     VARCHAR(50)
);

-- Indexes for common queries
CREATE INDEX idx_executions_task ON executions(task_id);
CREATE INDEX idx_executions_status ON executions(status) WHERE status IN ('pending', 'running');
CREATE INDEX idx_tasks_stage ON tasks(current_stage) WHERE current_stage != 'done';
CREATE INDEX idx_handoffs_task ON handoffs(task_id);
```

### Key Design Decisions

1. **Executions vs Runs**: Renamed "runs" to "executions" - clearer that it's an agent execution session, not a project run.

2. **JSONB for Flexibility**: Handoff payloads and artifacts use JSONB. Schema can evolve without migrations.

3. **Audit Trail**: Every agent transition creates a handoff record. Full history of who did what.

4. **Human Feedback Built-in**: `feedback` column on executions, `approved_by` on handoffs.

5. **Soft Stage Tracking**: `current_stage` on task is the source of truth, `current_execution_id` links to active work.

### Example Flow

```sql
-- 1. Human submits idea, PM agent picks it up
INSERT INTO tasks (project_id, task_key, title, description, current_stage)
VALUES (1, 'T-001', 'Add dark mode', 'User wants dark mode toggle', 'pm');

INSERT INTO executions (task_id, agent_id, status, incoming_handoff)
VALUES (1, (SELECT id FROM agents WHERE role = 'pm'), 'running',
        '{"source": "human", "idea": "Add dark mode toggle to settings"}');

-- 2. PM completes, hands off to DEV
UPDATE executions SET
    status = 'completed',
    completed_at = NOW(),
    result_status = 'pass',
    outgoing_handoff = '{"tasks_created": ["T-002", "T-003"], "priority": "high"}'
WHERE id = 1;

INSERT INTO handoffs (task_id, from_execution_id, from_stage, to_stage, payload)
VALUES (1, 1, 'pm', 'dev', '{"acceptance_criteria": "Toggle in settings, persists across sessions"}');

UPDATE tasks SET current_stage = 'dev' WHERE id = 1;
```

### Query Examples

```sql
-- What's currently running?
SELECT t.task_key, t.title, a.role, e.started_at
FROM executions e
JOIN tasks t ON e.task_id = t.id
JOIN agents a ON e.agent_id = a.id
WHERE e.status = 'running';

-- Task history (all handoffs)
SELECT h.from_stage, h.to_stage, h.payload, h.created_at
FROM handoffs h
WHERE h.task_id = 1
ORDER BY h.created_at;

-- Agent performance
SELECT a.role,
       COUNT(*) as total_executions,
       AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_seconds,
       SUM(CASE WHEN result_status = 'pass' THEN 1 ELSE 0 END) as passed
FROM executions e
JOIN agents a ON e.agent_id = a.id
WHERE e.status = 'completed'
GROUP BY a.role;
```

---

## Coding Principles (Injected to All Agents)

Every agent receives these principles at the start of their execution. They are non-negotiable standards that ensure consistency across the team.

### Core Principles

```markdown
# Agent Coding Standards

You are part of an automated development team. Follow these principles strictly.

## Code Quality
- Write elegant, simple solutions - avoid over-engineering
- DRY (Don't Repeat Yourself) - consolidate shared logic
- Single Responsibility - classes/functions do one thing well
- Prefer composition over inheritance
- Keep functions small (<30 lines) and focused

## Security First
- Never hardcode secrets, API keys, or credentials
- Validate all inputs at system boundaries
- Sanitize data before database queries (prevent SQL injection)
- Escape output to prevent XSS
- Use parameterized queries, never string concatenation
- Check OWASP Top 10 before marking security as passing

## Testing Requirements
- Write tests BEFORE implementation (TDD when possible)
- Every feature needs at least one happy path test
- Every bug fix needs a regression test
- Tests must be deterministic (no flaky tests)
- Mock external services, don't call real APIs in tests

## Git Discipline
- Small, focused commits with clear messages
- Never commit secrets, .env files, or credentials
- Don't commit generated files or dependencies
- Write commit messages in imperative mood ("Add feature" not "Added feature")

## Documentation
- Update README when behavior changes
- Add docstrings to public functions
- Comment only non-obvious logic (code should be self-documenting)
- Keep CHANGELOG updated for user-facing changes

## Error Handling
- Fail fast with clear error messages
- Log errors with context for debugging
- Don't swallow exceptions silently
- Provide actionable error messages to users

## Performance
- Measure before optimizing
- Don't premature optimize
- Use appropriate data structures
- Avoid N+1 queries in database access
```

### Role-Specific Reminders

Each agent also gets role-specific guidance:

**PM Agent:**
```markdown
- Break features into small, testable tasks
- Each task should be completable in one development session
- Define clear acceptance criteria for each task
- Set realistic priorities based on dependencies
- User stories follow: "As a [user], I want [goal], so that [reason]"
```

**DEV Agent:**
```markdown
- Read the full task description and acceptance criteria first
- Check for existing patterns in the codebase before creating new ones
- Don't introduce new dependencies without justification
- Leave the codebase cleaner than you found it
- If unsure, ask for clarification rather than guessing
```

**QA Agent:**
```markdown
- Test the acceptance criteria explicitly
- Include edge cases and error conditions
- Write tests that will catch regressions
- If tests fail, create a clear bug report with reproduction steps
- Don't pass code that has failing tests
```

**SEC Agent:**
```markdown
- Scan for hardcoded secrets and credentials
- Check dependency vulnerabilities (npm audit, pip-audit)
- Review authentication and authorization logic
- Look for injection vulnerabilities (SQL, XSS, command)
- Verify sensitive data is encrypted at rest and in transit
```

**DOCS Agent:**
```markdown
- Update README if setup steps changed
- Document new API endpoints with examples
- Add inline comments for complex algorithms
- Update CHANGELOG with user-facing changes
- Ensure examples actually work
```

**TESTING Agent:**
```markdown
- Run full E2E test suite, not just new tests
- Test on realistic data and scenarios
- Verify UI works across supported browsers
- Check mobile responsiveness if applicable
- Screenshot failures for debugging
```

### How Principles Are Injected

```python
# In base_agent.py
class BaseAgent:
    def build_prompt(self, task, context):
        return f"""
{CORE_PRINCIPLES}

{self.role_specific_principles}

---

# Your Task

{task.description}

## Acceptance Criteria
{task.acceptance_criteria}

## Project Context
{context.recent_changes}
{context.relevant_files}
"""
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Django 4.x, SQLAlchemy, PostgreSQL |
| Frontend | Django Templates, HTMX, WebSocket |
| Real-time | Django Channels, Redis |
| LLM | Ollama (llama3.2:8b, local) |
| Agent Runner | Python subprocess / Goose |
| Testing | Pytest, Playwright |
| Version Control | Git (local + optional remote) |

---

## Key Design Decisions

### 1. No External Dependencies
- Ollama runs locally in Docker
- PostgreSQL runs locally in Docker
- No cloud APIs required (can optionally add)

---

## Offline Mode - Emergency Engineering

**Scenario**: You're on a plane, at a remote cabin, in a disaster zone, or simply don't want cloud dependency. The entire system works without internet.

### What Works Offline

| Component | Offline Status | Notes |
|-----------|----------------|-------|
| Workflow Hub UI | Yes | Django serves locally at :8000 |
| Kanban Board | Yes | All state in local PostgreSQL |
| PM Agent | Yes | Uses Ollama LLM |
| DEV Agent | Yes | Writes code locally |
| QA Agent | Yes | Runs pytest locally |
| SEC Agent | Yes | Local code scanning |
| DOCS Agent | Yes | Updates local files |
| TESTING Agent | Yes | Playwright runs locally |
| Git Commits | Yes | Local repository |
| File Attachments | Yes | Stored in /uploads |

### What Requires Internet (Optional)

| Feature | Requires Internet | Fallback |
|---------|-------------------|----------|
| Git Push | Yes | Queue for later |
| Marketplace Posting | Yes | Draft mode, post when online |
| Remote Model APIs | Yes | Use Ollama instead |
| Package Installation | Yes | Pre-cache dependencies |

### Offline Setup

```bash
# Pre-flight checklist (do while online)
ollama pull llama3.2:8b          # Download model
pip install -r requirements.txt   # Cache Python deps
npm install                       # Cache Node deps (if any)
playwright install                # Download browsers

# Configure Goose for offline
cat > ~/.config/goose/profiles/offline.yaml << EOF
provider: ollama
processor:
  model: llama3.2:8b
  host: http://localhost:11434
EOF

# Start offline stack
docker compose up -d              # PostgreSQL
ollama serve                      # LLM (if not Docker)
./wf start --offline              # Workflow Hub + Orchestrator
```

### Emergency Engineering Workflow

```
1. Open http://localhost:8000/ui/
2. Create project or select existing
3. Submit task/idea via UI
4. Watch agents work through pipeline
5. Interject with feedback as needed
6. All code saved locally with git
7. Sync to remote when back online
```

### Recommended Local Models

| Model | Size | Speed | Quality | Use Case |
|-------|------|-------|---------|----------|
| llama3.2:3b | 2GB | Fast | Good | Quick tasks, low RAM |
| llama3.2:8b | 5GB | Medium | Better | Default recommendation |
| codellama:13b | 7GB | Slower | Best | Complex code generation |
| deepseek-coder:6.7b | 4GB | Medium | Great | Code-focused tasks |

```bash
# Download backup models while online
ollama pull llama3.2:3b
ollama pull codellama:13b
ollama pull deepseek-coder:6.7b
```

---

### 2. Human-in-the-Loop
- Pause points at critical stages
- Feedback can be injected any time
- All agent actions are logged and reversible

### 3. Task-Centric Runs
- Each task gets its own run through the pipeline
- Tasks can be blocked by other tasks
- Priority queue determines order

### 4. Workspace Isolation
- Each project has its own directory
- Git tracks all changes
- Checkpoints allow rollback

---

## File Structure (New)

```
/Users/mz/Dropbox/_CODING/Agentic/
├── app/
│   ├── orchestrator/           # NEW: Agent orchestration
│   │   ├── __init__.py
│   │   ├── daemon.py           # Background process
│   │   ├── base_agent.py       # Base agent class
│   │   ├── agents/
│   │   │   ├── pm.py
│   │   │   ├── dev.py
│   │   │   ├── qa.py
│   │   │   ├── security.py
│   │   │   ├── docs.py
│   │   │   └── testing.py
│   │   └── llm_client.py       # Ollama integration
│   ├── consumers.py            # NEW: WebSocket consumers
│   └── ...existing...
├── workspaces/                  # NEW: Project workspaces
│   └── .gitkeep
└── ...existing...
```

---

## Commands

```bash
# Start everything
./wf start           # Django + Orchestrator + Ollama

# Create a project
./wf project create "ListSnap" --workspace ~/code/listsnap

# Submit an idea (starts PM agent)
./wf idea "Mobile app that photographs items for marketplace listings"

# Watch agents work
./wf watch           # TUI showing real-time agent activity

# Pause/resume orchestration
./wf pause
./wf resume

# View pipeline status
./wf status          # Shows all runs and their stages
```

---

## Next Steps

1. **Review this plan** - Does this match your vision?
2. **Pick starting point** - Phase 1 (Orchestrator) is foundational
3. **Create ListSnap project** - Real project to test the pipeline
4. **Build PMAgent first** - It starts the whole workflow

---

*This plan was written after experiencing the full codebase, understanding the existing architecture, and incorporating your feedback about local-first, agent oversight, and Asana-like workflow.*
