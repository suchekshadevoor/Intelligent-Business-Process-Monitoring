"""
Core monitoring engine evaluating business records against configurable rules.
Includes deterministic deduplication fingerprinting to prevent alert proliferation.
"""

import json
from datetime import date, datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.schema import (
    Task,
    Order,
    Transaction,
    Expense,
    Department,
    MonitoringRule,
    Alert,
    Incident,
    AuditLog,
    utc_now,
)
from services.anomaly_service import AnomalyService
from config.settings import logger


class MonitoringService:
    @classmethod
    def evaluate_all_rules(cls, db: Session) -> Dict[str, Any]:
        """Run full evaluation of all active monitoring rules."""
        rules = db.query(MonitoringRule).filter(MonitoringRule.is_enabled == True).all()
        summary = {
            "evaluated_rules": len(rules),
            "new_alerts_created": 0,
            "existing_alerts_refreshed": 0,
            "details": [],
        }

        now = utc_now()
        for rule in rules:
            try:
                rule_config = json.loads(rule.threshold_config) if rule.threshold_config else {}
                rule_code = rule.rule_code

                if "OVERDUE-TASKS" in rule_code:
                    created, refreshed = cls._eval_overdue_tasks(db, rule, rule_config)
                elif "DELAYED-ORDERS" in rule_code:
                    created, refreshed = cls._eval_delayed_orders(db, rule, rule_config)
                elif "TXN-FAILURE" in rule_code:
                    created, refreshed = cls._eval_transaction_failure(db, rule, rule_config)
                elif "COST-ANOMALY" in rule_code:
                    created, refreshed = cls._eval_cost_anomalies(db, rule, rule_config)
                elif "DEPT-PERFORMANCE" in rule_code:
                    created, refreshed = cls._eval_dept_performance(db, rule, rule_config)
                elif "RECURRING-ISSUES" in rule_code:
                    created, refreshed = cls._eval_recurring_issues(db, rule, rule_config)
                elif "SLOW-RESOLUTION" in rule_code:
                    created, refreshed = cls._eval_slow_resolution(db, rule, rule_config)
                else:
                    created, refreshed = (0, 0)

                rule.last_evaluated_at = now
                summary["new_alerts_created"] += created
                summary["existing_alerts_refreshed"] += refreshed
                summary["details"].append({
                    "rule_code": rule.rule_code,
                    "rule_name": rule.rule_name,
                    "new_alerts": created,
                    "refreshed_alerts": refreshed,
                    "status": "success",
                })
            except Exception as e:
                logger.error(f"Error evaluating rule {rule.rule_code}: {e}", exc_info=True)
                summary["details"].append({
                    "rule_code": rule.rule_code,
                    "rule_name": rule.rule_name,
                    "error": str(e),
                    "status": "failed",
                })

        db.commit()
        return summary

    @classmethod
    def _create_or_refresh_alert(
        cls,
        db: Session,
        rule: MonitoringRule,
        title: str,
        description: str,
        category: str,
        severity: str,
        entity_type: str,
        entity_id: str,
        dept_id: int | None,
        fingerprint: str,
    ) -> Tuple[bool, bool]:
        """
        Deduplication engine: Checks if an active alert exists with this fingerprint.
        Returns (is_new, is_refreshed).
        """
        existing_alert = db.query(Alert).filter(Alert.fingerprint == fingerprint).first()

        now = utc_now()
        if existing_alert and existing_alert.status in ("New", "Acknowledged", "In Progress"):
            # Active alert already exists: refresh description and timestamp without duplicating
            existing_alert.updated_at = now
            existing_alert.description = description
            return False, True

        if existing_alert:
            previous_status = existing_alert.status
            existing_alert.title = title
            existing_alert.description = description
            existing_alert.severity = severity
            existing_alert.detected_at = now
            existing_alert.updated_at = now
            existing_alert.status = "New"
            existing_alert.resolved_at = None
            db.add(
                AuditLog(
                    entity_type="alert",
                    entity_id=existing_alert.alert_code,
                    action="REOPEN",
                    user_or_system=f"RuleEngine:{rule.rule_code}",
                    details_json=json.dumps({"from_status": previous_status, "to_status": "New"}),
                    timestamp=now,
                )
            )
            return False, True

        # Generate unique alert code
        import uuid
        alert_code = f"ALT-{now.strftime('%y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        new_alert = Alert(
            alert_code=alert_code,
            title=title,
            description=description,
            category=category,
            severity=severity,
            related_entity_type=entity_type,
            related_entity_id=entity_id,
            department_id=dept_id,
            detected_at=now,
            status="New",
            fingerprint=fingerprint,
            created_at=now,
            updated_at=now,
        )
        db.add(new_alert)

        # Audit log creation
        db.add(
            AuditLog(
                entity_type="alert",
                entity_id=alert_code,
                action="CREATE",
                user_or_system=f"RuleEngine:{rule.rule_code}",
                details_json=json.dumps({"title": title, "severity": severity, "entity": f"{entity_type}:{entity_id}"}),
                timestamp=now,
            )
        )
        return True, False

    @classmethod
    def _eval_overdue_tasks(cls, db: Session, rule: MonitoringRule, config: dict) -> Tuple[int, int]:
        min_days = int(config.get("min_days_overdue", 1))
        today = date.today()
        cutoff_date = today - timedelta(days=min_days)

        tasks = db.query(Task).filter(
            Task.status.not_in(("Completed", "Cancelled")),
            Task.due_date <= cutoff_date,
        ).all()

        created, refreshed = 0, 0
        for t in tasks:
            days_over = (today - t.due_date).days
            title = f"Task '{t.task_id}' Overdue by {days_over} Day(s)"
            desc = (
                f"Task '{t.task_name}' (ID: {t.task_id}) assigned to employee "
                f"#{t.assigned_employee_id or 'Unassigned'} was due on {t.due_date} "
                f"and remains in '{t.status}' status ({days_over} days overdue)."
            )
            fp = f"{rule.rule_code}:task:{t.task_id}"
            is_new, is_ref = cls._create_or_refresh_alert(
                db=db,
                rule=rule,
                title=title,
                description=desc,
                category="Tasks",
                severity=rule.severity,
                entity_type="task",
                entity_id=t.task_id,
                dept_id=t.department_id,
                fingerprint=fp,
            )
            if is_new:
                created += 1
            elif is_ref:
                refreshed += 1
        return created, refreshed

    @classmethod
    def _eval_delayed_orders(cls, db: Session, rule: MonitoringRule, config: dict) -> Tuple[int, int]:
        today = date.today()
        # Find delivered orders that arrived late, OR active orders past expected delivery date
        orders = db.query(Order).filter(
            (Order.actual_delivery_date != None) & (Order.actual_delivery_date > Order.expected_delivery_date) |
            ((Order.actual_delivery_date == None) & (Order.order_status.not_in(("Delivered", "Cancelled"))) & (Order.expected_delivery_date < today))
        ).all()

        created, refreshed = 0, 0
        for o in orders:
            delay = (o.actual_delivery_date - o.expected_delivery_date).days if o.actual_delivery_date else (today - o.expected_delivery_date).days
            title = f"Customer Order '{o.order_id}' Delivery Delay ({delay} Days)"
            desc = (
                f"Order '{o.order_id}' for customer '{o.customer_name}' with value ${o.order_value:,.2f} "
                f"breached expected delivery date ({o.expected_delivery_date}). Delay: {delay} day(s)."
            )
            fp = f"{rule.rule_code}:order:{o.order_id}"
            is_new, is_ref = cls._create_or_refresh_alert(
                db=db,
                rule=rule,
                title=title,
                description=desc,
                category="Orders",
                severity=rule.severity,
                entity_type="order",
                entity_id=o.order_id,
                dept_id=o.department_id,
                fingerprint=fp,
            )
            if is_new:
                created += 1
            elif is_ref:
                refreshed += 1
        return created, refreshed

    @classmethod
    def _eval_transaction_failure(cls, db: Session, rule: MonitoringRule, config: dict) -> Tuple[int, int]:
        threshold_pct = float(config.get("failure_rate_pct_threshold", 5.0))
        min_txns = int(config.get("min_txns_count", 10))
        window_days = rule.evaluation_window_days or 7

        start_time = utc_now() - timedelta(days=window_days)
        txns = db.query(Transaction).filter(Transaction.transaction_timestamp >= start_time).all()

        total = len(txns)
        if total < min_txns:
            return 0, 0

        failed = sum(1 for tx in txns if tx.status == "Failed")
        failure_rate = (failed / total) * 100.0

        if failure_rate > threshold_pct:
            # Breakdown by primary error
            error_counts = {}
            for tx in txns:
                if tx.status == "Failed":
                    error_counts[tx.error_category] = error_counts.get(tx.error_category, 0) + 1
            top_error = max(error_counts.items(), key=lambda x: x[1]) if error_counts else ("Unknown", 0)

            title = f"High Transaction Failure Rate ({failure_rate:.1f}%)"
            desc = (
                f"Financial transaction failure rate reached {failure_rate:.1f}% ({failed}/{total} failed) "
                f"over the past {window_days} days, exceeding the {threshold_pct}% threshold. "
                f"Primary error cause: '{top_error[0]}' with {top_error[1]} failures."
            )
            # Daily rolling fingerprint
            today_str = date.today().isoformat()
            fp = f"{rule.rule_code}:window:{today_str}"
            is_new, is_ref = cls._create_or_refresh_alert(
                db=db,
                rule=rule,
                title=title,
                description=desc,
                category="Transactions",
                severity=rule.severity,
                entity_type="transaction_batch",
                entity_id=f"WINDOW_{today_str}",
                dept_id=None,
                fingerprint=fp,
            )
            return (1, 0) if is_new else (0, 1)
        return 0, 0

    @classmethod
    def _eval_cost_anomalies(cls, db: Session, rule: MonitoringRule, config: dict) -> Tuple[int, int]:
        overrun_pct = float(config.get("budget_overrun_pct", 20.0))
        z_thresh = float(config.get("zscore_threshold", 2.5))

        window_days = rule.evaluation_window_days or 30
        cutoff = date.today() - timedelta(days=window_days)
        expenses = db.query(Expense).filter(Expense.date >= cutoff).all()

        if not expenses:
            return 0, 0

        # Calculate Z-Scores across window
        actual_amounts = [e.actual_amount for e in expenses]
        z_results = AnomalyService.detect_zscore_anomalies(actual_amounts, z_threshold=z_thresh)

        created, refreshed = 0, 0
        for idx, exp in enumerate(expenses):
            # Check budget variance
            b_res = AnomalyService.detect_budget_variance_anomaly(exp.budgeted_amount, exp.actual_amount, overrun_pct)
            z_res = z_results[idx]

            if b_res["is_anomaly"] or z_res["is_anomaly"]:
                reasons = []
                if b_res["is_anomaly"]:
                    reasons.append(b_res["explanation"])
                if z_res["is_anomaly"]:
                    reasons.append(z_res["explanation"])

                title = f"Cost Anomaly in {exp.expense_category} (${exp.actual_amount:,.2f})"
                desc = (
                    f"Expense ID '{exp.expense_id}' with vendor '{exp.vendor}' was flagged as an anomaly. "
                    f"Details: {' '.join(reasons)}"
                )
                fp = f"{rule.rule_code}:expense:{exp.expense_id}"
                is_new, is_ref = cls._create_or_refresh_alert(
                    db=db,
                    rule=rule,
                    title=title,
                    description=desc,
                    category="Expenses",
                    severity=rule.severity,
                    entity_type="expense",
                    entity_id=exp.expense_id,
                    dept_id=exp.department_id,
                    fingerprint=fp,
                )
                if is_new:
                    created += 1
                elif is_ref:
                    refreshed += 1
        return created, refreshed

    @classmethod
    def _eval_dept_performance(cls, db: Session, rule: MonitoringRule, config: dict) -> Tuple[int, int]:
        min_rate = float(config.get("min_completion_rate_pct", 80.0))
        departments = db.query(Department).all()

        created, refreshed = 0, 0
        today_str = date.today().isoformat()

        for dept in departments:
            tasks = db.query(Task).filter(Task.department_id == dept.id).all()
            if len(tasks) < 3:
                continue

            completed = sum(1 for t in tasks if t.status == "Completed")
            comp_rate = (completed / len(tasks)) * 100.0

            if comp_rate < min_rate:
                title = f"Department '{dept.code}' Task Completion Rate Below SLA ({comp_rate:.1f}%)"
                desc = (
                    f"Department '{dept.name}' ({dept.code}) has completed only {completed}/{len(tasks)} "
                    f"tasks ({comp_rate:.1f}%), falling below the minimum SLA target of {min_rate}%."
                )
                fp = f"{rule.rule_code}:dept:{dept.code}:{today_str}"
                is_new, is_ref = cls._create_or_refresh_alert(
                    db=db,
                    rule=rule,
                    title=title,
                    description=desc,
                    category="Department Performance",
                    severity=rule.severity,
                    entity_type="department",
                    entity_id=dept.code,
                    dept_id=dept.id,
                    fingerprint=fp,
                )
                if is_new:
                    created += 1
                elif is_ref:
                    refreshed += 1
        return created, refreshed

    @classmethod
    def _eval_recurring_issues(cls, db: Session, rule: MonitoringRule, config: dict) -> Tuple[int, int]:
        min_recurr = int(config.get("min_recurrence_count", 3))
        lookback = int(config.get("lookback_days", 14))

        cutoff = utc_now() - timedelta(days=lookback)
        alerts = db.query(Alert).filter(Alert.detected_at >= cutoff).all()

        # Group by category and department
        groups = {}
        for a in alerts:
            key = (a.category, a.department_id)
            groups[key] = groups.get(key, 0) + 1

        created, refreshed = 0, 0
        today_str = date.today().isoformat()

        for (cat, dept_id), count in groups.items():
            if count >= min_recurr:
                dept_name = "General"
                if dept_id:
                    d = db.query(Department).filter(Department.id == dept_id).first()
                    if d:
                        dept_name = d.name

                title = f"Recurring Operational Failure in {cat} ({count} Occurrences)"
                desc = (
                    f"Category '{cat}' in department '{dept_name}' has generated {count} alerts "
                    f"within the past {lookback} days, crossing the repeat issue threshold of {min_recurr}."
                )
                fp = f"{rule.rule_code}:recurr:{cat}:{dept_id or 0}:{today_str}"
                is_new, is_ref = cls._create_or_refresh_alert(
                    db=db,
                    rule=rule,
                    title=title,
                    description=desc,
                    category="Recurring Issues",
                    severity=rule.severity,
                    entity_type="recurring_category",
                    entity_id=f"{cat}_{dept_id or 0}",
                    dept_id=dept_id,
                    fingerprint=fp,
                )
                if is_new:
                    created += 1
                elif is_ref:
                    refreshed += 1
        return created, refreshed

    @classmethod
    def _eval_slow_resolution(cls, db: Session, rule: MonitoringRule, config: dict) -> Tuple[int, int]:
        max_hours = float(config.get("max_resolution_hours", 48.0))
        now = utc_now()

        incidents = db.query(Incident).filter(Incident.status.in_(("Open", "In Progress"))).all()
        created, refreshed = 0, 0

        for inc in incidents:
            inc_start = inc.first_detected_at.replace(tzinfo=None) if inc.first_detected_at.tzinfo else inc.first_detected_at
            duration_hours = (now - inc_start).total_seconds() / 3600.0
            if duration_hours > max_hours:
                title = f"Incident '{inc.incident_code}' Unresolved Beyond SLA ({duration_hours:.1f}h)"
                desc = (
                    f"Incident '{inc.title}' (ID: {inc.incident_code}) in {inc.category} has remained "
                    f"unresolved for {duration_hours:.1f} hours, exceeding the resolution SLA of {max_hours} hours."
                )
                fp = f"{rule.rule_code}:incident:{inc.incident_code}"
                is_new, is_ref = cls._create_or_refresh_alert(
                    db=db,
                    rule=rule,
                    title=title,
                    description=desc,
                    category="SLA Breaches",
                    severity=rule.severity,
                    entity_type="incident",
                    entity_id=inc.incident_code,
                    dept_id=inc.department_id,
                    fingerprint=fp,
                )
                if is_new:
                    created += 1
                elif is_ref:
                    refreshed += 1
        return created, refreshed
