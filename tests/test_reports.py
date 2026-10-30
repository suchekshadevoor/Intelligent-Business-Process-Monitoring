"""
Automated unit tests for daily executive performance report generation.
"""

from pathlib import Path
from datetime import date
import pandas as pd
from services.report_service import ReportService
from database.schema import Expense, Order, ScheduledReport, Task


def test_daily_report_generation(db_session):
    today = date.today()
    db_session.add_all([
        Task(task_id="RPT-TSK-1", task_name="Report task", start_date=today, due_date=today),
        Order(
            order_id="RPT-ORD-1",
            customer_name="Report customer",
            order_date=today,
            expected_delivery_date=today,
        ),
        Order(
            order_id="RPT-ORD-2",
            customer_name="Report customer",
            order_date=today,
            expected_delivery_date=today,
        ),
        Expense(
            expense_id="RPT-EXP-1",
            date=today,
            expense_category="Testing",
            budgeted_amount=100.0,
            actual_amount=145.0,
            vendor="Test vendor",
        ),
    ])
    db_session.commit()

    res = ReportService.generate_daily_report(db_session, user="TestRunner")

    assert "id" in res
    assert "html_path" in res
    assert "csv_path" in res

    # Verify physical file existence
    html_p = Path(res["html_path"])
    csv_p = Path(res["csv_path"])
    assert html_p.exists()
    assert csv_p.exists()
    assert html_p.stat().st_size > 0
    assert csv_p.stat().st_size > 0

    # Verify database record
    rep_row = db_session.query(ScheduledReport).filter(ScheduledReport.id == res["id"]).first()
    assert rep_row is not None
    assert rep_row.status == "Generated"
    assert "1_executive_summary" in res["summary"]
    assert "12_recommended_actions" in res["summary"]

    csv_metrics = pd.read_csv(csv_p).set_index("Metric")["Value"]
    assert csv_metrics["Total Orders"] == 2
    assert csv_metrics["Budget Variance ($)"] == 45.0
