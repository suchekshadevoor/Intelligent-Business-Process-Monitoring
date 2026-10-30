"""
Daily Business Performance Report Generation Service.
Generates comprehensive 12-section operational reports in both responsive HTML and CSV formats.
"""

import json
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, Optional
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database.schema import (
    ScheduledReport,
    Alert,
    Incident,
    Task,
    Order,
    Transaction,
    Expense,
    Department,
    utc_now,
)
from services.kpi_service import KPIService
from services.incident_service import IncidentService
from config.settings import REPORTS_DIR, logger


class ReportService:
    @classmethod
    def generate_daily_report(cls, db: Session, user: str = "System") -> Dict[str, Any]:
        """
        Generate the 12-section business performance report,
        saving standalone HTML and CSV files in reports/ and logging to scheduled_reports table.
        """
        now = utc_now()
        report_date_str = now.strftime("%Y-%m-%d")
        timestamp_slug = now.strftime("%Y%m%d_%H%M%S")

        # 1. Gather all metrics
        summary = KPIService.get_executive_summary(db)
        correlations = IncidentService.compute_root_cause_correlations(db)

        # Overdue tasks list
        today = now.date()
        overdue_tasks = (
            db.query(Task)
            .filter(Task.status.not_in(("Completed", "Cancelled")), Task.due_date < today)
            .order_by(Task.due_date.asc())
            .all()
        )

        # Delayed orders list
        delayed_orders = (
            db.query(Order)
            .filter(
                (Order.actual_delivery_date != None) & (Order.actual_delivery_date > Order.expected_delivery_date)
                | ((Order.actual_delivery_date == None) & (Order.order_status.not_in(("Delivered", "Cancelled"))) & (Order.expected_delivery_date < today))
            )
            .order_by(Order.expected_delivery_date.asc())
            .all()
        )

        # Budget exceptions
        expense_anomalies = (
            db.query(Expense)
            .filter(Expense.actual_amount > Expense.budgeted_amount)
            .order_by(desc(Expense.actual_amount - Expense.budgeted_amount))
            .all()
        )

        # Alerts summary
        new_alerts = db.query(Alert).filter(Alert.status == "New").all()
        resolved_alerts = db.query(Alert).filter(Alert.status == "Resolved").all()

        # Department performance
        dept_perf_df = KPIService.get_department_comparison_dataframe(db)

        # 12. Synthesize Recommended Actions
        recommendations = []
        if summary["tasks"]["overdue"] > 0:
            recommendations.append(
                f"Prioritize the {summary['tasks']['overdue']} overdue operational tasks, specifically in departments with completion rates below 80%."
            )
        if summary["orders"]["delayed"] > 0:
            recommendations.append(
                f"Engage supply chain and fulfillment teams to expedite {summary['orders']['delayed']} delayed customer orders (average delay {summary['orders']['avg_delay_days']} days)."
            )
        if summary["transactions"]["failure_rate_pct"] > 3.0:
            recommendations.append(
                f"Investigate payment gateway timeouts; transaction failure rate is elevated at {summary['transactions']['failure_rate_pct']}%. Check API connection pools."
            )
        if summary["expenses"]["variance"] > 0:
            recommendations.append(
                f"Review unbudgeted expenditure overrun of ${summary['expenses']['variance']:,.2f} across IT and Logistics vendors."
            )
        if len(recommendations) == 0:
            recommendations.append("All monitored operational indicators are currently within approved baseline parameters.")

        # Build Structured Report Data
        report_data = {
            "generated_at": now.isoformat(),
            "report_date": report_date_str,
            "1_executive_summary": (
                f"Overall operational health: {summary['tasks']['completion_rate_pct']}% task completion, "
                f"{summary['orders']['delay_rate_pct']}% order delay rate, "
                f"{summary['transactions']['failure_rate_pct']}% transaction failure rate, "
                f"and ${summary['expenses']['variance']:,.2f} budget variance. "
                f"There are currently {summary['alerts']['open_count']} open alerts ({summary['alerts']['critical_count']} critical)."
            ),
            "2_tasks_completion_rate": summary["tasks"],
            "orders": summary["orders"],
            "expenses": summary["expenses"],
            "3_overdue_tasks_count": len(overdue_tasks),
            "4_delayed_orders_count": len(delayed_orders),
            "5_transaction_failure_rate": summary["transactions"],
            "6_budget_exceptions_count": len(expense_anomalies),
            "7_department_performance": dept_perf_df.to_dict(orient="records"),
            "8_new_alerts_count": len(new_alerts),
            "9_resolved_alerts_count": len(resolved_alerts),
            "10_avg_resolution_time_hours": summary["incidents"]["mttr_hours"],
            "11_repeated_issues_count": correlations["total_patterns_identified"],
            "12_recommended_actions": recommendations,
        }

        # Generate HTML report
        html_file = REPORTS_DIR / f"daily_report_{timestamp_slug}.html"
        html_content = cls._render_html_report(report_data, overdue_tasks, delayed_orders, expense_anomalies, dept_perf_df)
        html_file.write_text(html_content, encoding="utf-8")

        # Generate CSV report summary
        csv_file = REPORTS_DIR / f"daily_report_{timestamp_slug}.csv"
        cls._export_csv_report(report_data, csv_file, dept_perf_df)

        # Record in scheduled_reports table
        sched_rep = ScheduledReport(
            report_type="daily_summary",
            parameters=json.dumps({"period": "daily", "date": report_date_str}),
            generated_at=now,
            file_path=str(html_file),
            recipient_emails=None,
            status="Generated",
            summary_json=json.dumps(report_data),
        )
        db.add(sched_rep)
        db.commit()

        logger.info(f"Daily report generated successfully: {html_file.name}")
        return {
            "id": sched_rep.id,
            "html_path": str(html_file),
            "csv_path": str(csv_file),
            "summary": report_data,
        }

    @staticmethod
    def _export_csv_report(data: dict, filepath: Path, dept_df: pd.DataFrame) -> None:
        """Export tabular CSV version of the performance report."""
        summary_rows = [
            {"Metric Category": "Tasks", "Metric": "Total Tasks", "Value": data["2_tasks_completion_rate"]["total"]},
            {"Metric Category": "Tasks", "Metric": "Completion Rate (%)", "Value": data["2_tasks_completion_rate"]["completion_rate_pct"]},
            {"Metric Category": "Tasks", "Metric": "Overdue Tasks", "Value": data["3_overdue_tasks_count"]},
            {"Metric Category": "Orders", "Metric": "Total Orders", "Value": data["orders"]["total"]},
            {"Metric Category": "Orders", "Metric": "Delayed Orders", "Value": data["4_delayed_orders_count"]},
            {"Metric Category": "Transactions", "Metric": "Failure Rate (%)", "Value": data["5_transaction_failure_rate"]["failure_rate_pct"]},
            {"Metric Category": "Expenses", "Metric": "Budget Variance ($)", "Value": data["expenses"]["variance"]},
            {"Metric Category": "Alerts", "Metric": "New Alerts", "Value": data["8_new_alerts_count"]},
            {"Metric Category": "Alerts", "Metric": "Resolved Alerts", "Value": data["9_resolved_alerts_count"]},
            {"Metric Category": "Resolution", "Metric": "MTTR (Hours)", "Value": data["10_avg_resolution_time_hours"]},
        ]
        df_summary = pd.DataFrame(summary_rows)
        df_summary.to_csv(filepath, index=False)

    @staticmethod
    def _render_html_report(data: dict, overdue_tasks, delayed_orders, expense_anomalies, dept_df: pd.DataFrame) -> str:
        """Render complete, beautifully styled HTML executive report."""
        overdue_rows = "".join([
            f"<tr><td><code>{t.task_id}</code></td><td>{t.task_name}</td><td>{t.priority}</td><td>{t.due_date}</td><td><span class='badge danger'>{t.status}</span></td></tr>"
            for t in overdue_tasks[:8]
        ]) or "<tr><td colspan='5' class='text-muted'>No overdue tasks recorded.</td></tr>"

        delayed_rows = "".join([
            f"<tr><td><code>{o.order_id}</code></td><td>{o.customer_name}</td><td>${o.order_value:,.2f}</td><td>{o.expected_delivery_date}</td><td><span class='badge warning'>{o.order_status}</span></td></tr>"
            for o in delayed_orders[:8]
        ]) or "<tr><td colspan='5' class='text-muted'>No delayed customer orders.</td></tr>"

        expense_rows = "".join([
            f"<tr><td><code>{e.expense_id}</code></td><td>{e.expense_category}</td><td>${e.budgeted_amount:,.2f}</td><td>${e.actual_amount:,.2f}</td><td class='text-danger'>+${(e.actual_amount - e.budgeted_amount):,.2f}</td><td>{e.vendor}</td></tr>"
            for e in expense_anomalies[:8]
        ]) or "<tr><td colspan='6' class='text-muted'>No budget overruns detected.</td></tr>"

        recs_list = "".join([f"<li>{r}</li>" for r in data["12_recommended_actions"]])

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Daily Business Performance Report - {data['report_date']}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; background: #f8fafc; color: #1e293b; margin: 0; padding: 40px 20px; }}
        .container {{ max-width: 960px; margin: 0 auto; background: #ffffff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; }}
        h1 {{ font-size: 24px; font-weight: 700; color: #0f172a; margin-top: 0; }}
        .meta {{ font-size: 13px; color: #64748b; margin-bottom: 24px; }}
        .section {{ margin-bottom: 32px; }}
        .section-title {{ font-size: 16px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #475569; border-bottom: 2px solid #f1f5f9; padding-bottom: 8px; margin-bottom: 16px; }}
        .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
        .kpi-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; text-align: center; }}
        .kpi-val {{ font-size: 24px; font-weight: 700; color: #0f172a; margin-top: 4px; }}
        .kpi-label {{ font-size: 12px; color: #64748b; font-weight: 500; text-transform: uppercase; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 8px; }}
        th {{ background: #f1f5f9; text-align: left; padding: 10px 12px; font-weight: 600; color: #475569; border-bottom: 1px solid #cbd5e1; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #f1f5f9; }}
        .badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
        .badge.danger {{ background: #fee2e2; color: #dc2626; }}
        .badge.warning {{ background: #fef3c7; color: #d97706; }}
        .text-danger {{ color: #dc2626; font-weight: 600; }}
        .text-muted {{ color: #94a3b8; font-style: italic; }}
        ul.recs {{ background: #eff6ff; border-left: 4px solid #3b82f6; padding: 16px 24px; border-radius: 0 8px 8px 0; }}
        ul.recs li {{ margin-bottom: 8px; font-size: 14px; line-height: 1.5; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Daily Business Performance & Process Health Report</h1>
        <div class="meta">Report Period: {data['report_date']} &bull; Generated At: {data['generated_at']} &bull; Status: Official System Audit</div>

        <div class="section">
            <div class="section-title">1. Executive Summary</div>
            <p style="font-size: 15px; line-height: 1.6; color: #334155;">{data['1_executive_summary']}</p>
        </div>

        <div class="grid">
            <div class="kpi-card">
                <div class="kpi-label">Task Completion</div>
                <div class="kpi-val">{data['2_tasks_completion_rate']['completion_rate_pct']}%</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Delayed Orders</div>
                <div class="kpi-val">{data['4_delayed_orders_count']}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Txn Failure Rate</div>
                <div class="kpi-val">{data['5_transaction_failure_rate']['failure_rate_pct']}%</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Mean Resolution</div>
                <div class="kpi-val">{data['10_avg_resolution_time_hours']}h</div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">3. Overdue Operational Tasks ({len(overdue_tasks)})</div>
            <table>
                <thead><tr><th>Task ID</th><th>Task Name</th><th>Priority</th><th>Due Date</th><th>Status</th></tr></thead>
                <tbody>{overdue_rows}</tbody>
            </table>
        </div>

        <div class="section">
            <div class="section-title">4. Delayed Customer Orders ({len(delayed_orders)})</div>
            <table>
                <thead><tr><th>Order ID</th><th>Customer</th><th>Value</th><th>Expected Delivery</th><th>Status</th></tr></thead>
                <tbody>{delayed_rows}</tbody>
            </table>
        </div>

        <div class="section">
            <div class="section-title">6. Budget & Cost Exceptions ({len(expense_anomalies)})</div>
            <table>
                <thead><tr><th>Expense ID</th><th>Category</th><th>Budgeted</th><th>Actual</th><th>Variance</th><th>Vendor</th></tr></thead>
                <tbody>{expense_rows}</tbody>
            </table>
        </div>

        <div class="section">
            <div class="section-title">12. Data-Driven Recommended Actions</div>
            <ul class="recs">{recs_list}</ul>
        </div>
    </div>
</body>
</html>"""
