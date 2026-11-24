## Context

This change extends the existing `fundamental_memo` package at `/Users/eugeneyzhou/my_work/uchicago_mc/mc_03/fundamental_memo`, where all 40 `pytest` tests, `ruff check`, and `mypy --strict` checks currently pass. See `proposal.md` for motivation and `specs/*/spec.md` for behavioral contracts.

## Goals / Non-Goals

**Goals:**
- Ingest Forward valuation multiples (`forward_pe`, `forward_ev_ebitda`, `pe_compression_pct`), Wall Street consensus targets (`analyst_target_mean`, `analyst_count`), peer `forward_pe` / `peer_median_forward_pe`, Reverse DCF Year-5 FCF magnitudes, and 3-year annual `historical_trajectory` records in pure Python with full offline mock fixture parity.
- Deterministically enforce the opening-sentence anti-echoing negative constraint on `valuation_and_debate` and `profitability_and_cash_quality`, incorporate Forward vs. Trailing multiple compression analysis, and guarantee `Grounding Audit: Passed` across all new Audit Trail fields.
- Deliver one-click Bear/Base/Bull sidebar presets via `st.session_state` callbacks, an `Analyst Consensus Target` overlay on the Football Field, a dual-axis 3-Year Historical Trajectory Plotly chart, and a Reverse DCF Reality Check callout card beside/above the 5×5 sensitivity matrix.

**Non-Goals:**
- Quarterly earnings surprise time series or multi-year sell-side consensus estimate curves beyond NTM forward multiples and consensus target price.
- Adding new third-party Python dependencies.

## Decisions

### 1. Schema Extensions (`schemas.py`)
- **Decision:**
  - Add `HistoricalYearPoint(BaseModel)` with `period: str`, `revenue: float`, `operating_margin: float | None = None`, and `free_cash_flow: float | None = None`.
  - Extend `FinancialSnapshot` with `forward_pe: float | None = None`, `forward_ev_ebitda: float | None = None`, `analyst_target_mean: float | None = None`, `analyst_count: int | None = None`, and `historical_trajectory: list[HistoricalYearPoint] = Field(default_factory=list)`.
  - Extend `PeerComparable` with `forward_pe: float | None = None`.
  - Extend `ValuationAnalysis` with `peer_median_forward_pe: float | None = None`, `implied_y5_fcf: float | None = None`, `implied_y5_fcf_multiple: float | None = None`, and `implied_y5_fcf_vs_current_revenue: float | None = None`.
  - Extend `compute_target_multiples(snapshot)` in `valuation_engine.py` to include `forward_pe`, `forward_ev_ebitda`, and `pe_compression_pct` (`(forward_pe - pe_ratio) / pe_ratio` when both `pe_ratio` and `forward_pe` are positive).
- **Alternatives considered:** Storing `historical_trajectory` outside `FinancialSnapshot` (rejected because keeping it on `FinancialSnapshot` ensures fixtures, Audit Trail JSON, and grounding verification consume a single unified snapshot schema).

### 2. Historical Trajectory & Forward Ingestion (`data_fetcher.py`, `mock_market_data.json`)
- **Decision:**
  - Extract up to the last 3 completed fiscal years (sorted oldest to newest) by aligning column labels across `income_stmt` (`Total Revenue`, `Operating Income` / `EBIT`) and `cashflow` (`Free Cash Flow`, or fallback `Operating Cash Flow - abs(Capital Expenditure)`). Format period labels cleanly as `FY<YYYY>` from timestamp/date column headers (or string labels if non-date).
  - Extract `forward_pe = _to_finite_float(info.get("forwardPE"))`, `analyst_target_mean = _to_finite_float(info.get("targetMeanPrice"))`, `analyst_count = int(raw)` when positive finite, and `forward_ev_ebitda` when forward EBITDA (`forwardEps` / `enterpriseToEbitda` fallback only if distinct forward estimate exists, or `info.get("forwardEnterpriseToEbitda")` / `None` cleanly — never conflating stale trailing `enterpriseToEbitda` with self-consistent trailing EV/EBITDA).
  - For peers in `fetch_peer_comparables`, extract `forward_pe = _to_finite_float(info_raw.get("forwardPE"))`.
  - Populate realistic 3-year `historical_trajectory` (`FY2022`, `FY2023`, `FY2024`), `forward_pe`, `forward_ev_ebitda`, `analyst_target_mean`, `analyst_count`, and peer `forward_pe` values in `fixtures/mock_market_data.json`.
- **Alternatives considered:** Fetching quarterly statements to synthesize 3 annual periods (rejected because annual `income_stmt` and `cashflow` frames in `yfinance` directly provide completed fiscal years).

### 3. Reverse DCF Year-5 FCF Magnitude (`valuation_engine.py`)
- **Decision:**
  - Inside `run_valuation_analysis(...)`, when `implied_fcf_cagr_5y is not None`:
    - `implied_y5_fcf = snapshot.free_cash_flow_ttm * ((1.0 + implied_fcf_cagr_5y) ** projection_years)`
    - `implied_y5_fcf_multiple = implied_y5_fcf / snapshot.free_cash_flow_ttm`
    - `implied_y5_fcf_vs_current_revenue = implied_y5_fcf / snapshot.revenue_ttm` (if `snapshot.revenue_ttm > 0.0` else `None`)
  - Also compute `peer_median_forward_pe = compute_positive_median([peer.forward_pe for peer in peers])`.
- **Alternatives considered:** Computing Year-5 FCF inside `streamlit_app.py` (rejected to preserve strict pure-Python engine ownership and include exact values in the Audit Trail JSON for numeric grounding).

### 4. Strict Opening-Sentence Anti-Echoing Audit & Forward Multiple Synthesis (`memo_synthesizer.py`, `renderer.py`)
- **Decision:**
  - Add a deterministic opening-sentence check inside `verify_memo_grounding_and_repetition(...)` for `valuation_and_debate` and `profitability_and_cash_quality`: inspect the first ~45 characters / opening clause of the first sentence and reject known metric-recitation openings (e.g., starting with `"Gross margin"`, `"Operating margin"`, `"ROIC"`, `"OCF/NI"`, `"EV/EBITDA"`, `"P/E"`, `"Base DCF"`, `"At 9.50% WACC"`, or a leading numeric figure). Feed explicit corrective instructions into the 2-retry loop when triggered.
  - Update `SYSTEM_PROMPT`, `build_synthesis_user_prompt(...)`, and `synthesize_mock_memo(...)` so:
    - `valuation_and_debate` opens with the core market debate/tension and explicitly contrasts trailing `pe_ratio` vs. `forward_pe` (`pe_compression_pct`) and `analyst_target_mean`.
    - `profitability_and_cash_quality` opens with business mix / operating leverage mechanics (referencing `business_summary` drivers) rather than reciting ribbon metrics.
  - Update `renderer.py` valuation summary table to add a `Forward P / E` row (Target vs. Peer Median) and include Consensus Target when available, keeping total rendered words within the `<= 750` word ceiling.
- **Alternatives considered:** Relying solely on prompt instructions without a deterministic opening-sentence check (rejected because small local models occasionally slip back into metric-first lead sentences unless verified and retried).

### 5. Sidebar Presets, Consensus Target Overlay, Trajectory Chart & Reality Check (`charts.py`, `streamlit_app.py`)
- **Decision:**
  - **Sidebar Scenario Presets (`streamlit_app.py`):** Initialize `st.session_state` keys (`dcf_wacc`, `dcf_terminal_growth`, `dcf_fcf_cagr`, `dcf_exit_multiple`) with Base defaults before rendering widgets, bind each `st.number_input(..., key=...)`, and place a 3-column `Bear | Base | Bull` button row at the top of `DCF assumptions` using `on_click=_apply_scenario_preset` callbacks so clicking any preset immediately updates all 4 widget values cleanly on rerun without widget-state conflicts.
  - **Football Field Consensus Line (`charts.py`):** When `snapshot.analyst_target_mean is not None`, include `analyst_target_mean` in `min_val`/`max_val` x-axis padding, add `fig.add_vline(x=snapshot.analyst_target_mean, line_width=2, line_dash="dot", line_color="#38BDF8")`, and add a paper-anchored annotation (`y=1.14` or staggered cleanly if close to `current_price` so the two callouts never collide!).
  - **3-Year Historical Trajectory Chart (`charts.py`):** Implement `build_historical_trajectory_chart(snapshot) -> go.Figure` using `plotly.subplots.make_subplots(specs=[[{"secondary_y": True}]])`: primary y-axis `go.Bar` for `Revenue ($B)` in `#3B82F6` and secondary y-axis `go.Scatter(mode="lines+markers")` for `Operating Margin (%)` in `#F59E0B`, plus an FCF progression caption helper in `streamlit_app.py`.
  - **Reverse DCF Reality Check Callout (`streamlit_app.py`):** Directly above the 5×5 DCF Sensitivity Matrix inside/alongside the sensitivity section, display `st.info(...)` summarizing `current_price`, `implied_fcf_cagr_5y`, `implied_y5_fcf_multiple`, `free_cash_flow_ttm`, `implied_y5_fcf`, and `revenue_ttm`, and render the 3-Year Historical Trajectory chart beside or right below the sensitivity block with `width="stretch"` and accessible `alt=` text.
- **Alternatives considered:** Mutating `st.session_state` after instantiating `st.number_input` widgets (rejected because Streamlit raises `StreamlitAPIException` if a widget's session-state key is modified after instantiation; `on_click` callbacks avoid this cleanly).

## Risks / Trade-offs

- **[Two vertical callouts (`Current Price` and `Analyst Consensus Target`) overlapping when prices are close]** → Mitigated by staggering the `Analyst Consensus Target` annotation vertically (`y=1.15` vs `Current Price` at `y=1.06`, with `margin.t=86`) whenever `abs(target - price) / max(price, 1) < 0.15`.
- **[Strict opening-sentence check rejecting a valid LLM draft on subtle wording]** → Mitigated by matching only unambiguous metric-ribbon lead-ins (starting with a ribbon metric label like `Gross margin`, `Operating margin`, `Base DCF`, `At <num>% WACC`, or a leading number) and feeding concrete rewrite examples into the 2-retry loop.
- **[Word count creeping above 750 with new Forward P/E row in rendered Markdown]** → Mitigated by keeping the new table row compact (~8 words) and maintaining tight word budgets in `synthesize_mock_memo(...)` and `InvestmentMemoSchema`.
