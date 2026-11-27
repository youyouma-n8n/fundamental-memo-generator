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

- **No local LLM required (Hybrid Cloud-Ready Mode):** When `localhost:11434` is not running (e.g., on Streamlit Community Cloud), **Enable AI Narrative Synthesis** defaults to off and the pure-Python **Deterministic Rule Engine (Zero-LLM)** generates a complete, grounded one-page memo + interactive Plotly charts + `.md`/`.html` exports in under 2 seconds.
- **With local Ollama:** Start Ollama at `http://localhost:11434/v1` — the app auto-detects it and enables AI synthesis automatically (`qwen3.8:27b-mlx`, `inkling-2-mini:latest`, `gemma4:31b-mlx`, `gemma4:26b-mlx`).
- **With Cloud API (BYOK):** Open **LLM Endpoint & Model Settings** in the sidebar to supply a Groq/OpenRouter/OpenAI Base URL, model ID (e.g., `llama-3.3-70b-versatile`), and API Key (or set `LLM_API_KEY` in Streamlit Secrets).

## Deploy to Streamlit Community Cloud

1. Push this repository to GitHub (root `requirements.txt` and `.streamlit/config.toml` are preconfigured).
2. On [share.streamlit.io](https://share.streamlit.io/), create a new app pointing to:
   - **Repository:** `youyouma-n8n/fundamental-memo-generator`
   - **Branch:** `main`
   - **Main file path:** `fundamental_memo/src/fundamental_memo/streamlit_app.py`
3. *(Optional)* Add `LLM_API_KEY = "..."` in **App Settings → Secrets** if you want cloud AI narrative synthesis enabled by default. Without any secrets, the app runs instantaneously in **Deterministic Rule Engine (Zero-LLM)** mode with 1-hour `yfinance` caching and automatic offline demo fallback.

See [fundamental_memo/README.md](fundamental_memo/README.md) for CLI flags and full module architecture.
