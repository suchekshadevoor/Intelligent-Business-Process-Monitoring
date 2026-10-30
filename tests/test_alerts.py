"""
Automated unit tests for alert lifecycle, deduplication fingerprinting, and audit logging.
"""

from datetime import date, timedelta
from database.schema import Task, Alert, Employee, AuditLog
from services.monitoring_service import MonitoringService
from services.alert_service import AlertService


def test_duplicate_alert_prevention(db_session):
    today = date.today()
    task = Task(
        task_id="DEDUP-TSK-1",
        task_name="Dedup Verification Task",
        start_date=today - timedelta(days=10),
        due_date=today - timedelta(days=2),
        status="Pending",
    )
    db_session.add(task)
    db_session.commit()

    # Run 1: Should create 1 alert
    res1 = MonitoringService.evaluate_all_rules(db_session)
    assert res1["new_alerts_created"] == 1
    assert db_session.query(Alert).count() == 1


def test_resolved_alert_is_reopened_when_condition_recurs(db_session):
    today = date.today()
    task = Task(
        task_id="REOPEN-TSK-1",
        task_name="Recurring overdue task",
        start_date=today - timedelta(days=10),
        due_date=today - timedelta(days=2),
        status="Pending",
    )
    db_session.add(task)
    db_session.commit()

    MonitoringService.evaluate_all_rules(db_session)
    alert = db_session.query(Alert).one()
    AlertService.update_alert_status(db_session, alert.id, "Resolved", user="Test operator", notes="Completed work.")

    result = MonitoringService.evaluate_all_rules(db_session)

    assert result["new_alerts_created"] == 0
    assert db_session.query(Alert).count() == 1
    assert alert.status == "New"
    assert alert.resolved_at is None

    # Run 2: Same conditions, should NOT create a duplicate alert
    res2 = MonitoringService.evaluate_all_rules(db_session)
    assert res2["new_alerts_created"] == 0
    assert res2["existing_alerts_refreshed"] >= 1
    assert db_session.query(Alert).count() == 1


def test_alert_state_transitions(db_session):
    today = date.today()
    task = Task(
        task_id="STATE-TSK-1",
        task_name="State Transition Task",
        start_date=today - timedelta(days=5),
        due_date=today - timedelta(days=1),
        status="In Progress",
    )
    db_session.add(task)
    db_session.commit()

    MonitoringService.evaluate_all_rules(db_session)
    alert = db_session.query(Alert).first()
    assert alert.status == "New"
    assert alert.resolved_at is None

    # Transition 1: Acknowledge
    res_ack = AlertService.update_alert_status(db_session, alert.id, "Acknowledged", user="Sarah Lead", notes="Investigating delay.")
    assert res_ack["success"] is True
    assert alert.status == "Acknowledged"

    # Transition 2: In Progress
    AlertService.update_alert_status(db_session, alert.id, "In Progress", user="Sarah Lead")
    assert alert.status == "In Progress"

    # Transition 3: Resolve
    res_res = AlertService.update_alert_status(db_session, alert.id, "Resolved", user="Sarah Lead", notes="Finished migration.")
    assert res_res["success"] is True
    assert alert.status == "Resolved"
    assert alert.resolved_at is not None

    # Verify audit trail entries were created
    logs = db_session.query(AuditLog).filter(AuditLog.entity_id == alert.alert_code).all()
    assert len(logs) >= 4  # CREATE + 3 status updates


def test_alert_owner_assignment(db_session):
    today = date.today()
    task = Task(
        task_id="OWNER-TSK-1",
        task_name="Owner Assignment Task",
        start_date=today - timedelta(days=5),
        due_date=today - timedelta(days=1),
        status="Pending",
    )
    db_session.add(task)
    db_session.commit()

    MonitoringService.evaluate_all_rules(db_session)
    alert = db_session.query(Alert).first()
    emp = db_session.query(Employee).first()

    assign_res = AlertService.assign_alert_owner(db_session, alert.id, emp.id, user="OpsManager")
    assert assign_res["success"] is True
    assert alert.assigned_owner_id == emp.id
