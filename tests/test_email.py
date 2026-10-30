"""
Automated unit tests for email notification service and Simulated Demo Mode.
"""

from database.schema import Alert, utc_now
from services.email_service import EmailService


def test_email_simulated_demo_mode(db_session):
    alert = Alert(
        alert_code="TEST-ALT-EMAIL",
        title="Critical Payment Gateway Outage",
        description="Gateway failure rate breached critical 25% threshold.",
        category="Transactions",
        severity="Critical",
        related_entity_type="transaction_batch",
        related_entity_id="BATCH-001",
        detected_at=utc_now(),
        status="New",
        fingerprint="test:email:1",
    )
    db_session.add(alert)
    db_session.commit()

    # Dispatch notification (SMTP is not configured in test environment)
    res = EmailService.send_alert_notification(alert)

    assert res["success"] is False
    assert res["delivered"] is False
    assert res["mode"] == "simulated_demo"
    assert "Not sent" in res["message"]


def test_test_smtp_connection_in_demo_mode():
    res = EmailService.test_smtp_connection()
    assert res["success"] is False
    assert res["mode"] == "simulated_demo"
    assert "SMTP credentials not configured" in res["error"]
