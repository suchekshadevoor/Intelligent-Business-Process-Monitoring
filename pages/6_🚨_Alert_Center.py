"""
Alert Management Center: Search, filter, lifecycle state machine transitions, owner assignment,
resolution notes, and audit log history.
"""

import streamlit as st
import pandas as pd
from datetime import date
from database.connection import get_db
from database.schema import Alert, Employee, Department
from services.alert_service import AlertService
from config.settings import SEVERITIES, ALERT_STATUSES, CATEGORIES
from ui_common import apply_theme, require_auth

st.set_page_config(page_title="Alert Center", page_icon="🚨", layout="wide")
apply_theme()
require_auth(allowed_roles=["admin", "manager"])

st.title("🚨 Operational Alert Management Center")
st.markdown("Monitor triggered threshold breaches, assign incident responders, manage alert lifecycles, and audit resolution logs.")

with get_db() as db:
    departments = db.query(Department).all()
    employees = db.query(Employee).filter(Employee.is_active == True).all()

dept_map = {0: "All Departments"}
for d in departments:
    dept_map[d.id] = f"{d.code} - {d.name}"

emp_map = {e.id: f"{e.name} ({e.role})" for e in employees}

# Search and Filters Bar
f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns([2, 1, 1, 1, 1])
with f_col1:
    search_q = st.text_input("🔍 Search alerts by code, title, or entity ID", value="")
with f_col2:
    status_filter = st.selectbox("Status", options=["All"] + ALERT_STATUSES, index=0)
with f_col3:
    severity_filter = st.selectbox("Severity", options=["All"] + SEVERITIES, index=0)
with f_col4:
    category_filter = st.selectbox("Category", options=["All"] + CATEGORIES, index=0)
with f_col5:
    dept_filter = st.selectbox("Department", options=list(dept_map.keys()), format_func=lambda x: dept_map[x], index=0)

with get_db() as db:
    alerts = AlertService.get_alerts(
        db,
        status=status_filter,
        severity=severity_filter,
        category=category_filter,
        department_id=dept_filter,
        search_term=search_q,
        limit=150,
    )

# Summary Counters
c1, c2, c3, c4 = st.columns(4)
c1.metric("Alerts Displayed", len(alerts))
c2.metric("Critical Alerts", sum(1 for a in alerts if a.severity == "Critical"), delta_color="inverse")
c3.metric("New / Unacknowledged", sum(1 for a in alerts if a.status == "New"))
c4.metric("In Progress", sum(1 for a in alerts if a.status == "In Progress"))

st.markdown("<br>", unsafe_allow_html=True)

if not alerts:
    st.info("No alerts match your current filter parameters.")
else:
    # Display each alert in a card with action forms
    for alert in alerts:
        sev_color = "#dc2626" if alert.severity == "Critical" else "#ea580c" if alert.severity == "High" else "#ca8a04" if alert.severity == "Medium" else "#475569"
        status_badge = "#fee2e2" if alert.status == "New" else "#fef9c3" if alert.status in ("Acknowledged", "In Progress") else "#dcfce7"
        status_text_color = "#b91c1c" if alert.status == "New" else "#854d0e" if alert.status in ("Acknowledged", "In Progress") else "#15803d"

        with st.expander(f"[{alert.severity.upper()}] {alert.title} — `{alert.alert_code}` ({alert.status})", expanded=False):
            col_info, col_actions = st.columns([3, 2])

            with col_info:
                st.markdown(f"**Description:** {alert.description}")
                st.markdown(f"**Category:** `{alert.category}` &bull; **Related Record:** `{alert.related_entity_type}: {alert.related_entity_id}`")
                st.markdown(f"**Department:** {alert.department.name if alert.department else 'General'}")
                st.markdown(f"**Detected At:** {alert.detected_at.strftime('%Y-%m-%d %H:%M:%S UTC') if alert.detected_at else 'N/A'}")
                if alert.resolved_at:
                    st.markdown(f"**Resolved At:** {alert.resolved_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                if alert.resolution_notes:
                    st.markdown(f"**Resolution Notes:**\n```\n{alert.resolution_notes}\n```")

                # View Audit Trail
                with get_db() as db:
                    history = AlertService.get_alert_history(db, alert.alert_code)
                if history:
                    st.markdown("##### 📜 Audit Trail History")
                    for h in history:
                        st.caption(f"&bull; **{h['timestamp']}** - `{h['action']}` by **{h['user_or_system']}** ({h.get('details_json', '')})")

            with col_actions:
                st.markdown("##### 🛠️ Operational Actions")
                
                # Owner Assignment Form
                current_owner_id = alert.assigned_owner_id or (list(emp_map.keys())[0] if emp_map else None)
                selected_owner = st.selectbox(
                    "Assign Incident Owner",
                    options=list(emp_map.keys()),
                    format_func=lambda x: emp_map[x],
                    index=list(emp_map.keys()).index(current_owner_id) if current_owner_id in emp_map else 0,
                    key=f"owner_{alert.id}",
                )

                if st.button("Assign Owner", key=f"btn_assign_{alert.id}"):
                    with get_db() as db:
                        res = AlertService.assign_alert_owner(db, alert.id, selected_owner, user="Manager")
                        if res["success"]:
                            st.success(f"Assigned to {res['assigned_to']}")
                            st.rerun()

                # Status Transition & Notes Form
                new_st = st.selectbox(
                    "Update Status",
                    options=ALERT_STATUSES,
                    index=ALERT_STATUSES.index(alert.status) if alert.status in ALERT_STATUSES else 0,
                    key=f"status_{alert.id}",
                )
                action_notes = st.text_input("Operational Notes / Resolution Summary", key=f"notes_{alert.id}")

                if st.button("Apply Status Change", key=f"btn_status_{alert.id}"):
                    with get_db() as db:
                        res = AlertService.update_alert_status(db, alert.id, new_st, user="Manager", notes=action_notes)
                        if res["success"]:
                            st.success(f"Alert transitioned to '{new_st}' successfully.")
                            st.rerun()
                        else:
                            st.error(res.get("error"))
