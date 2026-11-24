## Context

This change upgrades the existing `fundamental_memo` package at `/Users/eugeneyzhou/my_work/uchicago_mc/mc_03/fundamental_memo` (`src/fundamental_memo/{schemas.py,data_fetcher.py,valuation_engine.py,memo_synthesizer.py,renderer.py,cli.py,streamlit_app.py}` and `tests/`). See `proposal.md` for motivation and `specs/*/spec.md` for behavioral contracts.

Current baseline state:
- All 27 baseline `pytest` tests, `ruff check`, and `mypy --strict` checks pass in `fundamental_memo/.venv` (Python 3.12).
- The package currently computes basic 5-year perpetuity DCF, peer medians, OCF/Net Income, and accrual ratio, renders a 6-section Markdown memo (≤ 650 words), and exposes a CLI plus a Streamlit UI with 3 selectable Ollama/MLX models.
- The upgrade maps the proposal's conceptual layers (`engine/`, `synthesis/`, `app.py`) cleanly onto the existing `src/fundamental_memo/` layout (plus a new `charts.py` module) so CLI entry points and package imports stay cohesive.

## Goals / Non-Goals

**Goals:**
- Expand deterministic financial statement ratios (margins, ROIC, SBC-adjusted FCF, net cash, 52-week range, DSO/DIO, and OCF/Net Income gap driver) in pure Python with full offline mock fixture parity.
- Add a pure-Python Reverse DCF solver accurate within `±$0.01`, configurable FCF CAGR and Exit EV/EBITDA Multiple cross-check, and 25th–75th percentile peer comps range.
- Upgrade LLM synthesis to the 6-section `InvestmentMemoSchema` with "The Debate / Variant Perception", enforcing both the Single-Mention anti-repetition rule and a deterministic post-generation regex numeric grounding verifier against the Audit Trail JSON.
- Add interactive Plotly **Valuation Football Field** and **Peer Valuation vs. Growth Scatter** charts, expanded DCF sidebar controls, and a 5-card KPI header row in Streamlit.
- Keep `ruff check`, `mypy --strict`, and `pytest` 100% green.

**Non-Goals:**
- Adding `scipy` as a binary dependency when pure-Python root-finding achieves machine precision (`< 1e-12`) on a strictly monotonic 1D DCF function.
- Multi-currency FX conversion or historical quarterly charting beyond TTM / 52-week / 3-year CAGR metrics.
- Persistent database storage or PDF/PowerPoint export.

## Decisions

### 1. Audit Trail JSON Schema Extensions (`schemas.py`)
- **Decision:**
  - Add a nested `WorkingCapitalMetrics(BaseModel)` containing `dso_days: float | None`, `dio_days: float | None`, and `ocf_net_income_gap_driver: str`.
  - Extend `FinancialSnapshot` with optional raw and derived diagnostic fields (`gross_margin_ttm`, `operating_margin_ttm`, `roic_ttm`, `sbc_ttm`, `sbc_adjusted_fcf_ttm`, `net_cash`, `net_cash_to_market_cap`, `working_capital_metrics`, plus `fifty_two_week_low` / `fifty_two_week_high` serialized with JSON aliases `"52w_low"` and `"52w_high"` via `ConfigDict(populate_by_name=True)`).
  - Extend `PeerComparable` with `revenue_growth_3y: float | None = None` and `market_cap: float | None = None` (alongside existing `ev_to_ebitda`, `pe_ratio`, `fcf_yield`).
  - Extend `ValuationAnalysis` with `implied_fcf_cagr_5y: float | None`, `cagr_spread_vs_base: float | None`, `exit_multiple_dcf_value: float | None`, `exit_multiple_low_wacc_value: float | None`, `exit_multiple_high_wacc_value: float | None`, `peer_comps_p25_value: float | None`, and `peer_comps_p75_value: float | None`.
  - Replace the LLM output model fields in `InvestmentMemoSchema` (`executive_thesis`, `valuation_and_debate`, `profitability_and_cash_quality`, `bull_case`, `bear_case`, `key_downside_risks`) with per-section word budgets (`60`, `150`, `120`, and `90` total words for each bullet list) and alias `InvestmentMemoOutput = InvestmentMemoSchema` for import stability.
- **Alternatives considered:** Storing expanded diagnostics in a separate top-level object outside `financial_snapshot` (rejected because the proposal explicitly specifies extending `financial_snapshot` in the Audit Trail JSON).

### 2. Pure-Python Reverse DCF Solver & Exit Multiple DCF (`valuation_engine.py`)
- **Decision:**
  - Implement `solve_reverse_dcf_implied_cagr(...)` using pure-Python bisection over `[-0.20, 1.00]` (80 iterations, stopping early when `abs(price_est - current_price) < 1e-6`). Because 5-year unlevered DCF value is strictly monotonically increasing in `fcf_cagr` whenever `free_cash_flow_ttm > 0` and `wacc > terminal_growth_rate`, bisection is guaranteed to find the unique root to far better than `±$0.01` accuracy without adding `scipy`. If `current_price` lies outside `[DCF(-0.20), DCF(1.00)]`, return `None` cleanly.
  - Add optional `fcf_cagr_override: float | None = None` to `compute_dcf_intrinsic_value` and `run_valuation_analysis`: when provided (from Streamlit's `5Y FCF CAGR` input or CLI `--fcf-cagr`), use it directly; when omitted in CLI, preserve clamped 3-year historical revenue growth `[0.02, 0.15]`.
  - Implement `compute_exit_multiple_dcf_value(...)`: project 5 years of unlevered FCFs at `base_fcf_cagr` and Terminal Year EBITDA `ebitda_ttm * (1 + base_fcf_cagr)^5`, compute `PV(FCF_1..5) + PV(Terminal_Year_EBITDA * target_exit_ev_ebitda)` at `wacc`, add `net_cash` (`cash_and_equivalents - total_debt`), and divide by `shares_outstanding`. Also compute WACC ±100 bps sensitivity bounds for the Exit Multiple bar on the Football Field.
  - Compute per-peer implied share prices from each peer's positive EV/EBITDA and/or P/E multiple, then calculate linear-interpolated 25th and 75th percentiles (`peer_comps_p25_value`, `peer_comps_p75_value`) for the Football Field's Peer Comps range.
- **Alternatives considered:** Adding `scipy` for `scipy.optimize.brentq` (rejected as unnecessary overhead for a smooth, strictly monotonic 1D function; bisection has zero external dependencies and passes `mypy --strict` without stub packages).

### 3. Deterministic Gap Driver & Expanded Ingestion (`data_fetcher.py`)
- **Decision:**
  - Extract raw income-statement, balance-sheet, and cash-flow fields (`grossProfit`, `operatingIncome`, `costOfRevenue`, `stockholdersEquity`, `taxProvision`/`pretaxIncome`, `stockBasedCompensation`, `accountsReceivable`, `inventory`, `changeInWorkingCapital`, `fiftyTwoWeekLow`, `fiftyTwoWeekHigh`) from `yfinance` `.info` and statements with `None`-safe fallbacks.
  - Compute `effective_tax_rate` bounded to `[0.0, 0.50]` when positive pretax income is available, falling back to `0.21`. Compute `roic_ttm = (operating_income_ttm * (1 - tax_rate)) / (total_debt + total_equity - cash_and_equivalents)` returning `None` if `invested_capital <= 0`.
  - Deterministically classify `ocf_net_income_gap_driver` by comparing `ocf_ttm - net_income_ttm` against `sbc_ttm`, `change_in_working_capital`, and `capex_ttm` (explicitly distinguishing non-cash SBC / D&A add-backs, working-capital inflows/outflows, and CapEx reinvestment context).
  - Enrich `fixtures/mock_market_data.json` with realistic `AVGO` and peer (`NVDA`, `AMD`, `MRVL`, `QCOM`) attributes covering all new fields.
- **Alternatives considered:** Computing expanded snapshot ratios only inside `valuation_engine.py` (rejected because `FinancialSnapshot` in the Audit Trail JSON must carry these metrics cleanly from both live fetch and fixtures; we centralize ratio derivation in a pure helper invoked during snapshot construction).

### 4. Anti-Repetition & Regex Numeric Grounding Audit (`memo_synthesizer.py`, `renderer.py`)
- **Decision:**
  - Implement a dedicated pure verifier `verify_memo_grounding_and_repetition(memo, snapshot, valuation, peers, sensitivity) -> list[str]` returning concrete violation messages:
    1. **Single-Mention & Anti-Repetition Check:** Format canonical tokens for `dcf_intrinsic_value_per_share`, `implied_value_by_comps`, and `implied_fcf_cagr_5y`. Verify none of the exact DCF or Comps share price tokens appear in `bull_case` or `bear_case`, and total mentions of each headline valuation figure across all narrative fields do not exceed 2 (at most 1 in `executive_thesis` and 1 in `valuation_and_debate`).
    2. **Zero-Hallucination Regex Numeric Audit:** Collect every numeric value from the Audit Trail JSON (`snapshot`, `valuation`, `peers`, `target_multiples`, `sensitivity`) across standard institutional scales (raw, `%` via `×100`, `bps` via `×10000`, `$M` via `/1e6`, `$B` via `/1e9`, and rounded 0/1/2-decimal representations) plus approved model constants (`5`, `3`, `1`, `52`, `100`, `365`, `21`, `25`, `75`). Extract every numeric literal from the 6 LLM narrative fields via regex and flag any number not matched within rounding tolerance.
  - Run `verify_memo_grounding_and_repetition(...)` inside `synthesize_memo_with_llm(...)` right after Pydantic validation; any violations trigger the existing retry loop (up to 2 retries) with explicit corrective instructions. Also run it in `renderer.py` / `tests/` to guarantee offline mock memos and rendered outputs pass 100%.
  - Raise `MAX_MEMO_WORDS` in `renderer.py` from `650` to `750` so memos hitting the new `550–700` word target (including header block, valuation table, and sensitivity summary) pass cleanly while still blocking bloated outputs.
- **Alternatives considered:** Checking numeric grounding only via LLM self-critique (rejected because grounding must be deterministic in pure Python).

### 5. Dedicated Plotly Chart Module & Streamlit Upgrade (`charts.py`, `streamlit_app.py`)
- **Decision:**
  - Add `plotly>=5.20.0` to `pyproject.toml` (with `mypy` override for `plotly.*` if needed).
  - Create `src/fundamental_memo/charts.py` containing `build_valuation_football_field(snapshot, valuation, sensitivity) -> go.Figure` and `build_peer_valuation_scatter(snapshot, peers) -> go.Figure` so charts are cleanly modular and directly unit-testable in `pytest` without launching a browser.
  - Upgrade `streamlit_app.py`:
    - Add `5Y FCF CAGR` (`default=0.15`, `step=0.01`, `format="%.3f"`) and `Terminal Exit EV/EBITDA Multiple` (`default=15.0`, `step=0.5`, `format="%.1f"`) under DCF Assumptions.
    - Expand top KPI row to 5 `st.columns(5)` cards (`Current Price`, `DCF Intrinsic Value`, `Market-Implied FCF CAGR`, `ROIC / Operating Margin`, `Earnings Quality`).
    - Render the Valuation Football Field and Peer Valuation-Growth Scatter charts side-by-side (`st.columns(2)`) above the Markdown memo and download button.
- **Alternatives considered:** Inlining Plotly figure construction directly inside `streamlit_app.py` (rejected to preserve single-responsibility modularity and clean unit testing).

## Risks / Trade-offs

- **[Regex numeric grounding false positives on valid rounded/derived prose numbers]** → Mitigated by registering all standard institutional scales (`$B`, `$M`, `%`, `bps`, `x`, integer days) and rounded representations from the Audit Trail JSON, plus testing with realistic mock and mocked-LLM prose in `pytest`.
- **[Smaller local LLMs (`inkling-2-mini:latest`) struggling with strict Single-Mention + numeric grounding on first attempt]** → Mitigated by explicit section-level rules in the system/user prompt and feeding exact violation strings back into the 2-retry loop.
- **[`yfinance` missing balance sheet lines such as `Inventory` or `Stock Based Compensation` for certain tickers]** → Mitigated by making all expanded fields `float | None` with safe `None` propagation across formulas, KPI cards, and Plotly charts.
- **[Breaking change in `InvestmentMemoSchema` field names]** → Mitigated by updating `renderer.py`, `memo_synthesizer.py`, and `tests/` atomically in this change and aliasing `InvestmentMemoOutput = InvestmentMemoSchema`.
