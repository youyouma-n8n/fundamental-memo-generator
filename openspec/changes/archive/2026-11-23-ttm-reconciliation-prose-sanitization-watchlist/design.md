## Context

See [proposal.md](proposal.md) for motivation and scope. Two concrete codebase observations shape this technical design:
1. **Why `.info` vs. 4Q diverged in `data_fetcher.py`**: `build_snapshot_from_raw(...)` currently picks TTM flow metrics primarily from `info` (`totalRevenue`, `operatingCashflow`, `freeCashflow`) while falling back to *annual* `income_stmt` rows (`operating_income_ttm`, `gross_profit_ttm`) when `.info` omits them. For fast-growing equities like `NVDA`, dividing stale FY annual operating income by newer `.info` TTM revenue caused `operating_margin_ttm` to drop to ~36% while the actual last-4-quarters operating margin was ~65%, and `.info` revenue itself could lag or differ from the 4-quarter statement sum.
2. **Existing Pipeline & Session State Architecture**: `streamlit_app.py` manages sidebar DCF assumptions via `st.session_state` (`dcf_wacc`, `dcf_terminal_growth`, `dcf_fcf_cagr`, `dcf_exit_multiple`), while `ticker_input` is currently an unkeyed `st.text_input("Target ticker", value="AVGO")`. Promoting `target_ticker` into `st.session_state["target_ticker"]` enables clean one-click handoff from the Watchlist Screener back into `Single-Stock Deep-Dive`.

## Goals / Non-Goals

**Goals:**
- Reconcile TTM flow totals (`revenue_ttm`, `gross_profit_ttm`, `operating_income_ttm`, `ebitda_ttm`, `net_income_ttm`, `operating_cash_flow_ttm`, `capex_ttm`, `free_cash_flow_ttm`, `sbc_ttm`) directly from the 4 completed quarters in `quarterly_trajectory` whenever 4 valid quarters exist, guaranteeing 100% mathematical alignment between the `Quarterly (4Q)` view and headline TTM/DCF/ROIC/Reverse-DCF metrics.
- Ban raw `snake_case` Audit Trail JSON identifiers from LLM prose both proactively (prompt constraint) and deterministically (post-synthesis regex sanitizer with an institutional alias map).
- Deliver a pure-Python `run_watchlist_scan(...)` batch screener (zero LLM calls, concurrent live fetching via `ThreadPoolExecutor`) and a two-mode Streamlit top navigation (`Single-Stock Deep-Dive` | `Watchlist Quick-Scan Screener`) with one-click deep-dive handoff.

**Non-Goals:**
- Persisting watchlists to an external database or filesystem across browser restarts.
- Running LLM synthesis inside the Watchlist Quick-Scan Screener (the screener is intentionally pure-Python deterministic valuation only).
- Adding any new third-party Python dependencies.

## Decisions

### 1. Extending `QuarterlyPoint` and 4-Quarter TTM Reconciliation (`schemas.py`, `data_fetcher.py`)
- **Decision**:
  - Add optional flow fields to `QuarterlyPoint`: `gross_profit: float | None = None`, `operating_income: float | None = None`, `ebitda: float | None = None`, `net_income: float | None = None`, `operating_cash_flow: float | None = None`, `capex: float | None = None`, `sbc: float | None = None`. All default to `None` for full backward compatibility.
  - In `extract_quarterly_trajectory(...)`, populate each of these fields from `quarterly_income_stmt` (`"Gross Profit"`, `"Operating Income"`/`"EBIT"`, `"EBITDA"`/`"Normalized EBITDA"`, `"Net Income"`/`"Net Income Common Stockholders"`) and `quarterly_cashflow` (`"Operating Cash Flow"`/`"Cash Flow From Continuing Operating Activities"`, `"Capital Expenditure"`/`"Capital Expenditures"`, `"Stock Based Compensation"`).
  - In `build_snapshot_from_raw(...)`, introduce a dedicated reconciliation block when `len(quarterly_list) == 4`:
    - `revenue_ttm = sum(q.revenue for q in quarterly_list)` (always positive because `extract_quarterly_trajectory` filters `rev > 0`).
    - If all 4 quarters have `gross_profit is not None`, set `gross_profit_ttm = sum(...)`; else if all 4 have `gross_margin is not None`, derive `gross_profit_ttm = sum(q.revenue * q.gross_margin for q in quarterly_list)`.
    - If all 4 quarters have `operating_income is not None`, set `operating_income_ttm = sum(...)`; else if all 4 have `operating_margin is not None`, derive `operating_income_ttm = sum(q.revenue * q.operating_margin for q in quarterly_list)`.
    - If all 4 quarters have `ebitda is not None`, set `ebitda_ttm = sum(...)`; otherwise preserve the `.info` / statement `ebitda_ttm` fallback (and `ebitda_margin_ttm` is recomputed against the reconciled `revenue_ttm`).
    - If all 4 quarters have `net_income is not None`, set `net_income_ttm = sum(...)`.
    - If all 4 quarters have `operating_cash_flow is not None`, set `operating_cash_flow_ttm = sum(...)`; if all 4 have `capex is not None`, set `capex_ttm = sum(abs(q.capex) for q in quarterly_list)` and `free_cash_flow_ttm = operating_cash_flow_ttm - capex_ttm`. (If `operating_cash_flow` is absent on a fixture but all 4 quarters have `free_cash_flow is not None`, sum `free_cash_flow_ttm = sum(q.free_cash_flow for q in quarterly_list)`.)
    - If all 4 quarters have `sbc is not None`, set `sbc_ttm = sum(abs(q.sbc) for q in quarterly_list)`.
    - Recompute all downstream TTM ratios (`cost_of_revenue_ttm`, `gross_margin_ttm`, `operating_margin_ttm`, `ebitda_margin_ttm`, `fcf_margin_ttm`, `roic_ttm`, `sbc_adjusted_fcf_ttm`, `working_capital_metrics`) from these reconciled totals!
  - Populate matching quarterly flow fields on `fixtures/mock_market_data.json` so offline mock data is also 100% 4Q-reconciled.
- **Rationale**: Computing TTM flow totals directly from the 4 quarters guarantees `sum(4Q) == TTM` mathematically and eliminates `.info` vs. annual-statement lag distortion.
- **Alternatives Considered**: Preferring `.info` and only reconciling when `.info` differs by >10% — rejected because any discrepancy between the displayed 4-quarter table and headline TTM undermines institutional trust.

### 2. Prose Identifier Ban & Deterministic Post-Sanitizer (`memo_synthesizer.py`, `renderer.py`)
- **Decision**:
  - Append an explicit anti-identifier rule to `SYSTEM_PROMPT` instructing the LLM never to output raw `snake_case` JSON variable names (`pe_compression_pct`, `analyst_target_mean`, `ocf_to_net_income_ratio`, `implied_fcf_cagr_5y`, etc.) and to write natural institutional financial English.
  - Add a curated `AUDIT_TRAIL_IDENTIFIER_ALIASES: dict[str, str]` covering every Audit Trail JSON key across `FinancialSnapshot`, `ValuationAnalysis`, `PeerComparable`, `WorkingCapitalMetrics`, `DcfSensitivity`, and `target_multiples`, plus a clean fallback converter (`token.replace("_", " ")`) for any unmapped Audit Trail JSON key.
  - Implement `sanitize_memo_prose(memo: InvestmentMemoSchema, audit_keys: set[str] | None = None) -> InvestmentMemoSchema` scanning every narrative string and bullet with `re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b")` and replacing matched Audit Trail keys (case-sensitively matching snake_case identifiers) with their institutional English aliases (also normalizing backticked identifiers like `` `pe_compression_pct` `` → `forward P/E compression`).
  - Run `sanitize_memo_prose(...)` immediately after `InvestmentMemoSchema.model_validate_json(...)` inside `synthesize_memo_with_llm(...)` AND inside `render_investment_memo(...)` so both LLM synthesis and direct renderer callers (and downstream `html_exporter.py`) are guaranteed zero leaked `snake_case` identifiers!
  - Also add a helper `find_leaked_snake_case_identifiers(text: str) -> list[str]` for deterministic auditing and tests.
- **Rationale**: Prompting prevents 95%+ of leaks naturally; running the deterministic alias-map sanitizer before rendering and HTML export guarantees 100% elimination without wasting LLM retries on a trivial identifier slip.
- **Alternatives Considered**: Failing grounding validation and burning an LLM retry whenever a snake_case key leaks — rejected because deterministic alias substitution is instant, zero-risk, preserves every numeric value intact, and avoids unnecessary 30-second retries on local models.

### 3. Pure-Python Batch Watchlist Screener (`screener.py`, `fixtures/mock_market_data.json`)
- **Decision**:
  - Create a focused pure-Python module `fundamental_memo/src/fundamental_memo/screener.py` (re-exported in `__init__.py`) with:
    - `run_watchlist_scan(tickers: Sequence[str], wacc: float = DEFAULT_WACC, terminal_growth: float = DEFAULT_TERMINAL_GROWTH, base_cagr: float = DEFAULT_MAX_FCF_GROWTH, exit_multiple: float = DEFAULT_EXIT_EV_EBITDA, offline_mock: bool = False) -> list[dict[str, Any]]`.
    - Deduplicates and uppercases input tickers cleanly.
    - For live mode (`offline_mock=False`), fetches snapshots concurrently using `concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(tickers)))` so scanning 5+ tickers runs in parallel (targeting < 5s) rather than sequentially.
    - For offline mock mode (`offline_mock=True`), expand `fixtures/mock_market_data.json` (or add a lightweight `watchlist_profiles` map inside `mock_market_data.json`) with realistic distinct snapshots for `NVDA`, `AMD`, `MRVL`, `QCOM`, and `AVGO` so offline watchlist screening produces realistic differentiated rows across all 5 tickers in < 0.05s!
    - For each ticker, calls `run_valuation_analysis(snapshot, [], wacc=..., terminal_growth_rate=..., fcf_cagr_override=base_cagr, target_exit_ev_ebitda=exit_multiple)` + `compute_target_multiples(snapshot)` (no LLM calls, no per-ticker peer fetching overhead) and returns a record with: `ticker`, `company_name`, `current_price`, `dcf_value`, `dcf_upside_pct`, `implied_fcf_cagr_5y`, `forward_pe`, `ev_to_ebitda`, `roic_ttm`, `fcf_margin_ttm`, `earnings_quality_flag`, and `error` (`None` on success, concise error string on failure so one bad ticker never aborts the batch).
- **Rationale**: Separate `screener.py` keeps `cli.py` focused on single-ticker orchestration while giving both Streamlit and programmatic/CLI callers a clean, strictly typed batch API.

### 4. Two-Mode Streamlit Navigation & One-Click Handoff (`streamlit_app.py`)
- **Decision**:
  - Manage `target_ticker` via `st.session_state["target_ticker"]` (initialized to `"AVGO"`) and `peers_input` via `st.session_state["peers_input"]` (initialized to `"NVDA,AMD,MRVL,QCOM"`).
  - Add top mode switcher using `st.segmented_control` or `st.tabs(["Single-Stock Deep-Dive", "Watchlist Quick-Scan Screener"])` — specifically `st.segmented_control` or `st.tabs`? Think carefully!
    - With `st.tabs(...)`, Streamlit cannot programmatically switch the active tab on `st.rerun()` when the user clicks `Load Selected Ticker into Deep-Dive` in Tab 2!
    - With `st.segmented_control("Workspace mode", options=["Single-Stock Deep-Dive", "Watchlist Quick-Scan Screener"], key="active_mode", label_visibility="collapsed")` (native Streamlit 1.40+ widget, available in installed Streamlit `1.67.0`!), clicking `Load Selected Ticker into Deep-Dive` via an `on_click` callback can atomically set:
      - `st.session_state["target_ticker"] = selected_ticker`
      - `st.session_state["active_mode"] = "Single-Stock Deep-Dive"`
      - `st.session_state["auto_run_deep_dive"] = True`
      so Streamlit immediately switches back to `Single-Stock Deep-Dive` AND runs the full memo pipeline for the selected ticker in a single click!
    - Let's verify `st.segmented_control` works cleanly with `AppTest` in Streamlit `1.67.0` during apply (and if needed, keep clean fallback tests).
  - In `Watchlist Quick-Scan Screener`:
    - Default watchlist text input to `f"{target_ticker},{peers_input}"` (deduplicated).
    - `Run Batch Valuation Scan` button calls `run_watchlist_scan(...)` using active sidebar `wacc`, `terminal_growth`, `fcf_cagr`, `exit_ev_ebitda`, and `use_mock_data`, storing results in `st.session_state["watchlist_scan_results"]`.
    - Render a sortable, color-formatted `pandas.Styler` dataframe via `st.dataframe(..., width="stretch", hide_index=True, alt=...)` displaying `Ticker`, `Company`, `Price`, `Base DCF`, `DCF Upside %`, `Implied 5Y FCF CAGR`, `Forward P/E`, `EV/EBITDA`, `ROIC`, `FCF Margin`, `Earnings Quality` (green/red tinting on `DCF Upside %`).
    - Below the table, render a `st.selectbox` of successfully scanned tickers + `Load Selected Ticker into Deep-Dive` button (`on_click` callback updating `target_ticker`, switching `active_mode` to `"Single-Stock Deep-Dive"`, and setting `auto_run_deep_dive = True`).

## Risks / Trade-offs

- **[Risk] Live `yfinance` quarterly cash flow statements occasionally omit `Stock Based Compensation` or `EBITDA` on certain tickers** → **Mitigation**: Only override `ebitda_ttm` / `sbc_ttm` / `net_income_ttm` with the 4-quarter sum when all 4 quarters have non-null values for that line item; otherwise fall back cleanly to `.info` / annual statement values while always reconciling `revenue_ttm`, `operating_income_ttm`, `operating_cash_flow_ttm`, `capex_ttm`, and `free_cash_flow_ttm`.
- **[Risk] Concurrent live `yfinance` fetches across 5+ tickers could occasionally rate-limit or exceed 5 seconds depending on network latency** → **Mitigation**: Use bounded `ThreadPoolExecutor(max_workers=5)` so 5 tickers fetch in parallel (~1–3s typical), isolate any per-ticker exceptions cleanly into row-level error messages, and support deterministic sub-second offline mock screening across all 5 tickers.
- **[Risk] Over-eager snake_case regex could corrupt legitimate identifiers or URLs** → **Mitigation**: Restrict replacement strictly to known Audit Trail JSON keys (collected dynamically from `AUDIT_TRAIL_IDENTIFIER_ALIASES` + schema keys) and only operate on generated narrative prose fields—never on URLs, HTML tags, or code.
