"""
Alert management service: lifecycle transitions, assignment, filtering, and audit logging.
"""

import json
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, desc

from database.schema import Alert, Employee, Department, AuditLog, utc_now
from config.settings import ALERT_STATUSES, SEVERITIES, logger


class AlertService:
    @staticmethod
    def get_alerts(
        db: Session,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        department_id: Optional[int] = None,
        search_term: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Alert]:
        """Query alerts with flexible multi-attribute filtering."""
        q = db.query(Alert)

        if status and status != "All":
            q = q.filter(Alert.status == status)
        if severity and severity != "All":
            q = q.filter(Alert.severity == severity)
        if category and category != "All":
            q = q.filter(Alert.category == category)
        if department_id and department_id > 0:
            q = q.filter(Alert.department_id == department_id)
        if search_term and search_term.strip():
            term = f"%{search_term.strip()}%"
            q = q.filter(
                or_(
                    Alert.title.ilike(term),
                    Alert.alert_code.ilike(term),
                    Alert.description.ilike(term),
                    Alert.related_entity_id.ilike(term),
                )
            )

        return (
            q.options(joinedload(Alert.department), joinedload(Alert.assigned_owner))
            .order_by(desc(Alert.detected_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_alert_by_id(db: Session, alert_id: int) -> Optional[Alert]:
        return db.query(Alert).filter(Alert.id == alert_id).first()

    @staticmethod
    def update_alert_status(
        db: Session,
        alert_id: int,
        new_status: str,
        user: str = "Operator",
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transition alert through its operational lifecycle and log in audit table."""
        if new_status not in ALERT_STATUSES:
            raise ValueError(f"Invalid alert status '{new_status}'. Allowed: {ALERT_STATUSES}")

        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            return {"success": False, "error": f"Alert with ID {alert_id} not found."}

        old_status = alert.status
        now = utc_now()
        alert.status = new_status
        alert.updated_at = now

        if notes:
            existing = alert.resolution_notes or ""
            alert.resolution_notes = f"{existing}\n[{now.strftime('%Y-%m-%d %H:%M')}] ({user}): {notes}".strip()

        if new_status in ("Resolved", "Dismissed"):
            alert.resolved_at = now

        # Add audit log
        log = AuditLog(
            entity_type="alert",
            entity_id=alert.alert_code,
            action=f"STATUS_{new_status.upper().replace(' ', '_')}",
            user_or_system=user,
            details_json=json.dumps({
                "from_status": old_status,
                "to_status": new_status,
                "notes": notes or "",
            }),
            timestamp=now,
        )
        db.add(log)
        db.commit()

        logger.info(f"Alert {alert.alert_code} status transitioned: {old_status} -> {new_status} by {user}")
        return {"success": True, "alert": alert.to_dict()}

    @staticmethod
    def assign_alert_owner(
        db: Session,
        alert_id: int,
        employee_id: int,
        user: str = "Operator",
    ) -> Dict[str, Any]:
        """Assign an employee as the alert owner."""
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            return {"success": False, "error": f"Alert with ID {alert_id} not found."}

        emp = db.query(Employee).filter(Employee.id == employee_id).first()
        if not emp:
            return {"success": False, "error": f"Employee #{employee_id} not found."}

        alert.assigned_owner_id = emp.id
        now = utc_now()
        alert.updated_at = now

        db.add(
            AuditLog(
                entity_type="alert",
                entity_id=alert.alert_code,
                action="ASSIGN_OWNER",
                user_or_system=user,
                details_json=json.dumps({"assigned_employee": emp.name, "employee_id": emp.id}),
                timestamp=now,
            )
        )
        db.commit()
        return {"success": True, "assigned_to": emp.name}

    @staticmethod
    def get_alert_history(db: Session, alert_code: str) -> List[Dict[str, Any]]:
        """Retrieve audit history log for a specific alert."""
        logs = db.query(AuditLog).filter(
            AuditLog.entity_type == "alert",
            AuditLog.entity_id == alert_code,
        ).order_by(AuditLog.timestamp.asc()).all()
        return [l.to_dict() for l in logs]
