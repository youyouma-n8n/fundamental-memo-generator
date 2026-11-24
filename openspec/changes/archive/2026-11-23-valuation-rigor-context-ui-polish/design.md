## Context

This change refines the existing `fundamental_memo` package at `/Users/eugeneyzhou/my_work/uchicago_mc/mc_03/fundamental_memo` following the previous institutional upgrade (`institutional-memo-valuation-upgrade`). All 37 `pytest` tests, `ruff check`, and `mypy --strict` checks currently pass, and all three local Ollama models (`inkling-2-mini:latest`, `gemma4:31b-mlx`, `qwen3.8:27b-mlx`) run end-to-end with `reasoning_effort="none"`.

See `proposal.md` for motivation and `specs/*/spec.md` for behavioral contracts.

## Goals / Non-Goals

**Goals:**
- Guarantee accounting self-consistency (`enterprise_value = market_cap + total_debt - cash_and_equivalents`) across live fetches, fixtures, and `target_multiples.ev_to_ebitda`.
- Expose Perpetuity DCF's implied exit EV/EBITDA multiple and a 5×5 WACC × 5Y FCF CAGR DCF sensitivity matrix in `ValuationAnalysis` and render it interactively in Streamlit.
- Ground Bull/Bear cases in concise 2-sentence `business_summary` context while eliminating ribbon-echoing prose and preserving 100% numeric grounding accuracy.
- Fix all desktop UI/chart visual polish issues (KPI truncation, Football Field clipping/callout overlap, Peer Scatter bubble contrast + median line).

**Non-Goals:**
- Full SEC 10-K/10-Q segment revenue parsing beyond Yahoo Finance's `longBusinessSummary`.
- Adding new third-party dependencies (existing `pandas`, `plotly`, `streamlit` cover all new features natively).

## Decisions

### 1. Self-Consistent Enterprise Value (`schemas.py`, `data_fetcher.py`)
- **Decision:** Always compute `enterprise_value = market_cap + total_debt - cash_and_equivalents` in `build_snapshot_from_raw(...)` (ignoring raw upstream `info["enterpriseValue"]`) AND enforce the same accounting identity in `FinancialSnapshot`'s `@model_validator(mode="after")` so every `FinancialSnapshot` (live, custom JSON fixture, or bundled mock) satisfies `enterprise_value == market_cap + total_debt - cash_and_equivalents` to the exact dollar. Recompute `target_multiples["ev_to_ebitda"]` from this self-consistent `enterprise_value` (already uses `snapshot.enterprise_value / snapshot.ebitda_ttm`).
- **Alternatives considered:** Computing self-consistent EV only in `data_fetcher.py` (rejected because custom JSON fixtures or directly constructed snapshots could still carry mismatched `enterprise_value`).

### 2. Perpetuity-Implied Exit Multiple & 5×5 Sensitivity Matrix (`schemas.py`, `valuation_engine.py`)
- **Decision:**
  - Add `DcfSensitivityMatrix(BaseModel)` with `wacc_values: list[float]`, `cagr_values: list[float]`, and `grid: list[list[float | None]]`.
  - Add `implied_exit_ev_ebitda: float | None = None` and `dcf_sensitivity_matrix: DcfSensitivityMatrix | None = None` to `ValuationAnalysis`.
  - Compute `implied_exit_ev_ebitda`: with `fcf_5 = fcf_0 * (1 + base_cagr)^5`, `terminal_value_5 = fcf_5 * (1 + g_term) / (wacc - g_term)`, and `ebitda_5 = ebitda_ttm * (1 + base_cagr)^5`, return `terminal_value_5 / ebitda_5` if `ebitda_ttm > 0` else `None`.
  - Compute `dcf_sensitivity_matrix`:
    - `wacc_values = [base_wacc - 0.010, base_wacc - 0.005, base_wacc, base_wacc + 0.005, base_wacc + 0.010]`
    - `cagr_values = [max(0.0, base_cagr + delta) for delta in (-0.05, -0.025, 0.0, 0.025, 0.05)]`
    - For each `(cagr, wacc)` pair, evaluate `_evaluate_perpetuity_dcf_per_share(...)` if `wacc > terminal_growth_rate and wacc > 0`, otherwise record `None`. Thus `grid[2][2]` matches `dcf_intrinsic_value_per_share` identically.
- **Alternatives considered:** Clamping WACC columns upward when `base_wacc - 0.010 <= terminal_growth_rate` (rejected because shifting column spacing breaks symmetry; returning `None` for mathematically undefined cells keeps column intervals exact).

### 3. Sanitized `business_summary` & Grounding Auditor Whitelisting (`data_fetcher.py`, `memo_synthesizer.py`)
- **Decision:**
  - Add `business_summary: str | None = None` to `FinancialSnapshot`.
  - Implement `sanitize_business_summary(raw_summary: str | None, max_sentences: int = 2, max_chars: int = 450) -> str | None`: normalize whitespace, split on sentence boundaries (`(?<=[.!?])\s+`), take up to 2 sentences, and if total length exceeds 450 characters, trim cleanly at a word boundary ending with `"..."` (or keep sentence 1 if sentence 1 fits cleanly).
  - Add a realistic 2-sentence `business_summary` for `AVGO` in `fixtures/mock_market_data.json` (referencing custom AI accelerators, Ethernet networking switches, and enterprise infrastructure software).
  - In `verify_memo_grounding_and_repetition(...)`, extract any numeric tokens present in `snapshot.business_summary` and add them to the allowed grounding number bucket so qualitative facts (e.g., `"800G"`, `"5G"`, `"200+"`) never trigger false positives, while keeping zero-hallucination enforcement 100% strict for all financial figures.
- **Alternatives considered:** Stripping all digits from `business_summary` via regex (rejected because stripping digits corrupts legitimate semiconductor/product terms like `"5G"`, `"3nm"`, or `"800G"`).

### 4. Anti-Echoing Prose & Business-Grounded Bull/Bear Synthesis (`memo_synthesizer.py`, `renderer.py`)
- **Decision:**
  - Update `renderer.py` Key Metrics Ribbons to clean italicized markdown (`*Gross Margin:* ...`) matching the proposal's convention, and update `SYSTEM_PROMPT` + `build_synthesis_user_prompt(...)` to explicitly forbid opening any section body by reciting metrics already printed in its top ribbon.
  - Require `bull_case` and `bear_case` bullets to weave in at least one concrete segment/product driver from `financial_snapshot.business_summary` alongside financial durability/risks.
  - Update `synthesize_mock_memo(...)` so deterministic offline memos also avoid ribbon echoing and reference concrete business drivers extracted from `snapshot.business_summary` when available.
- **Alternatives considered:** Post-processing LLM text to strip repeated leading sentences (rejected as brittle compared to clean prompt instructions + updated deterministic mock synthesis).

### 5. Chart Polish & Native Styled 5×5 Sensitivity Table (`charts.py`, `streamlit_app.py`)
- **Decision:**
  - **KPI Row (`streamlit_app.py`):** Update the 5 columns to exact compact labels and deltas:
    1. `Current Price` (`$X.XX` | `52W: $L–$H`)
    2. `DCF Intrinsic Value` (`$X.XX` | `±X.X% vs. price`)
    3. `Market-Implied CAGR` (`X.X%` | `±X.X% vs. base`)
    4. `ROIC (TTM)` (`X.X%` | `OpM X.X% | GM X.X%`)
    5. `Earnings Quality` (`High`/`Moderate`/`Low` | `OCF/NI X.XXx | Adj $X.XB`)
  - **Valuation Football Field (`charts.py`):** Set `xaxis.range = [max(0.0, min_val * 0.75), max_val * 1.22]` where `min_val`/`max_val` span all bar endpoints and `current_price`. Draw the dashed vertical line via `fig.add_vline(x=snapshot.current_price, line_width=2, line_dash="dash", line_color=TARGET_ACCENT_COLOR)` and place the callout as an explicit paper-anchored annotation (`fig.add_annotation(x=snapshot.current_price, y=1.08, yref="paper", showarrow=False, text=f"Current Price: ${snapshot.current_price:,.2f}", font={"color": TARGET_ACCENT_COLOR})`) with `margin={"l": 10, "r": 30, "t": 72, "b": 40}` so it never overlaps the top bar.
  - **Peer Valuation Scatter (`charts.py`):** Pass `peer_median_ev_ebitda: float | None = None` to `build_peer_valuation_scatter(...)`. When positive market caps are available, pass raw `market_cap` values as `marker.size` with `sizemode="area"` and `sizeref = 2.0 * max(market_caps) / (42**2)` and `sizemin=8`. When `peer_median_ev_ebitda` is present, add `fig.add_hline(y=peer_median_ev_ebitda, line_dash="dash", line_color="#94A3B8", annotation_text=f"Peer Median ({peer_median_ev_ebitda:.1f}x)", annotation_position="top right")`.
  - **5×5 DCF Sensitivity Table (`streamlit_app.py`):** Build a `pandas.DataFrame` indexed by formatted CAGR rows (`"10.0%"` .. `"20.0%"`) with formatted WACC columns (`"8.50%"` .. `"10.50%"`), style via `df.style.apply(...)` (muted green background when cell > `current_price`, muted red/neutral when <= `current_price`, bold + accent border on center cell `(2, 2)`), render via native `st.dataframe(..., width="stretch", alt=...)` inside an `st.expander("5×5 DCF Sensitivity Matrix (WACC × 5Y FCF CAGR)", expanded=True)`, and display the implied exit EV/EBITDA comparison `st.caption(...)` directly beneath it.
- **Alternatives considered:** Custom HTML table via `st.markdown(..., unsafe_allow_html=True)` (rejected per `developing-with-streamlit` skill guidelines favoring native `st.dataframe` + `pandas.Styler` over raw HTML).

## Risks / Trade-offs

- **[Existing unit tests that pass arbitrary `enterprise_value` in `_sample_snapshot`]** → Mitigated by updating any test snapshot that intentionally diverged from `market_cap + total_debt - cash` (specifically `moderate_snapshot` in `test_valuation_engine.py`) and adding explicit tests asserting the exact EV accounting identity.
- **[`pandas.Styler` CSS compatibility across Streamlit versions]** → Mitigated by using standard `background-color`, `font-weight`, and `border` properties supported natively by Streamlit 1.67's `st.dataframe` and verifying via `AppTest`.
- **[Large market-cap spread (e.g. NVDA $3.15T vs MRVL $76B) with area sizing]** → Mitigated by setting `sizemin=8` alongside `sizemode="area"` and `sizeref = 2.0 * max(market_caps) / (42**2)` so smaller peers remain cleanly visible and clickable.
