"""Unit tests for Plotly Valuation Football Field and Peer Valuation-Growth Scatter builders."""

from __future__ import annotations

import pytest

from fundamental_memo.charts import (
    CONSENSUS_LINE_COLOR,
    MARGIN_LINE_COLOR,
    PEER_MUTED_COLOR,
    REVENUE_BAR_COLOR,
    SCATTER_MAX_BUBBLE_PX,
    TARGET_ACCENT_COLOR,
    build_historical_trajectory_chart,
    build_peer_valuation_scatter,
    build_valuation_football_field,
)
from fundamental_memo.data_fetcher import load_mock_market_data
from fundamental_memo.valuation_engine import compute_dcf_sensitivity, run_valuation_analysis


def test_valuation_football_field_padding_bars_and_top_callout() -> None:
    """Football Field renders 4 bars, dynamic [0.75*min, 1.22*max] range, and top price callout."""
    bundle = load_mock_market_data()
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    sensitivity = compute_dcf_sensitivity(bundle.snapshot)

    fig = build_valuation_football_field(bundle.snapshot, valuation, sensitivity)
    assert len(fig.data) == 1
    bar_trace = fig.data[0]
    labels = list(bar_trace.y)
    assert labels == [
        "52-Week Trading Range",
        "Perpetuity DCF Sensitivity",
        "Exit Multiple DCF Valuation",
        "Peer Comps Valuation Range",
    ]
    assert len(fig.layout.shapes) == 2
    assert fig.layout.shapes[0].x0 == bundle.snapshot.current_price
    assert fig.layout.shapes[0].line.dash == "dash"
    assert fig.layout.shapes[1].x0 == bundle.snapshot.analyst_target_mean
    assert fig.layout.shapes[1].line.dash == "dot"
    assert fig.layout.shapes[1].line.color == CONSENSUS_LINE_COLOR

    # Current Price and Consensus Target callouts are permanently staggered to prevent overlap
    assert len(fig.layout.annotations) == 2
    price_ann = fig.layout.annotations[0]
    consensus_ann = fig.layout.annotations[1]
    assert price_ann.yref == "paper"
    assert price_ann.y == pytest.approx(1.12)
    assert price_ann.xanchor == "right"
    assert price_ann.xshift == -4
    assert price_ann.showarrow is False
    assert f"${bundle.snapshot.current_price:,.2f}" in price_ann.text
    assert consensus_ann.yref == "paper"
    assert consensus_ann.y == pytest.approx(1.03)
    assert consensus_ann.xanchor == "left"
    assert consensus_ann.xshift == 4
    assert consensus_ann.showarrow is False
    assert "Analyst Consensus Target" in consensus_ann.text
    assert fig.layout.margin.t >= 65
    assert fig.layout.margin.r >= 40

    # Dynamic x-axis bounds prevent right-edge clipping
    x_range = list(fig.layout.xaxis.range)
    assert x_range[1] > max(bar_trace.base[i] + bar_trace.x[i] for i in range(len(labels))) * 1.20


def test_valuation_football_field_stagger_holds_for_close_and_wide_spreads() -> None:
    """Staggered vertical and horizontal anchors hold under both <2% and >50% target spreads."""
    bundle = load_mock_market_data()
    spreads = (
        bundle.snapshot.current_price * 1.01,
        bundle.snapshot.current_price * 1.65,
    )
    for target_price in spreads:
        snap = bundle.snapshot.model_copy(update={"analyst_target_mean": target_price})
        valuation = run_valuation_analysis(snap, bundle.peers)
        sensitivity = compute_dcf_sensitivity(snap)
        fig = build_valuation_football_field(snap, valuation, sensitivity)
        price_ann, consensus_ann = fig.layout.annotations[0], fig.layout.annotations[1]
        assert price_ann.y == pytest.approx(1.12)
        assert price_ann.xanchor == "right"
        assert price_ann.xshift == -4
        assert consensus_ann.y == pytest.approx(1.03)
        assert consensus_ann.xanchor == "left"
        assert consensus_ann.xshift == 4
        assert price_ann.y > consensus_ann.y


def test_valuation_football_field_handles_missing_optional_ranges() -> None:
    """Football Field omits bars cleanly when optional inputs like 52-week range are None."""
    bundle = load_mock_market_data()
    stripped_snapshot = bundle.snapshot.model_copy(
        update={"fifty_two_week_low": None, "fifty_two_week_high": None}
    )
    valuation = run_valuation_analysis(stripped_snapshot, [])
    sensitivity = compute_dcf_sensitivity(stripped_snapshot)

    fig = build_valuation_football_field(stripped_snapshot, valuation, sensitivity)
    labels = list(fig.data[0].y)
    assert "52-Week Trading Range" not in labels
    assert "Peer Comps Valuation Range" not in labels
    assert "Perpetuity DCF Sensitivity" in labels


def test_peer_valuation_scatter_area_bubbles_and_median_hline() -> None:
    """Scatter plot uses area bubble sizing, distinct target color, and Peer Median hline."""
    bundle = load_mock_market_data()
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    fig = build_peer_valuation_scatter(
        bundle.snapshot,
        bundle.peers,
        peer_median_ev_ebitda=valuation.peer_median_ev_ebitda,
    )

    assert len(fig.data) == 2
    peers_trace, target_trace = fig.data[0], fig.data[1]
    assert peers_trace.marker.color == PEER_MUTED_COLOR
    assert target_trace.marker.color == TARGET_ACCENT_COLOR
    assert peers_trace.marker.sizemode == "area"
    assert target_trace.marker.sizemode == "area"

    max_cap = max([bundle.snapshot.market_cap, *(p.market_cap or 0.0 for p in bundle.peers)])
    expected_sizeref = (2.0 * max_cap) / (SCATTER_MAX_BUBBLE_PX**2)
    assert peers_trace.marker.sizeref == pytest.approx(expected_sizeref)
    assert list(target_trace.text) == ["AVGO"]
    assert set(peers_trace.text) == {"NVDA", "AMD", "MRVL", "QCOM"}

    # Horizontal dashed Peer Median reference line placed cleanly at top left (font size 11)
    assert len(fig.layout.shapes) == 1
    assert fig.layout.shapes[0].y0 == pytest.approx(valuation.peer_median_ev_ebitda)
    assert fig.layout.shapes[0].line.dash == "dash"
    median_anns = [ann for ann in fig.layout.annotations if "Peer Median" in ann.text]
    assert len(median_anns) == 1
    assert median_anns[0].xanchor == "left"
    assert median_anns[0].x == pytest.approx(0.0)
    assert median_anns[0].font.size == 11


def test_historical_trajectory_chart_dual_axis_traces() -> None:
    """3-Year Historical Trajectory renders Revenue bars (#3B82F6) and Op Margin line (#F59E0B)."""
    bundle = load_mock_market_data()
    fig = build_historical_trajectory_chart(bundle.snapshot)

    assert len(fig.data) == 2
    rev_trace, margin_trace = fig.data[0], fig.data[1]
    assert list(rev_trace.x) == ["FY2022", "FY2023", "FY2024"]
    assert rev_trace.marker.color == REVENUE_BAR_COLOR
    assert margin_trace.line.color == MARGIN_LINE_COLOR
    assert len(margin_trace.y) == 3
