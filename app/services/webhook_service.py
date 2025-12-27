"""Webhook dispatch service."""
import json
import hashlib
import hmac
import os
import threading
import requests
from datetime import datetime
from app.db import get_db
from app.models.webhook import Webhook


def _is_auto_trigger_enabled():
    """Check if auto-trigger is enabled (reads env var at runtime)."""
    return os.getenv("AUTO_TRIGGER_AGENTS", "false").lower() == "true"


def dispatch_webhook(event_type: str, payload: dict):
    """
    Dispatch webhook to all registered endpoints for this event type.
    Runs in background thread to not block the request.

    If AUTO_TRIGGER_AGENTS=true, also automatically triggers the agent
    for state_change and run_created events.
    """
    thread = threading.Thread(target=_dispatch_async, args=(event_type, payload))
    thread.start()


def _dispatch_async(event_type: str, payload: dict):
    """Async webhook dispatch."""
    # Auto-trigger agents if enabled
    if _is_auto_trigger_enabled() and event_type in (EVENT_STATE_CHANGE, EVENT_RUN_CREATED):
        _auto_trigger_agent(payload)

    # Also dispatch to registered webhooks
    db = next(get_db())
    try:
        webhooks = db.query(Webhook).filter(Webhook.active == True).all()

        for webhook in webhooks:
            events = webhook.events.split(",") if webhook.events else []
            if event_type in events or "*" in events:
                _send_webhook(webhook, event_type, payload)
    finally:
        db.close()


def _auto_trigger_agent(payload: dict):
    """Automatically trigger the next agent based on state change payload."""
    import sys
    next_agent = payload.get("next_agent")
    run_id = payload.get("run_id")
    to_state = payload.get("to_state", "")

    if not run_id:
        return

    # Handle failed states - loop back to DEV
    failed_states = {"qa_failed", "sec_failed", "testing_failed", "docs_failed"}
    if to_state in failed_states:
        print(f"[Auto-trigger] {to_state} detected - looping back to DEV for run {run_id}", file=sys.stderr, flush=True)
        try:
            from app.db import SessionLocal
            from app.services.run_service import RunService
            db = SessionLocal()
            service = RunService(db)
            result, error = service.reset_to_dev(run_id, actor="auto-trigger", create_tasks=True)
            db.close()
            if result:
                print(f"[Auto-trigger] Looped back to DEV, state: {result.value}", file=sys.stderr, flush=True)
            else:
                print(f"[Auto-trigger] Loopback error: {error}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[Auto-trigger] Loopback error: {e}", file=sys.stderr, flush=True)
        return

    if not next_agent:
        return

    # Skip terminal states - these require human approval
    terminal_agents = {"deployed", "ready_for_deploy", None}
    if next_agent in terminal_agents:
        print(f"[Auto-trigger] Skipping {next_agent} (terminal/approval state)", file=sys.stderr, flush=True)
        return

    print(f"[Auto-trigger] Triggering {next_agent} agent for run {run_id}", file=sys.stderr, flush=True)

    try:
        from app.services.agent_service import AgentService
        service = AgentService()
        result = service.trigger_agent(run_id=run_id, agent_type=next_agent, async_mode=True)
        print(f"[Auto-trigger] Result: {result}", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[Auto-trigger] Error: {e}", file=sys.stderr, flush=True)


def _send_webhook(webhook: Webhook, event_type: str, payload: dict):
    """Send webhook to endpoint."""
    data = {
        "event": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        "payload": payload
    }

    headers = {"Content-Type": "application/json"}

    # Add HMAC signature if secret is configured
    if webhook.secret:
        body = json.dumps(data)
        signature = hmac.new(
            webhook.secret.encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()
        headers["X-Webhook-Signature"] = signature

    try:
        requests.post(webhook.url, json=data, headers=headers, timeout=10)
    except Exception as e:
        print(f"Webhook failed for {webhook.name}: {e}")


# Event types
EVENT_STATE_CHANGE = "state_change"
EVENT_REPORT_SUBMITTED = "report_submitted"
EVENT_RUN_CREATED = "run_created"
EVENT_GATE_FAILED = "gate_failed"
EVENT_READY_FOR_DEPLOY = "ready_for_deploy"
