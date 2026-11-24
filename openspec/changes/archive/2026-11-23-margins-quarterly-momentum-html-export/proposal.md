## Why

Acquisitive technology companies often show depressed GAAP operating margins due to non-cash M&A intangible amortization even when EBITDA and Free Cash Flow margins remain elite, while annual trends alone can miss recent sequential inflection points. Adding deterministic `ebitda_margin_ttm`, `fcf_margin_ttm`, and 4-quarter `quarterly_trajectory` metrics, preventing Football Field callout overlap across all price spreads, and enabling a self-contained interactive HTML report export closes the final institutional research workflow loop while maintaining strict zero-hallucination guarantees.

## What Changes

- **Cash/EBITDA Margins & 4-Quarter Momentum (`schemas.py`, `data_fetcher.py`, `fixtures/mock_market_data.json`)**:
  - Add `ebitda_margin_ttm` (`ebitda_ttm / revenue_ttm`) and `fcf_margin_ttm` (`free_cash_flow_ttm / revenue_ttm`) to `FinancialSnapshot` (graceful `None` fallback when `revenue_ttm <= 0`).
  - Add `QuarterlyPoint` and `FinancialSnapshot.quarterly_trajectory` extracting the 4 most recent completed fiscal quarters ordered oldest to newest (`period`, `revenue`, `gross_margin`, `operating_margin`, `free_cash_flow`) from quarterly income/cash-flow statements, with realistic 4-quarter mock sequences in offline mode.
- **Amortization-Aware Profitability Synthesis (`memo_synthesizer.py`, `renderer.py`)**:
  - Add `*EBITDA Margin:* XX.X% | *FCF Margin:* XX.X%` to the `Profitability & Cash Quality` header ribbon.
  - Instruct LLM synthesis (and deterministic offline mock synthesis) that when `ebitda_margin_ttm - operating_margin_ttm > 0.15` (15 percentage points), explicitly contextualize cash-flow margin durability (`ebitda_margin_ttm` and `fcf_margin_ttm`) rather than framing GAAP `operating_margin_ttm` alone as operational deterioration—while strictly preserving opening-sentence anti-echoing and numeric grounding rules.
- **Chart Annotation Fix, Quarterly Momentum View & Standalone HTML Export (`charts.py`, `html_exporter.py`, `streamlit_app.py`)**:
  - Fix Valuation Football Field top reference annotation overlap permanently by staggering `Current Price` (`yref="paper", y=1.12, xanchor="right", xshift=-4`) and `Analyst Consensus Target` (`yref="paper", y=1.03, xanchor="left", xshift=4`) with sufficient top/right margin headroom (`t >= 65, r >= 40`).
  - Upgrade the Historical Trajectory section in Streamlit into a clean tabbed view (`Annual (3Y)` | `Quarterly (4Q)`) displaying the 3-year dual-axis chart on Tab 1 and a compact 4-quarter momentum dataframe (`Quarter`, `Revenue ($B)`, `Gross Margin (%)`, `Operating Margin (%)`, `FCF ($B)`) on Tab 2.
  - Add a dedicated pure-Python `build_html_report(...)` exporter (`html_exporter.py`) generating a standalone, print-friendly HTML report bundling the header, 5-card KPI grid, interactive Plotly charts (single Plotly.js CDN `<script>` in `<head>`), Reverse DCF Reality Check callout, color-coded 5×5 DCF Sensitivity Matrix table, 4-quarter momentum table, rendered HTML memo body, and `Grounding Audit: Passed` badge—exposed via a side-by-side `Download report_<TICKER>.html` button next to `Download memo_<TICKER>.md`.

## Capabilities

### New Capabilities

- `cash-ebitda-margins-and-quarterly-trajectory`: Deterministically compute `ebitda_margin_ttm` and `fcf_margin_ttm` on `FinancialSnapshot` and extract the last 4 completed fiscal quarters (`quarterly_trajectory`) across live `yfinance` and offline mock modes.
- `amortization-aware-profitability-synthesis`: Display EBITDA and FCF margins in the Profitability & Cash Quality ribbon, contextualize M&A amortization spreads (`ebitda_margin_ttm - operating_margin_ttm > 15pp`) in prose, and preserve strict opening-sentence anti-echoing and numeric grounding verification.
- `chart-stagger-quarterly-view-and-html-export`: Permanently eliminate Football Field annotation overlap via staggered anchor positioning, add a tabbed `Annual (3Y) | Quarterly (4Q)` trajectory view in Streamlit, and export a self-contained interactive HTML report (`report_<TICKER>.html`) beside the Markdown download.

### Modified Capabilities

<!-- None in openspec/specs/ yet (previous changes remain unarchived in openspec/changes/). -->

## Impact

- **New Module**: `fundamental_memo/src/fundamental_memo/html_exporter.py` (pure-Python standalone HTML report generator with zero external dependencies).
- **Modified Modules**: `fundamental_memo/src/fundamental_memo/{schemas.py,data_fetcher.py,memo_synthesizer.py,renderer.py,charts.py,streamlit_app.py,__init__.py}`, `fundamental_memo/src/fundamental_memo/fixtures/mock_market_data.json`, and `fundamental_memo/tests/*`.
- **Dependencies**: Zero new third-party dependencies required.
- **Backward Compatibility**: Fully additive schema extensions (`ebitda_margin_ttm`, `fcf_margin_ttm`, `QuarterlyPoint`, `quarterly_trajectory`) with graceful `None`/empty defaults.
