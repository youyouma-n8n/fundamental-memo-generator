"""Interactive Plotly chart builders for Valuation Football Field and Peer Scatter analysis."""

from __future__ import annotations

import math
from collections.abc import Sequence

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from fundamental_memo.schemas import (
    DcfSensitivity,
    FinancialSnapshot,
    PeerComparable,
    ValuationAnalysis,
)
from fundamental_memo.valuation_engine import compute_target_multiples

TARGET_ACCENT_COLOR = "#FF4B4B"
PEER_MUTED_COLOR = "#64748B"
MEDIAN_LINE_COLOR = "#94A3B8"
CONSENSUS_LINE_COLOR = "#38BDF8"
REVENUE_BAR_COLOR = "#3B82F6"
MARGIN_LINE_COLOR = "#F59E0B"
SCATTER_MAX_BUBBLE_PX = 42.0


def build_valuation_football_field(
    snapshot: FinancialSnapshot,
    valuation: ValuationAnalysis,
    sensitivity: DcfSensitivity,
) -> go.Figure:
    """Build a horizontal Valuation Football Field comparing share-price valuation ranges.

    Displays available horizontal range bars for:
    - 52-Week Trading Range (52w_low to 52w_high)
    - Perpetuity DCF Sensitivity (WACC +1% to WACC -1%)
    - Exit Multiple DCF Valuation (WACC +1% to WACC -1%, centered on exit_multiple_dcf_value)
    - Peer Comps Valuation Range (25th to 75th percentile implied share price)
    Overlaid with a vertical dashed Current Price reference line and non-overlapping top callout.
    """
    labels: list[str] = []
    lows: list[float] = []
    highs: list[float] = []
    colors: list[str] = []
    hover_texts: list[str] = []

    if (
        snapshot.fifty_two_week_low is not None
        and snapshot.fifty_two_week_high is not None
        and snapshot.fifty_two_week_high >= snapshot.fifty_two_week_low
    ):
        low = snapshot.fifty_two_week_low
        high = snapshot.fifty_two_week_high
        labels.append("52-Week Trading Range")
        lows.append(low)
        highs.append(high)
        colors.append("#94A3B8")
        hover_texts.append(f"52-Week Range: ${low:,.2f} – ${high:,.2f}")

    dcf_low = min(sensitivity.high_wacc_value_per_share, sensitivity.low_wacc_value_per_share)
    dcf_high = max(sensitivity.high_wacc_value_per_share, sensitivity.low_wacc_value_per_share)
    labels.append("Perpetuity DCF Sensitivity")
    lows.append(dcf_low)
    highs.append(dcf_high)
    colors.append("#2563EB")
    hover_texts.append(
        f"Perpetuity DCF (WACC ±1%): ${dcf_low:,.2f} – ${dcf_high:,.2f} "
        f"(Base: ${valuation.dcf_intrinsic_value_per_share:,.2f})"
    )

    if valuation.exit_multiple_dcf_value is not None:
        exit_low_raw = (
            valuation.exit_multiple_high_wacc_value
            if valuation.exit_multiple_high_wacc_value is not None
            else valuation.exit_multiple_dcf_value * 0.95
        )
        exit_high_raw = (
            valuation.exit_multiple_low_wacc_value
            if valuation.exit_multiple_low_wacc_value is not None
            else valuation.exit_multiple_dcf_value * 1.05
        )
        exit_low = min(exit_low_raw, exit_high_raw)
        exit_high = max(exit_low_raw, exit_high_raw)
        exit_mult = valuation.dcf_assumptions.get("target_exit_ev_ebitda", 15.0)
        labels.append("Exit Multiple DCF Valuation")
        lows.append(exit_low)
        highs.append(exit_high)
        colors.append("#0EA5E9")
        hover_texts.append(
            f"Exit Multiple ({exit_mult:.1f}x EV/EBITDA): ${exit_low:,.2f} – ${exit_high:,.2f} "
            f"(Base: ${valuation.exit_multiple_dcf_value:,.2f})"
        )

    if (
        valuation.peer_comps_p25_value is not None
        and valuation.peer_comps_p75_value is not None
    ):
        p25 = min(valuation.peer_comps_p25_value, valuation.peer_comps_p75_value)
        p75 = max(valuation.peer_comps_p25_value, valuation.peer_comps_p75_value)
        labels.append("Peer Comps Valuation Range")
        lows.append(p25)
        highs.append(p75)
        colors.append("#10B981")
        comps_med_str = (
            f"${valuation.implied_value_by_comps:,.2f}"
            if valuation.implied_value_by_comps is not None
            else "N/A"
        )
        hover_texts.append(
            f"Peer Comps (25th–75th pct): ${p25:,.2f} – ${p75:,.2f} (Median: {comps_med_str})"
        )

    spans = [max(high - low, 1.0) for low, high in zip(lows, highs, strict=True)]
    range_annotations = [
        f"${low:,.0f} – ${high:,.0f}" for low, high in zip(lows, highs, strict=True)
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=labels,
            x=spans,
            base=lows,
            orientation="h",
            marker={"color": colors, "opacity": 0.85},
            text=range_annotations,
            textposition="outside",
            cliponaxis=False,
            hovertext=hover_texts,
            hoverinfo="text",
            name="Valuation Range",
            showlegend=False,
        )
    )

    fig.add_vline(
        x=snapshot.current_price,
        line_width=2,
        line_dash="dash",
        line_color=TARGET_ACCENT_COLOR,
    )

    all_values = [*lows, *highs, snapshot.current_price]
    if snapshot.analyst_target_mean is not None and snapshot.analyst_target_mean > 0.0:
        all_values.append(snapshot.analyst_target_mean)

    min_val = min(all_values)
    max_val = max(all_values)
    x_min = max(0.0, min_val * 0.75)
    x_max = max_val * 1.22

    # Permanently stagger top reference annotations in both vertical paper coordinate and
    # opposite horizontal anchors so Current Price and Analyst Consensus Target never collide.
    fig.add_annotation(
        x=snapshot.current_price,
        y=1.12,
        yref="paper",
        xanchor="right",
        xshift=-4,
        showarrow=False,
        text=f"Current Price: ${snapshot.current_price:,.2f}",
        font={"color": TARGET_ACCENT_COLOR, "size": 12},
    )

    if snapshot.analyst_target_mean is not None and snapshot.analyst_target_mean > 0.0:
        fig.add_vline(
            x=snapshot.analyst_target_mean,
            line_width=2,
            line_dash="dot",
            line_color=CONSENSUS_LINE_COLOR,
        )
        fig.add_annotation(
            x=snapshot.analyst_target_mean,
            y=1.03,
            yref="paper",
            xanchor="left",
            xshift=4,
            showarrow=False,
            text=f"Analyst Consensus Target: ${snapshot.analyst_target_mean:,.2f}",
            font={"color": CONSENSUS_LINE_COLOR, "size": 12},
        )

    fig.update_layout(
        title=f"Valuation Football Field — {snapshot.ticker}",
        xaxis_title="Implied Share Price (USD)",
        yaxis={"autorange": "reversed"},
        xaxis={"range": [x_min, x_max], "tickprefix": "$"},
        margin={"l": 10, "r": 40, "t": 78, "b": 40},
        height=380,
    )
    return fig


def build_peer_valuation_scatter(
    snapshot: FinancialSnapshot,
    peers: Sequence[PeerComparable],
    *,
    peer_median_ev_ebitda: float | None = None,
) -> go.Figure:
    """Build a Peer Valuation vs. Growth scatter chart highlighting Target vs. Peers.

    X-axis: Historical Revenue Growth (%)
    Y-axis: EV / EBITDA (x)
    Bubble size: Market Cap using sizemode="area" and sizeref = 2.0 * max(market_caps) / (42**2)
    Colors: Target ticker in #FF4B4B, peers in #64748B, with horizontal Peer Median line.
    """
    target_multiples = compute_target_multiples(snapshot)
    target_ev_ebitda = target_multiples["ev_to_ebitda"]

    peer_points: list[tuple[str, float, float, float | None, str]] = []
    for peer in peers:
        if (
            peer.ev_to_ebitda is not None
            and math.isfinite(peer.ev_to_ebitda)
            and peer.ev_to_ebitda > 0.0
            and peer.revenue_growth_3y is not None
            and math.isfinite(peer.revenue_growth_3y)
        ):
            size_metric = peer.market_cap if peer.market_cap is not None else peer.fcf_yield
            size_desc = (
                f"Mkt Cap: ${peer.market_cap / 1e9:,.1f}B"
                if peer.market_cap is not None
                else (
                    f"FCF Yield: {peer.fcf_yield * 100.0:.2f}%"
                    if peer.fcf_yield is not None
                    else "Size: N/A"
                )
            )
            hover = (
                f"<b>{peer.ticker}</b><br>"
                f"Rev Growth: {peer.revenue_growth_3y * 100.0:.1f}%<br>"
                f"EV/EBITDA: {peer.ev_to_ebitda:.1f}x<br>{size_desc}"
            )
            peer_points.append(
                (
                    peer.ticker,
                    peer.revenue_growth_3y * 100.0,
                    peer.ev_to_ebitda,
                    size_metric,
                    hover,
                )
            )

    target_point: tuple[str, float, float, float | None, str] | None = None
    if target_ev_ebitda is not None and math.isfinite(target_ev_ebitda) and target_ev_ebitda > 0.0:
        target_hover = (
            f"<b>{snapshot.ticker} (Target)</b><br>"
            f"Rev Growth: {snapshot.historical_revenue_growth_3y * 100.0:.1f}%<br>"
            f"EV/EBITDA: {target_ev_ebitda:.1f}x<br>"
            f"Mkt Cap: ${snapshot.market_cap / 1e9:,.1f}B"
        )
        target_point = (
            snapshot.ticker,
            snapshot.historical_revenue_growth_3y * 100.0,
            target_ev_ebitda,
            snapshot.market_cap,
            target_hover,
        )

    market_caps: list[float] = [
        pt[3] for pt in peer_points if pt[3] is not None and math.isfinite(pt[3]) and pt[3] > 0.0
    ]
    if (
        target_point is not None
        and target_point[3] is not None
        and math.isfinite(target_point[3])
        and target_point[3] > 0.0
    ):
        market_caps.append(target_point[3])

    max_cap = max(market_caps) if market_caps else 1.0
    sizeref = (2.0 * max_cap) / (SCATTER_MAX_BUBBLE_PX**2)
    fallback_cap = max_cap * 0.15

    peer_sizes = [
        pt[3] if (pt[3] is not None and math.isfinite(pt[3]) and pt[3] > 0.0) else fallback_cap
        for pt in peer_points
    ]
    target_size = (
        target_point[3]
        if (
            target_point is not None
            and target_point[3] is not None
            and math.isfinite(target_point[3])
            and target_point[3] > 0.0
        )
        else fallback_cap
    )

    fig = go.Figure()
    if peer_points:
        fig.add_trace(
            go.Scatter(
                x=[pt[1] for pt in peer_points],
                y=[pt[2] for pt in peer_points],
                mode="markers+text",
                text=[pt[0] for pt in peer_points],
                textposition="top center",
                hovertext=[pt[4] for pt in peer_points],
                hoverinfo="text",
                name="Peers",
                marker={
                    "size": peer_sizes,
                    "sizemode": "area",
                    "sizeref": sizeref,
                    "sizemin": 8,
                    "color": PEER_MUTED_COLOR,
                    "opacity": 0.80,
                    "line": {"width": 1.5, "color": "#FFFFFF"},
                },
            )
        )

    if target_point is not None:
        fig.add_trace(
            go.Scatter(
                x=[target_point[1]],
                y=[target_point[2]],
                mode="markers+text",
                text=[target_point[0]],
                textposition="top center",
                textfont={"color": TARGET_ACCENT_COLOR, "size": 13},
                hovertext=[target_point[4]],
                hoverinfo="text",
                name=f"Target ({snapshot.ticker})",
                marker={
                    "size": [target_size],
                    "sizemode": "area",
                    "sizeref": sizeref,
                    "sizemin": 10,
                    "color": TARGET_ACCENT_COLOR,
                    "opacity": 0.95,
                    "line": {"width": 2.0, "color": "#FFFFFF"},
                },
            )
        )

    if peer_median_ev_ebitda is not None and math.isfinite(peer_median_ev_ebitda):
        fig.add_hline(
            y=peer_median_ev_ebitda,
            line_width=1.5,
            line_dash="dash",
            line_color=MEDIAN_LINE_COLOR,
            annotation_text=f"Peer Median ({peer_median_ev_ebitda:.1f}x)",
            annotation_position="top left",
            annotation_font_color=PEER_MUTED_COLOR,
            annotation_font_size=11,
        )

    fig.update_layout(
        title=f"Peer Valuation vs. Growth — {snapshot.ticker}",
        xaxis_title="Historical Revenue Growth (%)",
        yaxis_title="EV / EBITDA (x)",
        xaxis={"ticksuffix": "%"},
        yaxis={"ticksuffix": "x"},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1.0},
        margin={"l": 10, "r": 20, "t": 62, "b": 40},
        height=370,
    )
    return fig


def build_historical_trajectory_chart(snapshot: FinancialSnapshot) -> go.Figure:
    """Build a dual-axis 3-Year Historical Trajectory chart (Revenue bars + Op Margin line)."""
    points = snapshot.historical_trajectory
    periods = [point.period for point in points]
    revenues_billions = [point.revenue / 1_000_000_000.0 for point in points]
    op_margins_pct = [
        point.operating_margin * 100.0 if point.operating_margin is not None else None
        for point in points
    ]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=periods,
            y=revenues_billions,
            name="Revenue ($B)",
            marker={"color": REVENUE_BAR_COLOR, "opacity": 0.85},
            text=[f"${rev:,.1f}B" for rev in revenues_billions],
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>Revenue: $%{y:,.2f}B<extra></extra>",
        ),
        secondary_y=False,
    )

    if any(margin is not None for margin in op_margins_pct):
        fig.add_trace(
            go.Scatter(
                x=periods,
                y=op_margins_pct,
                mode="lines+markers+text",
                name="Operating Margin (%)",
                line={"color": MARGIN_LINE_COLOR, "width": 3},
                marker={"color": MARGIN_LINE_COLOR, "size": 9},
                text=[
                    f"{margin:.1f}%" if margin is not None else "" for margin in op_margins_pct
                ],
                textposition="top center",
                hovertemplate="<b>%{x}</b><br>Operating Margin: %{y:.1f}%<extra></extra>",
            ),
            secondary_y=True,
        )

    max_rev = max(revenues_billions) if revenues_billions else 1.0
    fig.update_yaxes(
        title_text="Revenue ($B)",
        tickprefix="$",
        ticksuffix="B",
        range=[0.0, max_rev * 1.25],
        secondary_y=False,
    )
    fig.update_yaxes(
        title_text="Operating Margin (%)",
        ticksuffix="%",
        secondary_y=True,
    )
    fig.update_layout(
        title=f"3-Year Historical Trajectory — {snapshot.ticker}",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1.0},
        margin={"l": 10, "r": 10, "t": 62, "b": 36},
        height=340,
    )
    return fig
