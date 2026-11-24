## Context

This is a greenfield repository at `/Users/eugeneyzhou/my_work/uchicago_mc/mc_03` with OpenSpec configured under `openspec/`. See `proposal.md` for motivation and capability scope, and `specs/*/spec.md` for behavioral contracts.

Key environmental and architectural constraints:
- The workspace currently contains no Python source code or virtual environment; the host's default `/usr/bin/python3` is Python 3.9.6, whereas the data contracts use PEP 604 union syntax (`float | None`) with Pydantic v2, so the package will target Python `>=3.10` (with an isolated virtual environment created during implementation).
- Zero financial hallucination is a hard invariant: all market figures come from deterministic connectors or fixtures, all financial math runs in pure Python, and the LLM only synthesizes bounded narrative prose from validated JSON.
- Both CLI and Streamlit interfaces must invoke the exact same deterministic pipeline without duplicating business logic.

## Goals / Non-Goals

**Goals:**
- Deliver a clean, single-responsibility package layout under `fundamental_memo/` (`pyproject.toml`, `README.md`, `src/fundamental_memo/`, `tests/`) that passes `ruff`, `mypy`, and `pytest` cleanly.
- Enforce strict Pydantic v2 models at every pipeline stage (`FinancialSnapshot`, `PeerComparable`, `ValuationAnalysis`, `InvestmentMemoOutput`).
- Guarantee deterministic offline operation via `--mock-data` (both fixture financials and deterministic mock narrative synthesis) while allowing `--live-llm` override to exercise local Ollama/MLX models against fixture financials.
- Keep rendered Markdown memos consistently within the 450–600 word target window and strictly $\le 650$ words.
- Provide an intuitive Streamlit UI with the three specified model options (`inkling-2-mini:latest`, `gemma4:31b-mlx`, `qwen3.8:27b-mlx`) and an editable Ollama base URL (`http://localhost:11434/v1`).

**Non-Goals:**
- Direct SEC EDGAR/XBRL filing parsers, paid market data APIs, or cloud-hosted LLM providers.
- Multi-stage (e.g., 10-year fade) DCF models, Monte Carlo simulation, or portfolio construction.
- Persistent database storage, authentication, or PDF/DOCX export (Markdown output only).

## Decisions

### 1. Package Layout and Shared Pipeline Orchestration
- **Decision:** Structure the project under `fundamental_memo/` with `src/fundamental_memo/` containing the six core modules specified (`__init__.py`, `schemas.py`, `data_fetcher.py`, `valuation_engine.py`, `memo_synthesizer.py`, `renderer.py`, `cli.py`), plus `streamlit_app.py` and packaged mock fixtures under `src/fundamental_memo/fixtures/mock_market_data.json`. Expose a reusable `generate_memo_pipeline(...)` helper in `cli.py` (or re-exported in `__init__.py`) so both the CLI and `streamlit_app.py` execute the identical fetch → compute → synthesize → render sequence.
- **Alternatives considered:** Placing code at the repository root instead of `fundamental_memo/` (rejected because the specification explicitly defines the `fundamental_memo/` root layout); duplicating pipeline orchestration inside `streamlit_app.py` (rejected to prevent drift between CLI and UI).

### 2. Strict Pydantic v2 Data Contracts and Word Budgets (`schemas.py`)
- **Decision:** Define `FinancialSnapshot`, `PeerComparable`, `ValuationAnalysis`, and `InvestmentMemoOutput` as Pydantic v2 `BaseModel` classes with `extra="forbid"` on output schemas. Add an optional `total_assets: float | None = None` field to `FinancialSnapshot` so the accrual ratio uses Total Assets when available and cleanly falls back to Enterprise Value when unavailable. Enforce word-count limits (`executive_thesis <= 80`, `valuation_summary <= 100`, `earnings_quality_assessment <= 80`), exact bullet counts (`len(bull_case) == 3`, `len(bear_case) == 3`), and risk counts (`3 <= len(key_risks) <= 4`) via Pydantic `@field_validator` methods using whitespace-delimited word counting (`len(text.split())`). Also enforce concise per-bullet word bounds (e.g., $\le 28$ words per bullet) so total narrative stays within ~380–450 words, leaving ~130–160 words for Markdown headers/table scaffolding to land cleanly inside the 450–600 word target and $\le 650$ word cap.
- **Alternatives considered:** Post-hoc regex truncation of LLM output (rejected because silently truncating prose damages institutional quality and hides schema violations).

### 3. Market Data Ingestion and Offline Fixtures (`data_fetcher.py`)
- **Decision:** Use `yfinance.Ticker` for live target and peer fetching with defensive extraction across `.info`, `.cashflow`, `.income_stmt`, and `.balance_sheet`.
  - If `freeCashflow` is missing, derive `free_cash_flow_ttm = operating_cash_flow_ttm - abs(capex_ttm)`.
  - Derive `historical_revenue_growth_3y` as the 3-year revenue CAGR from annual income statements when $\ge 4$ annual periods exist (or available multi-year CAGR), falling back to Yahoo `revenueGrowth` when historical series are incomplete.
  - Wrap network timeouts, HTTP errors, and missing non-derivable fields (e.g., `current_price`, `shares_outstanding`) in a typed `DataFetchError`.
  - Bundle a deterministic fixture file (`mock_market_data.json`) with realistic figures for `AVGO` and semiconductor peers (`NVDA`, `AMD`, `MRVL`, `QCOM`) loaded via `importlib.resources` when `--mock-data` is enabled, and support arbitrary local JSON fixtures via `--fixture-path`.
- **Alternatives considered:** Hardcoding Python dictionaries in `data_fetcher.py` (rejected in favor of JSON fixtures so the same validation loader tests both built-in mock data and custom user JSON files).

### 4. Pure-Python Quantitative Engine & Edge-Case Handling (`valuation_engine.py`)
- **Decision:** Implement all financial formulas in pure Python with explicit parameter validation and docstrings:
  - **5-Year DCF:** Clamp projected FCF growth rate to `[0.02, 0.15]` from `historical_revenue_growth_3y`. Require `wacc > terminal_growth_rate`, `wacc > 0`, `shares_outstanding > 0`, and `free_cash_flow_ttm > 0` (raising a typed `ValuationError` / `NegativeFreeCashFlowError` on non-positive base FCF rather than compounding negative cash flows into invalid valuations). Project $\text{FCF}_t = \text{FCF}_0 \cdot (1 + g_{\text{fcf}})^t$ for $t \in \{1..5\}$, compute Gordon Growth $\text{TV} = \text{FCF}_5 \cdot (1 + g_{\text{term}}) / (\text{WACC} - g_{\text{term}})$, sum discounted cash flows plus discounted terminal value to obtain Enterprise Value, bridge to Equity Value via $\text{EV} + \text{Cash} - \text{Debt}$, and divide by `shares_outstanding`. Also provide a pure helper computing WACC sensitivity ($\pm 100\text{ bps}$) for the renderer's sensitivity note.
  - **Peer Comparables:** Exclude `None` and `<= 0` multiples before computing `statistics.median` for `ev_to_ebitda` and `pe_ratio`. Derive implied share price from EV/EBITDA (when median and `ebitda_ttm > 0` exist) and from P/E (when median and `net_income_ttm > 0` exist); average both when available, use the single available estimate if only one exists, or return `None`.
  - **Earnings Quality:** Compute `ocf_to_net_income_ratio = operating_cash_flow_ttm / net_income_ttm` (if `net_income_ttm <= 0`, set ratio to `0.0` and classify `"Low"`). Compute `accrual_ratio = (net_income_ttm - operating_cash_flow_ttm) / denominator` where `denominator` is `total_assets` if present and positive, else `enterprise_value`. Classify `earnings_quality_flag`: `"Low"` if `net_income_ttm <= 0` or `ocf_to_net_income_ratio < 0.8` or `accrual_ratio > 0.10`; `"High"` if `ocf_to_net_income_ratio >= 1.0` and `accrual_ratio <= 0.05`; otherwise `"Moderate"`.
- **Alternatives considered:** Silently clamping negative FCF to zero (rejected because a zero DCF value misrepresents distressed/high-capex equities instead of explicitly surfacing the modeling limitation).

### 5. Local OpenAI-Compatible Synthesizer & Deterministic Mock Synthesis (`memo_synthesizer.py`)
- **Decision:** Use the `openai` Python SDK (`OpenAI(base_url=base_url, api_key="ollama", timeout=...)`) targeting Ollama (`http://localhost:11434/v1` default) and MLX (`http://localhost:8080/v1`) endpoints.
  - Inject the system prompt enforcing strict citation of provided JSON only, pass serialized `FinancialSnapshot`, `PeerComparable`, and `ValuationAnalysis` JSON plus the exact `InvestmentMemoOutput` JSON schema and word limits in the user prompt, and request JSON output.
  - Strip optional markdown code fences before `InvestmentMemoOutput.model_validate_json(...)`. On JSON or Pydantic validation failure, retry up to 2 times (3 total attempts), appending the prior invalid response and concrete Pydantic validation error messages so the model can self-correct.
  - Provide `synthesize_mock_memo(snapshot, valuation, peers)` to deterministically generate a concise, metrics-grounded `InvestmentMemoOutput` when `--mock-data` is used without `--live-llm`.
- **Alternatives considered:** Using `urllib`/`requests` directly (rejected because `openai` SDK handles OpenAI-compatible chat completions cleanly and is standard across Ollama and MLX servers); using Instructor library (rejected to keep dependencies minimal and control the exact 2-retry validation prompt directly).

### 6. CLI & Streamlit Interface (`cli.py`, `streamlit_app.py`)
- **Decision:**
  - Implement `cli.py` with stdlib `argparse` for minimal dependencies, strict `mypy` compatibility, and exact support for the specified flags (`--ticker`, `--peers`, `--wacc`, `--terminal-growth`, `--model`, `--base-url`, `--output`, `--mock-data`, `--fixture-path`, `--live-llm`). Default `--model` to `inkling-2-mini:latest` and `--base-url` to `http://localhost:11434/v1`.
  - Implement `streamlit_app.py` with a sidebar form containing ticker, comma-separated peers, WACC and terminal growth sliders/number inputs, a `st.selectbox` dropdown with `["inkling-2-mini:latest", "gemma4:31b-mlx", "qwen3.8:27b-mlx"]`, an editable `base_url` text input defaulting to `http://localhost:11434/v1`, an "Use Offline Mock Data" toggle, and an optional "Use Live Local LLM with Mock Data" toggle. Display top-line `st.metric` KPI cards, the rendered Markdown memo, word count indicator, expandable validated JSON audit view, and a `st.download_button` for `memo_<TICKER>.md`.
- **Alternatives considered:** Using `typer` for CLI (acceptable, but `argparse` avoids Click/Typer runtime quirks and extra dependencies while keeping identical UX).

## Risks / Trade-offs

- **[Local model JSON adherence varies across `inkling-2-mini:latest`, `gemma4:31b-mlx`, and `qwen3.8:27b-mlx`]** → Mitigated by explicit JSON schema instructions, stripping markdown fences before parsing, and a 2-retry feedback loop passing exact Pydantic errors back to the model.
- **[`yfinance` upstream API changes or rate limiting]** → Mitigated by defensive extraction with fallback derivations (FCF from OCF - |CapEx|), clean `DataFetchError` reporting, and first-class offline `--mock-data` / `--fixture-path` execution.
- **[Post-render Markdown length exceeding 650 words due to verbose bullets or table formatting]** → Mitigated by tight per-field word limits in `InvestmentMemoOutput`, compact Markdown table formatting in `renderer.py`, and a hard post-render word-count guard raising `MemoWordLimitError`.
- **[Host default `/usr/bin/python3` is 3.9.6]** → Mitigated by declaring `requires-python = ">=3.10"` in `pyproject.toml` and documenting virtual environment creation with Python 3.10+ in `README.md` (and using Python 3.10+ during implementation/verification).
