# Architecture

## High-level
- Django app provides UI + API
- SQLAlchemy is used for DB access (not Django ORM)
- Postgres in Docker for persistence

## Modules
- `app/db/` SQLAlchemy engine/session setup
- `app/models/` SQLAlchemy models:
  - Project
  - Requirement
  - Task
  - Run
  - AgentReport
  - ThreatIntel
  - AuditEvent

## UI
- Django templates or minimal admin-like pages
- MVP can use Django admin only if we wire SQLAlchemy models carefully; otherwise build simple views.

## API
Minimal JSON endpoints for:
- create run
- submit report
- advance state
- list requirements/tasks/runs

## State machine
Implement explicit transition rules in code (single source of truth)
