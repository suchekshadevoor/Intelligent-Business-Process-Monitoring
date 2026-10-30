"""
Data import service: CSV parsing, schema validation, duplicate detection, and batch insertion.
"""

import json
import io
from datetime import datetime, date
from typing import Dict, Any, List, Tuple
import pandas as pd
from sqlalchemy.orm import Session

from database.schema import (
    Department,
    Employee,
    Task,
    Order,
    Transaction,
    Expense,
    AuditLog,
    utc_now,
)
from config.settings import logger

# Required column schemas
REQUIRED_COLUMNS = {
    "tasks": ["task_id", "task_name", "start_date", "due_date"],
    "orders": ["order_id", "customer_name", "order_date", "expected_delivery_date", "order_value"],
    "transactions": ["transaction_id", "transaction_timestamp", "transaction_type", "amount", "status", "payment_method"],
    "expenses": ["expense_id", "date", "expense_category", "budgeted_amount", "actual_amount", "vendor"],
}

DATE_FORMATS = ["%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d-%m-%Y"]
DATETIME_FORMATS = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"]


def parse_date(val: Any) -> date | None:
    if pd.isna(val) or val is None or str(val).strip() == "":
        return None
    val_str = str(val).strip().split(" ")[0].split("T")[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(val_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date format for '{val}'. Expected YYYY-MM-DD.")


def parse_datetime(val: Any) -> datetime | None:
    if pd.isna(val) or val is None or str(val).strip() == "":
        return None
    val_str = str(val).strip()
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(val_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Invalid timestamp format for '{val}'. Expected ISO or YYYY-MM-DD HH:MM:SS.")


class DataImportService:
    @staticmethod
    def read_csv(file_content: Any) -> pd.DataFrame:
        """Parse raw file buffer or string into pandas DataFrame."""
        if isinstance(file_content, (bytes, bytearray)):
            stream = io.BytesIO(file_content)
            return pd.read_csv(stream)
        elif isinstance(file_content, str):
            return pd.read_csv(io.StringIO(file_content))
        else:
            return pd.read_csv(file_content)

    @classmethod
    def validate_and_preview(cls, file_content: Any, entity_type: str) -> Dict[str, Any]:
        """Inspect and validate CSV structure, returning preview and schema check results."""
        if entity_type not in REQUIRED_COLUMNS:
            return {
                "valid": False,
                "error": f"Unsupported entity type '{entity_type}'. Must be one of {list(REQUIRED_COLUMNS.keys())}",
            }

        try:
            df = cls.read_csv(file_content)
        except Exception as e:
            return {"valid": False, "error": f"Failed to parse CSV file: {str(e)}"}

        req_cols = REQUIRED_COLUMNS[entity_type]
        missing_cols = [c for c in req_cols if c not in df.columns]

        if missing_cols:
            return {
                "valid": False,
                "total_rows": len(df),
                "missing_columns": missing_cols,
                "available_columns": list(df.columns),
                "error": f"Missing required columns: {', '.join(missing_cols)}",
            }

        preview_records = df.head(5).to_dict(orient="records")
        return {
            "valid": True,
            "total_rows": len(df),
            "columns": list(df.columns),
            "preview": preview_records,
            "df": df,
        }

    @classmethod
    def import_tasks(cls, df: pd.DataFrame, db: Session) -> Dict[str, Any]:
        results = {"total": len(df), "inserted": 0, "duplicates": 0, "errors": []}
        
        # Preload departments and employees maps
        dept_map = {d.code.upper(): d.id for d in db.query(Department).all()}
        dept_name_map = {d.name.lower(): d.id for d in db.query(Department).all()}
        emp_map = {e.email.lower(): e.id for e in db.query(Employee).all()}

        # Existing task IDs
        existing_ids = set(r[0] for r in db.query(Task.task_id).all())
        seen_in_batch = set()

        for idx, row in df.iterrows():
            row_num = idx + 2
            task_id = str(row.get("task_id", "")).strip()
            if not task_id:
                results["errors"].append({"row": row_num, "field": "task_id", "message": "task_id is empty."})
                continue

            if task_id in existing_ids or task_id in seen_in_batch:
                results["duplicates"] += 1
                continue
            seen_in_batch.add(task_id)

            try:
                start_d = parse_date(row.get("start_date"))
                due_d = parse_date(row.get("due_date"))
                comp_d = parse_date(row.get("completion_date"))
            except ValueError as ve:
                results["errors"].append({"row": row_num, "field": "date", "message": str(ve)})
                continue

            if not start_d or not due_d:
                results["errors"].append({"row": row_num, "field": "date", "message": "start_date and due_date are required."})
                continue

            # Resolve department
            dept_id = None
            if "department_code" in row and pd.notna(row["department_code"]):
                dept_id = dept_map.get(str(row["department_code"]).strip().upper())
            elif "department_name" in row and pd.notna(row["department_name"]):
                dept_id = dept_name_map.get(str(row["department_name"]).strip().lower())

            # Resolve employee
            emp_id = None
            if "assigned_employee_email" in row and pd.notna(row["assigned_employee_email"]):
                emp_id = emp_map.get(str(row["assigned_employee_email"]).strip().lower())

            try:
                est_cost = float(row.get("estimated_cost", 0.0) or 0.0)
                act_cost = float(row.get("actual_cost", 0.0) or 0.0)
            except ValueError:
                results["errors"].append({"row": row_num, "field": "cost", "message": "Cost amounts must be numeric."})
                continue

            new_task = Task(
                task_id=task_id,
                task_name=str(row.get("task_name", "Unnamed Task")),
                assigned_employee_id=emp_id,
                department_id=dept_id,
                start_date=start_d,
                due_date=due_d,
                completion_date=comp_d,
                status=str(row.get("status", "Pending")),
                priority=str(row.get("priority", "Medium")),
                estimated_cost=est_cost,
                actual_cost=act_cost,
                is_synthetic=False,
            )
            db.add(new_task)
            results["inserted"] += 1

        db.commit()
        cls._log_audit(db, "tasks", results["inserted"], results["duplicates"], len(results["errors"]))
        return results

    @classmethod
    def import_orders(cls, df: pd.DataFrame, db: Session) -> Dict[str, Any]:
        results = {"total": len(df), "inserted": 0, "duplicates": 0, "errors": []}
        dept_map = {d.code.upper(): d.id for d in db.query(Department).all()}
        existing_ids = set(r[0] for r in db.query(Order.order_id).all())
        seen_in_batch = set()

        for idx, row in df.iterrows():
            row_num = idx + 2
            order_id = str(row.get("order_id", "")).strip()
            if not order_id:
                results["errors"].append({"row": row_num, "field": "order_id", "message": "order_id is empty."})
                continue

            if order_id in existing_ids or order_id in seen_in_batch:
                results["duplicates"] += 1
                continue
            seen_in_batch.add(order_id)

            try:
                o_date = parse_date(row.get("order_date"))
                exp_date = parse_date(row.get("expected_delivery_date"))
                act_date = parse_date(row.get("actual_delivery_date"))
            except ValueError as ve:
                results["errors"].append({"row": row_num, "field": "date", "message": str(ve)})
                continue

            if not o_date or not exp_date:
                results["errors"].append({"row": row_num, "field": "date", "message": "order_date and expected_delivery_date are required."})
                continue

            try:
                val = float(row.get("order_value", 0.0) or 0.0)
            except ValueError:
                results["errors"].append({"row": row_num, "field": "order_value", "message": "order_value must be numeric."})
                continue

            dept_id = None
            if "department_code" in row and pd.notna(row["department_code"]):
                dept_id = dept_map.get(str(row["department_code"]).strip().upper())

            new_order = Order(
                order_id=order_id,
                customer_name=str(row.get("customer_name", "Unknown")),
                order_date=o_date,
                expected_delivery_date=exp_date,
                actual_delivery_date=act_date,
                order_value=val,
                order_status=str(row.get("order_status", "Pending")),
                department_id=dept_id,
                is_synthetic=False,
            )
            db.add(new_order)
            results["inserted"] += 1

        db.commit()
        cls._log_audit(db, "orders", results["inserted"], results["duplicates"], len(results["errors"]))
        return results

    @classmethod
    def import_transactions(cls, df: pd.DataFrame, db: Session) -> Dict[str, Any]:
        results = {"total": len(df), "inserted": 0, "duplicates": 0, "errors": []}
        dept_map = {d.code.upper(): d.id for d in db.query(Department).all()}
        existing_ids = set(r[0] for r in db.query(Transaction.transaction_id).all())
        seen_in_batch = set()

        for idx, row in df.iterrows():
            row_num = idx + 2
            txn_id = str(row.get("transaction_id", "")).strip()
            if not txn_id:
                results["errors"].append({"row": row_num, "field": "transaction_id", "message": "transaction_id is empty."})
                continue

            if txn_id in existing_ids or txn_id in seen_in_batch:
                results["duplicates"] += 1
                continue
            seen_in_batch.add(txn_id)

            try:
                ts = parse_datetime(row.get("transaction_timestamp"))
            except ValueError as ve:
                results["errors"].append({"row": row_num, "field": "transaction_timestamp", "message": str(ve)})
                continue

            if not ts:
                results["errors"].append({"row": row_num, "field": "transaction_timestamp", "message": "Timestamp required."})
                continue

            try:
                amt = float(row.get("amount", 0.0) or 0.0)
            except ValueError:
                results["errors"].append({"row": row_num, "field": "amount", "message": "amount must be numeric."})
                continue

            dept_id = None
            if "department_code" in row and pd.notna(row["department_code"]):
                dept_id = dept_map.get(str(row["department_code"]).strip().upper())

            new_txn = Transaction(
                transaction_id=txn_id,
                transaction_timestamp=ts,
                transaction_type=str(row.get("transaction_type", "Payment")),
                amount=amt,
                status=str(row.get("status", "Pending")),
                payment_method=str(row.get("payment_method", "Other")),
                error_category=str(row.get("error_category", "None")),
                department_id=dept_id,
                is_synthetic=False,
            )
            db.add(new_txn)
            results["inserted"] += 1

        db.commit()
        cls._log_audit(db, "transactions", results["inserted"], results["duplicates"], len(results["errors"]))
        return results

    @classmethod
    def import_expenses(cls, df: pd.DataFrame, db: Session) -> Dict[str, Any]:
        results = {"total": len(df), "inserted": 0, "duplicates": 0, "errors": []}
        dept_map = {d.code.upper(): d.id for d in db.query(Department).all()}
        existing_ids = set(r[0] for r in db.query(Expense.expense_id).all())
        seen_in_batch = set()

        for idx, row in df.iterrows():
            row_num = idx + 2
            exp_id = str(row.get("expense_id", "")).strip()
            if not exp_id:
                results["errors"].append({"row": row_num, "field": "expense_id", "message": "expense_id is empty."})
                continue

            if exp_id in existing_ids or exp_id in seen_in_batch:
                results["duplicates"] += 1
                continue
            seen_in_batch.add(exp_id)

            try:
                exp_date = parse_date(row.get("date"))
            except ValueError as ve:
                results["errors"].append({"row": row_num, "field": "date", "message": str(ve)})
                continue

            if not exp_date:
                results["errors"].append({"row": row_num, "field": "date", "message": "date is required."})
                continue

            try:
                b_amt = float(row.get("budgeted_amount", 0.0) or 0.0)
                a_amt = float(row.get("actual_amount", 0.0) or 0.0)
            except ValueError:
                results["errors"].append({"row": row_num, "field": "amounts", "message": "Budgeted and actual amounts must be numeric."})
                continue

            dept_id = None
            if "department_code" in row and pd.notna(row["department_code"]):
                dept_id = dept_map.get(str(row["department_code"]).strip().upper())

            new_exp = Expense(
                expense_id=exp_id,
                date=exp_date,
                department_id=dept_id,
                expense_category=str(row.get("expense_category", "General")),
                budgeted_amount=b_amt,
                actual_amount=a_amt,
                vendor=str(row.get("vendor", "Unknown")),
                description=str(row.get("description", "")),
                is_synthetic=False,
            )
            db.add(new_exp)
            results["inserted"] += 1

        db.commit()
        cls._log_audit(db, "expenses", results["inserted"], results["duplicates"], len(results["errors"]))
        return results

    @staticmethod
    def _log_audit(db: Session, entity_type: str, inserted: int, duplicates: int, errors: int):
        log = AuditLog(
            entity_type=f"import_{entity_type}",
            entity_id=f"IMPORT_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            action="CSV_IMPORT",
            user_or_system="DataImportService",
            details_json=json.dumps({"inserted": inserted, "duplicates": duplicates, "errors": errors}),
            timestamp=utc_now(),
        )
        db.add(log)
        db.commit()
