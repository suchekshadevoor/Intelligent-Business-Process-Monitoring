"""
Automated unit tests for dynamic KPI calculations and metrics aggregations.
"""

from datetime import date, datetime, timedelta, timezone
from database.schema import Task, Order, Transaction, Expense, Department
from services.kpi_service import KPIService


def test_kpi_summary_calculations(db_session):
    today = date.today()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    dept = db_session.query(Department).first()

    # Tasks: 4 total, 2 completed, 1 overdue, 1 pending future
    t1 = Task(task_id="K-TSK-1", task_name="T1", start_date=today, due_date=today - timedelta(days=2), status="Completed", department_id=dept.id)
    t2 = Task(task_id="K-TSK-2", task_name="T2", start_date=today, due_date=today - timedelta(days=1), status="Completed", department_id=dept.id)
    t3 = Task(task_id="K-TSK-3", task_name="T3", start_date=today, due_date=today - timedelta(days=3), status="In Progress", department_id=dept.id)
    t4 = Task(task_id="K-TSK-4", task_name="T4", start_date=today, due_date=today + timedelta(days=5), status="Pending", department_id=dept.id)

    # Orders: 2 total, 1 delayed (4 days delay)
    o1 = Order(order_id="K-ORD-1", customer_name="C1", order_date=today - timedelta(days=10), expected_delivery_date=today - timedelta(days=4), actual_delivery_date=None, order_value=1000.0, order_status="Processing", department_id=dept.id)
    o2 = Order(order_id="K-ORD-2", customer_name="C2", order_date=today - timedelta(days=5), expected_delivery_date=today + timedelta(days=5), actual_delivery_date=None, order_value=2000.0, order_status="Pending", department_id=dept.id)

    # Transactions: 5 total, 1 failed (20% failure rate)
    for i in range(5):
        db_session.add(
            Transaction(
                transaction_id=f"K-TX-{i}",
                transaction_timestamp=now - timedelta(hours=i),
                transaction_type="Payment",
                amount=500.0,
                status="Failed" if i == 0 else "Success",
                payment_method="ACH",
                department_id=dept.id,
            )
        )

    # Expenses: budgeted $5000, actual $6500 (variance +$1500, +30%)
    e1 = Expense(expense_id="K-EXP-1", date=today, department_id=dept.id, expense_category="Logistics", budgeted_amount=5000.0, actual_amount=6500.0, vendor="Test Air Cargo")

    db_session.add_all([t1, t2, t3, t4, o1, o2, e1])
    db_session.commit()

    kpis = KPIService.get_executive_summary(db_session)

    # Validate Tasks KPIs
    assert kpis["tasks"]["total"] == 4
    assert kpis["tasks"]["completed"] == 2
    assert kpis["tasks"]["overdue"] == 1
    assert kpis["tasks"]["completion_rate_pct"] == 50.0

    # Validate Orders KPIs
    assert kpis["orders"]["total"] == 2
    assert kpis["orders"]["delayed"] == 1
    assert kpis["orders"]["delay_rate_pct"] == 50.0
    assert kpis["orders"]["avg_delay_days"] == 4.0

    # Validate Transactions KPIs
    assert kpis["transactions"]["total"] == 5
    assert kpis["transactions"]["failed"] == 1
    assert kpis["transactions"]["failure_rate_pct"] == 20.0
    assert kpis["transactions"]["total_volume"] == 2500.0

    # Validate Expenses KPIs
    assert kpis["expenses"]["budgeted_total"] == 5000.0
    assert kpis["expenses"]["actual_total"] == 6500.0
    assert kpis["expenses"]["variance"] == 1500.0
    assert kpis["expenses"]["variance_pct"] == 30.0
