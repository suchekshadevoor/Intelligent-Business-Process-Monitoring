"""
Tasks Monitoring Page: Incomplete tasks past deadlines, SLA tracking, and status breakdown.
"""

import streamlit as st
import pandas as pd
from datetime import date
from sqlalchemy.orm import joinedload
from database.connection import get_db
from database.schema import Task, Department, Employee
from ui_common import apply_theme, require_auth

st.set_page_config(page_title="Tasks Monitor", page_icon="📋", layout="wide")
apply_theme()
current_user = require_auth()

st.title("📋 Tasks Monitor & Deadline Tracking")
st.markdown("Track operational tasks, identify overdue work items, and analyze completion rates.")

with get_db() as db:
    tasks = db.query(Task).options(joinedload(Task.department), joinedload(Task.assigned_employee)).all()
    departments = db.query(Department).all()

dept_map = {0: "All Departments"}
for d in departments:
    dept_map[d.id] = f"{d.code} - {d.name}"

if current_user["role"] in ("admin", "manager"):
    with st.expander("Task Actions", expanded=False):
        create_tab, update_tab = st.tabs(["Create Task", "Update Task Status"])
        with create_tab:
            with st.form("create_task_form"):
                col_id, col_name = st.columns(2)
                task_id = col_id.text_input("Task ID")
                task_name = col_name.text_input("Task Name")
                col_dates, col_owner = st.columns(2)
                task_start = col_dates.date_input("Start Date", value=date.today())
                task_due = col_dates.date_input("Due Date", value=date.today())
                department_id = col_owner.selectbox(
                    "Department",
                    options=list(dept_map),
                    format_func=lambda value: dept_map[value],
                )
                with get_db() as db:
                    employee_options = db.query(Employee).filter(Employee.is_active.is_(True)).all()
                employee_map = {0: "Unassigned", **{employee.id: employee.name for employee in employee_options}}
                employee_id = st.selectbox(
                    "Assigned Employee",
                    options=list(employee_map),
                    format_func=lambda value: employee_map[value],
                )
                priority = st.selectbox("Priority", ["Low", "Medium", "High", "Urgent"], index=1)
                estimated_cost = st.number_input("Estimated Cost", min_value=0.0, value=0.0, step=100.0)
                submitted = st.form_submit_button("Create Task", type="primary")
                if submitted:
                    if not task_id.strip() or not task_name.strip():
                        st.error("Task ID and task name are required.")
                    elif task_due < task_start:
                        st.error("Due date cannot be earlier than the start date.")
                    else:
                        with get_db() as db:
                            exists = db.query(Task.id).filter(Task.task_id == task_id.strip()).first()
                            if exists:
                                st.error("That task ID already exists.")
                            else:
                                db.add(Task(
                                    task_id=task_id.strip(),
                                    task_name=task_name.strip(),
                                    department_id=department_id or None,
                                    assigned_employee_id=employee_id or None,
                                    start_date=task_start,
                                    due_date=task_due,
                                    status="Pending",
                                    priority=priority,
                                    estimated_cost=estimated_cost,
                                    actual_cost=0.0,
                                    is_synthetic=False,
                                ))
                        if not exists:
                            st.success("Task created.")
                            st.rerun()
        with update_tab:
            if tasks:
                task_labels = {task.task_id: f"{task.task_id} - {task.task_name}" for task in tasks}
                with st.form("update_task_status_form"):
                    selected_task_id = st.selectbox(
                        "Task", options=list(task_labels), format_func=lambda value: task_labels[value]
                    )
                    new_task_status = st.selectbox(
                        "Status", ["Pending", "In Progress", "Completed", "Cancelled"]
                    )
                    update_submitted = st.form_submit_button("Save Task Status")
                    if update_submitted:
                        with get_db() as db:
                            task_to_update = db.query(Task).filter(Task.task_id == selected_task_id).one()
                            task_to_update.status = new_task_status
                            task_to_update.completion_date = date.today() if new_task_status == "Completed" else None
                        st.success("Task status updated.")
                        st.rerun()
            else:
                st.info("Create or import a task before updating its status.")

# Filters
col_f1, col_f2, col_f3, col_f4 = st.columns(4)
with col_f1:
    selected_dept = st.selectbox("Department", options=list(dept_map.keys()), format_func=lambda x: dept_map[x])
with col_f2:
    selected_status = st.selectbox("Status", options=["All", "Pending", "In Progress", "Completed", "Cancelled"])
with col_f3:
    selected_priority = st.selectbox("Priority", options=["All", "Urgent", "High", "Medium", "Low"])
with col_f4:
    overdue_only = st.checkbox("Show Overdue Only", value=False)

today = date.today()

task_rows = []
for t in tasks:
    is_overdue = t.status not in ("Completed", "Cancelled") and t.due_date < today
    if overdue_only and not is_overdue:
        continue
    if selected_dept > 0 and t.department_id != selected_dept:
        continue
    if selected_status != "All" and t.status != selected_status:
        continue
    if selected_priority != "All" and t.priority != selected_priority:
        continue

    days_over = (today - t.due_date).days if is_overdue else 0
    task_rows.append({
        "Task ID": t.task_id,
        "Task Name": t.task_name,
        "Department": t.department.name if t.department else "General",
        "Assigned To": t.assigned_employee.name if t.assigned_employee else "Unassigned",
        "Due Date": t.due_date.isoformat(),
        "Status": t.status,
        "Priority": t.priority,
        "Days Overdue": days_over if is_overdue else None,
        "Est. Cost ($)": t.estimated_cost,
        "Act. Cost ($)": t.actual_cost,
        "Is Overdue": "⚠️ Yes" if is_overdue else "No",
    })

df_tasks = pd.DataFrame(task_rows)

# Top Metrics Row
m1, m2, m3, m4 = st.columns(4)
total_shown = len(df_tasks)
overdue_count = sum(1 for r in task_rows if r["Is Overdue"] == "⚠️ Yes")
completed_count = sum(1 for r in task_rows if r["Status"] == "Completed")
completion_pct = (completed_count / total_shown * 100) if total_shown > 0 else 0

m1.metric("Tasks Displayed", total_shown)
m2.metric("Overdue Tasks", overdue_count, delta=-overdue_count if overdue_count > 0 else 0, delta_color="inverse")
m3.metric("Completed Tasks", completed_count)
m4.metric("Completion Rate", f"{completion_pct:.1f}%")

st.markdown("<br>", unsafe_allow_html=True)

if not df_tasks.empty:
    st.dataframe(df_tasks, use_container_width=True, hide_index=True)

    # Export Button
    csv_bytes = df_tasks.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Export Filtered Tasks (CSV)",
        data=csv_bytes,
        file_name=f"tasks_export_{today.isoformat()}.csv",
        mime="text/csv",
    )
else:
    st.info("No tasks match the selected filter criteria.")
