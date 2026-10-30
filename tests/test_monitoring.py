"""
Automated unit tests for monitoring rules evaluation and alert triggering.
"""

from datetime import date, datetime, timedelta, timezone
from database.schema import Task, Order, Transaction, Expense, Alert, MonitoringRule, Incident
from services.monitoring_service import MonitoringService


def test_overdue_task_detection(db_session):
    today = date.today()
    # Task that is past due date and incomplete
    task1 = Task(
        task_id="TEST-TSK-1",
        task_name="Overdue Server Upgrade",
        start_date=today - timedelta(days=10),
        due_date=today - timedelta(days=2),
        status="In Progress",
        priority="High",
        estimated_cost=2000.0,
        actual_cost=1500.0,
    )
    # Task that is completed (should NOT trigger)
    task2 = Task(
        task_id="TEST-TSK-2",
        task_name="Completed Migration",
        start_date=today - timedelta(days=10),
        due_date=today - timedelta(days=2),
        completion_date=today - timedelta(days=3),
        status="Completed",
        priority="Medium",
    )
    # Task that is due in the future (should NOT trigger)
    task3 = Task(
        task_id="TEST-TSK-3",
        task_name="Future Task",
        start_date=today,
        due_date=today + timedelta(days=5),
        status="Pending",
        priority="Low",
    )
    db_session.add_all([task1, task2, task3])
    db_session.commit()

    res = MonitoringService.evaluate_all_rules(db_session)
    assert res["new_alerts_created"] >= 1

    alerts = db_session.query(Alert).filter(Alert.category == "Tasks").all()
    assert len(alerts) == 1
    assert alerts[0].related_entity_id == "TEST-TSK-1"
    assert "Overdue" in alerts[0].title


def test_delayed_order_detection(db_session):
    today = date.today()
    # Order delayed past expected delivery date
    order1 = Order(
        order_id="TEST-ORD-1",
        customer_name="Test Corp",
        order_date=today - timedelta(days=12),
        expected_delivery_date=today - timedelta(days=3),
        actual_delivery_date=None,
        order_value=5000.0,
        order_status="Processing",
    )
    # Order on time (should NOT trigger)
    order2 = Order(
        order_id="TEST-ORD-2",
        customer_name="Prompt Co",
        order_date=today - timedelta(days=10),
        expected_delivery_date=today + timedelta(days=5),
        actual_delivery_date=None,
        order_value=3200.0,
        order_status="Pending",
    )
    db_session.add_all([order1, order2])
    db_session.commit()

    res = MonitoringService.evaluate_all_rules(db_session)
    alerts = db_session.query(Alert).filter(Alert.category == "Orders").all()
    assert len(alerts) == 1
    assert alerts[0].related_entity_id == "TEST-ORD-1"


def test_transaction_failure_threshold(db_session):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    # Add 10 transactions with 4 failures (40% failure rate > 10% threshold)
    for i in range(10):
        db_session.add(
            Transaction(
                transaction_id=f"TEST-TX-{i}",
                transaction_timestamp=now - timedelta(hours=i),
                transaction_type="Payment",
                amount=100.0,
                status="Failed" if i < 4 else "Success",
                payment_method="Credit Card",
                error_category="Gateway Timeout" if i < 4 else "None",
            )
        )
    db_session.commit()

    res = MonitoringService.evaluate_all_rules(db_session)
    alerts = db_session.query(Alert).filter(Alert.category == "Transactions").all()
    assert len(alerts) >= 1
    assert "Failure Rate" in alerts[0].title


def test_cost_anomaly_detection(db_session):
    today = date.today()
    # Normal expense
    exp1 = Expense(
        expense_id="TEST-EXP-1",
        date=today - timedelta(days=2),
        expense_category="Software",
        budgeted_amount=1000.0,
        actual_amount=1050.0,  # 5% overrun (below 20% threshold)
        vendor="Vendor A",
    )
    # Anomalous expense (> 20% overrun)
    exp2 = Expense(
        expense_id="TEST-EXP-2",
        date=today - timedelta(days=1),
        expense_category="Hardware",
        budgeted_amount=1000.0,
        actual_amount=2500.0,  # 150% overrun (flagged)
        vendor="Vendor B",
    )
    db_session.add_all([exp1, exp2])
    db_session.commit()

    res = MonitoringService.evaluate_all_rules(db_session)
    alerts = db_session.query(Alert).filter(Alert.category == "Expenses").all()
    assert len(alerts) == 1
    assert alerts[0].related_entity_id == "TEST-EXP-2"
