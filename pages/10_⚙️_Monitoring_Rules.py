"""
Monitoring Rules Configuration Page:
Dynamically manage the 7 monitoring rules, tune threshold parameters, toggle rule states,
and trigger immediate rule evaluations.
"""

import json
import streamlit as st
import pandas as pd
from database.connection import get_db
from database.schema import MonitoringRule
from services.monitoring_service import MonitoringService
from config.settings import SEVERITIES, CATEGORIES
from ui_common import apply_theme, require_auth

st.set_page_config(page_title="Monitoring Rules", page_icon="⚙️", layout="wide")
apply_theme()
require_auth(allowed_roles=["admin", "manager"])

st.title("⚙️ Monitoring Rules & Threshold Configuration")
st.markdown(
    "Configure operational monitoring rules, adjust sensitivity thresholds, enable/disable automated detectors, "
    "and inspect rule evaluation timestamps."
)

col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.caption("All thresholds are evaluated dynamically from database records. Changes take effect on the next monitoring cycle.")
with col_h2:
    if st.button("🔄 Evaluate All Rules Now", use_container_width=True, type="primary"):
        with get_db() as db:
            res = MonitoringService.evaluate_all_rules(db)
            st.success(f"Evaluated {res['evaluated_rules']} rule(s)! Created: {res['new_alerts_created']}, Refreshed: {res['existing_alerts_refreshed']}")
            st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

with get_db() as db:
    rules = db.query(MonitoringRule).all()

if not rules:
    st.warning("No monitoring rules defined in database.")
else:
    for rule in rules:
        with st.expander(f"{'🟢' if rule.is_enabled else '⚪'} [{rule.severity}] {rule.rule_name} (`{rule.rule_code}`)", expanded=False):
            col_r1, col_r2 = st.columns([3, 2])

            with col_r1:
                st.markdown(f"**Description:** {rule.description}")
                st.markdown(f"**Category:** `{rule.category}`")
                st.markdown(f"**Last Evaluated:** {rule.last_evaluated_at.strftime('%Y-%m-%d %H:%M:%S UTC') if rule.last_evaluated_at else 'Never'}")

                # JSON config editor
                current_cfg = rule.threshold_config or "{}"
                st.markdown("**Threshold Configuration (JSON):**")
                cfg_input = st.text_area(
                    "Parameters",
                    value=current_cfg,
                    key=f"cfg_{rule.id}",
                    height=100,
                    label_visibility="collapsed",
                )

            with col_r2:
                st.markdown("##### Rule Controls")
                is_active = st.toggle("Rule Active", value=rule.is_enabled, key=f"toggle_{rule.id}")
                
                new_sev = st.selectbox(
                    "Severity Level",
                    options=SEVERITIES,
                    index=SEVERITIES.index(rule.severity) if rule.severity in SEVERITIES else 1,
                    key=f"sev_{rule.id}",
                )

                new_window = st.number_input(
                    "Evaluation Window (Days)",
                    min_value=1,
                    max_value=90,
                    value=rule.evaluation_window_days or 7,
                    key=f"win_{rule.id}",
                )

                if st.button("Save Rule Changes", key=f"save_{rule.id}"):
                    try:
                        # Validate JSON
                        json.loads(cfg_input)
                        with get_db() as db:
                            r_db = db.query(MonitoringRule).filter(MonitoringRule.id == rule.id).first()
                            if r_db:
                                r_db.is_enabled = is_active
                                r_db.severity = new_sev
                                r_db.evaluation_window_days = new_window
                                r_db.threshold_config = cfg_input
                                db.commit()
                                st.success("Rule settings updated successfully.")
                                st.rerun()
                    except json.JSONDecodeError as je:
                        st.error(f"Invalid JSON format: {je}")
