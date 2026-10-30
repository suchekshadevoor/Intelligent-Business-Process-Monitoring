"""
Automation, Background Scheduler, and Email Settings Page:
Manage recurring APScheduler jobs, test SMTP notifications (or observe Simulated Demo Mode),
and review system audit logs.
"""

import streamlit as st
import pandas as pd
from datetime import date
from database.connection import get_db
from database.schema import AuditLog, Alert
from jobs.scheduler import scheduler_service
from services.email_service import EmailService
from config.settings import settings
from ui_common import apply_theme, require_auth

st.set_page_config(page_title="Automation & Settings", page_icon="⏱️", layout="wide")
apply_theme()
require_auth(allowed_roles=["admin"])

st.title("⏱️ Automation, Notifications & System Settings")
st.markdown("Control background recurring schedulers, configure notification delivery modes, and inspect enterprise audit logs.")

tab_sched, tab_email, tab_audit = st.tabs(["⏱️ Background Scheduler", "📧 Email Notification Settings", "📜 Enterprise Audit Logs"])

# Tab 1: Background Scheduler
with tab_sched:
    st.subheader("Background Monitoring Scheduler (APScheduler)")
    sched_status = scheduler_service.get_status()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Scheduler Status", "🟢 Active" if sched_status["is_running"] else "⚪ Stopped")
    c2.metric("Interval (Minutes)", sched_status["interval_minutes"])
    c3.metric("Last Run Status", sched_status["last_run_status"] or "None")
    c4.metric("Last Run Time", sched_status["last_run_time"] or "Never")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("##### Scheduler Lifecycle Controls")

    col_btn1, col_btn2, col_btn3, col_int = st.columns([1, 1, 1, 2])
    with col_int:
        new_interval = st.number_input("Interval (Minutes)", min_value=1, max_value=1440, value=sched_status["interval_minutes"])

    with col_btn1:
        if st.button("▶️ Start Scheduler", disabled=sched_status["is_running"], use_container_width=True):
            res = scheduler_service.start(interval_minutes=new_interval)
            st.success(res["message"])
            st.rerun()

    with col_btn2:
        if st.button("⏹️ Stop Scheduler", disabled=not sched_status["is_running"], use_container_width=True):
            res = scheduler_service.stop()
            st.warning(res["message"])
            st.rerun()

    with col_btn3:
        if st.button("⚡ Run Job Now", use_container_width=True):
            res = scheduler_service.trigger_now()
            st.info(f"Execution complete. Created: {res.get('new_alerts_created', 0)}, Refreshed: {res.get('existing_alerts_refreshed', 0)}")
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("Job Execution History")
    history = sched_status["recent_history"]
    if history:
        st.dataframe(pd.DataFrame(history), use_container_width=True, hide_index=True)
    else:
        st.caption("No scheduler jobs have executed during this application process session.")

# Tab 2: Email Notification Settings
with tab_email:
    st.subheader("Notification Configuration & Diagnostics")

    # Mode Indicator Box
    is_live = settings.is_smtp_configured and settings.ENABLE_EMAIL_ALERTS
    if is_live:
        st.success(f"🟢 **Live SMTP Mode Active**: Configured with host `{settings.SMTP_HOST}:{settings.SMTP_PORT}`.")
    else:
        st.info(
            "ℹ️ **Simulated Demo Mode Active**: External SMTP credentials not set or `ENABLE_EMAIL_ALERTS=False`. "
            "All email notifications will be formatted, verified, and safely logged without network failures."
        )

    st.markdown("##### Current Configuration (Read from `.env`)")
    col_em1, col_em2 = st.columns(2)
    with col_em1:
        st.text_input("SMTP Host", value=settings.SMTP_HOST or "(None - Demo Mode)", disabled=True)
        st.text_input("SMTP Port", value=str(settings.SMTP_PORT), disabled=True)
        st.text_input("Sender Address", value=settings.SMTP_FROM_EMAIL, disabled=True)
    with col_em2:
        st.text_input("SMTP Username", value=settings.SMTP_USERNAME or "(None - Demo Mode)", disabled=True)
        st.text_input("SMTP Password", value="••••••••" if settings.SMTP_PASSWORD else "(Not Set)", disabled=True)
        st.text_input("Default Recipient", value=settings.ALERT_RECIPIENT_EMAIL, disabled=True)

    st.markdown("---")
    st.subheader("Diagnostic Email Dispatch Verification")
    test_recip = st.text_input("Test Recipient Email", value=settings.ALERT_RECIPIENT_EMAIL)

    col_t1, col_t2 = st.columns(2)
    with col_t1:
        if st.button("🧪 Send Test Email (Diagnostic)", use_container_width=True):
            res = EmailService.test_smtp_connection(test_recipient=test_recip)
            if res["success"]:
                st.success(f"Success ({res['mode']}): {res.get('message', 'Email processed successfully.')}")
            else:
                st.warning(f"Note ({res['mode']}): {res.get('error')}")

    with col_t2:
        if st.button("🚨 Dispatch Sample Alert Notification", use_container_width=True):
            with get_db() as db:
                sample_alert = db.query(Alert).first()
            if sample_alert:
                res = EmailService.send_alert_notification(sample_alert, recipient_override=test_recip)
                if res["mode"] == "simulated_demo":
                    st.info(res["message"])
                elif res["success"]:
                    st.success(res["message"])
                else:
                    st.error(res.get("error", "Email delivery failed."))
            else:
                st.info("No alerts in database to use as sample.")

# Tab 3: Enterprise Audit Logs
with tab_audit:
    st.subheader("System State Change & Security Audit Trail")
    with get_db() as db:
        logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(100).all()

    if logs:
        log_rows = [
            {
                "Timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC") if l.timestamp else "",
                "Entity Type": l.entity_type,
                "Entity ID": l.entity_id,
                "Action": l.action,
                "Actor": l.user_or_system,
                "Details": l.details_json or "",
            }
            for l in logs
        ]
        st.dataframe(pd.DataFrame(log_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No audit logs recorded.")
