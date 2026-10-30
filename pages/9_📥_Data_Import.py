"""
Data Import & Template Management Page:
CSV file uploads, schema validation, duplicate detection, and downloadable template generator.
"""

from pathlib import Path
import streamlit as st
import pandas as pd
from database.connection import get_db
from services.data_import_service import DataImportService, REQUIRED_COLUMNS
from config.settings import SAMPLE_DATA_DIR
from ui_common import apply_theme, require_auth

st.set_page_config(page_title="Data Import", page_icon="📥", layout="wide")
apply_theme()
require_auth()

st.title("📥 Data Import & Template Management")
st.markdown(
    "Import operational records from CSV files into the relational database. "
    "The engine performs strict column validation, date parsing, and natural key duplicate prevention."
)

tab_upload, tab_templates = st.tabs(["📤 Upload Operational Records", "📄 Download CSV Templates"])

with tab_upload:
    entity_type = st.selectbox(
        "Select Entity Type to Import",
        options=["tasks", "orders", "transactions", "expenses"],
        format_func=lambda x: x.capitalize(),
    )

    st.markdown(f"**Required Columns for `{entity_type}`:** `{', '.join(REQUIRED_COLUMNS[entity_type])}`")

    uploaded_file = st.file_uploader(f"Choose a {entity_type}.csv file", type=["csv"])

    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        val_res = DataImportService.validate_and_preview(file_bytes, entity_type)

        if not val_res["valid"]:
            st.error(f"❌ Schema Validation Failed: {val_res.get('error')}")
            if "missing_columns" in val_res:
                st.warning(f"Missing: `{', '.join(val_res['missing_columns'])}`")
        else:
            st.success(f"✅ Schema Valid! Detected {val_res['total_rows']} record(s). Previewing first 5 rows below:")
            st.dataframe(pd.DataFrame(val_res["preview"]), use_container_width=True, hide_index=True)

            if st.button("🚀 Confirm & Import into Database", type="primary"):
                with st.spinner("Processing records, validating constraints, and checking duplicates..."):
                    df = val_res["df"]
                    with get_db() as db:
                        if entity_type == "tasks":
                            res = DataImportService.import_tasks(df, db)
                        elif entity_type == "orders":
                            res = DataImportService.import_orders(df, db)
                        elif entity_type == "transactions":
                            res = DataImportService.import_transactions(df, db)
                        elif entity_type == "expenses":
                            res = DataImportService.import_expenses(df, db)

                    # Display results
                    st.balloons()
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Total Rows Processed", res["total"])
                    c2.metric("Successfully Inserted", res["inserted"], delta=res["inserted"])
                    c3.metric("Duplicates Skipped", res["duplicates"], delta_color="off")
                    c4.metric("Row Errors", len(res["errors"]), delta=-len(res["errors"]) if res["errors"] else 0, delta_color="inverse")

                    if res["errors"]:
                        st.warning("⚠️ Some rows had validation errors:")
                        st.dataframe(pd.DataFrame(res["errors"]), use_container_width=True)

with tab_templates:
    st.subheader("Official CSV Templates for Data Integration")
    st.markdown("Download pre-formatted sample templates with sample values and headers:")

    template_files = {
        "Tasks Template": "tasks_sample.csv",
        "Orders Template": "orders_sample.csv",
        "Transactions Template": "transactions_sample.csv",
        "Expenses Template": "expenses_sample.csv",
    }

    cols = st.columns(4)
    for i, (name, filename) in enumerate(template_files.items()):
        fpath = SAMPLE_DATA_DIR / filename
        with cols[i]:
            st.markdown(f"**{name}**")
            if fpath.exists():
                content = fpath.read_bytes()
                st.download_button(
                    label=f"📥 Download {filename}",
                    data=content,
                    file_name=filename,
                    mime="text/csv",
                    key=f"dl_tpl_{filename}",
                )
            else:
                st.caption("Template generating...")
