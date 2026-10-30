"""
Automated tests for CSV data import, schema validation, and duplicate handling.
"""

import pandas as pd
from services.data_import_service import DataImportService
from database.schema import Task, Order, Transaction, Expense


def test_csv_validation_missing_columns():
    # CSV missing required 'due_date' column
    invalid_csv = "task_id,task_name,start_date\nTSK-X,Test Task,2026-01-01\n"
    res = DataImportService.validate_and_preview(invalid_csv, "tasks")
    assert res["valid"] is False
    assert "due_date" in res["missing_columns"]


def test_tasks_import_and_duplicate_prevention(db_session):
    csv_data = (
        "task_id,task_name,start_date,due_date,status,priority,estimated_cost,actual_cost\n"
        "IMP-TSK-1,Initial Task,2026-05-01,2026-05-10,Pending,Medium,1000,0\n"
        "IMP-TSK-2,Second Task,2026-05-02,2026-05-12,In Progress,High,2500,500\n"
    )
    df = pd.read_csv(pd.io.common.StringIO(csv_data))
    
    # Import 1
    res1 = DataImportService.import_tasks(df, db_session)
    assert res1["inserted"] == 2
    assert res1["duplicates"] == 0
    assert db_session.query(Task).filter(Task.task_id.in_(("IMP-TSK-1", "IMP-TSK-2"))).count() == 2

    # Import 2 (same data): should detect duplicates and insert 0
    res2 = DataImportService.import_tasks(df, db_session)
    assert res2["inserted"] == 0
    assert res2["duplicates"] == 2


def test_import_invalid_dates_handling(db_session):
    bad_csv = (
        "task_id,task_name,start_date,due_date\n"
        "BAD-TSK-1,Invalid Date Task,not-a-date,2026-05-10\n"
    )
    df = pd.read_csv(pd.io.common.StringIO(bad_csv))
    res = DataImportService.import_tasks(df, db_session)
    assert res["inserted"] == 0
    assert len(res["errors"]) == 1
    assert res["errors"][0]["field"] == "date"
