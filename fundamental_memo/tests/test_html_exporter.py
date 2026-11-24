"""Unit tests for the standalone pure-Python interactive HTML report exporter."""

from __future__ import annotations

from fundamental_memo.data_fetcher import load_mock_market_data
from fundamental_memo.html_exporter import PLOTLY_CDN_URL, build_html_report
from fundamental_memo.memo_synthesizer import synthesize_mock_memo
from fundamental_memo.renderer import render_investment_memo
from fundamental_memo.valuation_engine import compute_dcf_sensitivity, run_valuation_analysis


def test_build_html_report_contains_all_sections_and_single_plotly_cdn() -> None:
    """Standalone HTML report bundles KPIs, charts, sensitivity, 4Q table, memo, and badge."""
    bundle = load_mock_market_data()
    valuation = run_valuation_analysis(bundle.snapshot, bundle.peers)
    sensitivity = compute_dcf_sensitivity(bundle.snapshot)
    memo = synthesize_mock_memo(bundle.snapshot, valuation, bundle.peers)
    markdown = render_investment_memo(
        bundle.snapshot, valuation, bundle.peers, memo, sensitivity=sensitivity
    )

    html_doc = build_html_report(
        bundle.snapshot,
        valuation,
        bundle.peers,
        sensitivity,
        markdown,
        model_label="Offline Deterministic Mock",
    )

    assert html_doc.lstrip().startswith("<!DOCTYPE html>")
    assert "max-width: 960px;" in html_doc
    # Exactly one Plotly.js CDN script tag in <head>
    assert html_doc.count(PLOTLY_CDN_URL) == 1
    assert "Grounding Audit: Passed" in html_doc
    assert "Reverse DCF Reality Check" in html_doc
    assert "5×5 DCF Sensitivity Matrix" in html_doc
    assert "Quarterly Momentum (Last 4 Quarters)" in html_doc
    assert "2024-Q1" in html_doc
    assert "2024-Q4" in html_doc
    # Rendered memo HTML sections and tables
    assert "<h2>Executive Thesis</h2>" in html_doc
    assert "<h2>Profitability &amp; Cash Quality</h2>" in html_doc
    assert "EBITDA Margin:" in html_doc
    assert "FCF Margin:" in html_doc
    assert '<table class="memo-table">' in html_doc
    assert '<table class="sens-table">' in html_doc
    # Embedded interactive Plotly fragments
    assert "Plotly.newPlot" in html_doc


def test_build_html_report_escapes_special_chars_and_handles_missing_optionals() -> None:
    """HTML exporter safely escapes company names and omits missing optional panels cleanly."""
    bundle = load_mock_market_data()
    special_snap = bundle.snapshot.model_copy(
        update={
            "company_name": "Alpha & <Beta> Corp",
            "analyst_target_mean": None,
            "historical_trajectory": [],
            "quarterly_trajectory": [],
        }
    )
    valuation = run_valuation_analysis(special_snap, bundle.peers)
    sensitivity = compute_dcf_sensitivity(special_snap)
    memo = synthesize_mock_memo(special_snap, valuation, bundle.peers)
    markdown = render_investment_memo(
        special_snap, valuation, bundle.peers, memo, sensitivity=sensitivity
    )

    html_doc = build_html_report(special_snap, valuation, bundle.peers, sensitivity, markdown)
    assert "Alpha &amp; &lt;Beta&gt; Corp" in html_doc
    assert "<Beta>" not in html_doc
    assert "Quarterly Momentum (Last 4 Quarters)" not in html_doc
    assert html_doc.count(PLOTLY_CDN_URL) == 1
