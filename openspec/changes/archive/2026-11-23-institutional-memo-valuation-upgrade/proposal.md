## Why

The initial fundamental memo pipeline produces basic DCF and peer median numbers, but institutional investment committees require deeper capital-efficiency diagnostics (margins, ROIC, SBC-adjusted FCF, working capital drivers), market-implied expectations via Reverse DCF and Exit Multiple cross-checks, non-repetitive variant-perception commentary backed by automated numeric grounding checks, and visual valuation framing in the UI. Upgrading all three layers—quantitative engine, synthesis/verification layer, and Streamlit/Plotly visualizations—elevates the tool to institutional research standards while strictly preserving zero financial hallucination.

## What Changes

- **Expanded Financial Diagnostics (`schemas.py`, `data_fetcher.py`, `valuation_engine.py`, `fixtures/mock_market_data.json`)**:
  - Extend `FinancialSnapshot` and Audit Trail JSON with deterministic calculations for `gross_margin_ttm`, `operating_margin_ttm`, `roic_ttm` (using NOPAT with fallback 21% effective tax rate and invested capital), `sbc_ttm`, `sbc_adjusted_fcf_ttm`, `net_cash`, `net_cash_to_market_cap`, 52-week trading range (`52w_low`, `52w_high`), and `working_capital_metrics` (`dso_days`, `dio_days`, `ocf_net_income_gap_driver`).
  - Extend `PeerComparable` ingestion and mock fixtures with `revenue_growth_3y` (or YoY fallback), `market_cap`, and `fcf_yield`.
- **Reverse DCF & Exit Multiple Valuation (`valuation_engine.py`, `cli.py`)**:
  - Add a deterministic Reverse DCF root-finding solver computing `implied_fcf_cagr_5y` (reproducing `current_price` within `±$0.01`) and `cagr_spread_vs_base`.
  - Add configurable `5Y FCF CAGR` override (`--fcf-cagr`) and `Terminal Exit EV/EBITDA Multiple` (`--exit-multiple`, default `15.0x`) valuation cross-check (`exit_multiple_dcf_value`), plus 25th–75th percentile peer comps implied share price range for the Valuation Football Field.
- **BREAKING: Structured Debate Memo Schema & Grounding Audit (`schemas.py`, `memo_synthesizer.py`, `renderer.py`)**:
  - Upgrade the LLM output contract to `InvestmentMemoSchema` (aliasing `InvestmentMemoOutput` for import compatibility) with 6 structured, token-budgeted sections targeting 550–700 words: `executive_thesis` (max 60 words), `valuation_and_debate` (max 150 words), `profitability_and_cash_quality` (max 120 words), `bull_case` (3 bullets, max 90 words total), `bear_case` (3 bullets, max 90 words total), and `key_downside_risks` (3–4 bullets, max 90 words total).
  - Enforce anti-repetition rules (Single-Mention Rule capping headline valuation numbers to at most twice across `executive_thesis` + `valuation_and_debate` and forbidding them in `bull_case` and `bear_case`) and add a deterministic post-generation regex numeric grounding verifier against the Audit Trail JSON.
  - Update Markdown rendering (`renderer.py`) to format the upgraded sections cleanly with an updated post-render word ceiling (`<= 750` words to fit the 550–700 word target plus table scaffolding).
- **Streamlit UI & Plotly Visualizations (`streamlit_app.py`, `pyproject.toml`)**:
  - Add `plotly>=5.20.0` dependency.
  - Add sidebar controls under DCF Assumptions for `5Y FCF CAGR` (default `0.15`) and `Terminal Exit EV/EBITDA Multiple` (default `15.0`).
  - Expand top KPI row to 5 metrics (`Current Price`, `DCF Intrinsic Value`, `Market-Implied FCF CAGR`, `ROIC / Operating Margin`, `Earnings Quality`).
  - Render interactive **Valuation Football Field** and **Peer Valuation vs. Growth Scatter Plot** Plotly charts above the Markdown memo.

## Capabilities

### New Capabilities

- `expanded-financial-diagnostics`: Ingest and deterministically compute profitability margins, ROIC, SBC-adjusted FCF, net cash ratios, 52-week trading range, working capital days (DSO/DIO), and OCF-vs-Net-Income gap drivers across live and offline fixture modes.
- `reverse-dcf-and-exit-valuation`: Solve for market-implied 5-year FCF CAGR via Reverse DCF, compute Exit EV/EBITDA Multiple DCF valuation and peer comps 25th–75th percentile ranges, and ingest peer growth/market-cap metrics for valuation-growth comparison.
- `structured-debate-memo-synthesis`: Enforce the 6-section `InvestmentMemoSchema` with "The Debate / Variant Perception", Single-Mention non-redundancy validation, deterministic post-generation regex numeric grounding verification against the Audit Trail JSON, and updated one-page Markdown rendering.
- `interactive-valuation-charts`: Expose `5Y FCF CAGR` and `Terminal Exit EV/EBITDA Multiple` sidebar controls, a 5-card KPI header row, and interactive Plotly Valuation Football Field and Peer Valuation-Growth Scatter charts in the Streamlit UI.

### Modified Capabilities

<!-- None in openspec/specs/ yet (baseline change equity-fundamental-memo-generator is unarchived). -->

## Impact

- **Modified Modules**: `fundamental_memo/pyproject.toml`, `fundamental_memo/src/fundamental_memo/{__init__.py,schemas.py,data_fetcher.py,valuation_engine.py,memo_synthesizer.py,renderer.py,cli.py,streamlit_app.py}`, `fundamental_memo/src/fundamental_memo/fixtures/mock_market_data.json`, `fundamental_memo/README.md`, and `fundamental_memo/tests/*`.
- **New Dependency**: Adds `plotly>=5.20.0` (Reverse DCF uses pure-Python Brent/bisection root-finding over `[-0.20, 1.00]`, avoiding a heavy `scipy` binary dependency while meeting `±$0.01` accuracy).
- **Backward Compatibility**: `InvestmentMemoSchema` replaces the prior `valuation_summary` / `earnings_quality_assessment` / `key_risks` field names with `valuation_and_debate` / `profitability_and_cash_quality` / `key_downside_risks` (**BREAKING** for callers inspecting raw LLM schema attributes); existing CLI flags remain compatible with additive optional `--fcf-cagr` and `--exit-multiple` flags.
