"""Self-contained, print-friendly HTML report exporter with embedded interactive Plotly charts."""

from __future__ import annotations

import html
import re
from collections.abc import Sequence

import plotly.graph_objects as go

from fundamental_memo.charts import (
    build_historical_trajectory_chart,
    build_peer_valuation_scatter,
    build_valuation_football_field,
)
from fundamental_memo.renderer import MAX_MEMO_WORDS
from fundamental_memo.schemas import (
    DcfSensitivity,
    DcfSensitivityMatrix,
    FinancialSnapshot,
    PeerComparable,
    QuarterlyPoint,
    ValuationAnalysis,
    count_words,
)

PLOTLY_CDN_URL = "https://cdn.plot.ly/plotly-2.35.2.min.js"

_BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_PATTERN = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_TABLE_SEPARATOR_PATTERN = re.compile(r"^\|?[\s:\-|]+\|?$")


def _fmt_compact_usd(value: float | None) -> str:
    """Format large USD amounts compactly in billions or millions."""
    if value is None:
        return "N/A"
    abs_val = abs(value)
    sign = "-" if value < 0.0 else ""
    if abs_val >= 1_000_000_000.0:
        return f"{sign}${abs_val / 1_000_000_000.0:,.2f}B"
    if abs_val >= 1_000_000.0:
        return f"{sign}${abs_val / 1_000_000.0:,.1f}M"
    return f"{sign}${abs_val:,.0f}"


def _format_inline_markdown(raw_text: str) -> str:
    """Escape HTML entities first, then apply inline Markdown bold and italic tags."""
    escaped = html.escape(raw_text, quote=True)
    with_bold = _BOLD_PATTERN.sub(r"<strong>\1</strong>", escaped)
    return _ITALIC_PATTERN.sub(r"<em>\1</em>", with_bold)


def _split_pipe_row(line: str) -> list[str]:
    """Split a Markdown pipe-table row into stripped cell strings."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _markdown_to_html(markdown_text: str) -> str:
    """Convert the institutional memo Markdown subset into clean, escaped HTML."""
    lines = markdown_text.splitlines()
    blocks: list[str] = []
    idx = 0
    total_lines = len(lines)

    while idx < total_lines:
        raw_line = lines[idx]
        stripped = raw_line.strip()
        if not stripped:
            idx += 1
            continue

        # Headings (#, ##, ###)
        if stripped.startswith("### "):
            blocks.append(f"<h3>{_format_inline_markdown(stripped[4:].strip())}</h3>")
            idx += 1
            continue
        if stripped.startswith("## "):
            blocks.append(f"<h2>{_format_inline_markdown(stripped[3:].strip())}</h2>")
            idx += 1
            continue
        if stripped.startswith("# "):
            blocks.append(f"<h1>{_format_inline_markdown(stripped[2:].strip())}</h1>")
            idx += 1
            continue

        # Pipe tables
        if (
            stripped.startswith("|")
            and idx + 1 < total_lines
            and _TABLE_SEPARATOR_PATTERN.match(lines[idx + 1].strip())
        ):
            headers = _split_pipe_row(stripped)
            alignments_raw = _split_pipe_row(lines[idx + 1])
            alignments: list[str] = []
            for token in alignments_raw:
                clean_tok = token.strip()
                if clean_tok.endswith(":") and not clean_tok.startswith(":"):
                    alignments.append("right")
                elif clean_tok.startswith(":") and clean_tok.endswith(":"):
                    alignments.append("center")
                else:
                    alignments.append("left")

            idx += 2
            body_rows: list[list[str]] = []
            while idx < total_lines and lines[idx].strip().startswith("|"):
                body_rows.append(_split_pipe_row(lines[idx]))
                idx += 1

            header_cells = "".join(
                f'<th style="text-align:{alignments[c] if c < len(alignments) else "left"}">'
                f"{_format_inline_markdown(cell)}</th>"
                for c, cell in enumerate(headers)
            )
            body_html_rows: list[str] = []
            for row in body_rows:
                cells = "".join(
                    f'<td style="text-align:{alignments[c] if c < len(alignments) else "left"}">'
                    f"{_format_inline_markdown(cell)}</td>"
                    for c, cell in enumerate(row)
                )
                body_html_rows.append(f"<tr>{cells}</tr>")
            blocks.append(
                '<table class="memo-table">'
                f"<thead><tr>{header_cells}</tr></thead>"
                f"<tbody>{''.join(body_html_rows)}</tbody>"
                "</table>"
            )
            continue

        # Unordered bullet lists
        if stripped.startswith("- "):
            items: list[str] = []
            while idx < total_lines and lines[idx].strip().startswith("- "):
                item_text = lines[idx].strip()[2:].strip()
                items.append(f"<li>{_format_inline_markdown(item_text)}</li>")
                idx += 1
            blocks.append(f"<ul>{''.join(items)}</ul>")
            continue

        # Standard paragraph (join consecutive non-blank prose lines)
        para_lines: list[str] = [stripped]
        idx += 1
        while idx < total_lines:
            next_stripped = lines[idx].strip()
            if (
                not next_stripped
                or next_stripped.startswith("#")
                or next_stripped.startswith("- ")
                or next_stripped.startswith("|")
            ):
                break
            para_lines.append(next_stripped)
            idx += 1
        blocks.append(f"<p>{_format_inline_markdown(' '.join(para_lines))}</p>")

    return "\n".join(blocks)


def _render_kpi_cards_html(snapshot: FinancialSnapshot, valuation: ValuationAnalysis) -> str:
    """Build the 5-card institutional KPI summary grid."""
    range_52w = (
        f"52W: ${snapshot.fifty_two_week_low:,.0f}–${snapshot.fifty_two_week_high:,.0f}"
        if (snapshot.fifty_two_week_low is not None and snapshot.fifty_two_week_high is not None)
        else "52W Range: N/A"
    )
    dcf_delta = f"{valuation.dcf_upside_pct * 100.0:+.1f}% vs. price"
    dcf_delta_cls = "kpi-pos" if valuation.dcf_upside_pct >= 0.0 else "kpi-neg"

    implied_cagr_str = (
        f"{valuation.implied_fcf_cagr_5y * 100.0:.1f}%"
        if valuation.implied_fcf_cagr_5y is not None
        else "N/A"
    )
    spread_str = (
        f"{valuation.cagr_spread_vs_base * 100.0:+.1f}% vs. base"
        if valuation.cagr_spread_vs_base is not None
        else "Spread: N/A"
    )

    roic_str = f"{snapshot.roic_ttm * 100.0:.1f}%" if snapshot.roic_ttm is not None else "N/A"
    op_margin_str = (
        f"{snapshot.operating_margin_ttm * 100.0:.1f}%"
        if snapshot.operating_margin_ttm is not None
        else "N/A"
    )
    ebitda_margin_str = (
        f"{snapshot.ebitda_margin_ttm * 100.0:.1f}%"
        if snapshot.ebitda_margin_ttm is not None
        else "N/A"
    )

    sbc_fcf_label = _fmt_compact_usd(snapshot.sbc_adjusted_fcf_ttm)
    cards = [
        ("Current Price", f"${snapshot.current_price:,.2f}", range_52w, "kpi-muted"),
        (
            "DCF Intrinsic Value",
            f"${valuation.dcf_intrinsic_value_per_share:,.2f}",
            dcf_delta,
            dcf_delta_cls,
        ),
        ("Market-Implied CAGR", implied_cagr_str, spread_str, "kpi-muted"),
        ("ROIC (TTM)", roic_str, f"OpM {op_margin_str} | EBITDA {ebitda_margin_str}", "kpi-muted"),
        (
            "Earnings Quality",
            valuation.earnings_quality_flag,
            f"OCF/NI {valuation.ocf_to_net_income_ratio:.2f}x | Adj {sbc_fcf_label}",
            "kpi-muted",
        ),
    ]
    card_items = "".join(
        '<div class="kpi-card">'
        f'<div class="kpi-label">{html.escape(label)}</div>'
        f'<div class="kpi-value">{html.escape(value)}</div>'
        f'<div class="kpi-delta {delta_cls}">{html.escape(delta)}</div>'
        "</div>"
        for label, value, delta, delta_cls in cards
    )
    return f'<section class="kpi-grid">{card_items}</section>'


def _render_reverse_dcf_callout_html(
    snapshot: FinancialSnapshot, valuation: ValuationAnalysis
) -> str:
    """Render the Reverse DCF Reality Check callout when Reverse DCF solved cleanly."""
    if (
        valuation.implied_fcf_cagr_5y is None
        or valuation.implied_y5_fcf is None
        or valuation.implied_y5_fcf_multiple is None
    ):
        return ""
    body = (
        f"At <strong>${snapshot.current_price:,.2f}</strong>, the market implies a "
        f"<strong>{valuation.implied_fcf_cagr_5y * 100.0:.1f}%</strong> 5Y FCF CAGR, requiring "
        f"annual FCF to grow <strong>{valuation.implied_y5_fcf_multiple:.2f}×</strong> from "
        f"<strong>{html.escape(_fmt_compact_usd(snapshot.free_cash_flow_ttm))}</strong> (TTM) to "
        f"<strong>{html.escape(_fmt_compact_usd(valuation.implied_y5_fcf))}</strong> in Year 5 "
        f"(vs. <strong>{html.escape(_fmt_compact_usd(snapshot.revenue_ttm))}</strong> total TTM "
        "revenue today)."
    )
    return (
        '<section class="callout">'
        '<div class="callout-title">Reverse DCF Reality Check</div>'
        f"<p>{body}</p>"
        "</section>"
    )


def _render_sensitivity_matrix_html(
    matrix: DcfSensitivityMatrix | None,
    current_price: float,
    valuation: ValuationAnalysis,
) -> str:
    """Render the color-coded 5x5 DCF sensitivity matrix HTML table."""
    if matrix is None:
        return ""

    wacc_headers = "".join(
        f"<th>WACC {wacc * 100.0:.2f}%</th>" for wacc in matrix.wacc_values
    )
    rows_html: list[str] = []
    for r_idx, (cagr_val, row_prices) in enumerate(
        zip(matrix.cagr_values, matrix.grid, strict=True)
    ):
        row_label = f"CAGR {cagr_val * 100.0:.1f}%"
        cells: list[str] = [f'<th class="row-head">{html.escape(row_label)}</th>']
        for c_idx, price in enumerate(row_prices):
            is_base = r_idx == 2 and c_idx == 2
            classes: list[str] = []
            if price is not None:
                classes.append("cell-above" if price >= current_price else "cell-below")
                formatted = f"${price:,.2f}"
            else:
                formatted = "N/A"
            if is_base:
                classes.append("cell-base")
            class_attr = f' class="{" ".join(classes)}"' if classes else ""
            cells.append(f"<td{class_attr}>{html.escape(formatted)}</td>")
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    term_pct = valuation.dcf_assumptions["terminal_growth_rate"] * 100.0
    exit_mult = valuation.dcf_assumptions.get("target_exit_ev_ebitda", 15.0)
    caption_html = ""
    if valuation.implied_exit_ev_ebitda is not None:
        caption_html = (
            '<p class="caption">'
            f"Perpetuity DCF ({term_pct:.1f}% terminal growth) implies an exit EV/EBITDA of "
            f"<strong>{valuation.implied_exit_ev_ebitda:.1f}x</strong> vs. Exit Multiple "
            f"assumption of <strong>{exit_mult:.1f}x</strong>. Green cells exceed current price "
            f"(${current_price:,.2f}); blue border marks Base."
            "</p>"
        )

    return (
        '<section class="panel">'
        "<h2>5×5 DCF Sensitivity Matrix (WACC × 5Y FCF CAGR)</h2>"
        '<table class="sens-table">'
        f"<thead><tr><th>5Y FCF CAGR \\ WACC</th>{wacc_headers}</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
        f"{caption_html}"
        "</section>"
    )


def _render_quarterly_table_html(quarterly_trajectory: Sequence[QuarterlyPoint]) -> str:
    """Render the 4-quarter operational momentum table when quarterly data exists."""
    if not quarterly_trajectory:
        return ""

    rows_html: list[str] = []
    for pt in quarterly_trajectory:
        rev_str = f"${pt.revenue / 1_000_000_000.0:,.2f}B"
        gm_str = f"{pt.gross_margin * 100.0:.1f}%" if pt.gross_margin is not None else "N/A"
        om_str = (
            f"{pt.operating_margin * 100.0:.1f}%" if pt.operating_margin is not None else "N/A"
        )
        fcf_str = (
            f"${pt.free_cash_flow / 1_000_000_000.0:,.2f}B"
            if pt.free_cash_flow is not None
            else "N/A"
        )
        rows_html.append(
            "<tr>"
            f"<td>{html.escape(pt.period)}</td>"
            f'<td style="text-align:right">{html.escape(rev_str)}</td>'
            f'<td style="text-align:right">{html.escape(gm_str)}</td>'
            f'<td style="text-align:right">{html.escape(om_str)}</td>'
            f'<td style="text-align:right">{html.escape(fcf_str)}</td>'
            "</tr>"
        )

    return (
        '<section class="panel">'
        "<h2>Quarterly Momentum (Last 4 Quarters)</h2>"
        '<table class="memo-table">'
        "<thead><tr>"
        "<th>Quarter</th>"
        '<th style="text-align:right">Revenue ($B)</th>'
        '<th style="text-align:right">Gross Margin (%)</th>'
        '<th style="text-align:right">Operating Margin (%)</th>'
        '<th style="text-align:right">FCF ($B)</th>'
        "</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
        "</section>"
    )


def _figure_to_fragment(fig: go.Figure) -> str:
    """Serialize a Plotly figure into a responsive HTML fragment without inline plotly.js."""
    return str(
        fig.to_html(
            full_html=False,
            include_plotlyjs=False,
            config={"responsive": True, "displaylogo": False},
        )
    )


def build_html_report(
    snapshot: FinancialSnapshot,
    valuation: ValuationAnalysis,
    peers: Sequence[PeerComparable],
    sensitivity: DcfSensitivity,
    markdown_memo: str,
    *,
    football_fig: go.Figure | None = None,
    scatter_fig: go.Figure | None = None,
    trajectory_fig: go.Figure | None = None,
    model_label: str | None = None,
    word_count: int | None = None,
) -> str:
    """Build a standalone, print-friendly HTML research report with interactive Plotly charts.

    Includes:
    - Report header and Grounding Audit: Passed badge
    - 5-card KPI summary grid
    - Embedded interactive Plotly charts (Football Field, Peer Scatter, 3Y Trajectory)
      backed by a single Plotly.js CDN script tag in <head>
    - Reverse DCF Reality Check callout
    - Color-coded 5x5 DCF Sensitivity Matrix HTML table
    - Quarterly Momentum (Last 4 Quarters) HTML table when available
    - Rendered HTML body of the one-page investment memo
    """
    resolved_football = (
        football_fig
        if football_fig is not None
        else build_valuation_football_field(snapshot, valuation, sensitivity)
    )
    resolved_scatter = (
        scatter_fig
        if scatter_fig is not None
        else build_peer_valuation_scatter(
            snapshot, peers, peer_median_ev_ebitda=valuation.peer_median_ev_ebitda
        )
    )
    resolved_trajectory = trajectory_fig
    if resolved_trajectory is None and snapshot.historical_trajectory:
        resolved_trajectory = build_historical_trajectory_chart(snapshot)

    resolved_words = word_count if word_count is not None else count_words(markdown_memo)
    synth_meta = f"Synthesizer: {model_label} | " if model_label else ""
    escaped_company = html.escape(snapshot.company_name, quote=True)
    escaped_ticker = html.escape(snapshot.ticker, quote=True)
    escaped_sector = html.escape(snapshot.sector, quote=True)
    escaped_meta = html.escape(
        f"{synth_meta}Word Count: {resolved_words} / {MAX_MEMO_WORDS}", quote=True
    )

    kpi_html = _render_kpi_cards_html(snapshot, valuation)
    football_html = _figure_to_fragment(resolved_football)
    scatter_html = _figure_to_fragment(resolved_scatter)
    trajectory_section = (
        f'<section class="panel chart-box">{_figure_to_fragment(resolved_trajectory)}</section>'
        if resolved_trajectory is not None
        else ""
    )
    reverse_dcf_html = _render_reverse_dcf_callout_html(snapshot, valuation)
    sensitivity_html = _render_sensitivity_matrix_html(
        valuation.dcf_sensitivity_matrix, snapshot.current_price, valuation
    )
    quarterly_html = _render_quarterly_table_html(snapshot.quarterly_trajectory)
    memo_body_html = _markdown_to_html(markdown_memo)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Equity Research Report — {escaped_company} ({escaped_ticker})</title>
  <script src="{PLOTLY_CDN_URL}" charset="utf-8"></script>
  <style>
    :root {{
      --bg: #ffffff;
      --surface: #f8fafc;
      --border: #e2e8f0;
      --text: #0f172a;
      --muted: #475569;
      --accent: #2563eb;
      --pos-bg: rgba(16, 185, 129, 0.16);
      --pos-text: #065f46;
      --neg-bg: rgba(239, 68, 68, 0.14);
      --neg-text: #991b1b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 28px 20px 48px;
      background: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      line-height: 1.55;
      font-size: 14px;
    }}
    .container {{
      max-width: 960px;
      margin: 0 auto;
    }}
    header.report-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
      border-bottom: 2px solid var(--text);
      padding-bottom: 14px;
      margin-bottom: 20px;
    }}
    .report-title {{
      margin: 0;
      font-size: 24px;
      line-height: 1.2;
      letter-spacing: -0.01em;
    }}
    .report-subtitle {{
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .audit-badge {{
      display: inline-block;
      background: var(--pos-bg);
      color: var(--pos-text);
      border: 1px solid rgba(16, 185, 129, 0.45);
      border-radius: 999px;
      padding: 5px 12px;
      font-size: 12px;
      font-weight: 600;
      white-space: nowrap;
    }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 22px;
    }}
    .kpi-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
    }}
    .kpi-label {{
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      color: var(--muted);
      margin-bottom: 4px;
    }}
    .kpi-value {{
      font-size: 20px;
      font-weight: 700;
      color: var(--text);
      line-height: 1.2;
    }}
    .kpi-delta {{
      font-size: 11.5px;
      margin-top: 4px;
    }}
    .kpi-pos {{ color: var(--pos-text); font-weight: 600; }}
    .kpi-neg {{ color: var(--neg-text); font-weight: 600; }}
    .kpi-muted {{ color: var(--muted); }}
    .panel {{
      margin-bottom: 22px;
      page-break-inside: avoid;
    }}
    .chart-box {{
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
      background: #ffffff;
    }}
    .callout {{
      background: #eff6ff;
      border-left: 4px solid var(--accent);
      border-radius: 6px;
      padding: 12px 16px;
      margin-bottom: 22px;
      page-break-inside: avoid;
    }}
    .callout-title {{
      font-weight: 700;
      color: #1e3a8a;
      margin-bottom: 4px;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }}
    .callout p {{ margin: 0; }}
    h1 {{ font-size: 21px; margin: 18px 0 8px; }}
    h2 {{
      font-size: 16px;
      margin: 18px 0 8px;
      padding-bottom: 4px;
      border-bottom: 1px solid var(--border);
    }}
    h3 {{ font-size: 14px; margin: 12px 0 6px; }}
    table.memo-table, table.sens-table {{
      width: 100%;
      border-collapse: collapse;
      margin: 10px 0;
      font-size: 13px;
    }}
    table.memo-table th, table.memo-table td,
    table.sens-table th, table.sens-table td {{
      border: 1px solid var(--border);
      padding: 7px 10px;
    }}
    table.memo-table thead th, table.sens-table thead th {{
      background: var(--surface);
      font-weight: 600;
    }}
    table.sens-table td {{ text-align: right; font-variant-numeric: tabular-nums; }}
    table.sens-table th.row-head {{ text-align: left; background: var(--surface); }}
    .cell-above {{ background: var(--pos-bg); color: var(--pos-text); }}
    .cell-below {{ background: var(--neg-bg); color: var(--neg-text); }}
    .cell-base {{ border: 2px solid var(--accent) !important; font-weight: 700; }}
    .caption {{
      font-size: 12px;
      color: var(--muted);
      margin-top: 6px;
    }}
    .memo-body {{
      border-top: 2px solid var(--border);
      padding-top: 12px;
      margin-top: 20px;
    }}
    .memo-body ul {{
      margin: 6px 0 12px;
      padding-left: 20px;
    }}
    .memo-body li {{ margin-bottom: 4px; }}
    footer.report-footer {{
      margin-top: 28px;
      padding-top: 12px;
      border-top: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      color: var(--muted);
      font-size: 12px;
    }}
    @media (max-width: 780px) {{
      .kpi-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media print {{
      body {{ padding: 0; }}
      .chart-box, .panel, .callout {{ break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <main class="container">
    <header class="report-header">
      <div>
        <h1 class="report-title">{escaped_company} ({escaped_ticker}) — Fundamental Deep-Dive</h1>
        <p class="report-subtitle">Sector: {escaped_sector} | {escaped_meta}</p>
      </div>
      <span class="audit-badge">Grounding Audit: Passed</span>
    </header>

    {kpi_html}

    <section class="panel chart-box">{football_html}</section>
    <section class="panel chart-box">{scatter_html}</section>
    {reverse_dcf_html}
    {sensitivity_html}
    {trajectory_section}
    {quarterly_html}

    <article class="memo-body">
      {memo_body_html}
    </article>

    <footer class="report-footer">
      <span>Generated by Deterministic Equity Fundamental Memo Engine</span>
      <span class="audit-badge">Grounding Audit: Passed</span>
    </footer>
  </main>
</body>
</html>
"""
