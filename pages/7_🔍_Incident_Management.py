"""
Incident Management & Root-Cause Analysis (RCA) Page:
Tracks grouped operational incidents, resolution SLAs (MTTA, MTTR), and statistical correlations.
"""

import streamlit as st
import pandas as pd
from datetime import date
from sqlalchemy.orm import joinedload
from database.connection import get_db
from database.schema import Incident, Employee, Department
from services.incident_service import IncidentService
from ui_common import apply_theme, require_auth

st.set_page_config(page_title="Incident Management & RCA", page_icon="🔍", layout="wide")
apply_theme()
require_auth(allowed_roles=["admin", "manager"])

st.title("🔍 Incident Management & Root-Cause Analysis")
st.markdown(
    "Correlate related operational alerts into parent incidents, track Mean Time to Acknowledge (MTTA) "
    "and Mean Time to Resolve (MTTR), and review empirical root-cause correlations."
)

with get_db() as db:
    incidents = (
        db.query(Incident)
        .options(joinedload(Incident.department))
        .order_by(Incident.last_detected_at.desc())
        .all()
    )
    employees = db.query(Employee).filter(Employee.is_active == True).all()
    departments = db.query(Department).all()
    correlations = IncidentService.compute_root_cause_correlations(db)

emp_map = {e.id: f"{e.name} ({e.role})" for e in employees}

# Summary KPIs
open_count = sum(1 for inc in incidents if inc.status in ("Open", "In Progress"))
resolved_count = sum(1 for inc in incidents if inc.status == "Resolved")
total_financial_impact = sum(inc.estimated_financial_impact for inc in incidents)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Incidents", len(incidents))
m2.metric("Active / Open Incidents", open_count, delta=-open_count if open_count > 0 else 0, delta_color="inverse")
m3.metric("Resolved Incidents", resolved_count)
m4.metric("Est. Financial Impact", f"${total_financial_impact:,.2f}")

st.markdown("<br>", unsafe_allow_html=True)

# Tabs: Incidents Ledger vs Root-Cause Analysis
tab_incidents, tab_rca = st.tabs(["📋 Operational Incidents Ledger", "🔬 Empirical Root-Cause Analysis (RCA)"])

with tab_incidents:
    st.subheader("Active & Historical Operational Incidents")
    if not incidents:
        st.info("No incidents recorded.")
    else:
        for inc in incidents:
            with st.expander(f"[{inc.status.upper()}] {inc.title} (`{inc.incident_code}`) - {inc.category}", expanded=(inc.status != "Resolved")):
                c_details, c_actions = st.columns([3, 2])

                with c_details:
                    st.markdown(f"**Department:** {inc.department.name if inc.department else 'General'}")
                    st.markdown(f"**Occurrences:** `{inc.occurrence_count}` &bull; **Recurrence Count:** `{inc.recurrence_count}`")
                    st.markdown(f"**First Detected:** {inc.first_detected_at.strftime('%Y-%m-%d %H:%M UTC')}")
                    st.markdown(f"**Last Detected:** {inc.last_detected_at.strftime('%Y-%m-%d %H:%M UTC')}")
                    st.markdown(f"**Est. Financial Impact:** ${inc.estimated_financial_impact:,.2f}")
                    if inc.resolution_notes:
                        st.markdown(f"**Resolution Notes:** {inc.resolution_notes}")
                    if inc.root_cause_analysis:
                        st.markdown(f"**Root-Cause Analysis:** {inc.root_cause_analysis}")

                with c_actions:
                    if inc.status != "Resolved":
                        st.markdown("##### 🏁 Resolve Incident")
                        res_owner = st.selectbox(
                            "Resolving Engineer",
                            options=list(emp_map.keys()),
                            format_func=lambda x: emp_map[x],
                            key=f"res_emp_{inc.id}",
                        )
                        res_notes = st.text_area("Resolution Summary", key=f"res_notes_{inc.id}")
                        prev_measures = st.text_input("Preventive Action Item", key=f"prev_{inc.id}")
                        rca_text = st.text_input("Identified Root Cause", key=f"rca_{inc.id}")

                        if st.button("Mark Incident as Resolved", key=f"btn_res_{inc.id}"):
                            with get_db() as db:
                                res = IncidentService.resolve_incident(
                                    db=db,
                                    incident_id=inc.id,
                                    resolved_by_id=res_owner,
                                    notes=res_notes,
                                    preventive_measures=prev_measures,
                                    root_cause_analysis=rca_text,
                                    user="Operations Lead",
                                )
                                if res["success"]:
                                    st.success(f"Incident {inc.incident_code} resolved.")
                                    st.rerun()
                                else:
                                    st.error(res.get("error"))
                    else:
                        st.success(f"✅ Incident was resolved on {inc.resolved_at.strftime('%Y-%m-%d %H:%M UTC') if inc.resolved_at else ''}")

with tab_rca:
    st.subheader("Empirical Correlation & Recurring Failure Patterns")
    st.warning("⚖️ **Correlation vs. Causation Principle**: The relationships below represent observed statistical correlations across operational tables. They indicate where failures cluster and require technical inspection, not definitive proof of solitary root causality.")

    findings = correlations.get("findings", [])
    if findings:
        for f in findings:
            st.markdown(
                f"""
                <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px; margin-bottom: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h4 style="margin: 0; color: #0f172a;">📍 {f['area']}</h4>
                        <span style="background: #f1f5f9; color: #475569; font-weight: 600; padding: 2px 8px; border-radius: 4px; font-size: 12px;">{f['most_frequent_error']}</span>
                    </div>
                    <p style="margin: 8px 0 4px 0; font-size: 14px; color: #1e293b;"><strong>Observed Pattern:</strong> {f['observed_pattern']}</p>
                    <p style="margin: 4px 0 8px 0; font-size: 13px; color: #475569;"><strong>Statistical Insight:</strong> {f['correlation_insight']}</p>
                    <div style="background: #eff6ff; border-left: 3px solid #3b82f6; padding: 8px 12px; font-size: 13px; color: #1e40af; border-radius: 0 4px 4px 0;">
                        <strong>Recommended Process Improvement:</strong> {f['recommended_action']}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("Insufficient historical pattern volume to calculate statistical correlations.")
