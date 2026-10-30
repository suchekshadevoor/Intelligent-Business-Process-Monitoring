"""
FastAPI REST API: Intelligent Business Process Monitoring & Auto-Alert System.
Exposes OpenAPI documented endpoints for authentication, operational data,
monitoring triggers, alerts lifecycle, incident resolution, reports, and user management.
"""

from datetime import date, datetime
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from database.connection import get_db, init_db
from database.schema import (
    User,
    Task,
    Order,
    Transaction,
    Expense,
    Alert,
    Incident,
    Department,
    Employee,
    utc_now,
)
from services.auth_service import AuthService, PERMISSIONS
from services.kpi_service import KPIService
from services.monitoring_service import MonitoringService
from services.alert_service import AlertService
from services.incident_service import IncidentService
from services.report_service import ReportService
from services.email_service import EmailService
from services.anomaly_service import AnomalyService
from jobs.scheduler import scheduler_service
from config.settings import settings

# Initialize database
init_db()

app = FastAPI(
    title="Business Process Monitoring & Auto-Alert API",
    description="Enterprise REST API for monitoring tasks, orders, transactions, expenses, alerts, and SLA compliance.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for external frontend or microservice integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.API_CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency: Database Session
def db_session():
    with get_db() as db:
        yield db


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(db_session),
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = AuthService.verify_access_token(credentials.credentials)
    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first() if user_id else None
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_permission(permission: str):
    def permission_check(current_user: User = Depends(get_current_user)) -> User:
        if not AuthService.is_authorized(current_user.role, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")
        return current_user

    return permission_check


# Pydantic Schemas
class LoginRequest(BaseModel):
    username_or_email: str
    password: str


class CreateTaskRequest(BaseModel):
    task_id: str = Field(..., json_schema_extra={"example": "TSK-7701"})
    task_name: str = Field(..., json_schema_extra={"example": "Warehouse Network Infrastructure Audit"})
    department_id: Optional[int] = Field(None, json_schema_extra={"example": 1})
    assigned_employee_id: Optional[int] = Field(None, json_schema_extra={"example": 1})
    start_date: date
    due_date: date
    priority: str = Field("Medium", json_schema_extra={"example": "High"})
    estimated_cost: float = Field(0.0, ge=0, json_schema_extra={"example": 5000.0})


class CreateOrderRequest(BaseModel):
    order_id: str = Field(..., json_schema_extra={"example": "ORD-7701"})
    customer_name: str = Field(..., json_schema_extra={"example": "Vanguard Industrial Corp"})
    department_id: Optional[int] = Field(None, json_schema_extra={"example": 2})
    order_date: date
    expected_delivery_date: date
    order_value: float = Field(0.0, ge=0, json_schema_extra={"example": 28500.0})
    order_status: str = Field("Pending", json_schema_extra={"example": "Processing"})


class UpdateAlertStatusRequest(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "In Progress"})
    notes: Optional[str] = Field(None, json_schema_extra={"example": "Assigned to logistics response team."})
    user: str = Field("API Operator", json_schema_extra={"example": "Ops Lead"})


class AssignAlertOwnerRequest(BaseModel):
    employee_id: int
    user: str = "API Operator"


class ResolveIncidentRequest(BaseModel):
    resolved_by_id: Optional[int] = None
    notes: str
    preventive_measures: str
    root_cause_analysis: str
    user: str = "API Operator"


class CreateUserRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str = "analyst"


# 1. Health & Status
@app.get("/api/health", tags=["System"])
def health_check(db: Session = Depends(db_session)):
    """Health check verifying database connectivity and background scheduler state."""
    sched_info = scheduler_service.get_status()
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "database": "connected",
        "scheduler_active": sched_info["is_running"],
        "timestamp": utc_now().isoformat(),
    }


# 2. Authentication
@app.post("/api/auth/login", tags=["Authentication"])
def login(req: LoginRequest, db: Session = Depends(db_session)):
    """Authenticate with username or email and return user profile with permissions."""
    user = AuthService.authenticate_user(db, req.username_or_email, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    access_token, expires_at = AuthService.issue_access_token(user.id)
    return {
        "success": True,
        "user": user.to_dict(),
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.API_TOKEN_TTL_MINUTES * 60,
        "expires_at": datetime.fromtimestamp(expires_at).isoformat(),
        "permissions": PERMISSIONS.get(user.role, []),
    }


@app.get("/api/users", tags=["Users"])
def get_users(
    db: Session = Depends(db_session),
    current_user: User = Depends(require_permission("manage_users")),
):
    """List all registered system users."""
    return AuthService.list_users(db)


@app.post("/api/users", tags=["Users"], status_code=status.HTTP_201_CREATED)
def create_user(
    req: CreateUserRequest,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_permission("manage_users")),
):
    """Create a new user account (Admin role)."""
    res = AuthService.create_user(db, req.username, req.email, req.password, req.role, created_by="API Admin")
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


# 3. KPI & Analytics
@app.get("/api/kpis/summary", tags=["Analytics"])
def get_kpi_summary(
    department_id: Optional[int] = None,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_permission("view_dashboard")),
):
    """Retrieve high-level operational KPI metrics."""
    return KPIService.get_executive_summary(db, department_id=department_id)


# 4. Tasks Management
@app.get("/api/tasks", tags=["Tasks"])
def get_tasks(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    department_id: Optional[int] = None,
    overdue_only: bool = False,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_permission("view_dashboard")),
):
    """List operational tasks with multi-attribute filtering."""
    q = db.query(Task)
    if status and status != "All":
        q = q.filter(Task.status == status)
    if priority and priority != "All":
        q = q.filter(Task.priority == priority)
    if department_id and department_id > 0:
        q = q.filter(Task.department_id == department_id)
    if overdue_only:
        q = q.filter(Task.status.not_in(("Completed", "Cancelled")), Task.due_date < date.today())
    tasks = q.order_by(Task.due_date.asc()).all()
    return [t.to_dict() for t in tasks]


@app.post("/api/tasks", tags=["Tasks"], status_code=status.HTTP_201_CREATED)
def create_task(
    req: CreateTaskRequest,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_permission("create_records")),
):
    """Create and persist a new operational task."""
    if db.query(Task).filter(Task.task_id == req.task_id).first():
        raise HTTPException(status_code=400, detail=f"Task ID '{req.task_id}' already exists.")

    new_task = Task(
        task_id=req.task_id.strip(),
        task_name=req.task_name.strip(),
        department_id=req.department_id,
        assigned_employee_id=req.assigned_employee_id,
        start_date=req.start_date,
        due_date=req.due_date,
        status="Pending",
        priority=req.priority,
        estimated_cost=req.estimated_cost,
        actual_cost=0.0,
        is_synthetic=False,
    )
    db.add(new_task)
    db.commit()
    return {"success": True, "task": new_task.to_dict()}


# 5. Orders Management
@app.get("/api/orders", tags=["Orders"])
def get_orders(
    status: Optional[str] = None,
    department_id: Optional[int] = None,
    delayed_only: bool = False,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_permission("view_dashboard")),
):
    """List customer orders with delay filters."""
    q = db.query(Order)
    if status and status != "All":
        q = q.filter(Order.order_status == status)
    if department_id and department_id > 0:
        q = q.filter(Order.department_id == department_id)
    orders = q.order_by(Order.expected_delivery_date.asc()).all()
    today = date.today()

    res = []
    for o in orders:
        is_delayed = (o.actual_delivery_date and o.actual_delivery_date > o.expected_delivery_date) or (
            not o.actual_delivery_date and o.order_status not in ("Delivered", "Cancelled") and o.expected_delivery_date < today
        )
        if delayed_only and not is_delayed:
            continue
        d = o.to_dict()
        d["is_delayed"] = bool(is_delayed)
        res.append(d)
    return res


@app.post("/api/orders", tags=["Orders"], status_code=status.HTTP_201_CREATED)
def create_order(
    req: CreateOrderRequest,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_permission("create_records")),
):
    """Create and persist a new customer order."""
    if db.query(Order).filter(Order.order_id == req.order_id).first():
        raise HTTPException(status_code=400, detail=f"Order ID '{req.order_id}' already exists.")

    new_order = Order(
        order_id=req.order_id.strip(),
        customer_name=req.customer_name.strip(),
        department_id=req.department_id,
        order_date=req.order_date,
        expected_delivery_date=req.expected_delivery_date,
        order_value=req.order_value,
        order_status=req.order_status,
        is_synthetic=False,
    )
    db.add(new_order)
    db.commit()
    return {"success": True, "order": new_order.to_dict()}


# 6. Transactions & Expenses
@app.get("/api/transactions", tags=["Transactions"])
def get_transactions(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(db_session),
    current_user: User = Depends(require_permission("view_dashboard")),
):
    """List recent financial transactions."""
    txns = db.query(Transaction).order_by(Transaction.transaction_timestamp.desc()).limit(limit).all()
    return [t.to_dict() for t in txns]


@app.get("/api/expenses", tags=["Expenses"])
def get_expenses(
    db: Session = Depends(db_session),
    current_user: User = Depends(require_permission("view_dashboard")),
):
    """List expenses with automated anomaly detection tags."""
    expenses = db.query(Expense).order_by(Expense.date.desc()).all()
    amounts = [e.actual_amount for e in expenses]
    z_res = AnomalyService.detect_zscore_anomalies(amounts)
    iqr_res = AnomalyService.detect_iqr_anomalies(amounts)

    out = []
    for i, e in enumerate(expenses):
        b_res = AnomalyService.detect_budget_variance_anomaly(e.budgeted_amount, e.actual_amount)
        item = e.to_dict()
        item["is_anomaly"] = b_res["is_anomaly"] or z_res[i]["is_anomaly"] or iqr_res[i]["is_anomaly"]
        item["anomaly_reasons"] = [
            r["explanation"] for r in [b_res, z_res[i], iqr_res[i]] if r["is_anomaly"]
        ]
        out.append(item)
    return out


# 7. Alert Management
@app.get("/api/alerts", tags=["Alerts"])
def get_alerts(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    category: Optional[str] = None,
    department_id: Optional[int] = None,
    search: Optional[str] = None,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_permission("view_dashboard")),
):
    """Search and filter alerts."""
    alerts = AlertService.get_alerts(
        db, status=status, severity=severity, category=category, department_id=department_id, search_term=search
    )
    return [a.to_dict() for a in alerts]


@app.post("/api/alerts/{alert_id}/status", tags=["Alerts"])
def update_alert_status(
    alert_id: int,
    req: UpdateAlertStatusRequest,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_permission("resolve_alerts")),
):
    """Transition alert status through the operational lifecycle."""
    res = AlertService.update_alert_status(db, alert_id, req.status, user=req.user, notes=req.notes)
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@app.post("/api/alerts/{alert_id}/assign", tags=["Alerts"])
def assign_alert_owner(
    alert_id: int,
    req: AssignAlertOwnerRequest,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_permission("assign_alerts")),
):
    """Assign alert responder owner."""
    res = AlertService.assign_alert_owner(db, alert_id, req.employee_id, user=req.user)
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


# 8. Incident Management & RCA
@app.get("/api/incidents", tags=["Incidents"])
def get_incidents(
    status: Optional[str] = None,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_permission("view_dashboard")),
):
    """List grouped incidents and MTTA/MTTR metrics."""
    incidents = IncidentService.get_incidents(db, status=status)
    correlations = IncidentService.compute_root_cause_correlations(db)
    return {
        "incidents": [i.to_dict() for i in incidents],
        "root_cause_correlations": correlations,
    }


@app.post("/api/incidents/{incident_id}/resolve", tags=["Incidents"])
def resolve_incident(
    incident_id: int,
    req: ResolveIncidentRequest,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_permission("resolve_alerts")),
):
    """Resolve an incident and record root cause and preventive measures."""
    res = IncidentService.resolve_incident(
        db=db,
        incident_id=incident_id,
        resolved_by_id=req.resolved_by_id,
        notes=req.notes,
        preventive_measures=req.preventive_measures,
        root_cause_analysis=req.root_cause_analysis,
        user=req.user,
    )
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


# 9. Monitoring Execution & Reports
@app.post("/api/monitoring/run", tags=["Monitoring"])
def run_monitoring(
    db: Session = Depends(db_session),
    current_user: User = Depends(require_permission("run_monitoring")),
):
    """Trigger an immediate monitoring evaluation across all 7 business rules."""
    summary = MonitoringService.evaluate_all_rules(db)
    return {"success": True, "summary": summary}


@app.post("/api/reports/daily", tags=["Reports"])
def generate_report(
    db: Session = Depends(db_session),
    current_user: User = Depends(require_permission("view_reports")),
):
    """Generate a fresh 12-section Daily Business Performance Report."""
    res = ReportService.generate_daily_report(db, user="API Request")
    return {"success": True, "report": res}


@app.post("/api/email/test", tags=["Notifications"])
def test_email(
    recipient: Optional[EmailStr] = None,
    current_user: User = Depends(require_permission("manage_rules")),
):
    """Test SMTP email notification or inspect Simulated Demo Mode."""
    res = EmailService.test_smtp_connection(test_recipient=recipient)
    return res
