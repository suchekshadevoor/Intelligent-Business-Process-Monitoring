"""
Common UI components, styling, session helpers, and authentication gatekeeper for the Streamlit dashboard.
"""

import streamlit as st
from datetime import date, timedelta
from config.settings import settings
from database.connection import get_db, init_db
from database.schema import Department, User

# Custom CSS for polished, modern executive dashboard
CUSTOM_CSS = """
<style>
    /* Global layout & typography */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        padding-left: 2rem;
        padding-right: 2rem;
    }
    h1, h2, h3 {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        color: #0f172a;
        font-weight: 700;
    }
    
    /* Modern KPI metric card */
    .kpi-container {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 18px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        margin-bottom: 1rem;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .kpi-container:hover {
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.08);
    }
    .kpi-label {
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #64748b;
        margin-bottom: 4px;
    }
    .kpi-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #0f172a;
        line-height: 1.2;
    }
    .kpi-subtext {
        font-size: 0.8rem;
        margin-top: 6px;
        font-weight: 500;
    }
    .text-success { color: #16a34a; }
    .text-danger { color: #dc2626; }
    .text-warning { color: #ea580c; }
    .text-info { color: #2563eb; }

    /* Custom badges */
    .badge-critical { background: #fee2e2; color: #b91c1c; font-weight: 600; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }
    .badge-high { background: #ffedd5; color: #c2410c; font-weight: 600; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }
    .badge-medium { background: #fef9c3; color: #a16207; font-weight: 600; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }
    .badge-low { background: #f1f5f9; color: #475569; font-weight: 600; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }

    /* Streamlit tabs and cards adjustments */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding-top: 8px;
        padding-bottom: 8px;
        border-radius: 6px;
    }
</style>
"""


def apply_theme():
    """Apply CSS styles and header."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def get_db_session():
    """Yield database session safely for Streamlit pages."""
    return get_db()


def require_auth(allowed_roles=None):
    """
    Ensure user is authenticated.
    If not, renders a modern login box and stops page rendering until authenticated.
    Also renders current user role badge and Logout button in sidebar.
    """
    apply_theme()
    init_db()
    if not st.session_state.get("_bpm_initialized"):
        if settings.SEED_DEMO_DATA:
            from database.seed_data import seed_all
            with get_db() as db:
                seed_all(db)
        st.session_state["_bpm_initialized"] = True

    user = st.session_state.get("authenticated_user")
    if user:
        with get_db() as db:
            active_user = db.query(User).filter(User.id == user.get("id"), User.is_active.is_(True)).first()
            user = active_user.to_dict() if active_user else None
        st.session_state["authenticated_user"] = user

    if not user:
        st.markdown(
            """
            <div style="max-width: 480px; margin: 30px auto; background: #ffffff; padding: 28px; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.06);">
                <h2 style="margin-top: 0; color: #0f172a; text-align: center;">🔐 System Authentication</h2>
                <p style="color: #64748b; font-size: 14px; text-align: center; margin-bottom: 20px;">Please sign in to access the Business Process Monitor.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form"):
            username = st.text_input("Username or Email", placeholder="e.g. admin, manager, or analyst")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            submitted = st.form_submit_button("Sign In 🚀", use_container_width=True)

            if submitted:
                if not username or not password:
                    st.error("Please enter both username and password.")
                else:
                    from services.auth_service import AuthService
                    with get_db() as db:
                        auth_user = AuthService.authenticate_user(db, username, password)
                        if auth_user:
                            st.session_state["authenticated_user"] = auth_user.to_dict()
                            st.success(f"Welcome, {auth_user.username}!")
                            st.rerun()
                        else:
                            st.error("Invalid username or password.")

        if settings.SEED_DEMO_DATA:
            st.info("💡 **Demo Credentials**:\n- **Administrator**: `admin` / `Admin@123`\n- **Operations Manager**: `manager` / `Manager@123`\n- **Business Analyst**: `analyst` / `Analyst@123`")
        st.stop()

    # User is logged in
    # Sidebar User Profile & Logout
    st.sidebar.markdown(f"**Logged in as:** `{user['username']}`")
    role_badge = "#fee2e2" if user["role"] == "admin" else "#ffedd5" if user["role"] == "manager" else "#dbeafe"
    role_color = "#b91c1c" if user["role"] == "admin" else "#c2410c" if user["role"] == "manager" else "#1e40af"
    st.sidebar.markdown(
        f'<span style="background: {role_badge}; color: {role_color}; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 700;">Role: {user["role"].upper()}</span>',
        unsafe_allow_html=True,
    )

    if st.sidebar.button("🚪 Sign Out", key="btn_signout"):
        st.session_state["authenticated_user"] = None
        st.rerun()

    # Role guard check
    if allowed_roles and user["role"] not in allowed_roles:
        st.error(f"⛔ Access Denied. Your role ('{user['role']}') does not have permission to view this page. Requires: {', '.join(allowed_roles)}.")
        st.stop()

    return user


def render_sidebar_filters():
    """Render common sidebar filters (Department, Date Range)."""
    with get_db() as db:
        departments = db.query(Department).all()
        dept_options = {0: "All Departments"}
        for d in departments:
            dept_options[d.id] = f"{d.code} - {d.name}"

    st.sidebar.markdown("### 🔍 Filters")
    selected_dept_id = st.sidebar.selectbox(
        "Department",
        options=list(dept_options.keys()),
        format_func=lambda x: dept_options[x],
        index=0,
    )

    date_filter = st.sidebar.selectbox(
        "Time Horizon",
        options=["Last 30 Days", "Last 14 Days", "Last 7 Days", "All Time"],
        index=0,
    )

    today = date.today()
    if date_filter == "Last 7 Days":
        start_date = today - timedelta(days=7)
    elif date_filter == "Last 14 Days":
        start_date = today - timedelta(days=14)
    elif date_filter == "Last 30 Days":
        start_date = today - timedelta(days=30)
    else:
        start_date = None

    return selected_dept_id, start_date, today
