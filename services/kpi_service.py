"""
Dynamic KPI Engine and analytical queries service.
Aggregates operational metrics directly from relational tables and analytical views.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
import pandas as pd
from sqlalchemy import text, func
from sqlalchemy.orm import Session

from database.schema import (
    Task,
    Order,
    Transaction,
    Expense,
    Alert,
    Incident,
    IncidentResolution,
    Department,
)


class KPIService:
    @staticmethod
    def get_executive_summary(
        db: Session,
        department_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Compute high-level executive KPI metrics dynamically from the database."""
        today = date.today()

        # 1. Tasks KPIs
        task_q = db.query(Task)
        if department_id:
            task_q = task_q.filter(Task.department_id == department_id)
        if start_date:
            task_q = task_q.filter(Task.due_date >= start_date)
        if end_date:
            task_q = task_q.filter(Task.due_date <= end_date)

        all_tasks = task_q.all()
        total_tasks = len(all_tasks)
        completed_tasks = sum(1 for t in all_tasks if t.status == "Completed")
        overdue_tasks = sum(
            1 for t in all_tasks if t.status not in ("Completed", "Cancelled") and t.due_date < today
        )
        task_completion_rate = (completed_tasks / total_tasks * 100.0) if total_tasks > 0 else 0.0

        # 2. Orders KPIs
        order_q = db.query(Order)
        if department_id:
            order_q = order_q.filter(Order.department_id == department_id)
        if start_date:
            order_q = order_q.filter(Order.order_date >= start_date)
        if end_date:
            order_q = order_q.filter(Order.order_date <= end_date)

        all_orders = order_q.all()
        total_orders = len(all_orders)
        delayed_orders = 0
        total_delay_days = 0
        for o in all_orders:
            is_delayed = False
            delay = 0
            if o.actual_delivery_date and o.actual_delivery_date > o.expected_delivery_date:
                is_delayed = True
                delay = (o.actual_delivery_date - o.expected_delivery_date).days
            elif not o.actual_delivery_date and o.order_status not in ("Delivered", "Cancelled") and o.expected_delivery_date < today:
                is_delayed = True
                delay = (today - o.expected_delivery_date).days
            
            if is_delayed:
                delayed_orders += 1
                total_delay_days += max(delay, 0)

        order_delay_rate = (delayed_orders / total_orders * 100.0) if total_orders > 0 else 0.0
        avg_delay_days = (total_delay_days / delayed_orders) if delayed_orders > 0 else 0.0

        # 3. Transactions KPIs
        txn_q = db.query(Transaction)
        if department_id:
            txn_q = txn_q.filter(Transaction.department_id == department_id)
        if start_date:
            txn_q = txn_q.filter(func.date(Transaction.transaction_timestamp) >= start_date)
        if end_date:
            txn_q = txn_q.filter(func.date(Transaction.transaction_timestamp) <= end_date)

        all_txns = txn_q.all()
        total_txns = len(all_txns)
        failed_txns = sum(1 for tx in all_txns if tx.status == "Failed")
        success_txns = sum(1 for tx in all_txns if tx.status == "Success")
        txn_failure_rate = (failed_txns / total_txns * 100.0) if total_txns > 0 else 0.0
        total_volume = sum(tx.amount for tx in all_txns)

        # 4. Expenses KPIs
        exp_q = db.query(Expense)
        if department_id:
            exp_q = exp_q.filter(Expense.department_id == department_id)
        if start_date:
            exp_q = exp_q.filter(Expense.date >= start_date)
        if end_date:
            exp_q = exp_q.filter(Expense.date <= end_date)

        all_exp = exp_q.all()
        total_actual_exp = sum(e.actual_amount for e in all_exp)
        total_budgeted_exp = sum(e.budgeted_amount for e in all_exp)
        budget_variance = total_actual_exp - total_budgeted_exp
        budget_variance_pct = (budget_variance / total_budgeted_exp * 100.0) if total_budgeted_exp > 0 else 0.0

        # 5. Alerts KPIs
        alert_q = db.query(Alert)
        if department_id:
            alert_q = alert_q.filter(Alert.department_id == department_id)
        all_alerts = alert_q.all()
        open_alerts = sum(1 for a in all_alerts if a.status in ("New", "Acknowledged", "In Progress"))
        critical_alerts = sum(1 for a in all_alerts if a.severity == "Critical" and a.status in ("New", "Acknowledged", "In Progress"))
        high_alerts = sum(1 for a in all_alerts if a.severity == "High" and a.status in ("New", "Acknowledged", "In Progress"))
        resolved_alerts = sum(1 for a in all_alerts if a.status == "Resolved")

        # 6. Incident MTTA / MTTR KPIs
        resolutions = db.query(IncidentResolution).all()
        mtta_hours = 0.0
        mttr_hours = 0.0
        if resolutions:
            mtta_hours = round(sum(r.time_to_acknowledge_hours for r in resolutions) / len(resolutions), 1)
            mttr_hours = round(sum(r.time_to_resolve_hours for r in resolutions) / len(resolutions), 1)

        open_incidents = db.query(Incident).filter(Incident.status.in_(("Open", "In Progress"))).count()

        return {
            "tasks": {
                "total": total_tasks,
                "completed": completed_tasks,
                "overdue": overdue_tasks,
                "completion_rate_pct": round(task_completion_rate, 1),
            },
            "orders": {
                "total": total_orders,
                "delayed": delayed_orders,
                "delay_rate_pct": round(order_delay_rate, 1),
                "avg_delay_days": round(avg_delay_days, 1),
            },
            "transactions": {
                "total": total_txns,
                "failed": failed_txns,
                "successful": success_txns,
                "failure_rate_pct": round(txn_failure_rate, 1),
                "total_volume": round(total_volume, 2),
            },
            "expenses": {
                "actual_total": round(total_actual_exp, 2),
                "budgeted_total": round(total_budgeted_exp, 2),
                "variance": round(budget_variance, 2),
                "variance_pct": round(budget_variance_pct, 1),
            },
            "alerts": {
                "open_count": open_alerts,
                "critical_count": critical_alerts,
                "high_count": high_alerts,
                "resolved_count": resolved_alerts,
            },
            "incidents": {
                "open_count": open_incidents,
                "mtta_hours": mtta_hours,
                "mttr_hours": mttr_hours,
            },
        }

    @staticmethod
    def get_department_comparison_dataframe(db: Session) -> pd.DataFrame:
        """Query v_department_performance SQL view and return as pandas DataFrame."""
        query = text("""
            SELECT 
                department_name,
                department_code,
                total_tasks,
                completed_tasks,
                overdue_tasks,
                task_completion_rate AS [Completion Rate (%)],
                total_orders,
                delayed_orders,
                order_delay_rate AS [Delay Rate (%)],
                total_transactions,
                failed_transactions,
                txn_failure_rate AS [Txn Failure Rate (%)],
                total_actual_expenses AS [Actual Expenses ($)],
                total_budgeted_expenses AS [Budget ($)],
                total_budget_variance AS [Budget Variance ($)]
            FROM v_department_performance
            ORDER BY department_name ASC;
        """)
        with db.bind.connect() as conn:
            return pd.read_sql(query, conn)

    @staticmethod
    def get_transaction_trends_dataframe(db: Session, days: int = 14) -> pd.DataFrame:
        """Get daily transaction volume and failure rates."""
        query = text("""
            SELECT 
                txn_date AS date,
                SUM(total_transactions) AS total_transactions,
                SUM(failed_transactions) AS failed_transactions,
                ROUND(CAST(SUM(failed_transactions) AS FLOAT) / SUM(total_transactions) * 100.0, 2) AS failure_rate_pct,
                SUM(total_volume) AS total_volume
            FROM v_transaction_rates
            GROUP BY txn_date
            ORDER BY txn_date ASC;
        """)
        with db.bind.connect() as conn:
            return pd.read_sql(query, conn)

    @staticmethod
    def get_expense_by_category_dataframe(db: Session) -> pd.DataFrame:
        """Get expense breakdown by category."""
        query = text("""
            SELECT 
                expense_category,
                SUM(budgeted_amount) AS budgeted,
                SUM(actual_amount) AS actual,
                SUM(actual_amount - budgeted_amount) AS variance
            FROM expenses
            GROUP BY expense_category
            ORDER BY actual DESC;
        """)
        with db.bind.connect() as conn:
            return pd.read_sql(query, conn)
