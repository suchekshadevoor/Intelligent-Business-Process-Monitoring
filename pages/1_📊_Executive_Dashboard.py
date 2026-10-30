"""
Executive Dashboard Sub-page redirect / render.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
from sqlalchemy.orm import joinedload

from database.connection import get_db
from database.schema import Alert
from services.kpi_service import KPIService
from services.monitoring_service import MonitoringService
from ui_common import apply_theme, render_sidebar_filters, require_auth

st.set_page_config(page_title="Executive Dashboard", page_icon="📊", layout="wide")
apply_theme()
require_auth()

st.title("📊 Executive Dashboard & KPI Center")
st.markdown("High-level operational intelligence: task completion rates, order fulfillment SLAs, transaction health, and budget variances.")

dept_id, start_d, end_d = render_sidebar_filters()

with get_db() as db:
    kpis = KPIService.get_executive_summary(db, department_id=dept_id if dept_id > 0 else None, start_date=start_d, end_date=end_d)
    recent_alerts = (
        db.query(Alert)
        .options(joinedload(Alert.department))
        .filter(Alert.status.in_(("New", "Acknowledged", "In Progress")))
        .order_by(Alert.detected_at.desc())
        .limit(10)
        .all()
    )
    dept_df = KPIService.get_department_comparison_dataframe(db)
    txn_trends_df = KPIService.get_transaction_trends_dataframe(db)
    exp_cat_df = KPIService.get_expense_by_category_dataframe(db)

# 1. KPI Cards Row
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
            <div class="kpi-subtext text-warning">{delay_rate}% delay rate (avg {kpis['orders']['avg_delay_days']}d)</div>
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
            <div class="kpi-subtext text-info">{kpis['transactions']['failed']} failed / {kpis['transactions']['total']} total</div>
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
            <div class="kpi-subtext">{kpis['expenses']['variance_pct']}% of allocated budget</div>
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
            <div class="kpi-subtext text-danger"><strong>{crit_alt}</strong> Critical &bull; {kpis['alerts']['high_count']} High</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# 2. Charts Row
ch1, ch2 = st.columns(2)
with ch1:
    st.subheader("💳 Transaction Reliability Trend")
    if not txn_trends_df.empty:
        fig_tx = go.Figure()
        fig_tx.add_trace(go.Bar(x=txn_trends_df["date"], y=txn_trends_df["total_transactions"], name="Volume", marker_color="#94a3b8"))
        fig_tx.add_trace(go.Scatter(x=txn_trends_df["date"], y=txn_trends_df["failure_rate_pct"], name="Failure Rate (%)", yaxis="y2", line=dict(color="#dc2626", width=2)))
        fig_tx.update_layout(
            template="plotly_white",
            height=300,
            margin=dict(l=20, r=20, t=20, b=20),
            yaxis2=dict(title="Failure Rate (%)", overlaying="y", side="right", range=[0, 100]),
            legend=dict(orientation="h", y=1.05, x=1),
        )
        st.plotly_chart(fig_tx, use_container_width=True)

with ch2:
    st.subheader("💰 Category Expenditure vs Budget")
    if not exp_cat_df.empty:
        fig_exp = go.Figure(data=[
            go.Bar(name='Budget', x=exp_cat_df['expense_category'], y=exp_cat_df['budgeted'], marker_color='#94a3b8'),
            go.Bar(name='Actual', x=exp_cat_df['expense_category'], y=exp_cat_df['actual'], marker_color='#ea580c'),
        ])
        fig_exp.update_layout(barmode='group', template="plotly_white", height=300, margin=dict(l=20, r=20, t=20, b=20), legend=dict(orientation="h", y=1.05, x=1))
        st.plotly_chart(fig_exp, use_container_width=True)

# 3. Department Comparison Matrix
st.subheader("🏢 Department Operational Performance")
st.dataframe(dept_df, use_container_width=True, hide_index=True)
