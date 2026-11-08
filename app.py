
import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(
    page_title="Data Cleaner Agent",
    page_icon="🧹",
    layout="wide"
)


# Convert mixed text/date values for display only.
# This does not change the actual dataset used for cleaning.
def safe_preview_frame(df, rows=100):
    preview = df.head(rows).copy()

    for column in preview.columns:
        if preview[column].dtype == "object":
            preview[column] = preview[column].map(
                lambda value: str(value) if pd.notna(value) else None
            )

    return preview


@st.cache_data
def load_data(file_bytes, file_name):
    if file_name.lower().endswith(".csv"):
        return pd.read_csv(BytesIO(file_bytes))

    return pd.read_excel(BytesIO(file_bytes))


def make_profile(df):
    return pd.DataFrame({
        "Column": df.columns.astype(str),
        "Data Type": [str(dtype) for dtype in df.dtypes],
        "Missing Values": df.isna().sum().values,
        "Missing Percentage": (
            df.isna().mean().values * 100
        ).round(2),
        "Unique Values": df.nunique().values
    })


def make_excel(data, profile, summary):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        data.to_excel(
            writer, sheet_name="Cleaned_Data", index=False
        )
        profile.to_excel(
            writer, sheet_name="Data_Quality_Profile", index=False
        )
        summary.to_excel(
            writer, sheet_name="Cleaning_Summary", index=False
        )

    return output.getvalue()


st.title("🧹 Data Cleaner Agent")
st.write(
    "Upload your dataset, identify data quality issues, "
    "clean your data, and download the results."
)
st.divider()

uploaded_file = st.file_uploader(
    "Upload CSV or Excel file",
    type=["csv", "xlsx"]
)


if uploaded_file is not None:
    try:
        file_bytes = uploaded_file.getvalue()
        data = load_data(
            file_bytes, uploaded_file.name
        ).copy()

    except Exception as error:
        st.error(f"Could not read the file: {error}")
        st.stop()

    if data.empty:
        st.warning("The uploaded dataset has no rows.")
        st.stop()

    # Reset old cleaning results when a new file is uploaded.
    current_file_key = (
        f"{uploaded_file.name}:{len(file_bytes)}"
    )

    if st.session_state.get("current_file_key") != current_file_key:
        for key in [
            "cleaned_data",
            "cleaned_profile",
            "cleaning_summary",
            "cleaning_log",
            "outlier_results"
        ]:
            st.session_state.pop(key, None)

        st.session_state["current_file_key"] = current_file_key

    st.subheader("1. Original Dataset Overview")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Rows", f"{len(data):,}")
    col2.metric("Total Columns", f"{len(data.columns):,}")
    col3.metric(
        "Missing Cells",
        f"{int(data.isna().sum().sum()):,}"
    )
    col4.metric(
        "Duplicate Rows",
        f"{int(data.duplicated().sum()):,}"
    )

    with st.expander("Preview Original Dataset"):
        st.dataframe(
            safe_preview_frame(data),
            use_container_width=True
        )

    st.subheader("2. Data Quality Profile")

    profile = make_profile(data)

    st.dataframe(
        profile,
        use_container_width=True
    )

    st.subheader("3. Cleaning Options")

    missing_method = st.selectbox(
        "How should missing values be handled?",
        [
            "Keep unchanged",
            "Remove rows with missing values",
            "Fill numeric columns with mean",
            "Fill numeric columns with median",
            "Fill columns with mode"
        ]
    )

    remove_duplicates = st.checkbox(
        "Remove duplicate rows",
        value=True
    )

    detect_outliers = st.checkbox(
        "Detect numeric outliers using IQR",
        value=True
    )

    st.caption(
        "Outlier detection only reports potential outliers. "
        "It does not delete them."
    )

    if st.button("✨ Clean My Dataset", type="primary"):

        cleaned = data.copy()
        cleaning_log = []

        missing_before = int(
            cleaned.isna().sum().sum()
        )
        duplicates_before = int(
            cleaned.duplicated().sum()
        )

        # Handle missing values.
        if missing_method == "Remove rows with missing values":
            rows_before = len(cleaned)
            cleaned = cleaned.dropna()

            cleaning_log.append({
                "Action": "Remove rows with missing values",
                "Details": (
                    f"{rows_before - len(cleaned)} rows removed"
                )
            })

        elif missing_method == "Fill numeric columns with mean":
            filled = 0

            for column in cleaned.select_dtypes(
                include="number"
            ).columns:
                if cleaned[column].isna().any():
                    value = cleaned[column].mean()

                    if pd.notna(value):
                        cleaned[column] = cleaned[column].fillna(value)
                        filled += 1

            cleaning_log.append({
                "Action": "Fill numeric missing values with mean",
                "Details": f"Applied to {filled} numeric columns"
            })

        elif missing_method == "Fill numeric columns with median":
            filled = 0

            for column in cleaned.select_dtypes(
                include="number"
            ).columns:
                if cleaned[column].isna().any():
                    value = cleaned[column].median()

                    if pd.notna(value):
                        cleaned[column] = cleaned[column].fillna(value)
                        filled += 1

            cleaning_log.append({
                "Action": "Fill numeric missing values with median",
                "Details": f"Applied to {filled} numeric columns"
            })

        elif missing_method == "Fill columns with mode":
            filled = 0

            for column in cleaned.columns:
                modes = cleaned[column].mode(dropna=True)

                if cleaned[column].isna().any() and not modes.empty:
                    cleaned[column] = cleaned[column].fillna(
                        modes.iloc[0]
                    )
                    filled += 1

            cleaning_log.append({
                "Action": "Fill missing values with mode",
                "Details": (
                    f"Applied to {filled} columns where possible"
                )
            })

        else:
            cleaning_log.append({
                "Action": "Missing values",
                "Details": "Kept unchanged as requested"
            })

        # Remove duplicate rows if selected.
        if remove_duplicates:
            removed = int(cleaned.duplicated().sum())
            cleaned = cleaned.drop_duplicates()

            cleaning_log.append({
                "Action": "Remove duplicate rows",
                "Details": f"{removed} duplicate rows removed"
            })

        else:
            cleaning_log.append({
                "Action": "Remove duplicate rows",
                "Details": "Skipped"
            })

        # Detect numeric outliers using the IQR method.
        outlier_results = []

        if detect_outliers:
            numeric_columns = cleaned.select_dtypes(
                include="number"
            ).columns

            for column in numeric_columns:
                series = cleaned[column].dropna()

                if len(series) < 4 or series.nunique() < 2:
                    continue

                q1 = series.quantile(0.25)
                q3 = series.quantile(0.75)
                iqr = q3 - q1

                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr

                count = int(
                    (
                        (series < lower_bound)
                        | (series > upper_bound)
                    ).sum()
                )

                outlier_results.append({
                    "Column": str(column),
                    "Potential Outliers": count,
                    "Lower Bound": lower_bound,
                    "Upper Bound": upper_bound
                })

        # Create the cleaned data profile.
        cleaned_profile = make_profile(cleaned)

        missing_after = int(
            cleaned.isna().sum().sum()
        )
        duplicates_after = int(
            cleaned.duplicated().sum()
        )

        summary = pd.DataFrame([
            {"Metric": "Original Rows", "Value": len(data)},
            {"Metric": "Final Rows", "Value": len(cleaned)},
            {"Metric": "Original Columns", "Value": len(data.columns)},
            {"Metric": "Final Columns", "Value": len(cleaned.columns)},
            {"Metric": "Missing Cells Before", "Value": missing_before},
            {"Metric": "Missing Cells After", "Value": missing_after},
            {"Metric": "Duplicate Rows Before", "Value": duplicates_before},
            {"Metric": "Duplicate Rows After", "Value": duplicates_after},
            {
                "Metric": "Rows Removed Overall",
                "Value": len(data) - len(cleaned)
            }
        ])

        # Store results for display and download.
        st.session_state["cleaned_data"] = cleaned
        st.session_state["cleaned_profile"] = cleaned_profile
        st.session_state["cleaning_summary"] = summary
        st.session_state["cleaning_log"] = cleaning_log
        st.session_state["outlier_results"] = outlier_results

    # Display cleaning results.
    if "cleaned_data" in st.session_state:

        cleaned = st.session_state["cleaned_data"]

        st.divider()
        st.subheader("4. Cleaning Results")

        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Rows Before", f"{len(data):,}")
        col2.metric("Rows After", f"{len(cleaned):,}")
        col3.metric(
            "Missing Cells Left",
            f"{int(cleaned.isna().sum().sum()):,}"
        )
        col4.metric(
            "Duplicate Rows Left",
            f"{int(cleaned.duplicated().sum()):,}"
        )

        st.write("**Cleaning actions performed**")

        for item in st.session_state["cleaning_log"]:
            st.write(
                f"- {item['Action']}: {item['Details']}"
            )

        if st.session_state["outlier_results"]:
            st.subheader("5. Potential Outlier Report")

            outlier_df = pd.DataFrame(
                st.session_state["outlier_results"]
            )

            st.dataframe(
                outlier_df,
                use_container_width=True
            )

        with st.expander("Preview Cleaned Dataset"):
            st.dataframe(
                safe_preview_frame(cleaned),
                use_container_width=True
            )

        # Download cleaned data as CSV.
        csv_bytes = cleaned.to_csv(
            index=False
        ).encode("utf-8-sig")

        st.download_button(
            "⬇️ Download Cleaned CSV",
            data=csv_bytes,
            file_name="cleaned_data.csv",
            mime="text/csv"
        )

        # Download Excel report with three sheets.
        excel_bytes = make_excel(
            cleaned,
            st.session_state["cleaned_profile"],
            st.session_state["cleaning_summary"]
        )

        st.download_button(
            "⬇️ Download Excel Report",
            data=excel_bytes,
            file_name="data_cleaning_report.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            )
        )

else:
    st.info("Upload a CSV or Excel dataset to get started.")
