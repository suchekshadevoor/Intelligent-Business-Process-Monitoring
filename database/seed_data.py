"""
Seed data generator for demonstration and testing.
Populates departments, employees, default monitoring rules, and synthetic business records.
Exports sample CSV templates into sample_data/ directory.
"""

import json
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session
from database.schema import (
    User,
    Department,
    Employee,
    Task,
    Order,
    Transaction,
    Expense,
    MonitoringRule,
    Alert,
    Incident,
    AuditLog,
)
from services.auth_service import AuthService
from config.settings import logger, SAMPLE_DATA_DIR
import pandas as pd


def seed_default_users(db: Session) -> None:
    """Ensure baseline role accounts exist for authentication."""
    if db.query(User).count() == 0:
        logger.info("Seeding default authentication accounts...")
        AuthService.create_user(db, username="admin", email="admin@businessmonitor.local", password="Admin@123", role="admin")
        AuthService.create_user(db, username="manager", email="manager@businessmonitor.local", password="Manager@123", role="manager")
        AuthService.create_user(db, username="analyst", email="analyst@businessmonitor.local", password="Analyst@123", role="analyst")
        logger.info("Default user accounts seeded: admin, manager, analyst.")


def seed_all(db: Session, force_reset: bool = False) -> dict:
    """Populate full initial dataset if empty or force_reset is requested."""
    seed_default_users(db)

    if not force_reset and db.query(Department).count() > 0:
        logger.info("Database already seeded. Skipping initial seeding.")
        return {"status": "skipped", "message": "Database already populated."}

    if force_reset:
        logger.warning("Force resetting database records...")
        db.query(User).delete()
        db.query(AuditLog).delete()
        db.query(Alert).delete()
        db.query(Incident).delete()
        db.query(Task).delete()
        db.query(Order).delete()
        db.query(Transaction).delete()
        db.query(Expense).delete()
        db.query(MonitoringRule).delete()
        db.query(Employee).delete()
        db.query(Department).delete()
        db.commit()

    logger.info("Seeding departments and employees...")
    # 1. Departments
    dept_eng = Department(code="ENG", name="Engineering & Tech", manager_email="eng-lead@example.com", budget_monthly=120000.0)
    dept_ops = Department(code="OPS", name="Logistics & Operations", manager_email="ops-lead@example.com", budget_monthly=85000.0)
    dept_sup = Department(code="SUP", name="Customer Support", manager_email="support-lead@example.com", budget_monthly=45000.0)
    dept_mkt = Department(code="MKT", name="Growth & Marketing", manager_email="mkt-lead@example.com", budget_monthly=60000.0)
    dept_fit = Department(code="FIT", name="Finance & IT Infrastructure", manager_email="fin-lead@example.com", budget_monthly=95000.0)

    db.add_all([dept_eng, dept_ops, dept_sup, dept_mkt, dept_fit])
    db.flush()

    # 2. Employees
    employees = [
        Employee(name="Alex Rivera", email="alex.rivera@example.com", department_id=dept_eng.id, role="Senior Tech Lead"),
        Employee(name="Sarah Chen", email="sarah.chen@example.com", department_id=dept_eng.id, role="Backend Engineer"),
        Employee(name="Marcus Vance", email="marcus.vance@example.com", department_id=dept_ops.id, role="Supply Chain Manager"),
        Employee(name="Elena Rostova", email="elena.rostova@example.com", department_id=dept_ops.id, role="Fulfillment Supervisor"),
        Employee(name="David Miller", email="david.miller@example.com", department_id=dept_sup.id, role="Support Operations Lead"),
        Employee(name="Chloe Zhao", email="chloe.zhao@example.com", department_id=dept_mkt.id, role="Campaign Analyst"),
        Employee(name="Robert Hansen", email="robert.hansen@example.com", department_id=dept_fit.id, role="IT Systems Director"),
    ]
    db.add_all(employees)
    db.flush()

    # 3. Default Monitoring Rules (The 7 core business rules)
    rules = [
        MonitoringRule(
            rule_code="RULE-01-OVERDUE-TASKS",
            rule_name="Incomplete Task Past Deadline",
            description="Triggers an alert when an operational task remains incomplete and the due date has passed.",
            category="Tasks",
            severity="High",
            threshold_config=json.dumps({"min_days_overdue": 1}),
            is_enabled=True,
            evaluation_window_days=30,
        ),
        MonitoringRule(
            rule_code="RULE-02-DELAYED-ORDERS",
            rule_name="Customer Order Delivery Delay",
            description="Triggers when a customer order has breached its expected delivery date or was delivered late.",
            category="Orders",
            severity="High",
            threshold_config=json.dumps({"min_days_delayed": 1}),
            is_enabled=True,
            evaluation_window_days=30,
        ),
        MonitoringRule(
            rule_code="RULE-03-TXN-FAILURE-RATE",
            rule_name="Transaction Failure Rate Spike",
            description="Triggers when payment failure percentage exceeds threshold within the rolling evaluation window.",
            category="Transactions",
            severity="Critical",
            threshold_config=json.dumps({"failure_rate_pct_threshold": 5.0, "min_txns_count": 10}),
            is_enabled=True,
            evaluation_window_days=7,
        ),
        MonitoringRule(
            rule_code="RULE-04-COST-ANOMALY",
            rule_name="Operational Cost & Budget Outlier",
            description="Detects anomalous expenditure breaching budget variance percentage or statistical Z-score baseline.",
            category="Expenses",
            severity="High",
            threshold_config=json.dumps({"budget_overrun_pct": 20.0, "zscore_threshold": 2.5}),
            is_enabled=True,
            evaluation_window_days=30,
        ),
        MonitoringRule(
            rule_code="RULE-05-DEPT-PERFORMANCE",
            rule_name="Department SLA & Completion Decline",
            description="Flags departments whose task completion rate falls below the operational SLA minimum.",
            category="Department Performance",
            severity="Medium",
            threshold_config=json.dumps({"min_completion_rate_pct": 80.0}),
            is_enabled=True,
            evaluation_window_days=30,
        ),
        MonitoringRule(
            rule_code="RULE-06-RECURRING-ISSUES",
            rule_name="Repeated Operational Problem",
            description="Detects recurring failure patterns in the same category or department over a short interval.",
            category="Recurring Issues",
            severity="High",
            threshold_config=json.dumps({"min_recurrence_count": 3, "lookback_days": 14}),
            is_enabled=True,
            evaluation_window_days=14,
        ),
        MonitoringRule(
            rule_code="RULE-07-SLOW-RESOLUTION",
            rule_name="Slow Incident Resolution Target Breach",
            description="Triggers when an active incident remains unresolved beyond SLA target hours.",
            category="SLA Breaches",
            severity="Critical",
            threshold_config=json.dumps({"max_resolution_hours": 48.0}),
            is_enabled=True,
            evaluation_window_days=7,
        ),
    ]
    db.add_all(rules)
    db.flush()

    # 4. Generate Synthetic Records
    today = date.today()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    # Tasks
    tasks_data = [
        # Overdue tasks
        ("TSK-1001", "Core API Gateway Migration", employees[0].id, dept_eng.id, today - timedelta(days=25), today - timedelta(days=5), None, "In Progress", "High", 15000.0, 16200.0),
        ("TSK-1002", "Warehouse Barcode Scanner Firmware Patch", employees[2].id, dept_ops.id, today - timedelta(days=18), today - timedelta(days=4), None, "Pending", "Urgent", 4500.0, 1200.0),
        ("TSK-1003", "CRM Ticket Routing Logic Overhaul", employees[4].id, dept_sup.id, today - timedelta(days=20), today - timedelta(days=2), None, "In Progress", "Medium", 8000.0, 7500.0),
        ("TSK-1004", "Q3 Disaster Recovery Drill", employees[6].id, dept_fit.id, today - timedelta(days=14), today - timedelta(days=1), None, "Pending", "High", 6000.0, 500.0),
        ("TSK-1005", "Automated Billing Reconciliation Script", employees[1].id, dept_eng.id, today - timedelta(days=30), today - timedelta(days=10), None, "In Progress", "Urgent", 12000.0, 14500.0),
        # Completed on-time tasks
        ("TSK-1006", "Database Performance Indexing", employees[1].id, dept_eng.id, today - timedelta(days=35), today - timedelta(days=15), today - timedelta(days=16), "Completed", "Medium", 5000.0, 4800.0),
        ("TSK-1007", "Fleet Route Dispatch Optimization", employees[3].id, dept_ops.id, today - timedelta(days=40), today - timedelta(days=20), today - timedelta(days=21), "Completed", "High", 9500.0, 9200.0),
        ("TSK-1008", "Support Knowledge Base Refresh", employees[4].id, dept_sup.id, today - timedelta(days=28), today - timedelta(days=12), today - timedelta(days=14), "Completed", "Low", 3000.0, 2900.0),
        ("TSK-1009", "Customer Retention Email Campaign", employees[5].id, dept_mkt.id, today - timedelta(days=21), today - timedelta(days=7), today - timedelta(days=7), "Completed", "Medium", 4200.0, 4100.0),
        ("TSK-1010", "Quarterly Tax Prep & Financial Filing", employees[6].id, dept_fit.id, today - timedelta(days=45), today - timedelta(days=15), today - timedelta(days=15), "Completed", "High", 11000.0, 10800.0),
        # In progress within schedule
        ("TSK-1011", "OAuth2 Token Expiration Refactor", employees[0].id, dept_eng.id, today - timedelta(days=5), today + timedelta(days=10), None, "In Progress", "Medium", 7000.0, 2500.0),
        ("TSK-1012", "Cold Storage Temperature Monitor Calibration", employees[3].id, dept_ops.id, today - timedelta(days=3), today + timedelta(days=7), None, "Pending", "Low", 2500.0, 0.0),
        ("TSK-1013", "Omnichannel Chatbot Integration", employees[4].id, dept_sup.id, today - timedelta(days=6), today + timedelta(days=12), None, "In Progress", "High", 10000.0, 3400.0),
        ("TSK-1014", "SEO Landing Page Conversion Redesign", employees[5].id, dept_mkt.id, today - timedelta(days=4), today + timedelta(days=8), None, "In Progress", "Medium", 5500.0, 1800.0),
        ("TSK-1015", "Active Directory Security Permissions Audit", employees[6].id, dept_fit.id, today - timedelta(days=2), today + timedelta(days=14), None, "Pending", "Medium", 6500.0, 800.0),
    ]

    tasks = [
        Task(
            task_id=tid,
            task_name=name,
            assigned_employee_id=emp_id,
            department_id=d_id,
            start_date=s_date,
            due_date=d_date,
            completion_date=c_date,
            status=st,
            priority=pr,
            estimated_cost=ec,
            actual_cost=ac,
            is_synthetic=True,
        )
        for tid, name, emp_id, d_id, s_date, d_date, c_date, st, pr, ec, ac in tasks_data
    ]
    db.add_all(tasks)

    # Orders
    orders_data = [
        # Delayed orders
        ("ORD-2001", "Apex Global Trading", today - timedelta(days=20), today - timedelta(days=10), today - timedelta(days=6), 14500.0, "Delivered", dept_ops.id),
        ("ORD-2002", "Beacon Health Logistics", today - timedelta(days=15), today - timedelta(days=7), today - timedelta(days=2), 22400.0, "Delivered", dept_ops.id),
        ("ORD-2003", "Cascade Precision Works", today - timedelta(days=12), today - timedelta(days=4), None, 18900.0, "Shipped", dept_ops.id),
        ("ORD-2004", "Delta Freight Systems", today - timedelta(days=10), today - timedelta(days=3), None, 9800.0, "Processing", dept_ops.id),
        ("ORD-2005", "Echo Valley Retailers", today - timedelta(days=8), today - timedelta(days=1), None, 31200.0, "Pending", dept_ops.id),
        # On-time orders
        ("ORD-2006", "Falcon Aerospace Parts", today - timedelta(days=25), today - timedelta(days=15), today - timedelta(days=16), 45000.0, "Delivered", dept_ops.id),
        ("ORD-2007", "Garrison Tech Labs", today - timedelta(days=22), today - timedelta(days=12), today - timedelta(days=12), 12600.0, "Delivered", dept_ops.id),
        ("ORD-2008", "Horizon Energy Corp", today - timedelta(days=18), today - timedelta(days=8), today - timedelta(days=9), 28400.0, "Delivered", dept_ops.id),
        ("ORD-2009", "Imperial Medical Supplies", today - timedelta(days=14), today - timedelta(days=5), today - timedelta(days=6), 16700.0, "Delivered", dept_ops.id),
        # Future / pending on-schedule
        ("ORD-2010", "Jupiter Marine Group", today - timedelta(days=3), today + timedelta(days=5), None, 38000.0, "Processing", dept_ops.id),
        ("ORD-2011", "Kestrel Dynamics", today - timedelta(days=2), today + timedelta(days=7), None, 15500.0, "Pending", dept_ops.id),
        ("ORD-2012", "Lumina Optics", today - timedelta(days=1), today + timedelta(days=6), None, 8900.0, "Pending", dept_ops.id),
    ]

    orders = [
        Order(
            order_id=oid,
            customer_name=cname,
            order_date=odate,
            expected_delivery_date=edate,
            actual_delivery_date=adate,
            order_value=val,
            order_status=st,
            department_id=d_id,
            is_synthetic=True,
        )
        for oid, cname, odate, edate, adate, val, st, d_id in orders_data
    ]
    db.add_all(orders)

    # Transactions (simulating a cluster of failures in the past 48 hours)
    transactions = []
    txn_id_counter = 3001
    base_time = now - timedelta(days=6)

    payment_methods = ["Credit Card", "ACH Direct", "Wire Transfer", "PayPal", "Stripe Checkout"]
    error_reasons = ["Gateway Timeout", "Card Expired", "Insufficient Funds", "Network Reset", "Fraud Check Reject"]

    for day_offset in range(7):
        current_day_time = base_time + timedelta(days=day_offset)
        # Determine failure rate: day 5 and 6 have a failure spike (e.g., 25% failure rate due to gateway glitch)
        is_spike_day = (day_offset >= 4)

        for hour in [9, 11, 14, 16, 18]:
            ts = current_day_time.replace(hour=hour, minute=15, second=0)
            for batch_item in range(4):
                txn_id_counter += 1
                pm = payment_methods[(batch_item + day_offset) % len(payment_methods)]
                amount = 250.0 + (batch_item * 180.0) + (day_offset * 95.0)

                if is_spike_day and batch_item in (1, 3):
                    # Injected failure
                    err = "Gateway Timeout" if pm in ("Stripe Checkout", "PayPal") else "Insufficient Funds"
                    status = "Failed"
                elif day_offset == 1 and batch_item == 2:
                    err = "Card Expired"
                    status = "Failed"
                else:
                    err = "None"
                    status = "Success"

                transactions.append(
                    Transaction(
                        transaction_id=f"TXN-{txn_id_counter}",
                        transaction_timestamp=ts,
                        transaction_type="Payment" if batch_item != 3 else "Refund",
                        amount=amount,
                        status=status,
                        payment_method=pm,
                        error_category=err,
                        department_id=dept_fit.id if batch_item % 2 == 0 else dept_ops.id,
                        is_synthetic=True,
                    )
                )

    db.add_all(transactions)

    # Expenses (Including normal expenses and deliberate statistical outliers)
    expenses_data = [
        # Normal operations expenses
        ("EXP-4001", today - timedelta(days=26), dept_eng.id, "Software", 4500.0, 4600.0, "AWS Cloud Services", "Monthly compute cluster hosting"),
        ("EXP-4002", today - timedelta(days=24), dept_eng.id, "Hardware", 8000.0, 8150.0, "Dell Enterprise", "Developer workstations batch upgrade"),
        ("EXP-4003", today - timedelta(days=20), dept_ops.id, "Logistics", 15000.0, 15400.0, "DHL Express Freight", "Regional dispatch shipping costs"),
        ("EXP-4004", today - timedelta(days=18), dept_ops.id, "Packaging", 3500.0, 3600.0, "EcoPack Packaging", "Biodegradable corrugated shipping boxes"),
        ("EXP-4005", today - timedelta(days=16), dept_sup.id, "Software", 2800.0, 2800.0, "Zendesk Subscriptions", "Annual enterprise seat licenses"),
        ("EXP-4006", today - timedelta(days=15), dept_mkt.id, "Marketing", 12000.0, 12300.0, "Google Ads", "Search engine customer acquisition"),
        ("EXP-4007", today - timedelta(days=14), dept_mkt.id, "Marketing", 8000.0, 7900.0, "LinkedIn B2B Ads", "Enterprise procurement lead generation"),
        ("EXP-4008", today - timedelta(days=12), dept_fit.id, "Consulting", 6000.0, 6200.0, "PwC Advisory", "Quarterly audit review support"),
        ("EXP-4009", today - timedelta(days=10), dept_fit.id, "Facilities", 14000.0, 14000.0, "WeWork Space", "Headquarters office lease payment"),

        # ANOMALIES (statistically significant cost overruns)
        ("EXP-4010", today - timedelta(days=5), dept_eng.id, "Software", 2500.0, 14200.0, "CloudHosting Corp", "Unscheduled cloud GPU auto-scaling compute spike"),
        ("EXP-4011", today - timedelta(days=3), dept_ops.id, "Logistics", 4000.0, 18500.0, "Expedited Air Cargo", "Emergency charter flight due to port congestion"),
        ("EXP-4012", today - timedelta(days=2), dept_fit.id, "Consulting", 3000.0, 9800.0, "CyberSec Specialists", "Emergency incident response retainer retainer"),
    ]

    expenses = [
        Expense(
            expense_id=eid,
            date=edate,
            department_id=d_id,
            expense_category=cat,
            budgeted_amount=b_amt,
            actual_amount=a_amt,
            vendor=ven,
            description=desc,
            is_synthetic=True,
        )
        for eid, edate, d_id, cat, b_amt, a_amt, ven, desc in expenses_data
    ]
    db.add_all(expenses)

    # Initial Incident to demonstrate SLA tracking and resolution
    inc_code = "INC-8001"
    initial_incident = Incident(
        incident_code=inc_code,
        title="Gateway Timeout Payment Failures Spike",
        category="Transactions",
        department_id=dept_fit.id,
        first_detected_at=now - timedelta(hours=52),
        last_detected_at=now - timedelta(hours=4),
        occurrence_count=8,
        estimated_financial_impact=6800.0,
        status="Open",
        assigned_owner_id=employees[0].id,
        resolution_notes="Investigating upstream API timeout from payment gateway service provider.",
        root_cause_analysis="Correlated with payment provider maintenance window and TCP connection pool exhaustion.",
        recurrence_count=2,
    )
    db.add(initial_incident)

    # Audit log entry for initial seed
    db.add(
        AuditLog(
            entity_type="system",
            entity_id="SYSTEM_INIT",
            action="INITIAL_SEED",
            user_or_system="System Seeder",
            details_json=json.dumps({"departments": 5, "employees": len(employees), "rules": len(rules), "synthetic": True}),
        )
    )

    db.commit()
    logger.info("Successfully committed all seed data to database.")

    # Export sample CSV files to sample_data/ for user downloads and testing
    generate_sample_csvs()

    return {
        "status": "success",
        "departments": 5,
        "employees": len(employees),
        "tasks": len(tasks),
        "orders": len(orders),
        "transactions": len(transactions),
        "expenses": len(expenses),
        "rules": len(rules),
    }


def generate_sample_csvs() -> None:
    """Generate sample CSV templates with both valid and demonstrative rows."""
    today = date.today()

    # Tasks sample
    tasks_df = pd.DataFrame([
        {
            "task_id": "TSK-9001",
            "task_name": "Quarterly Security Vulnerability Scan",
            "department_code": "ENG",
            "assigned_employee_email": "sarah.chen@example.com",
            "start_date": (today - timedelta(days=10)).isoformat(),
            "due_date": (today - timedelta(days=2)).isoformat(),
            "completion_date": "",
            "status": "In Progress",
            "priority": "High",
            "estimated_cost": 4500.0,
            "actual_cost": 4200.0,
        },
        {
            "task_id": "TSK-9002",
            "task_name": "Supplier Contract Renegotiation",
            "department_code": "OPS",
            "assigned_employee_email": "marcus.vance@example.com",
            "start_date": (today - timedelta(days=5)).isoformat(),
            "due_date": (today + timedelta(days=15)).isoformat(),
            "completion_date": "",
            "status": "Pending",
            "priority": "Medium",
            "estimated_cost": 2500.0,
            "actual_cost": 0.0,
        },
    ])
    tasks_df.to_csv(SAMPLE_DATA_DIR / "tasks_sample.csv", index=False)

    # Orders sample
    orders_df = pd.DataFrame([
        {
            "order_id": "ORD-9001",
            "customer_name": "Pinnacle Dynamics",
            "order_date": (today - timedelta(days=12)).isoformat(),
            "expected_delivery_date": (today - timedelta(days=3)).isoformat(),
            "actual_delivery_date": "",
            "order_value": 17800.0,
            "order_status": "Processing",
            "department_code": "OPS",
        },
        {
            "order_id": "ORD-9002",
            "customer_name": "Summit Corp",
            "order_date": (today - timedelta(days=8)).isoformat(),
            "expected_delivery_date": (today + timedelta(days=4)).isoformat(),
            "actual_delivery_date": "",
            "order_value": 8400.0,
            "order_status": "Pending",
            "department_code": "OPS",
        },
    ])
    orders_df.to_csv(SAMPLE_DATA_DIR / "orders_sample.csv", index=False)

    # Transactions sample
    txns_df = pd.DataFrame([
        {
            "transaction_id": "TXN-9001",
            "transaction_timestamp": f"{today.isoformat()}T10:30:00",
            "transaction_type": "Payment",
            "amount": 1250.0,
            "status": "Success",
            "payment_method": "Credit Card",
            "error_category": "None",
            "department_code": "FIT",
        },
        {
            "transaction_id": "TXN-9002",
            "transaction_timestamp": f"{today.isoformat()}T11:45:00",
            "transaction_type": "Payment",
            "amount": 3400.0,
            "status": "Failed",
            "payment_method": "Stripe Checkout",
            "error_category": "Gateway Timeout",
            "department_code": "FIT",
        },
    ])
    txns_df.to_csv(SAMPLE_DATA_DIR / "transactions_sample.csv", index=False)

    # Expenses sample
    expenses_df = pd.DataFrame([
        {
            "expense_id": "EXP-9001",
            "date": (today - timedelta(days=3)).isoformat(),
            "department_code": "ENG",
            "expense_category": "Software",
            "budgeted_amount": 3000.0,
            "actual_amount": 6200.0,
            "vendor": "CloudHost Enterprise",
            "description": "Monthly database backup expansion storage",
        },
        {
            "expense_id": "EXP-9002",
            "date": (today - timedelta(days=1)).isoformat(),
            "department_code": "MKT",
            "expense_category": "Marketing",
            "budgeted_amount": 5000.0,
            "actual_amount": 4900.0,
            "vendor": "Digital Ad Platform",
            "description": "Quarterly product launch PPC campaign",
        },
    ])
    expenses_df.to_csv(SAMPLE_DATA_DIR / "expenses_sample.csv", index=False)
    logger.info("Sample CSV templates written to sample_data/ directory.")
