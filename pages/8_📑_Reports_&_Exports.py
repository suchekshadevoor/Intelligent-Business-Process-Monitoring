"""
Reports & Power BI Integration Page:
On-demand report generation, HTML/CSV downloads, and Power BI connection guidance with SQL view exports.
"""

import json
from pathlib import Path
import streamlit as st
import pandas as pd
from datetime import date
from database.connection import get_db
from database.schema import ScheduledReport
from database.views import VIEWS_DDL
from services.report_service import ReportService
from ui_common import apply_theme, require_auth

st.set_page_config(page_title="Reports & Power BI", page_icon="📑", layout="wide")
apply_theme()
require_auth()

st.title("📑 Executive Reports & Power BI Integration")
st.markdown("Generate 12-section business performance audits, download HTML/CSV summaries, and export data models to Microsoft Power BI.")

tab_reports, tab_powerbi = st.tabs(["📑 Automated Daily Performance Reports", "📊 Power BI Integration & SQL Views"])

with tab_reports:
    col_act1, col_act2 = st.columns([3, 1])
    with col_act1:
        st.markdown("### Generate Fresh Performance Report")
        st.caption("Compiles all 12 operational sections: tasks, orders, transactions, budget anomalies, and process recommendations.")
    with col_act2:
        if st.button("⚡ Generate Report Now", use_container_width=True):
            with get_db() as db:
                res = ReportService.generate_daily_report(db, user="Dashboard Operator")
                st.success("New Daily Performance Report successfully generated!")
                st.rerun()

    st.markdown("---")
    st.subheader("Archived Performance Reports")

    with get_db() as db:
        reports = db.query(ScheduledReport).order_by(ScheduledReport.generated_at.desc()).limit(15).all()

    if not reports:
        st.info("No reports have been generated yet. Click 'Generate Report Now' above.")
    else:
        for rep in reports:
            rep_date = rep.generated_at.strftime("%Y-%m-%d %H:%M UTC")
            summary_dict = json.loads(rep.summary_json) if rep.summary_json else {}

            with st.expander(f"Daily Audit Report - {rep_date} (`ID #{rep.id}`)", expanded=False):
                st.markdown(f"**Executive Overview:** {summary_dict.get('1_executive_summary', 'N/A')}")
                
                # Recommendations
                recs = summary_dict.get("12_recommended_actions", [])
                if recs:
                    st.markdown("**Data-Driven Action Items:**")
                    for r in recs:
                        st.markdown(f"- {r}")

                # Download Buttons
                if rep.file_path and Path(rep.file_path).exists():
                    html_bytes = Path(rep.file_path).read_bytes()
                    st.download_button(
                        label="📥 Download Responsive HTML Report",
                        data=html_bytes,
                        file_name=Path(rep.file_path).name,
                        mime="text/html",
                        key=f"dl_html_{rep.id}",
                    )

with tab_powerbi:
    st.subheader("Microsoft Power BI Connection Architecture")
    st.markdown(
        """
        The system provides **two enterprise pathways** for importing operational intelligence into **Microsoft Power BI Desktop / Service**:
        
        1. **Direct Database Connection via SQLite ODBC / SQLAlchemy**:
           Point Power BI Desktop to `business_monitor.db` using the standard SQLite3 ODBC driver and query the registered analytical SQL views directly.
        
        2. **Periodic CSV Sync Ingestion**:
           Export normalized, pre-aggregated datasets from the SQL views below and load them directly into your Power BI semantic data model.
        """
    )

    st.markdown("### Registered SQL Analytical Views for Power BI")
    
    with get_db() as db:
        for view_name, ddl in VIEWS_DDL.items():
            with st.expander(f"SQL View: `{view_name}`", expanded=False):
                st.code(ddl.strip(), language="sql")
                
                # Query preview and export
                try:
                    df_view = pd.read_sql(f"SELECT * FROM {view_name} LIMIT 25", db.bind)
                    st.dataframe(df_view, use_container_width=True, hide_index=True)
                    csv_bytes = df_view.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label=f"📥 Download `{view_name}.csv` for Power BI",
                        data=csv_bytes,
                        file_name=f"{view_name}.csv",
                        mime="text/csv",
                        key=f"dl_view_{view_name}",
                    )
                except Exception as e:
                    st.warning(f"Unable to preview view {view_name}: {e}")
