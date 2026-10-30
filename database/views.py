"""
SQL Views for analytical queries, Power BI integration, and KPI calculations.
"""

from sqlalchemy import text
from config.settings import logger

VIEWS_DDL = {
    "v_overdue_tasks": """
        CREATE VIEW IF NOT EXISTS v_overdue_tasks AS
        SELECT 
            t.id,
            t.task_id,
            t.task_name,
            t.status,
            t.priority,
            t.due_date,
            t.completion_date,
            t.estimated_cost,
            t.actual_cost,
            t.department_id,
            d.name AS department_name,
            e.name AS assigned_employee_name,
            CAST((julianday('now') - julianday(t.due_date)) AS INTEGER) AS days_overdue
        FROM tasks t
        LEFT JOIN departments d ON t.department_id = d.id
        LEFT JOIN employees e ON t.assigned_employee_id = e.id
        WHERE t.status NOT IN ('Completed', 'Cancelled')
          AND date(t.due_date) < date('now');
    """,

    "v_delayed_orders": """
        CREATE VIEW IF NOT EXISTS v_delayed_orders AS
        SELECT 
            o.id,
            o.order_id,
            o.customer_name,
            o.order_date,
            o.expected_delivery_date,
            o.actual_delivery_date,
            o.order_value,
            o.order_status,
            o.department_id,
            d.name AS department_name,
            CASE 
                WHEN o.actual_delivery_date IS NOT NULL 
                THEN CAST((julianday(o.actual_delivery_date) - julianday(o.expected_delivery_date)) AS INTEGER)
                ELSE CAST((julianday('now') - julianday(o.expected_delivery_date)) AS INTEGER)
            END AS delay_days
        FROM orders o
        LEFT JOIN departments d ON o.department_id = d.id
        WHERE (o.actual_delivery_date IS NOT NULL AND date(o.actual_delivery_date) > date(o.expected_delivery_date))
           OR (o.actual_delivery_date IS NULL AND o.order_status NOT IN ('Delivered', 'Cancelled') AND date(o.expected_delivery_date) < date('now'));
    """,

    "v_transaction_rates": """
        CREATE VIEW IF NOT EXISTS v_transaction_rates AS
        SELECT 
            date(transaction_timestamp) AS txn_date,
            department_id,
            COUNT(*) AS total_transactions,
            SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) AS failed_transactions,
            SUM(CASE WHEN status = 'Success' THEN 1 ELSE 0 END) AS successful_transactions,
            ROUND(
                (CAST(SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)) * 100.0, 
                2
            ) AS failure_rate_pct,
            SUM(amount) AS total_volume
        FROM transactions
        GROUP BY date(transaction_timestamp), department_id;
    """,

    "v_expense_variances": """
        CREATE VIEW IF NOT EXISTS v_expense_variances AS
        SELECT 
            e.id,
            e.expense_id,
            e.date,
            e.department_id,
            d.name AS department_name,
            e.expense_category,
            e.budgeted_amount,
            e.actual_amount,
            (e.actual_amount - e.budgeted_amount) AS variance_amount,
            ROUND(
                CASE 
                    WHEN e.budgeted_amount > 0 THEN ((e.actual_amount - e.budgeted_amount) / e.budgeted_amount) * 100.0
                    ELSE 0.0
                END, 2
            ) AS variance_pct,
            e.vendor,
            e.description
        FROM expenses e
        LEFT JOIN departments d ON e.department_id = d.id;
    """,

    "v_open_alerts": """
        CREATE VIEW IF NOT EXISTS v_open_alerts AS
        SELECT 
            a.id,
            a.alert_code,
            a.title,
            a.category,
            a.severity,
            a.related_entity_type,
            a.related_entity_id,
            a.detected_at,
            a.status,
            d.name AS department_name,
            e.name AS assigned_owner_name
        FROM alerts a
        LEFT JOIN departments d ON a.department_id = d.id
        LEFT JOIN employees e ON a.assigned_owner_id = e.id
        WHERE a.status IN ('New', 'Acknowledged', 'In Progress');
    """,

    "v_department_performance": """
        CREATE VIEW IF NOT EXISTS v_department_performance AS
        SELECT 
            d.id AS department_id,
            d.name AS department_name,
            d.code AS department_code,
            COALESCE(t_stats.total_tasks, 0) AS total_tasks,
            COALESCE(t_stats.completed_tasks, 0) AS completed_tasks,
            COALESCE(t_stats.overdue_tasks, 0) AS overdue_tasks,
            COALESCE(t_stats.task_completion_rate, 0.0) AS task_completion_rate,
            COALESCE(o_stats.total_orders, 0) AS total_orders,
            COALESCE(o_stats.delayed_orders, 0) AS delayed_orders,
            COALESCE(o_stats.order_delay_rate, 0.0) AS order_delay_rate,
            COALESCE(txn_stats.total_txns, 0) AS total_transactions,
            COALESCE(txn_stats.failed_txns, 0) AS failed_transactions,
            COALESCE(txn_stats.txn_failure_rate, 0.0) AS txn_failure_rate,
            COALESCE(exp_stats.total_actual_exp, 0.0) AS total_actual_expenses,
            COALESCE(exp_stats.total_budgeted_exp, 0.0) AS total_budgeted_expenses,
            COALESCE(exp_stats.total_variance, 0.0) AS total_budget_variance
        FROM departments d
        LEFT JOIN (
            SELECT 
                department_id,
                COUNT(*) AS total_tasks,
                SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS completed_tasks,
                SUM(CASE WHEN status NOT IN ('Completed', 'Cancelled') AND date(due_date) < date('now') THEN 1 ELSE 0 END) AS overdue_tasks,
                ROUND(CAST(SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100.0, 2) AS task_completion_rate
            FROM tasks
            GROUP BY department_id
        ) t_stats ON d.id = t_stats.department_id
        LEFT JOIN (
            SELECT 
                department_id,
                COUNT(*) AS total_orders,
                SUM(CASE WHEN (actual_delivery_date IS NOT NULL AND date(actual_delivery_date) > date(expected_delivery_date))
                              OR (actual_delivery_date IS NULL AND order_status NOT IN ('Delivered', 'Cancelled') AND date(expected_delivery_date) < date('now'))
                         THEN 1 ELSE 0 END) AS delayed_orders,
                ROUND(CAST(SUM(CASE WHEN (actual_delivery_date IS NOT NULL AND date(actual_delivery_date) > date(expected_delivery_date))
                              OR (actual_delivery_date IS NULL AND order_status NOT IN ('Delivered', 'Cancelled') AND date(expected_delivery_date) < date('now'))
                         THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100.0, 2) AS order_delay_rate
            FROM orders
            GROUP BY department_id
        ) o_stats ON d.id = o_stats.department_id
        LEFT JOIN (
            SELECT 
                department_id,
                COUNT(*) AS total_txns,
                SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) AS failed_txns,
                ROUND(CAST(SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100.0, 2) AS txn_failure_rate
            FROM transactions
            GROUP BY department_id
        ) txn_stats ON d.id = txn_stats.department_id
        LEFT JOIN (
            SELECT 
                department_id,
                SUM(actual_amount) AS total_actual_exp,
                SUM(budgeted_amount) AS total_budgeted_exp,
                SUM(actual_amount - budgeted_amount) AS total_variance
            FROM expenses
            GROUP BY department_id
        ) exp_stats ON d.id = exp_stats.department_id;
    """
}


def create_views(db_engine) -> None:
    """Create all analytical views in the database."""
    with db_engine.connect() as conn:
        for view_name, ddl in VIEWS_DDL.items():
            try:
                conn.execute(text(ddl))
                logger.debug(f"View {view_name} verified/created.")
            except Exception as e:
                logger.warning(f"Could not create view {view_name}: {e}")
        conn.commit()
