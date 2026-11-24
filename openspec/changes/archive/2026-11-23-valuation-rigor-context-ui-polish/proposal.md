## Why

Live market feeds frequently report stale or inconsistent `enterpriseValue` figures relative to live market cap and balance-sheet debt/cash, while the current memo prose repeats header metric ribbons and lacks concrete business-segment drivers, and the Streamlit UI exhibits KPI label truncation, clipped Football Field annotations, and lacks a 2D DCF sensitivity table. Consolidating deterministic valuation rigor, sanitized business context, anti-echoing synthesis rules, and chart/UI polish into one cohesive upgrade strengthens both analytical trustworthiness and visual presentation without compromising zero-hallucination guarantees.

## What Changes

- **Self-Consistent EV, Implied Exit Multiple & 5×5 DCF Sensitivity Matrix (`schemas.py`, `data_fetcher.py`, `valuation_engine.py`, `fixtures/mock_market_data.json`)**:
  - Deterministically compute `enterprise_value = market_cap + total_debt - cash_and_equivalents` instead of trusting upstream API `enterpriseValue`, and recompute `target_multiples.ev_to_ebitda` from it.
  - Compute `implied_exit_ev_ebitda = Terminal Value_{t=5} / EBITDA_{t=5}` from the Perpetuity DCF so users can compare it directly against `target_exit_ev_ebitda`.
  - Add a deterministic 5×5 `dcf_sensitivity_matrix` (`WACC` in `base ± {0, 0.5%, 1.0%}` × `5Y FCF CAGR` in `max(0, base ± {0, 2.5%, 5.0%})`) whose center cell matches `dcf_intrinsic_value_per_share`.
  - Ingest `longBusinessSummary` from `yfinance` `.info`, truncate cleanly to the first 2 sentences (max 450 characters), add realistic 2-sentence `business_summary` text to offline mock fixtures, and whitelist qualitative `business_summary` numeric tokens in the grounding auditor.
- **Anti-Echoing Prose & Business-Grounded Bull/Bear Cases (`memo_synthesizer.py`, `renderer.py`)**:
  - Enforce an Anti-Echoing prompt/synthesis rule so section bodies do not open by re-listing metrics already displayed in each section's top Key Metrics Ribbon.
  - Require `bull_case` and `bear_case` bullets to integrate at least one concrete business/segment driver from `financial_snapshot.business_summary` alongside financial durability/risks, updating both LLM prompts and deterministic offline mock synthesis.
- **Streamlit UI & Plotly Visual Polish (`charts.py`, `streamlit_app.py`)**:
  - Reformat the 5 top KPI cards (`Current Price`, `DCF Intrinsic Value`, `Market-Implied CAGR`, `ROIC (TTM)`, `Earnings Quality`) with concise labels/deltas to prevent `...` ellipsis truncation at desktop viewports (`>= 1280px`).
  - Fix Valuation Football Field right-edge label clipping using `xaxis.range = [min_val * 0.75, max_val * 1.22]` and move the `Current Price` callout cleanly above the top bar (`yref="paper", y=1.08, showarrow=False`).
  - Upgrade Peer Valuation vs. Growth Scatter with `sizemode="area"`, `sizeref = 2.0 * max(market_caps) / (42**2)`, and a horizontal dashed `Peer Median` EV/EBITDA reference line (`fig.add_hline`).
  - Render an interactive color-coded 5×5 DCF Sensitivity Table below the charts (highlighting the Base Case center cell, muted green above `current_price`, muted red/neutral below `current_price`) with an implied exit EV/EBITDA comparison caption.

## Capabilities

### New Capabilities

- `valuation-rigor-and-sensitivity-matrix`: Enforce self-consistent `enterprise_value` calculation, compute perpetuity-implied exit EV/EBITDA (`implied_exit_ev_ebitda`) and a 5×5 WACC × FCF CAGR sensitivity matrix (`dcf_sensitivity_matrix`), and ingest sanitized 2-sentence `business_summary` context across live and offline modes.
- `business-grounded-non-echoing-synthesis`: Enforce anti-echoing section prose (avoiding repetition of top Key Metrics Ribbons), ground Bull/Bear cases in concrete business/segment drivers from `business_summary`, and preserve zero-hallucination numeric grounding with `business_summary` token whitelisting.
- `ui-chart-and-sensitivity-polish`: Eliminate KPI card truncation across the 5-card header row, fix Football Field label padding and `Current Price` callout placement, add area-scaled bubbles and a `Peer Median` reference line to Peer Scatter, and render a color-coded 5×5 DCF Sensitivity Table with implied exit multiple caption.

### Modified Capabilities

<!-- None in openspec/specs/ yet (previous changes remain unarchived in openspec/changes/). -->

## Impact

- **Modified Modules**: `fundamental_memo/src/fundamental_memo/{schemas.py,data_fetcher.py,valuation_engine.py,memo_synthesizer.py,renderer.py,charts.py,streamlit_app.py,__init__.py}`, `fundamental_memo/src/fundamental_memo/fixtures/mock_market_data.json`, and `fundamental_memo/tests/*`.
- **Dependencies**: No new third-party dependencies required (`pandas`, `plotly`, `streamlit`, `pydantic`, `yfinance`, `openai` are already installed in `fundamental_memo/.venv`).
- **Backward Compatibility**: Fully additive on `ValuationAnalysis` (`implied_exit_ev_ebitda`, `dcf_sensitivity_matrix`) and `FinancialSnapshot` (`business_summary`); self-consistent `enterprise_value` overrides stale/mismatched API `enterpriseValue` values to guarantee exact accounting identity `EV = Market Cap + Total Debt - Cash`.
