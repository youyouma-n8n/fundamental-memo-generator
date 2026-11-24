"""Interactive Streamlit web application for the Equity Fundamental Memo Generator."""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pandas.io.formats.style import Styler

from fundamental_memo.charts import (
    build_historical_trajectory_chart,
    build_peer_valuation_scatter,
    build_valuation_football_field,
)
from fundamental_memo.cli import PipelineResult, parse_peer_tickers, run_memo_pipeline
from fundamental_memo.html_exporter import build_html_report
from fundamental_memo.memo_synthesizer import DEFAULT_BASE_URL, SUPPORTED_MODELS
from fundamental_memo.renderer import MAX_MEMO_WORDS
from fundamental_memo.schemas import (
    DcfSensitivityMatrix,
    FinancialSnapshot,
    FundamentalMemoError,
    QuarterlyPoint,
)
from fundamental_memo.screener import run_watchlist_scan
from fundamental_memo.valuation_engine import (
    DEFAULT_EXIT_EV_EBITDA,
    DEFAULT_MAX_FCF_GROWTH,
    DEFAULT_TERMINAL_GROWTH,
    DEFAULT_WACC,
)

MODEL_OPTIONS: tuple[str, ...] = SUPPORTED_MODELS
MODE_DEEP_DIVE = "Single-Stock Deep-Dive"
MODE_WATCHLIST = "Watchlist Quick-Scan Screener"

SCENARIO_PRESETS: dict[str, dict[str, float]] = {
    "Bear": {
        "dcf_wacc": 0.105,
        "dcf_terminal_growth": 0.020,
        "dcf_fcf_cagr": 0.080,
        "dcf_exit_multiple": 12.0,
    },
    "Base": {
        "dcf_wacc": DEFAULT_WACC,
        "dcf_terminal_growth": DEFAULT_TERMINAL_GROWTH,
        "dcf_fcf_cagr": DEFAULT_MAX_FCF_GROWTH,
        "dcf_exit_multiple": DEFAULT_EXIT_EV_EBITDA,
    },
    "Bull": {
        "dcf_wacc": 0.085,
        "dcf_terminal_growth": 0.030,
        "dcf_fcf_cagr": 0.250,
        "dcf_exit_multiple": 20.0,
    },
}


def _init_dcf_session_state() -> None:
    """Initialize DCF sidebar inputs, target ticker, and workspace mode in st.session_state."""
    for key, default_val in SCENARIO_PRESETS["Base"].items():
        if key not in st.session_state:
            st.session_state[key] = default_val
    if "target_ticker" not in st.session_state:
        st.session_state["target_ticker"] = "AVGO"
    if "peers_input" not in st.session_state:
        st.session_state["peers_input"] = "NVDA,AMD,MRVL,QCOM"
    if "active_mode" not in st.session_state:
        st.session_state["active_mode"] = MODE_DEEP_DIVE
    if "auto_run_deep_dive" not in st.session_state:
        st.session_state["auto_run_deep_dive"] = False


def _apply_scenario_preset(preset_name: str) -> None:
    """Apply Bear, Base, or Bull DCF assumptions to st.session_state via button callback."""
    preset = SCENARIO_PRESETS[preset_name]
    for key, value in preset.items():
        st.session_state[key] = value


def _handoff_watchlist_to_deep_dive() -> None:
    """Atomically set target ticker, switch mode to Deep-Dive, and schedule a full memo run."""
    chosen = str(st.session_state.get("watchlist_selected_ticker", "")).strip().upper()
    if not chosen:
        return
    st.session_state["target_ticker"] = chosen
    st.session_state["active_mode"] = MODE_DEEP_DIVE
    st.session_state["auto_run_deep_dive"] = True


def _switch_to_deep_dive_mode() -> None:
    """Ensure clicking the sidebar Generate button switches back into Single-Stock Deep-Dive."""
    st.session_state["active_mode"] = MODE_DEEP_DIVE


def _fmt_compact_billions(value: float | None) -> str:
    """Format a USD dollar figure compactly for KPI deltas and callouts."""
    if value is None:
        return "N/A"
    abs_val = abs(value)
    sign = "-" if value < 0.0 else ""
    if abs_val >= 1_000_000_000.0:
        return f"{sign}${abs_val / 1_000_000_000.0:,.1f}B"
    if abs_val >= 1_000_000.0:
        return f"{sign}${abs_val / 1_000_000.0:,.0f}M"
    return f"{sign}${abs_val:,.0f}"


def _build_fcf_trajectory_caption(snapshot: FinancialSnapshot) -> str:
    """Format a concise 3-year + TTM FCF progression caption for the trajectory chart."""
    parts: list[str] = []
    for point in snapshot.historical_trajectory:
        if point.free_cash_flow is not None:
            parts.append(f"{point.period}: {_fmt_compact_billions(point.free_cash_flow)}")
    progression = " → ".join(parts) if parts else "Historical annual FCF unavailable"
    return (
        f"Annual FCF progression: {progression} | "
        f"TTM FCF: {_fmt_compact_billions(snapshot.free_cash_flow_ttm)}."
    )


def build_styled_sensitivity_table(
    matrix: DcfSensitivityMatrix, current_price: float
) -> Styler:
    """Build a color-coded pandas Styler for the 5x5 DCF sensitivity matrix."""
    col_labels = [f"WACC {w * 100.0:.2f}%" for w in matrix.wacc_values]
    row_labels = [f"CAGR {c * 100.0:.1f}%" for c in matrix.cagr_values]

    raw_df = pd.DataFrame(matrix.grid, index=row_labels, columns=col_labels)
    raw_df.index.name = "5Y FCF CAGR \\ WACC"

    center_row = len(row_labels) // 2
    center_col = len(col_labels) // 2

    def _style_grid(frame: pd.DataFrame) -> pd.DataFrame:
        styles = pd.DataFrame("", index=frame.index, columns=frame.columns)
        for r_idx in range(len(frame.index)):
            for c_idx in range(len(frame.columns)):
                val = frame.iat[r_idx, c_idx]
                cell_parts: list[str] = []
                if isinstance(val, (int, float)) and pd.notna(val):
                    if float(val) > current_price:
                        cell_parts.append("background-color: rgba(16, 185, 129, 0.20)")
                    else:
                        cell_parts.append("background-color: rgba(239, 68, 68, 0.14)")
                if r_idx == center_row and c_idx == center_col:
                    cell_parts.append("font-weight: 700")
                    cell_parts.append("border: 2px solid #2563EB")
                styles.iat[r_idx, c_idx] = "; ".join(cell_parts)
        return styles

    return raw_df.style.apply(_style_grid, axis=None).format(
        lambda val: f"${float(val):,.2f}" if pd.notna(val) else "N/A"
    )


def build_quarterly_momentum_dataframe(
    quarterly_trajectory: Sequence[QuarterlyPoint],
) -> pd.DataFrame:
    """Build a compact formatted DataFrame for the 4-quarter operational momentum view."""
    rows: list[dict[str, str]] = []
    for pt in quarterly_trajectory:
        rows.append(
            {
                "Quarter": pt.period,
                "Revenue ($B)": f"${pt.revenue / 1_000_000_000.0:,.2f}B",
                "Gross Margin (%)": (
                    f"{pt.gross_margin * 100.0:.1f}%" if pt.gross_margin is not None else "N/A"
                ),
                "Operating Margin (%)": (
                    f"{pt.operating_margin * 100.0:.1f}%"
                    if pt.operating_margin is not None
                    else "N/A"
                ),
                "FCF ($B)": (
                    f"${pt.free_cash_flow / 1_000_000_000.0:,.2f}B"
                    if pt.free_cash_flow is not None
                    else "N/A"
                ),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "Quarter",
            "Revenue ($B)",
            "Gross Margin (%)",
            "Operating Margin (%)",
            "FCF ($B)",
        ],
    )


def build_styled_watchlist_table(scan_results: Sequence[dict[str, Any]]) -> Styler:
    """Build a sortable, color-formatted pandas Styler for Watchlist Quick-Scan results."""
    rows: list[dict[str, Any]] = []
    for row in scan_results:
        if row.get("error") is not None:
            continue
        rows.append(
            {
                "Ticker": str(row["ticker"]),
                "Company": str(row["company_name"]),
                "Price": row["current_price"],
                "Base DCF": row["dcf_value"],
                "DCF Upside %": (
                    float(row["dcf_upside_pct"]) * 100.0
                    if row["dcf_upside_pct"] is not None
                    else None
                ),
                "Implied 5Y FCF CAGR": (
                    float(row["implied_fcf_cagr_5y"]) * 100.0
                    if row["implied_fcf_cagr_5y"] is not None
                    else None
                ),
                "Forward P/E": row["forward_pe"],
                "EV/EBITDA": row["ev_to_ebitda"],
                "ROIC": float(row["roic_ttm"]) * 100.0 if row["roic_ttm"] is not None else None,
                "FCF Margin": (
                    float(row["fcf_margin_ttm"]) * 100.0
                    if row["fcf_margin_ttm"] is not None
                    else None
                ),
                "Earnings Quality": str(row["earnings_quality_flag"]),
            }
        )

    columns = [
        "Ticker",
        "Company",
        "Price",
        "Base DCF",
        "DCF Upside %",
        "Implied 5Y FCF CAGR",
        "Forward P/E",
        "EV/EBITDA",
        "ROIC",
        "FCF Margin",
        "Earnings Quality",
    ]
    df = pd.DataFrame(rows, columns=columns)

    def _color_upside(val: object) -> str:
        if isinstance(val, (int, float)) and pd.notna(val):
            if float(val) >= 0.0:
                return "background-color: rgba(16, 185, 129, 0.20); font-weight: 600"
            return "background-color: rgba(239, 68, 68, 0.14); font-weight: 600"
        return ""

    return df.style.map(_color_upside, subset=["DCF Upside %"]).format(
        {
            "Price": lambda v: f"${float(v):,.2f}" if pd.notna(v) else "N/A",
            "Base DCF": lambda v: f"${float(v):,.2f}" if pd.notna(v) else "N/A",
            "DCF Upside %": lambda v: f"{float(v):+.1f}%" if pd.notna(v) else "N/A",
            "Implied 5Y FCF CAGR": lambda v: f"{float(v):.1f}%" if pd.notna(v) else "N/A",
            "Forward P/E": lambda v: f"{float(v):.1f}x" if pd.notna(v) else "N/A",
            "EV/EBITDA": lambda v: f"{float(v):.1f}x" if pd.notna(v) else "N/A",
            "ROIC": lambda v: f"{float(v):.1f}%" if pd.notna(v) else "N/A",
            "FCF Margin": lambda v: f"{float(v):.1f}%" if pd.notna(v) else "N/A",
        }
    )


def _render_watchlist_screener(
    *,
    ticker_input: str,
    peers_input: str,
    wacc: float,
    terminal_growth: float,
    fcf_cagr: float,
    exit_ev_ebitda: float,
    use_mock_data: bool,
) -> None:
    """Render Watchlist Quick-Scan Screener mode with one-click deep-dive handoff."""
    default_tokens = parse_peer_tickers(f"{ticker_input},{peers_input}")
    default_watchlist = ",".join(default_tokens) if default_tokens else "NVDA,AMD,MRVL,QCOM,AVGO"

    st.subheader("Watchlist Quick-Scan Screener")
    st.caption(
        "Runs only the deterministic pure-Python DCF & Reverse DCF engine across multiple tickers "
        "(zero LLM latency) using your active sidebar WACC, Terminal g, 5Y FCF CAGR, and Exit "
        "Multiple assumptions."
    )

    input_col, btn_col = st.columns([3, 1], vertical_alignment="bottom")
    watchlist_raw = input_col.text_input(
        "Watchlist tickers (comma-separated)",
        value=default_watchlist,
        key="watchlist_tickers_input",
        help="Enter 2 or more comma-separated tickers to screen in parallel.",
    )
    scan_button = btn_col.button(
        "Run Batch Valuation Scan",
        key="run_watchlist_scan_btn",
        type="primary",
        icon=":material/query_stats:",
        width="stretch",
    )

    if scan_button:
        watchlist_tickers = parse_peer_tickers(watchlist_raw)
        if not watchlist_tickers:
            st.error("Please enter at least one ticker symbol to scan.")
            return
        with st.spinner(
            f"Running deterministic batch valuation scan for {len(watchlist_tickers)} tickers..."
        ):
            t0 = time.perf_counter()
            scan_results = run_watchlist_scan(
                tickers=watchlist_tickers,
                wacc=wacc,
                terminal_growth=terminal_growth,
                base_cagr=fcf_cagr,
                exit_multiple=exit_ev_ebitda,
                offline_mock=use_mock_data,
            )
            elapsed = time.perf_counter() - t0
        st.session_state["watchlist_scan_results"] = scan_results
        st.session_state["watchlist_scan_elapsed"] = elapsed

    stored_scan: list[dict[str, Any]] | None = st.session_state.get("watchlist_scan_results")
    if not stored_scan:
        st.info(
            "Enter a basket of tickers above and click **Run Batch Valuation Scan** to compare "
            "intrinsic values, market-implied growth, multiples, and earnings quality in seconds."
        )
        return

    valid_rows = [row for row in stored_scan if row.get("error") is None]
    failed_rows = [row for row in stored_scan if row.get("error") is not None]
    elapsed_sec = float(st.session_state.get("watchlist_scan_elapsed", 0.0))

    if valid_rows:
        st.caption(
            f"Scanned **{len(valid_rows)}** tickers in **{elapsed_sec:.2f}s** "
            f"(pure Python, no LLM) | WACC **{wacc * 100.0:.2f}%** | "
            f"5Y FCF CAGR **{fcf_cagr * 100.0:.1f}%** | Term g **{terminal_growth * 100.0:.2f}%**"
        )
        st.dataframe(
            build_styled_watchlist_table(valid_rows),
            width="stretch",
            hide_index=True,
            alt="Watchlist Quick-Scan Screener valuation comparison table",
        )

        valid_tickers = [str(row["ticker"]) for row in valid_rows]
        pick_col, load_col, _ = st.columns([2, 2, 2], vertical_alignment="bottom")
        pick_col.selectbox(
            "Select ticker for full One-Page Memo",
            options=valid_tickers,
            key="watchlist_selected_ticker",
        )
        load_col.button(
            "Load Selected Ticker into Deep-Dive",
            key="load_selected_deep_dive_btn",
            type="primary",
            icon=":material/open_in_new:",
            on_click=_handoff_watchlist_to_deep_dive,
            width="stretch",
        )

    if failed_rows:
        err_summary = "; ".join(f"{row['ticker']}: {row['error']}" for row in failed_rows)
        st.warning(f"Skipped tickers with data/valuation errors: {err_summary}")


def render_app() -> None:
    """Render the interactive Streamlit application layout and handle analysis runs."""
    st.set_page_config(
        page_title="Equity Fundamental Memo Generator",
        page_icon=":material/analytics:",
        layout="wide",
    )

    _init_dcf_session_state()

    st.title("Equity fundamental deep-dive & one-page memo generator")
    st.caption(
        "Deterministic pure-Python valuation engine, Reverse DCF, and strictly grounded "
        "local LLM synthesis (zero financial hallucination)."
    )

    with st.sidebar:
        st.header("Analysis parameters")
        ticker_input = st.text_input("Target ticker", key="target_ticker").strip().upper()
        peers_input = st.text_input(
            "Peer tickers (comma-separated)",
            key="peers_input",
            help="Provide 3 to 5 sector peer tickers for comparable multiples and scatter plot.",
        )

        st.subheader("DCF assumptions")
        preset_col_bear, preset_col_base, preset_col_bull = st.columns(3)
        preset_col_bear.button(
            "Bear",
            key="preset_bear",
            width="stretch",
            on_click=_apply_scenario_preset,
            args=("Bear",),
        )
        preset_col_base.button(
            "Base",
            key="preset_base",
            width="stretch",
            on_click=_apply_scenario_preset,
            args=("Base",),
        )
        preset_col_bull.button(
            "Bull",
            key="preset_bull",
            width="stretch",
            on_click=_apply_scenario_preset,
            args=("Bull",),
        )

        wacc = float(
            st.number_input(
                "WACC",
                min_value=0.01,
                max_value=0.30,
                step=0.005,
                format="%.3f",
                key="dcf_wacc",
            )
        )
        terminal_growth = float(
            st.number_input(
                "Terminal growth rate",
                min_value=0.00,
                max_value=0.10,
                step=0.005,
                format="%.3f",
                key="dcf_terminal_growth",
            )
        )
        fcf_cagr = float(
            st.number_input(
                "5Y FCF CAGR",
                min_value=-0.20,
                max_value=0.60,
                step=0.01,
                format="%.3f",
                key="dcf_fcf_cagr",
                help="Explicit 5-year unlevered Free Cash Flow CAGR assumption.",
            )
        )
        exit_ev_ebitda = float(
            st.number_input(
                "Terminal Exit EV/EBITDA Multiple",
                min_value=2.0,
                max_value=60.0,
                step=0.5,
                format="%.1f",
                key="dcf_exit_multiple",
                help="Terminal Year EBITDA exit multiple for DCF cross-check.",
            )
        )

        st.subheader("Local LLM configuration")
        selected_model_raw = st.selectbox(
            "Analysis model",
            options=list(MODEL_OPTIONS),
            index=0,
            help="Select the local Ollama/MLX model used to synthesize the one-page memo.",
        )
        selected_model = selected_model_raw if selected_model_raw is not None else MODEL_OPTIONS[0]
        base_url = st.text_input(
            "OpenAI-compatible base URL",
            value=DEFAULT_BASE_URL,
            help="Default Ollama endpoint: http://localhost:11434/v1 (MLX: http://localhost:8080/v1).",
        ).strip()

        st.subheader("Data & offline mode")
        use_mock_data = st.checkbox(
            "Use Offline Mock Data",
            value=False,
            help="Run deterministically offline using bundled fixture data without network calls.",
        )
        use_live_llm = False
        if use_mock_data:
            use_live_llm = st.checkbox(
                "Use live local LLM with mock data",
                value=False,
                help="Keep offline mock financials but call the selected local LLM for prose.",
            )

        run_button = st.button(
            "Generate one-page memo",
            key="generate_memo_btn",
            type="primary",
            on_click=_switch_to_deep_dive_mode,
            width="stretch",
        )

    selected_mode = st.segmented_control(
        "Workspace mode",
        options=[MODE_DEEP_DIVE, MODE_WATCHLIST],
        key="active_mode",
        label_visibility="collapsed",
    )
    active_mode = selected_mode if selected_mode is not None else MODE_DEEP_DIVE

    if active_mode == MODE_WATCHLIST:
        _render_watchlist_screener(
            ticker_input=ticker_input,
            peers_input=peers_input,
            wacc=wacc,
            terminal_growth=terminal_growth,
            fcf_cagr=fcf_cagr,
            exit_ev_ebitda=exit_ev_ebitda,
            use_mock_data=use_mock_data,
        )
        return

    should_run_deep_dive = run_button or bool(st.session_state.pop("auto_run_deep_dive", False))
    if should_run_deep_dive:
        if not ticker_input:
            st.error("Please enter a target equity ticker symbol.")
            return
        peer_list = parse_peer_tickers(peers_input)
        with st.spinner(f"Running fundamental analysis for {ticker_input}..."):
            try:
                result = run_memo_pipeline(
                    ticker=ticker_input,
                    peers=peer_list,
                    wacc=wacc,
                    terminal_growth=terminal_growth,
                    fcf_cagr=fcf_cagr,
                    exit_ev_ebitda=exit_ev_ebitda,
                    model=selected_model,
                    base_url=base_url or DEFAULT_BASE_URL,
                    mock_data=use_mock_data,
                    live_llm=use_live_llm,
                    max_retries=3,
                )
            except (FundamentalMemoError, ValueError) as exc:
                st.error(
                    f"Analysis failed: {exc}\n\n"
                    "Troubleshooting: verify your ticker symbol and DCF inputs (WACC > terminal "
                    "growth), confirm your local Ollama/MLX server is running at the configured "
                    "Base URL, or enable 'Use Offline Mock Data' for a deterministic offline run."
                )
                return
            except Exception as exc:  # noqa: BLE001
                st.error(f"Unexpected error during analysis: {exc}")
                return

        st.session_state["last_pipeline_result"] = result
        st.session_state["last_selected_model"] = selected_model

    stored_result: PipelineResult | None = st.session_state.get("last_pipeline_result")
    if stored_result is None:
        st.info(
            "Configure your target ticker, peers, DCF assumptions, and local model in the sidebar, "
            "then click **Generate one-page memo**."
        )
        return

    valuation = stored_result.valuation
    snapshot = stored_result.snapshot

    col_price, col_dcf, col_implied, col_roic, col_quality = st.columns(5)

    col_price.metric(
        "Current Price",
        f"${snapshot.current_price:,.2f}",
        delta=(
            f"52W: ${snapshot.fifty_two_week_low:,.0f}–${snapshot.fifty_two_week_high:,.0f}"
            if (
                snapshot.fifty_two_week_low is not None
                and snapshot.fifty_two_week_high is not None
            )
            else None
        ),
        delta_color="off",
    )
    col_dcf.metric(
        "DCF Intrinsic Value",
        f"${valuation.dcf_intrinsic_value_per_share:,.2f}",
        delta=f"{valuation.dcf_upside_pct * 100.0:+.1f}% vs. price",
    )

    implied_cagr_str = (
        f"{valuation.implied_fcf_cagr_5y * 100.0:.1f}%"
        if valuation.implied_fcf_cagr_5y is not None
        else "N/A"
    )
    spread_delta_str = (
        f"{valuation.cagr_spread_vs_base * 100.0:+.1f}% vs. base"
        if valuation.cagr_spread_vs_base is not None
        else None
    )
    col_implied.metric(
        "Market-Implied CAGR",
        implied_cagr_str,
        delta=spread_delta_str,
        delta_color="inverse",
    )

    roic_str = f"{snapshot.roic_ttm * 100.0:.1f}%" if snapshot.roic_ttm is not None else "N/A"
    op_margin_str = (
        f"{snapshot.operating_margin_ttm * 100.0:.1f}%"
        if snapshot.operating_margin_ttm is not None
        else "N/A"
    )
    gm_str = (
        f"{snapshot.gross_margin_ttm * 100.0:.1f}%"
        if snapshot.gross_margin_ttm is not None
        else "N/A"
    )
    col_roic.metric(
        "ROIC (TTM)",
        roic_str,
        delta=f"OpM {op_margin_str} | GM {gm_str}",
        delta_color="off",
    )

    sbc_fcf_label = _fmt_compact_billions(snapshot.sbc_adjusted_fcf_ttm)
    col_quality.metric(
        "Earnings Quality",
        valuation.earnings_quality_flag,
        delta=f"OCF/NI {valuation.ocf_to_net_income_ratio:.2f}x | Adj {sbc_fcf_label}",
        delta_color="off",
    )

    chart_col_left, chart_col_right = st.columns(2)
    with chart_col_left:
        football_fig = build_valuation_football_field(
            snapshot, valuation, stored_result.sensitivity
        )
        st.plotly_chart(
            football_fig,
            width="stretch",
            alt=f"Valuation Football Field chart for {snapshot.ticker}",
        )
    with chart_col_right:
        scatter_fig = build_peer_valuation_scatter(
            snapshot,
            stored_result.peers,
            peer_median_ev_ebitda=valuation.peer_median_ev_ebitda,
        )
        st.plotly_chart(
            scatter_fig,
            width="stretch",
            alt=f"Peer Valuation vs. Growth scatter chart for {snapshot.ticker}",
        )

    if (
        valuation.implied_fcf_cagr_5y is not None
        and valuation.implied_y5_fcf is not None
        and valuation.implied_y5_fcf_multiple is not None
    ):
        st.info(
            f"At **${snapshot.current_price:,.2f}**, the market implies a "
            f"**{valuation.implied_fcf_cagr_5y * 100.0:.1f}%** 5Y FCF CAGR, requiring annual FCF "
            f"to grow **{valuation.implied_y5_fcf_multiple:.2f}×** from "
            f"**{_fmt_compact_billions(snapshot.free_cash_flow_ttm)}** (TTM) to "
            f"**{_fmt_compact_billions(valuation.implied_y5_fcf)}** in Year 5 "
            f"(vs. **{_fmt_compact_billions(snapshot.revenue_ttm)}** total TTM revenue today).",
            title="Reverse DCF Reality Check",
            icon=":material/insights:",
        )

    lower_col_left, lower_col_right = st.columns([3, 2])
    with lower_col_left:
        if valuation.dcf_sensitivity_matrix is not None:
            with st.expander("5×5 DCF Sensitivity Matrix (WACC × 5Y FCF CAGR)", expanded=True):
                styled_matrix = build_styled_sensitivity_table(
                    valuation.dcf_sensitivity_matrix, snapshot.current_price
                )
                st.dataframe(
                    styled_matrix,
                    width="stretch",
                    height="auto",
                    alt=f"5x5 DCF sensitivity matrix for {snapshot.ticker}",
                )
                term_pct = valuation.dcf_assumptions["terminal_growth_rate"] * 100.0
                exit_mult = valuation.dcf_assumptions.get("target_exit_ev_ebitda", 15.0)
                if valuation.implied_exit_ev_ebitda is not None:
                    st.caption(
                        f"Perpetuity DCF ({term_pct:.1f}% terminal growth) implies an exit "
                        f"EV/EBITDA of **{valuation.implied_exit_ev_ebitda:.1f}x** vs. your Exit "
                        f"Multiple assumption of **{exit_mult:.1f}x**. Green cells exceed "
                        f"current price (${snapshot.current_price:,.2f}); blue border marks Base."
                    )
    trajectory_fig: go.Figure | None = None
    with lower_col_right:
        tab_annual, tab_quarterly = st.tabs(["Annual (3Y)", "Quarterly (4Q)"])
        with tab_annual:
            if snapshot.historical_trajectory:
                trajectory_fig = build_historical_trajectory_chart(snapshot)
                st.plotly_chart(
                    trajectory_fig,
                    width="stretch",
                    alt=f"3-Year Historical Trajectory chart for {snapshot.ticker}",
                )
                st.caption(_build_fcf_trajectory_caption(snapshot))
            else:
                st.caption("Annual 3-year historical trajectory data is unavailable.")
        with tab_quarterly:
            if snapshot.quarterly_trajectory:
                quarterly_df = build_quarterly_momentum_dataframe(snapshot.quarterly_trajectory)
                st.dataframe(
                    quarterly_df,
                    width="stretch",
                    hide_index=True,
                    alt=f"4-quarter momentum table for {snapshot.ticker}",
                )
                st.caption(
                    "Last 4 completed fiscal quarters ordered chronologically (oldest to newest)."
                )
            else:
                st.caption("Quarterly statement data was unavailable for this ticker.")

    synth_label = (
        "Offline Deterministic Mock"
        if stored_result.used_mock_llm
        else str(st.session_state.get("last_selected_model", MODEL_OPTIONS[0]))
    )
    st.caption(
        f"Word Count: **{stored_result.word_count} / {MAX_MEMO_WORDS}** | "
        f"Synthesizer: **{synth_label}** | Grounding Audit: **Passed**"
    )

    html_report = build_html_report(
        snapshot,
        valuation,
        stored_result.peers,
        stored_result.sensitivity,
        stored_result.markdown,
        football_fig=football_fig,
        scatter_fig=scatter_fig,
        trajectory_fig=trajectory_fig,
        model_label=synth_label,
        word_count=stored_result.word_count,
    )
    dl_col_md, dl_col_html, _ = st.columns([1, 1, 2])
    dl_col_md.download_button(
        label=f"Download memo_{snapshot.ticker}.md",
        data=stored_result.markdown,
        file_name=f"memo_{snapshot.ticker}.md",
        mime="text/markdown",
        icon=":material/description:",
        width="stretch",
    )
    dl_col_html.download_button(
        label=f"Download report_{snapshot.ticker}.html",
        data=html_report,
        file_name=f"report_{snapshot.ticker}.html",
        mime="text/html",
        icon=":material/html:",
        width="stretch",
    )

    st.divider()
    st.markdown(stored_result.markdown)

    with st.expander("Verified Quantitative Data (Audit Trail JSON)"):
        st.json(stored_result.audit_trail_json())


if __name__ == "__main__":
    render_app()
