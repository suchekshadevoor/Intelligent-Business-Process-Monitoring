"""
User Management and Role-Based Access Control Console (Admin Only).
"""

import streamlit as st
import pandas as pd
from database.connection import get_db
from database.schema import User, AuditLog
from services.auth_service import AuthService, PERMISSIONS
from ui_common import apply_theme, require_auth

st.set_page_config(page_title="User Management", page_icon="👤", layout="wide")
apply_theme()

# Enforce Admin authentication
current_user = require_auth(allowed_roles=["admin"])

st.title("👤 User Management & Role-Based Permissions (RBAC)")
st.markdown("Provision operator accounts, configure role permissions, and manage active system credentials.")

tab_users, tab_create, tab_roles = st.tabs(["👥 Registered Users", "➕ Provision New User", "🛡️ RBAC Permissions Matrix"])

with tab_users:
    with get_db() as db:
        users = AuthService.list_users(db)

    if users:
        df_users = pd.DataFrame(users)
        st.dataframe(df_users, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("Manage User Account")
        user_options = {u["id"]: f"{u['username']} ({u['email']}) - Role: {u['role'].upper()}" for u in users}

        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            target_user_id = st.selectbox("Select User", options=list(user_options.keys()), format_func=lambda x: user_options[x])
        with c2:
            new_role = st.selectbox("Change Role", options=list(PERMISSIONS.keys()), format_func=lambda x: x.capitalize())
            if st.button("Update Role", use_container_width=True):
                with get_db() as db:
                    res = AuthService.update_user_role(db, target_user_id, new_role, updated_by=current_user["username"])
                    if res["success"]:
                        st.success(f"Updated role to {new_role}!")
                        st.rerun()
                    else:
                        st.error(res["error"])
        with c3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Toggle Active / Deactivate", use_container_width=True):
                with get_db() as db:
                    res = AuthService.toggle_user_active(db, target_user_id, updated_by=current_user["username"])
                    if res["success"]:
                        st.success(f"User active status toggled to {res['user']['is_active']}")
                        st.rerun()

with tab_create:
    st.subheader("Provision New Operator Account")
    with st.form("create_user_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_username = st.text_input("Username", placeholder="e.g. john_doe")
            new_email = st.text_input("Email Address", placeholder="e.g. john@businessmonitor.local")
        with col2:
            new_password = st.text_input("Password", type="password", placeholder="Strong password (min 6 chars)")
            new_user_role = st.selectbox("Assign Role", options=["analyst", "manager", "admin"], format_func=lambda x: x.capitalize())

        submit_user = st.form_submit_button("Create User Account 🚀", use_container_width=True)
        if submit_user:
            if not new_username or not new_email or not new_password:
                st.error("All fields are required.")
            elif len(new_password) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                with get_db() as db:
                    res = AuthService.create_user(
                        db=db,
                        username=new_username,
                        email=new_email,
                        password=new_password,
                        role=new_user_role,
                        created_by=current_user["username"],
                    )
                    if res["success"]:
                        st.success(f"User '{new_username}' successfully provisioned with role '{new_user_role}'.")
                        st.rerun()
                    else:
                        st.error(res["error"])

with tab_roles:
    st.subheader("System Role Permission Matrix")
    matrix = [
        {"Feature / Action": "View Executive Dashboard & Charts", "Admin": "✅", "Manager": "✅", "Analyst": "✅"},
        {"Feature / Action": "View Reports & Export CSVs", "Admin": "✅", "Manager": "✅", "Analyst": "✅"},
        {"Feature / Action": "Import Records via CSV", "Admin": "✅", "Manager": "✅", "Analyst": "✅"},
        {"Feature / Action": "Create Tasks & Orders", "Admin": "✅", "Manager": "✅", "Analyst": "❌"},
        {"Feature / Action": "Run Monitoring Checks", "Admin": "✅", "Manager": "✅", "Analyst": "❌"},
        {"Feature / Action": "Acknowledge / Assign Alerts", "Admin": "✅", "Manager": "✅", "Analyst": "❌"},
        {"Feature / Action": "Resolve Operational Incidents", "Admin": "✅", "Manager": "✅", "Analyst": "❌"},
        {"Feature / Action": "Modify Monitoring Thresholds", "Admin": "✅", "Manager": "✅", "Analyst": "❌"},
        {"Feature / Action": "User Provisioning & Role Management", "Admin": "✅", "Manager": "❌", "Analyst": "❌"},
    ]
    st.dataframe(pd.DataFrame(matrix), use_container_width=True, hide_index=True)
