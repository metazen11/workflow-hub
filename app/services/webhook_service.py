"""Webhook dispatch service."""
import json
import hashlib
import hmac
import threading
import requests
from datetime import datetime
from app.db import get_db
from app.models.webhook import Webhook


def dispatch_webhook(event_type: str, payload: dict):
    """
    Dispatch webhook to all registered endpoints for this event type.
    Runs in background thread to not block the request.
    """
    thread = threading.Thread(target=_dispatch_async, args=(event_type, payload))
    thread.start()


def _dispatch_async(event_type: str, payload: dict):
    """Async webhook dispatch."""
    db = next(get_db())
    try:
        webhooks = db.query(Webhook).filter(Webhook.active == True).all()

        for webhook in webhooks:
            events = webhook.events.split(",") if webhook.events else []
            if event_type in events or "*" in events:
                _send_webhook(webhook, event_type, payload)
    finally:
        db.close()


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
