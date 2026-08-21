from __future__ import annotations

from pathlib import Path
import sqlite3

import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
CSV_PATH = APP_DIR / "dashboard_metrics_history.csv"
DB_PATH = APP_DIR / "garmin_dashboard.db"
TABLE_NAME = "metrics_history"

st.set_page_config(
    page_title="Garmin Recovery Dashboard",
    page_icon=":bar_chart:",
    layout="wide",
)

st.markdown(
    """
    <style>
    .stApp {
        background: radial-gradient(circle at 20% 0%, #f2f8ff 0%, #f9fbf4 45%, #ffffff 100%);
    }
    .kpi-title {
        font-size: 0.85rem;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: #4b5a66;
        margin-bottom: 0.2rem;
    }
    .kpi-value {
        font-size: 1.7rem;
        font-weight: 700;
        color: #0f172a;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _load_from_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    return pd.read_csv(path)


def _load_from_sqlite(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {path}")
    query = f"SELECT * FROM {TABLE_NAME} ORDER BY date ASC"
    with sqlite3.connect(path) as conn:
        return pd.read_sql_query(query, conn)


@st.cache_data(show_spinner=False)
def load_data(source: str) -> pd.DataFrame:
    if source == "CSV":
        df = _load_from_csv(CSV_PATH)
    elif source == "SQLite":
        df = _load_from_sqlite(DB_PATH)
    else:
        if CSV_PATH.exists():
            df = _load_from_csv(CSV_PATH)
        elif DB_PATH.exists():
            df = _load_from_sqlite(DB_PATH)
        else:
            raise FileNotFoundError("No dashboard data source found.")

    if "date" not in df.columns:
        raise ValueError("Column 'date' is missing in source data.")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")

    numeric_cols = [
        "resting_hr",
        "min_hr",
        "max_hr",
        "sleep_score",
        "acute_load",
        "acute_chronic_ratio",
        "calories",
        "steps",
        "vo2max",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def format_value(value: float | int | None, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}{suffix}"
    return f"{value}{suffix}"


def latest_and_delta(df: pd.DataFrame, column: str) -> tuple[float | None, float | None]:
    if column not in df.columns or df.empty:
        return None, None
    series = df[column].dropna()
    if series.empty:
        return None, None
    latest = series.iloc[-1]
    previous = series.iloc[-2] if len(series) > 1 else None
    if previous is None:
        return float(latest), None
    return float(latest), float(latest - previous)


def main() -> None:
    st.title("Garmin Recovery Dashboard")
    st.caption("Built from your daily Garmin export. Optimized for Streamlit deployment.")

    source = st.sidebar.selectbox("Data source", ["Auto", "CSV", "SQLite"], index=0)

    try:
        df = load_data(source)
    except Exception as exc:
        st.error(f"Could not load dashboard data: {exc}")
        st.info("Run export.py first so dashboard_metrics_history.csv or garmin_dashboard.db exists.")
        return

    if df.empty:
        st.warning("No rows found in your history yet.")
        return

    min_date = df["date"].min().date()
    max_date = df["date"].max().date()
    date_range = st.sidebar.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = min_date
        end_date = max_date

    filtered = df[(df["date"].dt.date >= start_date) & (df["date"].dt.date <= end_date)]

    if filtered.empty:
        st.warning("No data in the selected date range.")
        return

    c1, c2, c3, c4, c5 = st.columns(5)

    kpi_sleep, delta_sleep = latest_and_delta(filtered, "sleep_score")
    kpi_steps, delta_steps = latest_and_delta(filtered, "steps")
    kpi_cal, delta_cal = latest_and_delta(filtered, "calories")
    kpi_acute, delta_acute = latest_and_delta(filtered, "acute_load")
    kpi_vo2, delta_vo2 = latest_and_delta(filtered, "vo2max")

    with c1:
        st.markdown('<div class="kpi-title">Sleep Score</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="kpi-value">{format_value(kpi_sleep)}</div>', unsafe_allow_html=True)
        st.caption(f"Delta: {format_value(delta_sleep)}")

    with c2:
        st.markdown('<div class="kpi-title">Steps</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="kpi-value">{format_value(kpi_steps)}</div>', unsafe_allow_html=True)
        st.caption(f"Delta: {format_value(delta_steps)}")

    with c3:
        st.markdown('<div class="kpi-title">Calories</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="kpi-value">{format_value(kpi_cal)}</div>', unsafe_allow_html=True)
        st.caption(f"Delta: {format_value(delta_cal)}")

    with c4:
        st.markdown('<div class="kpi-title">Acute Load</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="kpi-value">{format_value(kpi_acute)}</div>', unsafe_allow_html=True)
        st.caption(f"Delta: {format_value(delta_acute)}")

    with c5:
        st.markdown('<div class="kpi-title">VO2 Max</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="kpi-value">{format_value(kpi_vo2)}</div>', unsafe_allow_html=True)
        st.caption(f"Delta: {format_value(delta_vo2)}")

    st.divider()

    plot_candidates = [
        "sleep_score",
        "steps",
        "calories",
        "acute_load",
        "acute_chronic_ratio",
        "vo2max",
        "resting_hr",
        "min_hr",
        "max_hr",
    ]
    plot_cols = [col for col in plot_candidates if col in filtered.columns]

    selected_metrics = st.multiselect(
        "Metrics to plot",
        options=plot_cols,
        default=[c for c in ["sleep_score", "steps", "acute_load", "vo2max"] if c in plot_cols],
    )

    if selected_metrics:
        chart_df = filtered.set_index("date")[selected_metrics]
        st.line_chart(chart_df, use_container_width=True)

    a, b = st.columns([1.5, 1])

    with a:
        st.subheader("Daily Table")
        display_cols = [
            "date",
            "sleep_score",
            "steps",
            "calories",
            "acute_load",
            "acute_chronic_ratio",
            "acute_status",
            "load_focus",
            "vo2max",
            "training_status_phrase",
        ]
        display_cols = [c for c in display_cols if c in filtered.columns]
        table_df = filtered[display_cols].copy()
        table_df["date"] = table_df["date"].dt.strftime("%Y-%m-%d")
        st.dataframe(table_df.sort_values("date", ascending=False), use_container_width=True)

    with b:
        st.subheader("Load Focus Split")
        if "load_focus" in filtered.columns:
            focus_counts = (
                filtered["load_focus"]
                .fillna("UNKNOWN")
                .value_counts(dropna=False)
                .rename_axis("load_focus")
                .reset_index(name="days")
            )
            st.bar_chart(focus_counts.set_index("load_focus"), use_container_width=True)
        else:
            st.info("Column 'load_focus' not found.")


if __name__ == "__main__":
    main()
