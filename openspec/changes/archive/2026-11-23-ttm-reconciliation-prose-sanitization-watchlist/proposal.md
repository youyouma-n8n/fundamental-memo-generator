## Why

External market data API `.info` summaries can lag or diverge from actual quarterly financial statements—producing headline TTM revenue and operating margin mismatches (for example, NVDA `.info` revenue or stale annual operating income diverging sharply from the actual last-4-quarters sum)—while local LLMs occasionally leak raw Audit Trail JSON `snake_case` field identifiers (`pe_compression_pct`, `analyst_target_mean`) into memo prose. Reconciling TTM flow metrics directly from the 4 completed fiscal quarters, sanitizing leaked JSON identifiers deterministically, and adding a pure-Python **Watchlist Quick-Scan Screener** closes the final data-integrity and multi-ticker research workflow gaps without adding LLM latency.

## What Changes

- **Four-Quarter Sum TTM Reconciliation (`schemas.py`, `data_fetcher.py`)**:
  - Extend `QuarterlyPoint` with optional quarterly flow fields (`gross_profit`, `operating_income`, `ebitda`, `net_income`, `operating_cash_flow`, `capex`, `sbc`) extracted from `quarterly_income_stmt` and `quarterly_cashflow`.
  - In `build_snapshot_from_raw(...)`, whenever `quarterly_trajectory` contains **4 valid completed quarters**, deterministically compute TTM flow totals (`revenue_ttm`, `gross_profit_ttm`, `operating_income_ttm`, `ebitda_ttm` with `.info` fallback if quarterly EBITDA/D&A is missing, `net_income_ttm` when available across all 4 quarters, `operating_cash_flow_ttm`, `capex_ttm`, `free_cash_flow_ttm = operating_cash_flow_ttm - capex_ttm`, and `sbc_ttm` when available across all 4 quarters) as the exact 4-quarter sums, and recompute all downstream TTM ratios (`gross_margin_ttm`, `operating_margin_ttm`, `ebitda_margin_ttm`, `fcf_margin_ttm`, `roic_ttm`, `ocf_to_net_income_ratio`, `implied_fcf_cagr_5y`, `dcf_intrinsic_value_per_share`). Fall back to `.info` / annual statement fields only when fewer than 4 quarters are available.
- **Pure-Python Batch Watchlist Screener (`cli.py` / `screener.py`, `fixtures/mock_market_data.json`)**:
  - Add `run_watchlist_scan(tickers, wacc, terminal_growth, base_cagr, exit_multiple, offline_mock=False) -> list[dict]` executing only the deterministic quantitative engine (skipping LLM synthesis) across a basket of tickers (using concurrent fetching for live tickers so 5+ tickers complete rapidly) and returning one structured valuation summary record per ticker (`ticker`, `company_name`, `current_price`, `dcf_value`, `dcf_upside_pct`, `implied_fcf_cagr_5y`, `forward_pe`, `ev_to_ebitda`, `roic_ttm`, `fcf_margin_ttm`, `earnings_quality_flag`, plus graceful per-ticker error isolation).
- **LLM Prose Identifier Ban & Deterministic Post-Sanitizer (`memo_synthesizer.py`, `renderer.py`)**:
  - Add an explicit system-prompt rule forbidding raw `snake_case` JSON identifiers in prose and requiring natural institutional financial English.
  - Add deterministic `sanitize_memo_prose(...)` / `audit_memo_prose(...)` scanning generated prose fields with `\b[a-z]+(?:_[a-z0-9]+){1,}\b` and replacing any leaked Audit Trail JSON key via a comprehensive human-readable institutional alias map (e.g., `pe_compression_pct` → `forward P/E compression`, `analyst_target_mean` → `consensus target price`, `implied_fcf_cagr_5y` → `market-implied 5-year FCF CAGR`, `ocf_to_net_income_ratio` → `OCF-to-Net-Income ratio`) prior to grounding verification and Markdown/HTML rendering.
- **Two-Mode Streamlit Navigation & Watchlist Screener UI (`streamlit_app.py`)**:
  - Introduce top two-tab navigation: `Single-Stock Deep-Dive` and `Watchlist Quick-Scan Screener`.
  - Preserve the complete existing Deep-Dive workflow in Tab 1 (using `st.session_state["target_ticker"]` so watchlist handoff updates the sidebar ticker cleanly).
  - In Tab 2, provide a comma-separated watchlist ticker input (defaulting to `f"{target_ticker},{peer_tickers}"`), a `Run Batch Valuation Scan` button using current sidebar DCF inputs, a sortable color-formatted `st.dataframe` (`Price`, `Base DCF`, `DCF Upside %`, `Implied 5Y FCF CAGR`, `Forward P/E`, `EV/EBITDA`, `ROIC`, `FCF Margin`, `Earnings Quality`), and a quick-select dropdown + `Load Selected Ticker into Deep-Dive` button that sets `st.session_state["target_ticker"]` and triggers a full one-page memo run.

## Capabilities

### New Capabilities

- `four-quarter-ttm-reconciliation`: Deterministically derive TTM headline flow metrics and all downstream profitability/valuation ratios from the exact sum of the last 4 completed fiscal quarters whenever 4 quarters are available, falling back cleanly to `.info` only when fewer than 4 quarters exist.
- `prose-identifier-sanitization`: Prevent raw Audit Trail JSON `snake_case` variable names from appearing in synthesized investment memos via both LLM prompt rules and deterministic alias-map sanitization prior to Markdown and HTML rendering.
- `watchlist-quick-scan-screener`: Execute pure-Python batch deterministic valuation scans across multiple tickers without LLM latency and provide a two-mode Streamlit navigation (`Single-Stock Deep-Dive` | `Watchlist Quick-Scan Screener`) with one-click handoff into the full memo workflow.

### Modified Capabilities

<!-- None in openspec/specs/ yet (previous changes remain unarchived in openspec/changes/). -->

## Impact

- **Modified Modules**: `fundamental_memo/src/fundamental_memo/{schemas.py,data_fetcher.py,memo_synthesizer.py,renderer.py,cli.py,streamlit_app.py,__init__.py}`, `fundamental_memo/src/fundamental_memo/fixtures/mock_market_data.json`, and `fundamental_memo/tests/*`.
- **Optional New Module**: `fundamental_memo/src/fundamental_memo/screener.py` (or colocated in `cli.py`, re-exported from `__init__.py` as `run_watchlist_scan`).
- **Dependencies**: Zero new third-party dependencies required (`concurrent.futures` from stdlib handles concurrent live ticker scans).
- **Backward Compatibility**: All new `QuarterlyPoint` flow fields are optional (`default=None`), preserving compatibility with existing fixtures and callers while automatically reconciling TTM totals whenever 4 complete quarters are provided.
