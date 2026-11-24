## Why

Trailing multiples alone distort growth equities undergoing rapid earnings expansion, and percentage Reverse DCF growth rates are far more actionable when translated into concrete Year-5 Free Cash Flow dollar magnitudes alongside a 3-year historical financial trajectory. Adding forward consensus multiples, Wall Street analyst targets, 3-year historical revenue/margin/FCF trends, one-click Bear/Base/Bull DCF presets, and stricter anti-echoing prose enforcement makes the memo and Streamlit interface immediately decision-ready for institutional equity committees while maintaining strict zero-hallucination guarantees.

## What Changes

- **Forward Multiples, Consensus Target & 3-Year Historical Trajectory (`schemas.py`, `data_fetcher.py`, `valuation_engine.py`, `fixtures/mock_market_data.json`)**:
  - Ingest forward consensus fields (`forwardPE`, forward EBITDA / `forward_ev_ebitda`, `targetMeanPrice` as `analyst_target_mean`, `numberOfAnalystOpinions` as `analyst_count`) with graceful `None` fallback, compute `target_multiples.forward_pe`, `target_multiples.forward_ev_ebitda`, and `target_multiples.pe_compression_pct = (forward_pe - pe_ratio) / pe_ratio`.
  - Append `forward_pe` to each peer in `peer_comparables` and compute `valuation_analysis.peer_median_forward_pe`.
  - Compute Reverse DCF Year-5 FCF magnitude on `ValuationAnalysis`: `implied_y5_fcf = free_cash_flow_ttm * (1 + implied_fcf_cagr_5y)^5`, `implied_y5_fcf_multiple = implied_y5_fcf / free_cash_flow_ttm`, and `implied_y5_fcf_vs_current_revenue = implied_y5_fcf / revenue_ttm`.
  - Extract a 3-year annual `historical_trajectory` list (`period`, `revenue`, `operating_margin`, `free_cash_flow`) ordered oldest-to-newest from annual income/cash-flow statements, with realistic 3-year sequences in offline mock fixtures.
- **Strict Opening-Sentence Anti-Echoing & Forward Multiple Synthesis (`memo_synthesizer.py`, `renderer.py`)**:
  - Enforce a strict opening-sentence negative constraint so `valuation_and_debate` and `profitability_and_cash_quality` begin with an analytical mechanism, business driver, or valuation tension—never with a metric name or number already displayed in that section's header table or ribbon (validated deterministically alongside the regex numeric grounding audit).
  - Require `valuation_and_debate` to compare trailing `pe_ratio` vs. `forward_pe` and `analyst_target_mean`, assessing whether forward earnings growth materially compresses the trailing multiple premium.
  - Display Forward P/E and Analyst Consensus Target in the rendered Markdown valuation table while preserving `Grounding Audit: Passed` across all new Audit Trail fields.
- **Scenario Presets, Trajectory Chart & Reverse DCF Reality Check UI (`charts.py`, `streamlit_app.py`)**:
  - Add a 3-column `Bear | Base | Bull` preset button bar at the top of `DCF assumptions` in the sidebar using `st.session_state` callbacks updating `WACC`, `Terminal growth rate`, `5Y FCF CAGR`, and `Terminal Exit EV/EBITDA Multiple` immediately.
  - Add a vertical dotted `#38BDF8` `Analyst Consensus Target` reference line and callout to the Valuation Football Field when `analyst_target_mean` is available.
  - Add a 3rd Plotly chart (**3-Year Historical Trajectory**): dual-axis combo chart showing `Revenue ($B)` as bars (`#3B82F6`) and `Operating Margin (%)` as a line overlay (`#F59E0B`) across 3 fiscal years, plus a caption summarizing FCF progression.
  - Display a compact **Reverse DCF Reality Check** callout card (`st.info`) directly above or beside the 5×5 DCF Sensitivity Matrix showing required Year-5 FCF dollar magnitude and multiple vs. current TTM FCF and TTM revenue.

## Capabilities

### New Capabilities

- `forward-multiples-and-historical-trajectory`: Ingest forward multiples (`forward_pe`, `forward_ev_ebitda`, `pe_compression_pct`), analyst consensus targets (`analyst_target_mean`, `analyst_count`), peer `forward_pe` / `peer_median_forward_pe`, Reverse DCF Year-5 FCF magnitudes (`implied_y5_fcf`, `implied_y5_fcf_multiple`, `implied_y5_fcf_vs_current_revenue`), and 3-year annual `historical_trajectory` sequences across live and offline modes.
- `strict-anti-echoing-forward-synthesis`: Enforce the strict opening-sentence negative constraint preventing metric-ribbon echoing in `valuation_and_debate` and `profitability_and_cash_quality`, require Forward vs. Trailing multiple compression & consensus target commentary, and preserve deterministic numeric grounding across all new Audit Trail fields.
- `scenario-presets-and-trajectory-ui`: Provide Bear/Base/Bull sidebar preset callbacks in `st.session_state`, an `Analyst Consensus Target` dotted line on the Football Field, a dual-axis 3-Year Historical Trajectory Plotly chart, and a Reverse DCF Year-5 FCF Reality Check callout card beside/above the 5×5 sensitivity matrix.

### Modified Capabilities

<!-- None in openspec/specs/ yet (previous changes remain unarchived in openspec/changes/). -->

## Impact

- **Modified Modules**: `fundamental_memo/src/fundamental_memo/{schemas.py,data_fetcher.py,valuation_engine.py,memo_synthesizer.py,renderer.py,charts.py,streamlit_app.py,__init__.py}`, `fundamental_memo/src/fundamental_memo/fixtures/mock_market_data.json`, and `fundamental_memo/tests/*`.
- **Dependencies**: Zero new third-party dependencies (`plotly.subplots`, `pandas`, `streamlit`, `yfinance`, `pydantic`, `openai` are already installed).
- **Backward Compatibility**: Fully additive schema extensions (`HistoricalYearPoint`, `historical_trajectory`, `analyst_target_mean`, `analyst_count`, `forward_pe`, `forward_ev_ebitda`, `pe_compression_pct`, `peer_median_forward_pe`, `implied_y5_fcf`, `implied_y5_fcf_multiple`, `implied_y5_fcf_vs_current_revenue`) with graceful `None`/empty-list defaults.
