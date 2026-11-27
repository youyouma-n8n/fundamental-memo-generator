## Why

To make the application publicly shareable on Streamlit Community Cloud while keeping the local Ollama workflow intact, users need out-of-the-box cloud inference via Groq's free-tier OpenAI-compatible API (without manually typing base URLs or model slugs), graceful handling of `401 Unauthorized` / `429 Too Many Requests` errors that still preserves all quantitative charts and data, `.streamlit/secrets.toml` hygiene in `.gitignore`, and clear author attribution crediting `"Built by Josh Zhou @ UChicago"`.

## What Changes

- **Author Attribution (`streamlit_app.py`)**:
  - Display `"Built by Josh Zhou @ UChicago"` visibly in both the sidebar footer (below the `Data & offline mode` / `Generate one-page memo` controls) and the main page subheader/footer without obstructing charts or downloads.
- **LLM Provider & Groq Free-Tier Model Selector (`streamlit_app.py`, `deterministic_memo.py`)**:
  - Upgrade the `LLM Endpoint & Model Settings` expander in the sidebar with an `LLM Provider` selector offering `Groq (Cloud Free Tier)`, `Local Ollama`, and `Custom OpenAI-Compatible` (defaulting intelligently to `Local Ollama` when `localhost:11434` is reachable and `Groq (Cloud Free Tier)` otherwise).
  - When `Groq (Cloud Free Tier)` is selected: pre-fill `https://api.groq.com/openai/v1`, show a pre-populated Groq free-tier model selectbox (`llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `qwen/qwen3-32b`, `Custom model ID...`), render a password-masked `Groq API Key` input (`placeholder="gsk_..."`) falling back to `st.secrets.get("GROQ_API_KEY")` / `os.getenv("GROQ_API_KEY")` (and `LLM_API_KEY`), and display an inline warning if no key is provided when AI synthesis is enabled.
  - When `Local Ollama` is selected: preserve `http://localhost:11434/v1` base URL, default model `qwen3.8:27b-mlx` (editable), and optional API key (`"ollama"` placeholder).
  - When `Custom OpenAI-Compatible` is selected: expose editable Base URL, Model, and API Key inputs.
- **Cloud-Resilient Inference & Error Handling (`memo_synthesizer.py`, `deterministic_memo.py`, `streamlit_app.py`)**:
  - Explicitly catch `AuthenticationError` (`401 Unauthorized`) and `RateLimitError` (`429 Too Many Requests`) alongside `APIConnectionError` / `APITimeoutError` in `synthesize_memo_with_llm(...)`, and avoid sending Ollama-specific `reasoning_effort="none"` to non-reasoning Groq Llama models to preserve free-tier RPM quota.
  - Ensure `generate_memo(...)` catches `401` / `429` / connectivity errors cleanly without crashing the Streamlit session, displaying a clear error/warning banner identifying the exact cause (invalid API key vs. free-tier rate limit vs. unreachable endpoint) while still rendering all deterministic quantitative metrics, charts, Audit Trail JSON, and Deterministic Rule Engine memo fallback.
- **Streamlit Community Cloud Hygiene (`.gitignore`, `requirements.txt`, `.streamlit/config.toml`)**:
  - Add `.streamlit/secrets.toml` to root `.gitignore` so API keys can never be committed.
  - Audit root `requirements.txt` (zero Apple Silicon / `mlx` packages) and `.streamlit/config.toml` (`base = "dark"`, `headless = true`) with automated verification tests.

## Capabilities

### New Capabilities

- `author-attribution-ui`: Display `"Built by Josh Zhou @ UChicago"` attribution cleanly in both the sidebar footer and main page header/footer across local and deployed sessions.
- `groq-provider-and-secrets-selection`: Provide an `LLM Provider` switcher (`Groq (Cloud Free Tier)`, `Local Ollama`, `Custom OpenAI-Compatible`) with pre-populated Groq free-tier models, custom model ID input, masked `Groq API Key` with `st.secrets` / `os.getenv` fallback, and preserved Local Ollama defaults.
- `cloud-inference-resilience-and-hygiene`: Handle Groq `401 Unauthorized` and `429 Too Many Requests` cleanly while keeping all quantitative charts and Audit Trail data visible, optimize request parameters for Groq free-tier models, and enforce `.streamlit/secrets.toml` exclusion in `.gitignore` plus Linux-safe `requirements.txt`.

### Modified Capabilities

<!-- Additive capabilities layering cleanly on top of existing specs. -->

## Impact

- **Modified Files**: `fundamental_memo/src/fundamental_memo/{streamlit_app.py,memo_synthesizer.py,deterministic_memo.py,__init__.py}`, `.gitignore`, `requirements.txt` (audit), `.streamlit/config.toml` (audit), `fundamental_memo/tests/{test_deterministic_memo.py,test_synthesizer_and_renderer.py,test_cli_e2e.py}`.
- **Backward Compatibility**: 100% backward-compatible with local Ollama (`http://localhost:11434/v1`), `Use Offline Mock Data`, CLI flags, and Deterministic Rule Engine (Zero-LLM) mode.
