# Equity Fundamental Deep-Dive & One-Page Memo Generator

Deterministic pure-Python equity valuation engine, Watchlist Quick-Scan Screener, interactive Plotly charts, standalone HTML report export, and strictly grounded local LLM (Ollama / MLX) one-page investment memo generator.

## Repository Layout

- `fundamental_memo/` — Python package (`src/fundamental_memo/`), unit & Streamlit `AppTest` suite (`tests/`), offline mock fixtures (`fixtures/`), and full documentation (`fundamental_memo/README.md`).
- `openspec/` — Spec-driven specifications (`openspec/specs/`, 23 validated capabilities) and archived change history (`openspec/changes/archive/`).
- `.agents/` — Workspace agent skills and OpenSpec workflows.

## Quick Start on a New MacBook

Requires **Python 3.12+** (or 3.10+) and optionally [Ollama](https://ollama.com/) / MLX for local LLM synthesis.

```bash
git clone https://github.com/youyouma-n8n/fundamental-memo-generator.git
cd fundamental-memo-generator/fundamental_memo

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Run Tests & Quality Checks

```bash
pytest -v
ruff check src tests
mypy src tests
```

### Launch the Streamlit Web App

```bash
streamlit run src/fundamental_memo/streamlit_app.py
```

- **No local LLM required to test immediately:** enable **Use Offline Mock Data** in the sidebar (or switch to **Watchlist Quick-Scan Screener** to screen live tickers in pure Python without Ollama/MLX).
- **With local Ollama:** ensure Ollama is running at `http://localhost:11434/v1` and pull one of the configured models (`inkling-2-mini:latest`, `gemma4:31b-mlx`, or `qwen3.8:27b-mlx`).

See [fundamental_memo/README.md](fundamental_memo/README.md) for CLI flags and full module architecture.
