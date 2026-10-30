"""
Expenses & Anomaly Detection Page: Operational costs, statistical Z-score/IQR outlier detection,
and budget variance analysis with full mathematical explanations.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from sqlalchemy.orm import joinedload
from database.connection import get_db
from database.schema import Expense, Department
from services.anomaly_service import AnomalyService
from ui_common import apply_theme, require_auth

st.set_page_config(page_title="Expenses & Anomalies", page_icon="💰", layout="wide")
apply_theme()
require_auth()

st.title("💰 Expenses & Statistical Cost Anomaly Detection")
st.markdown(
    "Detect anomalous operational expenditures using budget variance thresholds, standard deviation "
    "Z-scores, and Tukey's IQR fences. Every flagged anomaly includes an explainable baseline rationale."
)

with get_db() as db:
    expenses = (
        db.query(Expense)
        .options(joinedload(Expense.department))
        .order_by(Expense.date.desc())
        .all()
    )
    departments = db.query(Department).all()

dept_map = {0: "All Departments"}
for d in departments:
    dept_map[d.id] = f"{d.code} - {d.name}"

# Controls & Sensitivity Configuration
with st.expander("⚙️ Anomaly Detection Baseline & Sensitivity Settings", expanded=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        budget_thresh_pct = st.slider("Budget Overrun Threshold (%)", min_value=5.0, max_value=100.0, value=20.0, step=5.0)
    with c2:
        zscore_thresh = st.slider("Z-Score Threshold (σ)", min_value=1.5, max_value=4.0, value=2.5, step=0.1)
    with c3:
        iqr_mult = st.slider("IQR Outlier Multiplier", min_value=1.0, max_value=3.0, value=1.5, step=0.1)
    st.caption("ℹ️ *Statistical Note*: Z-Score detects deviations from the Gaussian mean; IQR provides a non-parametric outlier fence robust to skewed distributions.")

# Run Anomaly Evaluations
all_actuals = [e.actual_amount for e in expenses]
z_results = AnomalyService.detect_zscore_anomalies(all_actuals, z_threshold=zscore_thresh)
iqr_results = AnomalyService.detect_iqr_anomalies(all_actuals, multiplier=iqr_mult)

expense_rows = []
anomalies_list = []

for idx, e in enumerate(expenses):
    b_res = AnomalyService.detect_budget_variance_anomaly(e.budgeted_amount, e.actual_amount, overrun_threshold_pct=budget_thresh_pct)
    z_res = z_results[idx]
    iqr_res = iqr_results[idx]

    is_flagged = b_res["is_anomaly"] or z_res["is_anomaly"] or iqr_res["is_anomaly"]
    flag_reasons = []
    if b_res["is_anomaly"]:
        flag_reasons.append(f"Budget Overrun: {b_res['explanation']}")
    if z_res["is_anomaly"]:
        flag_reasons.append(f"Z-Score ({z_res['score']}σ): {z_res['explanation']}")
    if iqr_res["is_anomaly"]:
        flag_reasons.append(f"IQR Fence: {iqr_res['explanation']}")

    var_amt = e.actual_amount - e.budgeted_amount
    var_pct = (var_amt / e.budgeted_amount * 100) if e.budgeted_amount > 0 else 0

    record = {
        "Expense ID": e.expense_id,
        "Date": e.date.isoformat(),
        "Department": e.department.name if e.department else "General",
        "Category": e.expense_category,
        "Budget ($)": e.budgeted_amount,
        "Actual ($)": e.actual_amount,
        "Variance ($)": var_amt,
        "Variance (%)": f"{var_pct:+.1f}%",
        "Vendor": e.vendor,
        "Description": e.description or "-",
        "Anomaly?": "⚠️ Anomaly" if is_flagged else "Normal",
        "Reasons": " | ".join(flag_reasons) if flag_reasons else "Within normal baseline",
    }
    expense_rows.append(record)
    if is_flagged:
        anomalies_list.append((e, flag_reasons))

df_expenses = pd.DataFrame(expense_rows)

# Metrics
total_exp = sum(e.actual_amount for e in expenses)
total_bud = sum(e.budgeted_amount for e in expenses)
total_var = total_exp - total_bud
flagged_count = len(anomalies_list)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Expenses Recorded", f"${total_exp:,.2f}")
m2.metric("Total Approved Budget", f"${total_bud:,.2f}")
m3.metric("Net Budget Variance", f"{'+' if total_var > 0 else ''}${total_var:,.2f}", delta=f"{total_var / total_bud * 100:.1f}%", delta_color="inverse")
m4.metric("Detected Anomalies", flagged_count, delta=-flagged_count if flagged_count > 0 else 0, delta_color="inverse")

st.markdown("<br>", unsafe_allow_html=True)

# Scatter Chart: Budget vs Actual with Anomalies
if not df_expenses.empty:
    fig_scatter = px.scatter(
        df_expenses,
        x="Budget ($)",
        y="Actual ($)",
        color="Anomaly?",
        color_discrete_map={"Normal": "#2563eb", "⚠️ Anomaly": "#dc2626"},
        hover_data=["Expense ID", "Category", "Vendor", "Variance ($)"],
        title="Actual Expense vs Budget Allocation (Anomalies Highlighted in Red)",
        template="plotly_white",
        height=320,
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

# Explanations for Flagged Anomalies
st.subheader("🔍 Statistical Anomaly Audit Feed")
st.info("⚠️ **Note**: Detected records are statistical anomalies requiring operational review; high expenditure may represent planned capacity scaling or legitimate emergencies.")

if anomalies_list:
    for exp, reasons in anomalies_list:
        with st.container():
            st.markdown(
                f"""
                <div style="background: #fff; border-left: 5px solid #dc2626; border-radius: 6px; padding: 14px 18px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h4 style="margin: 0; color: #0f172a;">{exp.expense_category}: {exp.vendor} (<code>{exp.expense_id}</code>)</h4>
                        <span style="background: #fee2e2; color: #b91c1c; font-weight: 700; padding: 4px 10px; border-radius: 4px; font-size: 13px;">
                            ${exp.actual_amount:,.2f} (Budget: ${exp.budgeted_amount:,.2f})
                        </span>
                    </div>
                    <p style="margin: 6px 0 8px 0; color: #475569; font-size: 14px;"><strong>Department:</strong> {exp.department.name if exp.department else 'General'} &bull; <strong>Date:</strong> {exp.date} &bull; <strong>Description:</strong> {exp.description or 'N/A'}</p>
                    <div style="background: #f8fafc; border-radius: 4px; padding: 8px 12px; font-size: 13px; color: #334155; border: 1px solid #e2e8f0;">
                        {'<br>'.join(['&bull; ' + r for r in reasons])}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
else:
    st.success("No cost anomalies detected under current sensitivity thresholds.")

st.markdown("<br>", unsafe_allow_html=True)
st.subheader("📋 Complete Expenses Ledger")
st.dataframe(df_expenses, use_container_width=True, hide_index=True)

# Export
today = date.today()
csv_bytes = df_expenses.to_csv(index=False).encode("utf-8")
st.download_button(
    label="📥 Export Expense Records (CSV)",
    data=csv_bytes,
    file_name=f"expenses_export_{today.isoformat()}.csv",
    mime="text/csv",
)
