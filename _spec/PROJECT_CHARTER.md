# Project Charter

## Purpose
Create a local-first web app ("Workflow Hub") to manage agentic software development cycles with explicit handoffs, test/security gates, and human approval for deployment.

## Primary users
- You (owner/operator)
- Optional collaborators later (but MVP assumes single user)

## Non-goals (MVP)
- Production hosting
- Full CI/CD automation to production
- OAuth/SSO
- Multi-tenant org support

## Constraints
- Must run locally (Docker + Postgres)
- Must log every run and decision
- Must be safe-by-default (no secret storage in app DB beyond local admin login)
