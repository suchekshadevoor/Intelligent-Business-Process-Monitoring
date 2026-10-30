"""
Transactions Monitoring Page: Payment gateways, failure rate spike detection, and error categorization.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from sqlalchemy.orm import joinedload
from database.connection import get_db
from database.schema import Transaction
from ui_common import apply_theme, require_auth

st.set_page_config(page_title="Transactions Monitor", page_icon="💳", layout="wide")
apply_theme()
require_auth()

st.title("💳 Financial Transactions & Gateway Reliability")
st.markdown("Monitor transaction processing rates, detect gateway outage spikes, and analyze error root categories.")

with get_db() as db:
    txns = (
        db.query(Transaction)
        .options(joinedload(Transaction.department))
        .order_by(Transaction.transaction_timestamp.desc())
        .all()
    )

# Filters
col1, col2, col3 = st.columns(3)
with col1:
    selected_status = st.selectbox("Status", options=["All", "Success", "Failed", "Pending"])
with col2:
    pm_options = ["All"] + sorted(list(set(t.payment_method for t in txns)))
    selected_pm = st.selectbox("Payment Method", options=pm_options)
with col3:
    err_options = ["All"] + sorted(list(set(t.error_category for t in txns if t.error_category != "None")))
    selected_err = st.selectbox("Error Category", options=err_options)

filtered_txns = []
for t in txns:
    if selected_status != "All" and t.status != selected_status:
        continue
    if selected_pm != "All" and t.payment_method != selected_pm:
        continue
    if selected_err != "All" and t.error_category != selected_err:
        continue

    filtered_txns.append({
        "Transaction ID": t.transaction_id,
        "Timestamp": t.transaction_timestamp.strftime("%Y-%m-%d %H:%M"),
        "Type": t.transaction_type,
        "Amount ($)": t.amount,
        "Status": t.status,
        "Payment Method": t.payment_method,
        "Error Category": t.error_category if t.error_category != "None" else "-",
        "Department": t.department.name if t.department else "General",
    })

df_txns = pd.DataFrame(filtered_txns)

# Metrics
total_tx = len(df_txns)
failed_tx = sum(1 for r in filtered_txns if r["Status"] == "Failed")
fail_rate = (failed_tx / total_tx * 100) if total_tx > 0 else 0
total_amt = sum(r["Amount ($)"] for r in filtered_txns)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Transactions Listed", total_tx)
m2.metric("Failed Transactions", failed_tx, delta=-failed_tx if failed_tx > 0 else 0, delta_color="inverse")
m3.metric("Failure Rate", f"{fail_rate:.1f}%")
m4.metric("Total Processed Volume", f"${total_amt:,.2f}")

st.markdown("<br>", unsafe_allow_html=True)

if not df_txns.empty:
    # Charts Row
    c_chart1, c_chart2 = st.columns(2)
    with c_chart1:
        # Errors Pareto
        failed_df = df_txns[df_txns["Status"] == "Failed"]
        if not failed_df.empty:
            err_counts = failed_df["Error Category"].value_counts().reset_index()
            err_counts.columns = ["Error Category", "Count"]
            fig_err = px.bar(
                err_counts,
                x="Error Category",
                y="Count",
                title="Primary Failure Categories",
                color="Count",
                color_continuous_scale="Reds",
                template="plotly_white",
                height=280,
            )
            st.plotly_chart(fig_err, use_container_width=True)
        else:
            st.success("Zero failures in the selected subset.")

    with c_chart2:
        # Failure by payment method
        pm_stats = df_txns.groupby("Payment Method")["Status"].apply(lambda s: (s == "Failed").mean() * 100).reset_index()
        pm_stats.columns = ["Payment Method", "Failure Rate (%)"]
        fig_pm = px.bar(
            pm_stats,
            x="Payment Method",
            y="Failure Rate (%)",
            title="Failure Rate by Payment Method (%)",
            color="Failure Rate (%)",
            color_continuous_scale="Blues",
            template="plotly_white",
            height=280,
        )
        st.plotly_chart(fig_pm, use_container_width=True)

    st.dataframe(df_txns, use_container_width=True, hide_index=True)

    # Export
    today = date.today()
    csv_bytes = df_txns.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Export Transactions to CSV",
        data=csv_bytes,
        file_name=f"transactions_export_{today.isoformat()}.csv",
        mime="text/csv",
    )
else:
    st.info("No transactions match the selected criteria.")
