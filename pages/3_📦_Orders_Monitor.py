"""
Orders Monitoring Page: Customer order fulfillment, delivery delay detection, and SLA tracking.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from database.connection import get_db
from database.schema import Order, Department
from ui_common import apply_theme, require_auth

st.set_page_config(page_title="Orders Monitor", page_icon="📦", layout="wide")
apply_theme()
current_user = require_auth()

st.title("📦 Customer Orders & Delivery SLA Monitor")
st.markdown("Monitor order fulfillment, detect delivery delays, and calculate supplier and logistics SLA variances.")

with get_db() as db:
    orders = db.query(Order).all()
    departments = db.query(Department).all()

dept_map = {0: "All Departments"}
for d in departments:
    dept_map[d.id] = f"{d.code} - {d.name}"

if current_user["role"] in ("admin", "manager"):
    with st.expander("Order Actions", expanded=False):
        create_tab, update_tab = st.tabs(["Create Order", "Update Order Status"])
        with create_tab:
            with st.form("create_order_form"):
                col_id, col_customer = st.columns(2)
                order_id = col_id.text_input("Order ID")
                customer_name = col_customer.text_input("Customer")
                col_dates, col_department = st.columns(2)
                order_date = col_dates.date_input("Order Date", value=date.today())
                expected_date = col_dates.date_input("Expected Delivery", value=date.today())
                department_id = col_department.selectbox(
                    "Department",
                    options=list(dept_map),
                    format_func=lambda value: dept_map[value],
                )
                order_value = st.number_input("Order Value", min_value=0.0, value=0.0, step=100.0)
                order_status = st.selectbox("Initial Status", ["Pending", "Processing", "Shipped"])
                submitted = st.form_submit_button("Create Order", type="primary")
                if submitted:
                    if not order_id.strip() or not customer_name.strip():
                        st.error("Order ID and customer are required.")
                    elif expected_date < order_date:
                        st.error("Expected delivery cannot be earlier than the order date.")
                    else:
                        with get_db() as db:
                            exists = db.query(Order.id).filter(Order.order_id == order_id.strip()).first()
                            if exists:
                                st.error("That order ID already exists.")
                            else:
                                db.add(Order(
                                    order_id=order_id.strip(),
                                    customer_name=customer_name.strip(),
                                    department_id=department_id or None,
                                    order_date=order_date,
                                    expected_delivery_date=expected_date,
                                    order_value=order_value,
                                    order_status=order_status,
                                    is_synthetic=False,
                                ))
                        if not exists:
                            st.success("Order created.")
                            st.rerun()
        with update_tab:
            if orders:
                order_labels = {order.order_id: f"{order.order_id} - {order.customer_name}" for order in orders}
                with st.form("update_order_status_form"):
                    selected_order_id = st.selectbox(
                        "Order", options=list(order_labels), format_func=lambda value: order_labels[value]
                    )
                    new_order_status = st.selectbox(
                        "Status", ["Pending", "Processing", "Shipped", "Delivered", "Cancelled"]
                    )
                    delivered_today = st.checkbox("Record delivery today")
                    update_submitted = st.form_submit_button("Save Order Status")
                    if update_submitted:
                        with get_db() as db:
                            order_to_update = db.query(Order).filter(Order.order_id == selected_order_id).one()
                            order_to_update.order_status = new_order_status
                            if new_order_status == "Delivered" and delivered_today:
                                order_to_update.actual_delivery_date = date.today()
                            elif new_order_status in ("Pending", "Processing", "Shipped", "Cancelled"):
                                order_to_update.actual_delivery_date = None
                        st.success("Order status updated.")
                        st.rerun()
            else:
                st.info("Create or import an order before updating its status.")

# Filters
f1, f2, f3 = st.columns(3)
with f1:
    selected_dept = st.selectbox("Department", options=list(dept_map.keys()), format_func=lambda x: dept_map[x])
with f2:
    selected_status = st.selectbox("Order Status", options=["All", "Pending", "Processing", "Shipped", "Delivered", "Cancelled"])
with f3:
    delayed_only = st.checkbox("Show Delayed Orders Only", value=False)

today = date.today()
order_rows = []

for o in orders:
    if selected_dept > 0 and o.department_id != selected_dept:
        continue
    if selected_status != "All" and o.order_status != selected_status:
        continue

    is_delayed = False
    delay_days = 0
    if o.actual_delivery_date and o.actual_delivery_date > o.expected_delivery_date:
        is_delayed = True
        delay_days = (o.actual_delivery_date - o.expected_delivery_date).days
    elif not o.actual_delivery_date and o.order_status not in ("Delivered", "Cancelled") and o.expected_delivery_date < today:
        is_delayed = True
        delay_days = (today - o.expected_delivery_date).days

    if delayed_only and not is_delayed:
        continue

    order_rows.append({
        "Order ID": o.order_id,
        "Customer": o.customer_name,
        "Order Date": o.order_date.isoformat(),
        "Expected Delivery": o.expected_delivery_date.isoformat(),
        "Actual Delivery": o.actual_delivery_date.isoformat() if o.actual_delivery_date else "-",
        "Status": o.order_status,
        "Order Value ($)": o.order_value,
        "Delay (Days)": delay_days if is_delayed else 0,
        "Delayed?": "⚠️ Yes" if is_delayed else "On Time",
    })

df_orders = pd.DataFrame(order_rows)

# Top Metrics Row
m1, m2, m3, m4 = st.columns(4)
total_count = len(df_orders)
delayed_count = sum(1 for r in order_rows if r["Delayed?"] == "⚠️ Yes")
delay_rate = (delayed_count / total_count * 100) if total_count > 0 else 0
total_val = sum(r["Order Value ($)"] for r in order_rows)

m1.metric("Orders Listed", total_count)
m2.metric("Delayed Orders", delayed_count, delta=-delayed_count if delayed_count > 0 else 0, delta_color="inverse")
m3.metric("Delay Rate", f"{delay_rate:.1f}%")
m4.metric("Total Order Value", f"${total_val:,.2f}")

st.markdown("<br>", unsafe_allow_html=True)

if not df_orders.empty:
    # Chart: Delays distribution
    if delayed_count > 0:
        delayed_df = df_orders[df_orders["Delay (Days)"] > 0]
        fig_delays = px.bar(
            delayed_df,
            x="Order ID",
            y="Delay (Days)",
            color="Customer",
            title="Days Delayed per Overdue Order",
            template="plotly_white",
            height=280,
        )
        st.plotly_chart(fig_delays, use_container_width=True)

    st.dataframe(df_orders, use_container_width=True, hide_index=True)

    # Export Button
    csv_bytes = df_orders.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Export Orders to CSV",
        data=csv_bytes,
        file_name=f"orders_export_{today.isoformat()}.csv",
        mime="text/csv",
    )
else:
    st.info("No orders found matching the filter criteria.")
