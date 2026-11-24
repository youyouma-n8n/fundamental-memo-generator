## Context

See [proposal.md](proposal.md) for motivation and capability overview. The codebase lives under `fundamental_memo/src/fundamental_memo/` with Pydantic v2 contracts (`schemas.py`), Yahoo Finance + offline fixture ingestion (`data_fetcher.py`, `fixtures/mock_market_data.json`), deterministic DCF/comps valuation (`valuation_engine.py`), Ollama/MLX LLM synthesis + strict numeric grounding verification (`memo_synthesizer.py`), one-page Markdown rendering (`renderer.py`), Plotly visualizers (`charts.py`), and the Streamlit web UI (`streamlit_app.py`).

Two constraints shape this design:
1. **Strict Zero-Hallucination & Word Budget**: `renderer.py` enforces `MAX_MEMO_WORDS = 750` and runs `verify_memo_grounding_and_repetition(...)` so every numeric literal in synthesized prose must originate from the deterministic Audit Trail JSON.
2. **Zero Extra Dependencies & Strict Typing**: The project passes `mypy --strict` and `ruff` with no extra third-party packages beyond `pydantic`, `yfinance`, `openai`, `streamlit`, `plotly`, and `pandas`.

## Goals / Non-Goals

**Goals:**
- Auto-derive `ebitda_margin_ttm` and `fcf_margin_ttm` on `FinancialSnapshot` (so both live ingestion and direct test/fixture construction populate them consistently).
- Extract a chronological 4-quarter `QuarterlyPoint` list from `yfinance` quarterly statements and mirror it in offline fixtures.
- Surface cash/EBITDA margins in the Profitability & Cash Quality ribbon and encode the `> 15pp` M&A amortization rule in both LLM prompting and offline deterministic synthesis without breaching the 750-word ceiling or grounding audit.
- Permanently eliminate Valuation Football Field top callout collisions across any spread between `Current Price` and `Analyst Consensus Target`.
- Deliver a pure-Python `html_exporter.py` module generating a standalone, print-friendly interactive HTML research pack downloadable directly alongside the Markdown memo in Streamlit.

**Non-Goals:**
- Server-side PDF rendering (e.g., headless Chromium / WeasyPrint / Kaleido static PNG rasterization); browser "Print → Save as PDF" over print-friendly HTML CSS covers offline PDF export cleanly with zero native binary dependencies.
- Modifying DCF math, Reverse DCF bisection, or peer multiple formulas.
- Bundling the multi-megabyte inline Plotly.js source inside the HTML file (a single pinned Plotly.js CDN `<script>` tag in `<head>` keeps exported files compact while preserving full interactive hover/zoom).

## Decisions

### 1. Auto-derived TTM cash & EBITDA margins on `FinancialSnapshot`
- **Decision**: Add optional fields `ebitda_margin_ttm: float | None = None` and `fcf_margin_ttm: float | None = None` on `FinancialSnapshot` plus a Pydantic `model_validator(mode="after")` that automatically populates them as `ebitda_ttm / revenue_ttm` and `free_cash_flow_ttm / revenue_ttm` whenever they are `None` and `revenue_ttm > 0.0` (leaving them `None` when `revenue_ttm <= 0.0`).
- **Rationale**: Existing unit tests and fixtures that construct `FinancialSnapshot` directly without passing the two new margin fields will automatically receive accurate, self-consistent margin values without breaking backward compatibility.
- **Alternatives Considered**: Computing margins only inside `build_snapshot_from_raw()` in `data_fetcher.py` — rejected because direct `FinancialSnapshot(...)` construction in tests or downstream callers would leave them `None`.

### 2. Quarterly trajectory schema and `yfinance` extraction
- **Decision**: Add `QuarterlyPoint(BaseModel)` with fields `period: str`, `revenue: float`, `gross_margin: float | None = None`, `operating_margin: float | None = None`, `free_cash_flow: float | None = None`, and `quarterly_trajectory: list[QuarterlyPoint] = Field(default_factory=list)` on `FinancialSnapshot`. Add `extract_quarterly_trajectory(quarterly_income_stmt, quarterly_cashflow, *, max_quarters=4)` in `data_fetcher.py` following the same defensive row-lookup pattern as `extract_historical_trajectory`.
- **Period Formatting**: Convert column dates/timestamps into `"YYYY-Q<1..4>"` using calendar quarter `((month - 1) // 3) + 1` (e.g., `2025-10-31` → `"2025-Q4"`), falling back to cleaned string labels if a column is not date-parseable. Sort columns chronologically oldest to newest and slice `[-max_quarters:]`.
- **FCF Fallback**: Prefer `"Free Cash Flow"` from `quarterly_cashflow`; when absent, compute `operating_cash_flow - abs(capex)` using `"Operating Cash Flow"` / `"Cash Flow From Continuing Operating Activities"` and `"Capital Expenditure"` / `"Capital Expenditures"`.
- **Offline Mock Fixtures**: Add realistic 4-quarter `quarterly_trajectory` sequences (`2025-Q1` through `2025-Q4`) for all bundled mock tickers in `fixtures/mock_market_data.json` (especially `AVGO`, `NVDA`, `AAPL`, `MSFT`).

### 3. Amortization-aware profitability synthesis & grounding compatibility
- **Decision**:
  - Update `renderer.py`'s `Profitability & Cash Quality` ribbon to include `*EBITDA Margin:* {_fmt_pct(snapshot.ebitda_margin_ttm, decimals=1)} | *FCF Margin:* {_fmt_pct(snapshot.fcf_margin_ttm, decimals=1)}`. To protect the 750-word limit, keep the addition concise (+6 words) and keep per-section prompt word targets conservative.
  - In `memo_synthesizer.py`:
    - Add a deterministic helper `_has_amortization_margin_gap(snapshot)` returning `True` when `ebitda_margin_ttm` and `operating_margin_ttm` are both non-null and `(ebitda_margin_ttm - operating_margin_ttm) > 0.15`.
    - Inject an explicit rule into the LLM system prompt (and conditional guidance in the user prompt when the gap exceeds 15pp) directing `profitability_and_cash_quality` to evaluate `ebitda_margin_ttm` and `fcf_margin_ttm` alongside `operating_margin_ttm`, noting non-cash amortization/D&A rather than calling GAAP operating margin an operational collapse.
    - Update `synthesize_mock_memo(...)` similarly so offline runs demonstrate the exact same amortization-aware analysis when `ebitda_margin_ttm - operating_margin_ttm > 0.15`.
    - Extend `_collect_allowed_numbers(...)` to whitelist year tokens (`2024`, `2025`, `2026`, etc.) and quarter numbers extracted from `snapshot.quarterly_trajectory[].period` (in addition to `ebitda_margin_ttm` and `fcf_margin_ttm`, which are automatically picked up via recursive traversal of `snapshot.model_dump()`).

### 4. Permanent Valuation Football Field annotation stagger
- **Decision**: Replace the conditional overlap heuristic in `charts.py:build_valuation_football_field` with permanent vertical and horizontal anchor staggering:
  - `Current Price`: `x=snapshot.current_price`, `y=1.12`, `yref="paper"`, `xanchor="right"`, `xshift=-4`, `showarrow=False`, `font={"color": TARGET_ACCENT_COLOR, "size": 12}`.
  - `Analyst Consensus Target` (when present): `x=snapshot.analyst_target_mean`, `y=1.03`, `yref="paper"`, `xanchor="left"`, `xshift=4`, `showarrow=False`, `font={"color": CONSENSUS_LINE_COLOR, "size": 12}`.
  - Layout margins: `margin={"l": 10, "r": 40, "t": 78, "b": 40}` (exceeding `t >= 65` and `r >= 40` so `y=1.12` sits comfortably below the chart title and right-anchored/left-anchored labels never clip).
- **Rationale**: Opposite `xanchor` + opposing `xshift` + 0.09 paper-height vertical separation guarantees zero bounding-box collision even when `analyst_target_mean == current_price` or when the spread is wide.
- **Alternatives Considered**: Dynamic threshold switching (`relative_gap < 0.25`) — previously proved brittle near boundary spreads where long label text (`Analyst Consensus Target: $XXX.XX`) still collided horizontally.

### 5. Tabbed Annual (3Y) / Quarterly (4Q) panel in Streamlit
- **Decision**: In `streamlit_app.py`, wrap the lower-right Historical Trajectory panel in `tab_annual, tab_quarterly = st.tabs(["Annual (3Y)", "Quarterly (4Q)"])`.
  - `Annual (3Y)`: Existing `build_historical_trajectory_chart(snapshot)` with `width="stretch"` and `alt=...` plus `_build_fcf_trajectory_caption(snapshot)`.
  - `Quarterly (4Q)`: Build a clean `pandas.DataFrame` via a pure helper `build_quarterly_momentum_dataframe(snapshot.quarterly_trajectory)` with columns `Quarter`, `Revenue ($B)`, `Gross Margin (%)`, `Operating Margin (%)`, `FCF ($B)` rendered with `st.dataframe(..., width="stretch", hide_index=True, alt=...)`. If `quarterly_trajectory` is empty, render a concise `st.caption(...)` notice.
- **Rationale**: Preserves the compact two-column lower dashboard rhythm alongside the 5×5 DCF Sensitivity Matrix without adding vertical scroll bloat.

### 6. Pure-Python Self-Contained HTML Exporter (`html_exporter.py`)
- **Decision**: Create `fundamental_memo/src/fundamental_memo/html_exporter.py` exposing `build_html_report(snapshot, valuation, peers, sensitivity, markdown_memo, *, football_fig=None, scatter_fig=None, trajectory_fig=None, model_label=None, word_count=None) -> str`.
  - **Markdown-to-HTML Conversion**: Implement a focused pure-Python converter (`_markdown_to_html`) handling the exact GFM subset produced by `renderer.py` (`#`/`##`/`###` headings, pipe tables with `---` alignment rows, unordered `- ` lists, inline `**bold**`, `*italic*`, and HTML escaping via `html.escape`) — avoiding any new third-party `markdown` dependency.
  - **Plotly Embedding**: Include a single `<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>` tag in `<head>`. Convert each Plotly figure via `fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})`. If figure arguments are omitted, build them internally using `charts.py` builders so callers can invoke `build_html_report` with or without pre-built figures.
  - **Structured Sections & Print-Friendly Styling**: Light institutional print-friendly palette (`max-width: 960px; margin: 0 auto; font-family: system-ui, -apple-system, sans-serif; color: #0f172a; background: #ffffff;`), `@media print` page-break hygiene, 5-card KPI grid (CSS grid `repeat(5, 1fr)`), interactive charts stack, Reverse DCF Reality Check callout, color-coded 5×5 DCF sensitivity HTML table (matching the green/red/base-border convention of `streamlit_app.py`), 4-quarter momentum HTML table (when available), rendered one-page investment memo HTML, and a header/footer `Grounding Audit: Passed` pill badge.
  - **Streamlit Integration**: Place two side-by-side download buttons (`st.columns(2)`) directly above the rendered Markdown memo: `Download memo_<TICKER>.md` (`mime="text/markdown"`) and `Download report_<TICKER>.html` (`mime="text/html"`), reusing the already-built `football_fig`, `scatter_fig`, and `trajectory_fig` to avoid redundant chart construction.

## Risks / Trade-offs

- **[Risk] Adding `*EBITDA Margin:*` and `*FCF Margin:*` to the Profitability ribbon could push borderline memos past the 750-word limit** → **Mitigation**: Keep the ribbon addition concise (~6 words), preserve existing conservative per-section prompt word budgets, and cover `count_words(rendered) <= MAX_MEMO_WORDS` in unit and E2E tests.
- **[Risk] Plotly.js CDN unavailable in completely air-gapped environments when opening `.html` locally** → **Mitigation**: All KPI cards, Reverse DCF callout, 5×5 sensitivity table, 4-quarter momentum table, and full investment memo render purely in static HTML/CSS even offline; the single CDN `<script>` enables full interactive Plotly charts whenever online (explicitly matching the proposal specification).
- **[Risk] Yahoo Finance quarterly cash-flow/income-statement column timestamps can occasionally be offset by a few days between statements** → **Mitigation**: Normalize timestamps to `YYYY-Q#` period keys before joining income statement and cash flow rows so slight filing date differences align cleanly onto the same fiscal quarter.
- **[Risk] Pure-Python Markdown-to-HTML converter encountering unexpected formatting** → **Mitigation**: Escape all raw text via `html.escape` before applying inline `**bold**`/`*italic*` formatting, cover headings/tables/bullet lists/paragraphs/escaped entities in dedicated unit tests, and test against real output of `render_investment_memo(...)`.
