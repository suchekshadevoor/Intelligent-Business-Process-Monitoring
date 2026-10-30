"""
SQLAlchemy ORM models for the Intelligent Business Process Monitoring System.
Includes all normalized operational entities, monitoring configurations, alerts, and incident tracking.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Date,
    Boolean,
    ForeignKey,
    Text,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utc_now() -> datetime:
    """Return naive UTC datetime for consistent SQLite storage and arithmetic."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(150), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    salt = Column(String(64), nullable=False)
    role = Column(String(30), default="analyst", nullable=False)  # admin, manager, analyst
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    manager_email = Column(String(150), nullable=True)
    budget_monthly = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    employees = relationship("Employee", back_populates="department", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="department")
    orders = relationship("Order", back_populates="department")
    transactions = relationship("Transaction", back_populates="department")
    expenses = relationship("Expense", back_populates="department")
    alerts = relationship("Alert", back_populates="department")
    incidents = relationship("Incident", back_populates="department")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "manager_email": self.manager_email,
            "budget_monthly": self.budget_monthly,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    role = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    department = relationship("Department", back_populates="employees")
    tasks = relationship("Task", back_populates="assigned_employee")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "department_id": self.department_id,
            "department_name": self.department.name if self.department else None,
            "role": self.role,
            "is_active": self.is_active,
        }


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(50), unique=True, nullable=False, index=True)
    task_name = Column(String(200), nullable=False)
    assigned_employee_id = Column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    start_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False, index=True)
    completion_date = Column(Date, nullable=True)
    status = Column(String(50), default="Pending", nullable=False, index=True)  # Pending, In Progress, Completed, Cancelled
    priority = Column(String(20), default="Medium", nullable=False)  # Low, Medium, High, Urgent
    estimated_cost = Column(Float, default=0.0, nullable=False)
    actual_cost = Column(Float, default=0.0, nullable=False)
    is_synthetic = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    department = relationship("Department", back_populates="tasks")
    assigned_employee = relationship("Employee", back_populates="tasks")

    __table_args__ = (
        Index("idx_tasks_status_due", "status", "due_date"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "task_name": self.task_name,
            "assigned_employee": self.assigned_employee.name if self.assigned_employee else "Unassigned",
            "department_id": self.department_id,
            "department_name": self.department.name if self.department else "General",
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "completion_date": self.completion_date.isoformat() if self.completion_date else None,
            "status": self.status,
            "priority": self.priority,
            "estimated_cost": self.estimated_cost,
            "actual_cost": self.actual_cost,
            "is_synthetic": self.is_synthetic,
        }


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(50), unique=True, nullable=False, index=True)
    customer_name = Column(String(150), nullable=False)
    order_date = Column(Date, nullable=False)
    expected_delivery_date = Column(Date, nullable=False, index=True)
    actual_delivery_date = Column(Date, nullable=True)
    order_value = Column(Float, default=0.0, nullable=False)
    order_status = Column(String(50), default="Pending", nullable=False, index=True)  # Pending, Processing, Shipped, Delivered, Cancelled
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    is_synthetic = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    department = relationship("Department", back_populates="orders")

    __table_args__ = (
        Index("idx_orders_status_delivery", "order_status", "expected_delivery_date"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "order_id": self.order_id,
            "customer_name": self.customer_name,
            "order_date": self.order_date.isoformat() if self.order_date else None,
            "expected_delivery_date": self.expected_delivery_date.isoformat() if self.expected_delivery_date else None,
            "actual_delivery_date": self.actual_delivery_date.isoformat() if self.actual_delivery_date else None,
            "order_value": self.order_value,
            "order_status": self.order_status,
            "department_id": self.department_id,
            "department_name": self.department.name if self.department else "General",
            "is_synthetic": self.is_synthetic,
        }


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String(50), unique=True, nullable=False, index=True)
    transaction_timestamp = Column(DateTime, nullable=False, index=True)
    transaction_type = Column(String(50), nullable=False)  # Payment, Refund, Transfer, Chargeback
    amount = Column(Float, default=0.0, nullable=False)
    status = Column(String(30), nullable=False, index=True)  # Success, Failed, Pending
    payment_method = Column(String(50), nullable=False)  # Credit Card, ACH, Wire, PayPal, Stripe
    error_category = Column(String(100), default="None", nullable=False, index=True)  # Insufficient Funds, Gateway Timeout, etc.
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    is_synthetic = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    department = relationship("Department", back_populates="transactions")

    __table_args__ = (
        Index("idx_txn_status_time", "status", "transaction_timestamp"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "transaction_timestamp": self.transaction_timestamp.isoformat() if self.transaction_timestamp else None,
            "transaction_type": self.transaction_type,
            "amount": self.amount,
            "status": self.status,
            "payment_method": self.payment_method,
            "error_category": self.error_category,
            "department_id": self.department_id,
            "department_name": self.department.name if self.department else "General",
            "is_synthetic": self.is_synthetic,
        }


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    expense_id = Column(String(50), unique=True, nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    expense_category = Column(String(100), nullable=False, index=True)  # Software, Hardware, Travel, Consulting, Logistics, etc.
    budgeted_amount = Column(Float, default=0.0, nullable=False)
    actual_amount = Column(Float, default=0.0, nullable=False)
    vendor = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    is_synthetic = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    department = relationship("Department", back_populates="expenses")

    def to_dict(self):
        variance = self.actual_amount - self.budgeted_amount
        variance_pct = (variance / self.budgeted_amount * 100.0) if self.budgeted_amount > 0 else 0.0
        return {
            "id": self.id,
            "expense_id": self.expense_id,
            "date": self.date.isoformat() if self.date else None,
            "department_id": self.department_id,
            "department_name": self.department.name if self.department else "General",
            "expense_category": self.expense_category,
            "budgeted_amount": self.budgeted_amount,
            "actual_amount": self.actual_amount,
            "variance": variance,
            "variance_pct": round(variance_pct, 2),
            "vendor": self.vendor,
            "description": self.description,
            "is_synthetic": self.is_synthetic,
        }


class MonitoringRule(Base):
    __tablename__ = "monitoring_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_code = Column(String(50), unique=True, nullable=False, index=True)
    rule_name = Column(String(150), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50), nullable=False, index=True)  # Tasks, Orders, Transactions, Expenses, Performance, Recurring, SLA
    severity = Column(String(20), default="High", nullable=False)  # Critical, High, Medium, Low
    threshold_config = Column(Text, default="{}", nullable=False)  # JSON formatted parameters
    is_enabled = Column(Boolean, default=True, nullable=False)
    evaluation_window_days = Column(Integer, default=7, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    last_evaluated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "rule_code": self.rule_code,
            "rule_name": self.rule_name,
            "description": self.description,
            "category": self.category,
            "severity": self.severity,
            "threshold_config": self.threshold_config,
            "is_enabled": self.is_enabled,
            "evaluation_window_days": self.evaluation_window_days,
            "department_id": self.department_id,
            "last_evaluated_at": self.last_evaluated_at.isoformat() if self.last_evaluated_at else None,
        }


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_code = Column(String(50), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), default="High", nullable=False, index=True)  # Critical, High, Medium, Low
    related_entity_type = Column(String(50), nullable=False)  # task, order, transaction, expense, department
    related_entity_id = Column(String(100), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    detected_at = Column(DateTime, default=utc_now, nullable=False, index=True)
    status = Column(String(30), default="New", nullable=False, index=True)  # New, Acknowledged, In Progress, Resolved, Dismissed
    assigned_owner_id = Column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    fingerprint = Column(String(128), unique=True, nullable=False, index=True)  # Deduplication hash
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    department = relationship("Department", back_populates="alerts")
    assigned_owner = relationship("Employee", foreign_keys=[assigned_owner_id])

    __table_args__ = (
        Index("idx_alerts_status_sev", "status", "severity"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "alert_code": self.alert_code,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "severity": self.severity,
            "related_entity_type": self.related_entity_type,
            "related_entity_id": self.related_entity_id,
            "department_id": self.department_id,
            "department_name": self.department.name if self.department else "General",
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "status": self.status,
            "assigned_owner": self.assigned_owner.name if self.assigned_owner else "Unassigned",
            "resolution_notes": self.resolution_notes,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "fingerprint": self.fingerprint,
        }


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_code = Column(String(50), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    category = Column(String(50), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    first_detected_at = Column(DateTime, default=utc_now, nullable=False)
    last_detected_at = Column(DateTime, default=utc_now, nullable=False)
    occurrence_count = Column(Integer, default=1, nullable=False)
    estimated_financial_impact = Column(Float, default=0.0, nullable=False)
    status = Column(String(30), default="Open", nullable=False, index=True)  # Open, In Progress, Resolved
    assigned_owner_id = Column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    root_cause_analysis = Column(Text, nullable=True)
    recurrence_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    department = relationship("Department", back_populates="incidents")
    assigned_owner = relationship("Employee", foreign_keys=[assigned_owner_id])
    resolutions = relationship("IncidentResolution", back_populates="incident", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "incident_code": self.incident_code,
            "title": self.title,
            "category": self.category,
            "department_id": self.department_id,
            "department_name": self.department.name if self.department else "General",
            "first_detected_at": self.first_detected_at.isoformat() if self.first_detected_at else None,
            "last_detected_at": self.last_detected_at.isoformat() if self.last_detected_at else None,
            "occurrence_count": self.occurrence_count,
            "estimated_financial_impact": self.estimated_financial_impact,
            "status": self.status,
            "assigned_owner": self.assigned_owner.name if self.assigned_owner else "Unassigned",
            "resolution_notes": self.resolution_notes,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "root_cause_analysis": self.root_cause_analysis,
            "recurrence_count": self.recurrence_count,
        }


class IncidentResolution(Base):
    __tablename__ = "incident_resolutions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(Integer, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    resolved_by_id = Column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime, default=utc_now, nullable=False)
    time_to_acknowledge_hours = Column(Float, default=0.0, nullable=False)
    time_to_resolve_hours = Column(Float, default=0.0, nullable=False)
    notes = Column(Text, nullable=True)
    preventive_measures = Column(Text, nullable=True)

    incident = relationship("Incident", back_populates="resolutions")
    resolved_by = relationship("Employee")


class ScheduledReport(Base):
    __tablename__ = "scheduled_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_type = Column(String(50), nullable=False)  # daily_summary, executive_brief, department_health
    parameters = Column(Text, default="{}", nullable=False)
    generated_at = Column(DateTime, default=utc_now, nullable=False)
    file_path = Column(String(255), nullable=True)
    recipient_emails = Column(String(255), nullable=True)
    status = Column(String(30), default="Generated", nullable=False)  # Generated, Sent, Failed
    summary_json = Column(Text, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(50), nullable=False, index=True)  # alert, incident, rule, import, report
    entity_id = Column(String(100), nullable=False, index=True)
    action = Column(String(50), nullable=False)  # CREATE, UPDATE_STATUS, ASSIGN, RESOLVE, IMPORT
    user_or_system = Column(String(100), default="System", nullable=False)
    details_json = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=utc_now, nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "action": self.action,
            "user_or_system": self.user_or_system,
            "details_json": self.details_json,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
