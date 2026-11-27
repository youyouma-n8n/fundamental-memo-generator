## Why

Currently the Streamlit application treats a local Ollama/MLX endpoint (`http://localhost:11434/v1`) as mandatory unless the user explicitly enables offline mock data, which prevents deploying the app directly to Streamlit Community Cloud for club members or reviewers without a local LLM running. Introducing a hybrid cloud-ready architecture—pairing a pure-Python deterministic rule-based memo engine with auto-detection of local Ollama, optional BYOK cloud API support, `yfinance` caching/fallback resilience, and root Streamlit Cloud deployment config—lets the app run instantaneously with zero LLM dependencies in the cloud while preserving 100% of the local Ollama workflow unchanged.

## What Changes

- **Deterministic Rule-Based Memo Engine & Graceful Fallback (`deterministic_memo.py`, `cli.py`, `__init__.py`)**:
  - Add pure-Python `fundamental_memo/src/fundamental_memo/deterministic_memo.py` exposing `build_deterministic_memo_schema(...)` and `build_deterministic_memo(audit_trail: Mapping[str, Any]) -> str` that synthesize a complete 6-section Markdown investment memo directly from the Audit Trail JSON using threshold-driven institutional rules (ROIC > 15%, Forward P/E compression > 20%, Reverse DCF implied CAGR > 25%, amortization margin spread > 15pp, working-capital DSO/DIO triggers, and WACC sensitivity), verified through `sanitize_memo_prose` and `verify_memo_grounding_and_repetition` (`Mode: Deterministic Rule Engine (Zero-LLM) | Grounding Audit: Passed`).
  - Add graceful auto-fallback wrapper `generate_memo(...)` (and integrate it into `run_memo_pipeline(...)`): bypasses LLM calls immediately when `use_ai_synthesis=False` or when `api_key` is empty for non-localhost endpoints; catches connectivity/timeout errors when `use_ai_synthesis=True` and falls back to the Deterministic Rule Engine with a non-blocking notice (`"Local LLM unreachable — switched to Deterministic Rule Engine"`) rather than failing the page.
  - Add fast (`< 0.3s`) local health probe `probe_local_llm_endpoint(...)` to auto-detect whether `http://localhost:11434` is reachable.
- **Adaptive Hybrid Sidebar & Cloud `yfinance` Resilience (`streamlit_app.py`)**:
  - Replace mandatory LLM sidebar controls with a `### Narrative Synthesis` section containing:
    - `Enable AI Narrative Synthesis (Ollama / Cloud API)` checkbox defaulting to `True` only when `localhost:11434` responds to the `< 0.3s` health ping, and `False` otherwise (instant zero-LLM cloud mode).
    - Collapsible `st.expander("LLM Endpoint & Model Settings")` with `Base URL` (default `http://localhost:11434/v1`), `Model` selector (default `qwen3.8:27b-mlx`, presets including `inkling-2-mini:latest`, `gemma4:31b-mlx`, `gemma4:26b-mlx`, `llama-3.3-70b-versatile`, plus custom model entry), and masked `API Key` (`type="password"`, reading `st.secrets.get("LLM_API_KEY", "")` when configured, optional for localhost and required for non-localhost cloud endpoints).
  - Display synthesis mode clearly in the status caption (`Mode: Deterministic Rule Engine (Zero-LLM) | Grounding Audit: Passed` or `Mode: AI Synthesis (<model>) | Grounding Audit: Passed`) plus any non-blocking fallback notice.
  - Wrap live `yfinance` market data fetches in `@st.cache_data(ttl=3600)` to prevent cloud IP throttling, and automatically fall back to bundled offline mock profiles for supported demo tickers (`AVGO`, `NVDA`, `AMD`, `MRVL`, `QCOM`) with a clear warning banner when live `yfinance` fails.
- **Streamlit Community Cloud Deployment Artifacts (`requirements.txt`, `.streamlit/config.toml`)**:
  - Add root `requirements.txt` pinning all runtime dependencies (`streamlit`, `yfinance`, `pandas`, `numpy`, `scipy`, `plotly`, `pydantic`, `openai`, `markdown`, plus editable package installation `-e ./fundamental_memo`).
  - Add root `.streamlit/config.toml` configuring the dark institutional theme (`primaryColor = "#3B82F6"`, `backgroundColor = "#0E1117"`, `secondaryBackgroundColor = "#161B22"`, `textColor = "#F8FAFC"`) and `headless = true`.

## Capabilities

### New Capabilities

- `deterministic-rule-memo-engine`: Generate a complete, threshold-driven, zero-hallucination 6-section investment memo purely in Python from the Audit Trail JSON, with automatic graceful fallback whenever AI synthesis is disabled, unconfigured for cloud APIs, or unreachable.
- `hybrid-sidebar-and-cloud-resilience`: Auto-detect local Ollama availability (`< 0.3s` probe), provide collapsible BYOK/local LLM sidebar settings with `st.secrets` support, cache live `yfinance` fetches for 1 hour, and gracefully fall back to demo fixtures on cloud IP throttling.
- `streamlit-cloud-deployment-config`: Provide root `requirements.txt` and `.streamlit/config.toml` artifacts enabling clean one-click deployment to Streamlit Community Cloud with consistent dark institutional theming.

### Modified Capabilities

<!-- Existing main specs in openspec/specs/ remain intact; hybrid cloud mode layers on top additively. -->

## Impact

- **New Files**: `fundamental_memo/src/fundamental_memo/deterministic_memo.py`, `fundamental_memo/tests/test_deterministic_memo.py`, `requirements.txt`, `.streamlit/config.toml`.
- **Modified Files**: `fundamental_memo/src/fundamental_memo/{cli.py,memo_synthesizer.py,streamlit_app.py,__init__.py}`, `fundamental_memo/tests/test_cli_e2e.py`, and root `README.md` (Streamlit Cloud deployment note).
- **Backward Compatibility**: Preserves local Ollama/MLX CLI and Streamlit workflows 100% unchanged when `localhost:11434` is running; all existing CLI flags and test suites continue to pass.
