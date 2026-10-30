"""
Main Streamlit Application: Intelligent Business Process Monitoring & Auto-Alert System.
Operational Command Center.
"""

import streamlit as st
from datetime import date
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy.orm import joinedload

from config.settings import settings
from database.connection import get_db
from database.schema import Alert, Task, Order, Transaction, Expense
from services.kpi_service import KPIService
from services.monitoring_service import MonitoringService
from ui_common import apply_theme, render_sidebar_filters, require_auth

# 1. Page Configuration
st.set_page_config(
    page_title="Business Process Monitor",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()
require_auth()

# Sidebar Branding
st.sidebar.markdown(f"## ⚡ **BPM Command Center**")
st.sidebar.caption(f"Environment: `{settings.APP_ENV}` | TZ: `{settings.TIMEZONE}`")
st.sidebar.markdown("---")

dept_id, start_d, end_d = render_sidebar_filters()

st.sidebar.markdown("---")
# Quick Run Button in Sidebar
if st.sidebar.button("🔄 Run Monitoring Checks", use_container_width=True):
    with get_db() as db:
        res = MonitoringService.evaluate_all_rules(db)
        st.sidebar.success(f"Evaluated! {res['new_alerts_created']} new, {res['existing_alerts_refreshed']} refreshed.")
        st.rerun()

# Main Page Header
st.title("⚡ Operational Command Center")
st.markdown(
    "Real-time monitoring of tasks, customer delivery SLAs, transaction failure spikes, "
    "budget exceptions, and automated alerting."
)

# Fetch Dynamic Metrics
with get_db() as db:
    kpis = KPIService.get_executive_summary(db, department_id=dept_id if dept_id > 0 else None, start_date=start_d, end_date=end_d)
    recent_alerts = (
        db.query(Alert)
        .options(joinedload(Alert.department))
        .filter(Alert.status.in_(("New", "Acknowledged", "In Progress")))
        .order_by(Alert.detected_at.desc())
        .limit(6)
        .all()
    )
    dept_df = KPIService.get_department_comparison_dataframe(db)
    txn_trends_df = KPIService.get_transaction_trends_dataframe(db)
    exp_cat_df = KPIService.get_expense_by_category_dataframe(db)

# 2. Executive KPI Cards Row
c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    task_rate = kpis["tasks"]["completion_rate_pct"]
    st.markdown(
        f"""
        <div class="kpi-container">
            <div class="kpi-label">Task Completion</div>
            <div class="kpi-value">{task_rate}%</div>
            <div class="kpi-subtext {'text-success' if task_rate >= 80 else 'text-danger'}">
                {kpis['tasks']['completed']} / {kpis['tasks']['total']} completed ({kpis['tasks']['overdue']} overdue)
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c2:
    delay_rate = kpis["orders"]["delay_rate_pct"]
    st.markdown(
        f"""
        <div class="kpi-container">
            <div class="kpi-label">Delayed Orders</div>
            <div class="kpi-value {'text-danger' if delay_rate > 15 else 'text-success'}">{kpis['orders']['delayed']}</div>
            <div class="kpi-subtext text-warning">
                {delay_rate}% delay rate (avg {kpis['orders']['avg_delay_days']}d)
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c3:
    fail_rate = kpis["transactions"]["failure_rate_pct"]
    st.markdown(
        f"""
        <div class="kpi-container">
            <div class="kpi-label">Txn Failure Rate</div>
            <div class="kpi-value {'text-danger' if fail_rate > 5 else 'text-success'}">{fail_rate}%</div>
            <div class="kpi-subtext text-info">
                {kpis['transactions']['failed']} failed / {kpis['transactions']['total']} total
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c4:
    var = kpis["expenses"]["variance"]
    st.markdown(
        f"""
        <div class="kpi-container">
            <div class="kpi-label">Budget Variance</div>
            <div class="kpi-value {'text-danger' if var > 0 else 'text-success'}">{'+' if var > 0 else ''}${var:,.0f}</div>
            <div class="kpi-subtext">
                {kpis['expenses']['variance_pct']}% of allocated budget
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c5:
    open_alt = kpis["alerts"]["open_count"]
    crit_alt = kpis["alerts"]["critical_count"]
    st.markdown(
        f"""
        <div class="kpi-container">
            <div class="kpi-label">Active Alerts</div>
            <div class="kpi-value {'text-danger' if crit_alt > 0 else 'text-warning'}">{open_alt}</div>
            <div class="kpi-subtext text-danger">
                <strong>{crit_alt}</strong> Critical &bull; {kpis['alerts']['high_count']} High
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# 3. Operational Visualizations Row
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader("💳 Transaction Volume & Failure Trends")
    if not txn_trends_df.empty:
        fig_tx = go.Figure()
        fig_tx.add_trace(go.Bar(
            x=txn_trends_df["date"],
            y=txn_trends_df["total_transactions"],
            name="Total Txns",
            marker_color="#94a3b8",
        ))
        fig_tx.add_trace(go.Scatter(
            x=txn_trends_df["date"],
            y=txn_trends_df["failure_rate_pct"],
            name="Failure Rate (%)",
            yaxis="y2",
            mode="lines+markers",
            line=dict(color="#dc2626", width=2),
        ))
        fig_tx.update_layout(
            template="plotly_white",
            height=300,
            margin=dict(l=20, r=20, t=20, b=20),
            yaxis=dict(title="Transaction Volume"),
            yaxis2=dict(title="Failure Rate (%)", overlaying="y", side="right", range=[0, 100]),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_tx, use_container_width=True)
    else:
        st.info("No transaction data available for current selection.")

with col_chart2:
    st.subheader("💰 Actual Expenditure vs Budget by Category")
    if not exp_cat_df.empty:
        fig_exp = go.Figure(data=[
            go.Bar(name='Budget', x=exp_cat_df['expense_category'], y=exp_cat_df['budgeted'], marker_color='#94a3b8'),
            go.Bar(name='Actual', x=exp_cat_df['expense_category'], y=exp_cat_df['actual'], marker_color='#ea580c'),
        ])
        fig_exp.update_layout(
            barmode='group',
            template="plotly_white",
            height=300,
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_exp, use_container_width=True)
    else:
        st.info("No expense data available.")

# 4. Critical Alerts & Immediate Attention Table
st.subheader("🚨 Priority Active Alerts Requiring Attention")
if recent_alerts:
    alert_rows = []
    for a in recent_alerts:
        alert_rows.append({
            "Alert Code": a.alert_code,
            "Severity": a.severity,
            "Category": a.category,
            "Title": a.title,
            "Entity": f"{a.related_entity_type}: {a.related_entity_id}",
            "Department": a.department.name if a.department else "General",
            "Detected At": a.detected_at.strftime("%Y-%m-%d %H:%M") if a.detected_at else "",
            "Status": a.status,
        })
    df_alerts = pd.DataFrame(alert_rows)
    st.dataframe(
        df_alerts,
        use_container_width=True,
        hide_index=True,
    )
else:
    st.success("🎉 No active alerts! All business operations are healthy.")

# 5. Department Performance Matrix
st.subheader("🏢 Department Operational Performance Comparison")
if not dept_df.empty:
    st.dataframe(dept_df, use_container_width=True, hide_index=True)
else:
    st.info("No department performance data available.")
