## 1. Project Scaffold & Tooling

- [x] 1.1 Create the `fundamental_memo/` package directory structure (`pyproject.toml`, `README.md`, `src/fundamental_memo/__init__.py`, `src/fundamental_memo/fixtures/`, `tests/`) with Python `>=3.10`, dependencies (`pydantic>=2`, `yfinance`, `openai`, `streamlit`), dev dependencies (`pytest`, `ruff`, `mypy`), and tool configurations for `ruff` and `mypy`; verify editable installation (`pip install -e ".[dev]"`) succeeds in a Python 3.10+ virtual environment.

## 2. Data Contracts (`schemas.py`)

- [x] 2.1 Implement Pydantic v2 schemas (`FinancialSnapshot`, `PeerComparable`, `ValuationAnalysis`, `InvestmentMemoOutput`) and domain exception hierarchy in `fundamental_memo/src/fundamental_memo/schemas.py`, including word-count validators (`executive_thesis <= 80`, `valuation_summary <= 100`, `earnings_quality_assessment <= 80`), list-length validators (exact 3 for `bull_case`/`bear_case`, 3–4 for `key_risks`), and optional `total_assets` support; verify `mypy` and `ruff` pass on `schemas.py`.

## 3. Financial Data Ingestion (`data_fetcher.py`)

- [x] 3.1 Create bundled offline mock fixture `fundamental_memo/src/fundamental_memo/fixtures/mock_market_data.json` containing realistic, internally consistent financial records for `AVGO` and semiconductor peers (`NVDA`, `AMD`, `MRVL`, `QCOM`); verify JSON parses cleanly against `FinancialSnapshot` and `PeerComparable`.
- [x] 3.2 Implement `fundamental_memo/src/fundamental_memo/data_fetcher.py` with live `yfinance` ingestion for target + 3–5 peer tickers, missing-FCF fallback derivation (`operating_cash_flow_ttm - abs(capex_ttm)`), 3-year historical revenue CAGR extraction, timeout/missing-field `DataFetchError` handling, graceful per-peer failure handling, built-in `--mock-data` loader, and custom `--fixture-path` JSON loader; verify offline fixture loading and fallback derivations via unit tests.

## 4. Quantitative Valuation Engine (`valuation_engine.py`)

- [x] 4.1 Implement pure-Python 5-year unlevered DCF valuation (clamped growth floor 2% / cap 15%, configurable WACC and Gordon Growth terminal rate, EV-to-Equity bridge, WACC $\pm 100\text{ bps}$ sensitivity helper, and explicit `NegativeFreeCashFlowError` / invalid-parameter guards) in `fundamental_memo/src/fundamental_memo/valuation_engine.py`; verify exact DCF math and edge cases via unit tests.
- [x] 4.2 Implement peer comparable median calculations (excluding `None` and `<= 0` outliers), implied share price blending (EV/EBITDA equity bridge + P/E), and earnings quality diagnostics (`ocf_to_net_income_ratio`, `accrual_ratio` with Total Assets → Enterprise Value denominator fallback, and `earnings_quality_flag` classification) in `fundamental_memo/src/fundamental_memo/valuation_engine.py`; verify all branches via unit tests.

## 5. LLM Synthesis & One-Page Markdown Renderer (`memo_synthesizer.py`, `renderer.py`)

- [x] 5.1 Implement `fundamental_memo/src/fundamental_memo/memo_synthesizer.py` with an OpenAI-compatible local client (`http://localhost:11434/v1` default, supporting MLX endpoints), strict anti-hallucination system prompt with serialized `FinancialSnapshot` + `ValuationAnalysis` JSON, code-fence stripping, automatic retry loop (max 2 retries with validation-error feedback), and deterministic offline `synthesize_mock_memo(...)`; verify retry handling with mocked client responses and verify offline mock output passes `InvestmentMemoOutput` validation.
- [x] 5.2 Implement `fundamental_memo/src/fundamental_memo/renderer.py` to render all six required Markdown memo sections (Header Block, Executive Thesis, Valuation & Comps Summary Table with DCF sensitivity note, Earnings Quality & Cash Conversion, Bull vs. Bear Case, Key Downside Risks) and enforce a strict post-render word-count check ($\le 650$ words, raising `MemoWordLimitError` on violation); verify rendered output contains all sections and enforces the 650-word cap via unit tests.

## 6. CLI & Streamlit Web UI (`cli.py`, `streamlit_app.py`)

- [x] 6.1 Implement shared pipeline orchestration and `argparse` CLI entry point in `fundamental_memo/src/fundamental_memo/cli.py` supporting `--ticker`, `--peers`, `--wacc`, `--terminal-growth`, `--model` (default `inkling-2-mini:latest`), `--base-url` (default `http://localhost:11434/v1`), `--output`, `--mock-data`, `--fixture-path`, and `--live-llm`; verify running `python -m fundamental_memo.cli --ticker AVGO --peers NVDA,AMD,MRVL,QCOM --mock-data --output memo_AVGO.md` exits 0 and writes a valid memo under 650 words.
- [x] 6.2 Implement `fundamental_memo/src/fundamental_memo/streamlit_app.py` with sidebar controls for ticker, peers, WACC, terminal growth, model dropdown (`inkling-2-mini:latest`, `gemma4:31b-mlx`, `qwen3.8:27b-mlx`), editable Ollama base URL (`http://localhost:11434/v1`), offline mock mode toggle (plus optional live-LLM toggle), KPI metric summary cards, rendered Markdown memo with word count, JSON audit expander, error banner handling, and `.md` download button; verify module imports cleanly and passes `ruff` and `mypy` checks (plus Streamlit AppTest or headless smoke check).

## 7. Verification Suite & Documentation

- [x] 7.1 Implement comprehensive `pytest` suite under `fundamental_memo/tests/` covering `test_valuation_engine.py` (DCF math, EV-to-Equity bridge, growth clamping, negative FCF, peer medians with `None`/negative outliers, earnings quality flags), `test_schemas.py` (`InvestmentMemoOutput` word-limit and bullet-count rejections), `test_synthesizer_and_renderer.py` (retry loop, offline mock synthesis, post-render $\le 650$ word guard), and `test_cli_e2e.py` (offline `--mock-data` CLI dry run producing `memo_AVGO.md` under 650 words); verify `pytest` passes 100%.
- [x] 7.2 Complete `fundamental_memo/README.md` with installation steps, CLI usage examples (live Ollama/MLX and offline `--mock-data`), Streamlit UI launch command, and architecture overview; run `ruff check`, `mypy`, and `pytest` across the entire package and confirm zero warnings or failures.
