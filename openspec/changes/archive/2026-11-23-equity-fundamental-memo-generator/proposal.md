## Why

Fundamental equity analysis workflows that rely directly on LLMs for financial figures and valuation math are prone to numerical hallucination, inconsistent methodology, and verbose unstructured prose. Building a deterministic, modular Python pipeline that separates verified data ingestion and pure-Python financial modeling from strictly bounded local LLM synthesis—exposed via both a CLI and a Streamlit UI—produces repeatable, institutional-grade one-page investment memos suitable for executive review.

## What Changes

- Create a new Python package under `fundamental_memo/` (`pyproject.toml`, `README.md`, `src/fundamental_memo/`, `tests/`) adhering to Pydantic v2 data contracts, full type annotations, and `ruff`/`mypy` compliance.
- Add deterministic market and financial statement ingestion (`data_fetcher.py`) via `yfinance` for a target ticker and 3–5 peer comparables, with missing-field fallback derivations (e.g., computing Free Cash Flow from Operating Cash Flow and CapEx) and an offline `--mock-data` fixture mode.
- Add a pure-Python quantitative engine (`valuation_engine.py`) implementing a 5-year unlevered DCF model with configurable WACC and terminal growth rate, EV-to-Equity bridge, peer median EV/EBITDA and P/E comparable valuation, and earnings quality diagnostics (OCF/Net Income ratio, Accrual Ratio, and quality rating).
- Add a local OpenAI-compatible LLM synthesizer (`memo_synthesizer.py`) targeting Ollama (`http://localhost:11434/v1` default) or MLX endpoints, enforcing structured JSON output (`InvestmentMemoOutput`) with word-count constraints, automatic retry on validation failure (up to 2 retries), and deterministic offline synthesis when `--mock-data` is active (with an opt-in `--live-llm` override).
- Add a one-page Markdown renderer (`renderer.py`) formatting the header block, executive thesis, valuation & comps summary table, earnings quality assessment, bull/bear cases, and downside risks, with a strict post-render check enforcing total length $\le 650$ words (target 450–600 words).
- Add a CLI entry point (`cli.py`) supporting `python -m fundamental_memo.cli` with configurable ticker, peers, WACC, terminal growth, model, base URL, output path, `--mock-data`, and `--live-llm`.
- Add a Streamlit web UI (`streamlit_app.py`) featuring a model dropdown (`inkling-2-mini:latest`, `gemma4:31b-mlx`, `qwen3.8:27b-mlx`), editable Ollama base URL, ticker/peer/DCF parameter controls, offline mock toggle, rendered memo preview, and Markdown download.
- Add a `pytest` suite (`tests/`) validating DCF/comps/earnings-quality math, Pydantic schema and word-limit enforcement, and an offline end-to-end CLI dry run.

## Capabilities

### New Capabilities

- `financial-data-ingestion`: Fetch, normalize, and validate target and peer financial snapshots via `yfinance` or deterministic offline JSON fixtures, gracefully handling missing financial line items and network errors.
- `quantitative-valuation-engine`: Deterministically compute 5-year DCF intrinsic value per share, EV-to-Equity bridge, outlier-filtered peer median multiples, implied comps valuation, and earnings quality diagnostics in pure Python.
- `memo-synthesis-and-rendering`: Synthesize strictly grounded, schema-validated `InvestmentMemoOutput` narratives via a local OpenAI-compatible LLM (or deterministic offline mock synthesizer) and render a concise one-page Markdown memo enforced to $\le 650$ words.
- `cli-and-streamlit-ui`: Provide both a scriptable CLI (`python -m fundamental_memo.cli`) and an interactive Streamlit web UI with model selection (`inkling-2-mini:latest`, `gemma4:31b-mlx`, `qwen3.8:27b-mlx`) and configurable Ollama endpoint settings.

### Modified Capabilities

<!-- None: greenfield repository with no existing specs. -->

## Impact

- **New Package & Files**: Adds `fundamental_memo/` containing `pyproject.toml`, `README.md`, `src/fundamental_memo/{__init__.py,cli.py,schemas.py,data_fetcher.py,valuation_engine.py,memo_synthesizer.py,renderer.py,streamlit_app.py}`, bundled mock fixtures, and `tests/`.
- **Dependencies**: Introduces Python 3.10+ runtime dependencies (`pydantic>=2`, `yfinance`, `openai`, `streamlit`) and dev/verification dependencies (`pytest`, `ruff`, `mypy`).
- **External Integrations**: Integrates with Yahoo Finance (`yfinance`) for live market data and local OpenAI-compatible inference servers (Ollama at `http://localhost:11434/v1` by default, or MLX at `http://localhost:8080/v1`); both can be bypassed offline via `--mock-data`.
