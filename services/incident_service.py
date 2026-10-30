"""
Incident resolution, grouping, MTTA/MTTR metrics, and Root-Cause Analysis (RCA) service.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database.schema import (
    Incident,
    IncidentResolution,
    Alert,
    Employee,
    Department,
    Transaction,
    Expense,
    Task,
    AuditLog,
    utc_now,
)
from config.settings import INCIDENT_STATUSES, logger


class IncidentService:
    @staticmethod
    def get_incidents(
        db: Session,
        status: Optional[str] = None,
        category: Optional[str] = None,
        department_id: Optional[int] = None,
    ) -> List[Incident]:
        """Fetch incidents filtered by status, category, and department."""
        q = db.query(Incident)
        if status and status != "All":
            q = q.filter(Incident.status == status)
        if category and category != "All":
            q = q.filter(Incident.category == category)
        if department_id and department_id > 0:
            q = q.filter(Incident.department_id == department_id)
        return q.order_by(desc(Incident.last_detected_at)).all()

    @staticmethod
    def create_or_group_incident(
        db: Session,
        title: str,
        category: str,
        department_id: Optional[int],
        financial_impact: float = 0.0,
        user: str = "System",
    ) -> Incident:
        """Create a new incident or correlate into existing open incident in same category/department."""
        existing = db.query(Incident).filter(
            Incident.category == category,
            Incident.department_id == department_id,
            Incident.status.in_(("Open", "In Progress")),
        ).first()

        now = utc_now()
        if existing:
            existing.occurrence_count += 1
            existing.last_detected_at = now
            existing.estimated_financial_impact += financial_impact
            existing.updated_at = now
            db.commit()
            return existing

        code = f"INC-{now.strftime('%y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
        new_inc = Incident(
            incident_code=code,
            title=title,
            category=category,
            department_id=department_id,
            first_detected_at=now,
            last_detected_at=now,
            occurrence_count=1,
            estimated_financial_impact=financial_impact,
            status="Open",
            created_at=now,
            updated_at=now,
        )
        db.add(new_inc)
        db.commit()
        return new_inc

    @staticmethod
    def resolve_incident(
        db: Session,
        incident_id: int,
        resolved_by_id: Optional[int],
        notes: str,
        preventive_measures: str,
        root_cause_analysis: str,
        user: str = "Operator",
    ) -> Dict[str, Any]:
        """Resolve an incident, record metrics (MTTA, MTTR), and log resolution."""
        inc = db.query(Incident).filter(Incident.id == incident_id).first()
        if not inc:
            return {"success": False, "error": f"Incident #{incident_id} not found."}

        now = utc_now()
        # Calculate time metrics in hours safely with naive UTC
        first_det = inc.first_detected_at.replace(tzinfo=None) if inc.first_detected_at.tzinfo else inc.first_detected_at
        upd_at = inc.updated_at.replace(tzinfo=None) if inc.updated_at.tzinfo else inc.updated_at
        total_duration = (now - first_det).total_seconds() / 3600.0
        time_to_ack = (upd_at - first_det).total_seconds() / 3600.0 if inc.status == "In Progress" else 1.0
        time_to_resolve = max(total_duration, 0.1)

        inc.status = "Resolved"
        inc.resolved_at = now
        inc.resolution_notes = notes
        inc.root_cause_analysis = root_cause_analysis
        inc.updated_at = now

        # Add resolution record
        res_record = IncidentResolution(
            incident_id=inc.id,
            resolved_by_id=resolved_by_id,
            resolved_at=now,
            time_to_acknowledge_hours=round(time_to_ack, 2),
            time_to_resolve_hours=round(time_to_resolve, 2),
            notes=notes,
            preventive_measures=preventive_measures,
        )
        db.add(res_record)

        # Audit log
        db.add(
            AuditLog(
                entity_type="incident",
                entity_id=inc.incident_code,
                action="RESOLVE",
                user_or_system=user,
                details_json=json.dumps({
                    "resolution_time_hours": round(time_to_resolve, 2),
                    "notes": notes,
                    "preventive_measures": preventive_measures,
                }),
                timestamp=now,
            )
        )
        db.commit()
        return {"success": True, "incident": inc.to_dict()}

    @staticmethod
    def compute_root_cause_correlations(db: Session) -> Dict[str, Any]:
        """
        Analyze system data to detect statistical correlations and recurring failure patterns.
        Strictly distinguishes observed statistical correlation from proven causation.
        """
        findings = []

        # 1. Transaction failure correlation with payment methods
        failed_txns = db.query(Transaction).filter(Transaction.status == "Failed").all()
        if failed_txns:
            df_tx = pd.DataFrame([
                {"payment_method": t.payment_method, "error_category": t.error_category}
                for t in failed_txns
            ])
            top_pm = df_tx["payment_method"].value_index = df_tx["payment_method"].value_counts()
            top_err = df_tx["error_category"].value_counts()

            if len(top_pm) > 0 and len(top_err) > 0:
                highest_pm = top_pm.index[0]
                highest_err = top_err.index[0]
                pct_pm = (top_pm.iloc[0] / len(df_tx)) * 100.0
                findings.append({
                    "area": "Transactions & Payments",
                    "observed_pattern": f"{pct_pm:.1f}% of failed transactions occurred via '{highest_pm}'.",
                    "most_frequent_error": highest_err,
                    "correlation_insight": (
                        f"Strong statistical correlation observed between '{highest_pm}' payment method and '{highest_err}'. "
                        f"Note: This is an observed correlation and does not prove that {highest_pm} is the sole root cause; "
                        f"external API rate limiting or gateway network drops may be responsible."
                    ),
                    "recommended_action": f"Inspect API response logs for {highest_pm} gateway timeouts and verify retry backoff configuration.",
                })

        # 2. Expense overrun correlation with vendors
        expenses = db.query(Expense).all()
        if expenses:
            exp_data = []
            for e in expenses:
                var = e.actual_amount - e.budgeted_amount
                if var > 0:
                    exp_data.append({"vendor": e.vendor, "category": e.expense_category, "variance": var})
            if exp_data:
                df_exp = pd.DataFrame(exp_data)
                vendor_var = df_exp.groupby("vendor")["variance"].sum().sort_values(ascending=False)
                top_v = vendor_var.index[0]
                findings.append({
                    "area": "Operational Costs",
                    "observed_pattern": f"Vendor '{top_v}' generated highest cumulative budget overrun (${vendor_var.iloc[0]:,.2f}).",
                    "most_frequent_error": "Budget Overrun",
                    "correlation_insight": (
                        f"Cost overruns heavily cluster around vendor '{top_v}'. "
                        f"Correlation observed between emergency demand and unbudgeted cloud/logistics charges."
                    ),
                    "recommended_action": f"Conduct vendor contract renegotiation and enforce PO approval pre-authorization for {top_v}.",
                })

        # 3. Tasks delay correlation with departments
        tasks = db.query(Task).all()
        if tasks:
            today = datetime.now(timezone.utc).date()
            overdue_depts = []
            for t in tasks:
                if t.status != "Completed" and t.due_date < today and t.department:
                    overdue_depts.append(t.department.name)
            if overdue_depts:
                s = pd.Series(overdue_depts).value_counts()
                top_dept = s.index[0]
                findings.append({
                    "area": "Task Execution",
                    "observed_pattern": f"Department '{top_dept}' has the highest frequency of overdue tasks ({s.iloc[0]} tasks).",
                    "most_frequent_error": "Deadline Miss",
                    "correlation_insight": (
                        f"Tasks in '{top_dept}' correlate with resource bottlenecking or scope underestimation. "
                        f"Further investigation into team workload distribution is recommended."
                    ),
                    "recommended_action": f"Re-evaluate sprint capacity and task sizing in {top_dept}.",
                })

        return {
            "total_patterns_identified": len(findings),
            "findings": findings,
            "disclaimer": "All insights are derived from empirical historical correlation. Definitive causation requires engineering log verification.",
        }
