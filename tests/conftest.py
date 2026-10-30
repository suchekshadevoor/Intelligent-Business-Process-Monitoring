"""
Pytest fixtures and test database setup.
Creates isolated in-memory or temporary database for testing.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from database.schema import Base, Department, Employee, MonitoringRule
from database.views import create_views
import json

TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="function")
def db_session():
    """Create an isolated fresh in-memory database session for each test."""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    create_views(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    # Seed base departments and employees
    dept_eng = Department(code="ENG", name="Engineering", manager_email="eng@test.local", budget_monthly=100000.0)
    dept_ops = Department(code="OPS", name="Operations", manager_email="ops@test.local", budget_monthly=50000.0)
    db.add_all([dept_eng, dept_ops])
    db.flush()

    emp1 = Employee(name="Test Engineer", email="eng1@test.local", department_id=dept_eng.id, role="Dev")
    emp2 = Employee(name="Test Logistics", email="ops1@test.local", department_id=dept_ops.id, role="Ops")
    db.add_all([emp1, emp2])
    db.flush()

    # Seed core monitoring rules
    rules = [
        MonitoringRule(
            rule_code="RULE-01-OVERDUE-TASKS",
            rule_name="Overdue Tasks",
            description="Test overdue tasks rule",
            category="Tasks",
            severity="High",
            threshold_config=json.dumps({"min_days_overdue": 1}),
            is_enabled=True,
            evaluation_window_days=30,
        ),
        MonitoringRule(
            rule_code="RULE-02-DELAYED-ORDERS",
            rule_name="Delayed Orders",
            description="Test delayed orders rule",
            category="Orders",
            severity="High",
            threshold_config=json.dumps({"min_days_delayed": 1}),
            is_enabled=True,
            evaluation_window_days=30,
        ),
        MonitoringRule(
            rule_code="RULE-03-TXN-FAILURE-RATE",
            rule_name="Txn Failure Rate",
            description="Test transaction failure rate rule",
            category="Transactions",
            severity="Critical",
            threshold_config=json.dumps({"failure_rate_pct_threshold": 10.0, "min_txns_count": 5}),
            is_enabled=True,
            evaluation_window_days=7,
        ),
        MonitoringRule(
            rule_code="RULE-04-COST-ANOMALY",
            rule_name="Cost Anomaly",
            description="Test cost anomaly rule",
            category="Expenses",
            severity="High",
            threshold_config=json.dumps({"budget_overrun_pct": 20.0, "zscore_threshold": 2.0}),
            is_enabled=True,
            evaluation_window_days=30,
        ),
    ]
    db.add_all(rules)
    db.commit()

    yield db

    db.close()
    Base.metadata.drop_all(bind=engine)
