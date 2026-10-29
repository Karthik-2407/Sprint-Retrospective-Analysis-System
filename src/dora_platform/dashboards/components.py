"""Reusable Streamlit UI components for the DORA Platform dashboard.

Includes modern executive KPI cards, Altair time series charts,
status badges with explanations, and evidence viewers.
"""

# ruff: noqa: E501, W291, W293

from __future__ import annotations

from typing import TYPE_CHECKING

import altair as alt
import pandas as pd  # type: ignore[import-untyped]
import streamlit as st

if TYPE_CHECKING:
    from dora_platform.dashboards.data_service import MetricCardData


def render_top_hero(
    tenant_name: str,
    project_name: str,
    scope_name: str,
    window_name: str,
) -> None:
    """Render the executive top banner."""
    st.markdown(
        f"""
        <div class="top-hero">
            <div>
                <div class="hero-tag">
                    <span class="pulse-dot pulse-green"></span>
                    <span>System Operational &bull; DORA Metrics Engine v0.1.0</span>
                </div>
                <h1 class="hero-title" style="margin-top: 0.6rem;">{tenant_name}</h1>
                <p class="hero-subtitle">
                    Scope: <strong>{project_name}</strong> &bull; 
                    Target: <strong>{scope_name}</strong> &bull; 
                    Window: <strong>{window_name}</strong>
                </p>
            </div>
            <div style="text-align: right; display: none;">
                <span style="font-size: 0.8rem; color: #94a3b8;">Data Engine</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_badge(status: str) -> str:
    """Return HTML for a status badge matching D2 principles."""
    labels = {
        "ok": "OK (Verified)",
        "no_events": "NO EVENTS (0 in window)",
        "undetectable": "UNDETECTABLE (Source Missing)",
        "insufficient_sample": "INSUFFICIENT SAMPLE (n < 30)",
        "partial_data": "PARTIAL DATA (Lag/Backfill)",
    }
    label = labels.get(status, status.upper())
    return f'<span class="status-badge {status}">{label}</span>'


def render_kpi_card(metric: MetricCardData, accent: str = "blue") -> None:
    """Render a card displaying value, sample size, CI, and definition."""
    accent_color = {
        "blue": "#2563eb",
        "purple": "#7c3aed",
        "green": "#059669",
        "amber": "#d97706",
        "red": "#dc2626",
    }.get(accent, "#2563eb")

    # Sample size pill
    if metric.n >= metric.n_required:
        n_badge = f'<span class="metric-n-badge n-pass">n = {metric.n} &ge; {metric.n_required} &check;</span>'
    else:
        n_badge = (
            f'<span class="metric-n-badge n-fail">n = {metric.n} &lt; {metric.n_required}</span>'
        )

    # Confidence Interval display
    if metric.ci_lower is not None and metric.ci_upper is not None:
        ci_str = f"95% CI: [{metric.ci_lower:.1f}, {metric.ci_upper:.1f}]"
        ci_badge = f'<span class="metric-ci-pill">{ci_str}</span>'
    else:
        ci_badge = '<span class="metric-ci-pill">CI: N/A (n &lt; 30)</span>'

    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-card-top-bar" style="background-color: {accent_color};"></div>
            <div>
                <div class="card-header-row">
                    <div>
                        <span class="def-version-tag">{metric.definition_version}</span>
                        <h4 class="metric-category-title" style="margin-top: 0.35rem;">{metric.title}</h4>
                    </div>
                    {render_status_badge(metric.status)}
                </div>
                <div style="display: flex; align-items: baseline;">
                    <div class="metric-main-value">{metric.value_display}</div>
                    <span class="metric-unit">{metric.unit}</span>
                </div>
                <p style="font-size: 0.82rem; color: #64748b; margin: 0.4rem 0 0.8rem; line-height: 1.45;">
                    {metric.note or ""}
                </p>
            </div>
            <div class="metric-footer">
                <div>{n_badge}</div>
                <div>{ci_badge}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_trend_chart(
    df: pd.DataFrame, title: str, y_title: str, unit: str, color_hex: str = "#2563eb"
) -> None:
    """Render an interactive Altair time-series chart with confidence bounds."""
    if df.empty or df["rolling_avg"].isna().all():
        st.info(f"Insufficient historical samples to plot time-series trend for {title}.")
        return

    # Base chart
    base = alt.Chart(df).encode(
        x=alt.X("date:T", title="Date", axis=alt.Axis(format="%b %d", labelAngle=-45, grid=False)),
    )

    # Shaded confidence band if bounds are present
    if "ci_lower" in df.columns and "ci_upper" in df.columns and not df["ci_lower"].isna().all():
        band = base.mark_area(opacity=0.15, color=color_hex).encode(
            y=alt.Y("ci_lower:Q", title=y_title),
            y2="ci_upper:Q",
        )
    else:
        band = None

    # Line for rolling average
    line = base.mark_line(color=color_hex, strokeWidth=3).encode(
        y=alt.Y("rolling_avg:Q", title=f"{y_title} ({unit})"),
        tooltip=[
            alt.Tooltip("date:T", title="Date", format="%Y-%m-%d"),
            alt.Tooltip("rolling_avg:Q", title="7d Rolling Avg", format=".2f"),
            alt.Tooltip("daily_value:Q", title="Daily Observation", format=".2f"),
        ],
    )

    # Points for daily observations
    points = base.mark_circle(size=40, color=color_hex, opacity=0.6).encode(
        y="daily_value:Q",
    )

    chart = (band + line + points) if band is not None else (line + points)

    st.altair_chart(
        chart.properties(
            title=title,
            height=280,
            width="container",
        )
        .configure_title(
            fontSize=13,
            fontWeight=700,
            color="#1e293b",
            anchor="start",
        )
        .configure_view(
            strokeWidth=0,
        ),
        use_container_width=True,
    )


def render_status_explainer() -> None:
    """Render the D2 status transparency guide."""
    with st.expander("ℹ️ Statistical Rigor & Metric Status Transparency (D2 & D4 Principles)"):
        st.markdown(
            r"""
            This platform adheres to **strict operational honesty**:
            
            - **OK**: Validly computed from continuous event telemetry. Legitimate zero is displayed when zero incidents or deployments occurred.
            - **NO_EVENTS**: Ingestion pipelines are healthy and active, but zero matching events occurred in the selected window.
            - **UNDETECTABLE**: Ingestion source is missing, misconfigured, or unreachable. **Rendered as N/A, never silently coerced to 0**.
            - **INSUFFICIENT_SAMPLE**: The sample size is strictly below the statistical minimum (**$n < 30$**). Inferential statistics are suppressed to prevent noisy micro-samples from misleading teams.
            - **PARTIAL_DATA**: Computed with acknowledged pipeline backfill or latency gaps.
            
            **Statistical Methods:**
            - **Wilson Score Interval**: Employed for binomial failure rates (CFR) with continuity correction.
            - **Percentile Bootstrap**: Employed for duration metrics (Lead Time, Recovery Time) with $B = 2,000$ resamples.
            - **Spearman Rank Correlation ($\rho$)**: Enforced strictly at $n \ge 30$ paired observations.
            """
        )
