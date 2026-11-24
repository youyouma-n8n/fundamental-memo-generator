## 1. Schemas & Self-Consistent Enterprise Value (`schemas.py`, `data_fetcher.py`, `mock_market_data.json`)

- [x] 1.1 Add `DcfSensitivityMatrix`, `ValuationAnalysis.implied_exit_ev_ebitda`, `ValuationAnalysis.dcf_sensitivity_matrix`, and `FinancialSnapshot.business_summary` in `fundamental_memo/src/fundamental_memo/schemas.py`, and enforce exact self-consistent `enterprise_value = market_cap + total_debt - cash_and_equivalents` in `FinancialSnapshot` (and re-export `DcfSensitivityMatrix` in `__init__.py`); verify `ruff` and `mypy --strict` pass on `schemas.py`.
- [x] 1.2 Update `fundamental_memo/src/fundamental_memo/data_fetcher.py` to always compute `enterprise_value = market_cap + total_debt - cash_and_equivalents` (never trusting raw API `enterpriseValue`), add `sanitize_business_summary(...)` extracting the first 2 sentences capped at 450 characters from `longBusinessSummary`, and add a realistic 2-sentence `business_summary` to `fundamental_memo/src/fundamental_memo/fixtures/mock_market_data.json`; verify via unit tests in `test_data_fetcher.py`.

## 2. Quantitative Engine Rigor (`valuation_engine.py`)

- [x] 2.1 Implement `compute_implied_exit_ev_ebitda(...)` (`Terminal Value_{t=5} / EBITDA_{t=5}`, returning `None` when `ebitda_ttm <= 0`) and `compute_dcf_sensitivity_matrix(...)` (5 WACC columns `base ± {0, 0.5%, 1.0%}` × 5 CAGR rows `max(0.0, base ± {0, 2.5%, 5.0%})`) in `fundamental_memo/src/fundamental_memo/valuation_engine.py`, wiring both into `run_valuation_analysis(...)`; verify center cell `grid[2][2]` equals `dcf_intrinsic_value_per_share` and `ev_to_ebitda` uses self-consistent EV in `test_valuation_engine.py`.

## 3. Anti-Echoing Synthesis & Business-Summary Grounding (`memo_synthesizer.py`, `renderer.py`)

- [x] 3.1 Upgrade `fundamental_memo/src/fundamental_memo/memo_synthesizer.py` to whitelist numeric tokens appearing in `snapshot.business_summary` inside `verify_memo_grounding_and_repetition(...)`, enforce the Anti-Echoing prose constraint (no opening repetition of section Key Metrics Ribbons) and business-grounded `bull_case`/`bear_case` requirements in prompts and `synthesize_mock_memo(...)`; verify grounding passes with `business_summary` and still rejects fabricated numbers in `test_synthesizer_and_renderer.py`.
- [x] 3.2 Polish section Key Metrics Ribbons in `fundamental_memo/src/fundamental_memo/renderer.py` (italicized labels matching the anti-echoing contract) and verify rendered Markdown memos pass grounding and word-limit checks in `test_synthesizer_and_renderer.py`.

## 4. Plotly Chart & Streamlit UI Polish (`charts.py`, `streamlit_app.py`)

- [x] 4.1 Update `fundamental_memo/src/fundamental_memo/charts.py` so `build_valuation_football_field(...)` uses `xaxis.range = [max(0.0, min_val * 0.75), max_val * 1.22]` with a paper-anchored `Current Price` annotation (`yref="paper", y=1.08, showarrow=False`), and `build_peer_valuation_scatter(...)` uses `sizemode="area"` (`sizeref = 2.0 * max(market_caps) / (42**2)`) plus a horizontal dashed `Peer Median` reference line (`add_hline`); verify layout bounds, annotation placement, area sizing, and `hline` in `test_charts.py`.
- [x] 4.2 Update `fundamental_memo/src/fundamental_memo/streamlit_app.py` with compact non-truncating 5-card KPI header formatting (`Current Price`, `DCF Intrinsic Value`, `Market-Implied CAGR`, `ROIC (TTM)`, `Earnings Quality`), pass `peer_median_ev_ebitda` into the scatter chart, and render a color-coded 5×5 DCF Sensitivity Table (`st.dataframe` + `pandas.Styler`, Base Case highlighted, green above `current_price`, red/neutral below) inside an expander directly below the charts with the implied exit EV/EBITDA comparison caption; verify via Streamlit `AppTest` in `test_cli_e2e.py`.

## 5. Verification Suite & Final Quality Pass

- [x] 5.1 Update and expand `fundamental_memo/tests/` (`test_schemas.py`, `test_data_fetcher.py`, `test_valuation_engine.py`, `test_synthesizer_and_renderer.py`, `test_charts.py`, `test_cli_e2e.py`) to verify all five acceptance criteria (exact EV identity, non-truncating KPI labels, Football Field padding/callout, grounding audit with `business_summary`, and 5×5 center-cell parity), and run `ruff check src tests`, `mypy src tests`, and `pytest -v` confirming zero warnings or failures.
