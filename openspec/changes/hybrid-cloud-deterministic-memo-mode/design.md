## Context

See [proposal.md](proposal.md) for motivation and capability overview. Currently:
- `memo_synthesizer.py` exposes `synthesize_memo_with_llm(...)` (raises `SynthesisError` on connection/timeout failures) and `synthesize_mock_memo(...)` (used only when `mock_data=True and not live_llm`).
- `cli.py:run_memo_pipeline(...)` unconditionally invokes `synthesize_memo_with_llm(...)` whenever `mock_data=False`.
- `streamlit_app.py` renders `Analysis model` and `OpenAI-compatible base URL` unconditionally in the sidebar and calls `run_memo_pipeline(...)` without caching `yfinance` fetches or handling cloud IP throttling.
- The repository has `fundamental_memo/pyproject.toml`, but no root `requirements.txt` or `.streamlit/config.toml` for Streamlit Community Cloud.

## Goals / Non-Goals

**Goals:**
- Provide a dedicated, threshold-driven `deterministic_memo.py` module capable of rendering a complete 6-section institutional memo purely from the Audit Trail JSON in `< 0.1s` with zero external LLM dependencies.
- Support three seamless synthesis modes through one unified `generate_memo(...)` wrapper: (1) local Ollama (`localhost:11434`), (2) BYOK cloud OpenAI-compatible APIs (Groq, OpenRouter, OpenAI via `API Key` or `st.secrets`), and (3) pure Deterministic Rule Engine (zero-LLM, default when `localhost:11434` is offline or when a cloud endpoint has no API key).
- Ensure Streamlit Community Cloud deploys cleanly from the repository root (`requirements.txt` + `.streamlit/config.toml`) and survives `yfinance` rate-limiting via 1-hour caching and automatic demo-ticker fallback.

**Non-Goals:**
- Bundling API keys in the repository (cloud keys remain strictly BYOK via password input or Streamlit Cloud Secrets).
- Removing any existing CLI flags or breaking local Ollama workflows (`inkling-2-mini:latest`, `gemma4:31b-mlx`, `qwen3.8:27b-mlx`).

## Decisions

### 1. Dedicated `deterministic_memo.py` Module & Audit-Trail Entry Point
- **Decision**: Create `fundamental_memo/src/fundamental_memo/deterministic_memo.py` exposing:
  - `probe_local_llm_endpoint(base_url: str = DEFAULT_BASE_URL, timeout: float = 0.25) -> bool`: parses host/port from `base_url` and performs a fast non-blocking `socket.create_connection((host, port), timeout=timeout)` check (returns `False` immediately for non-localhost URLs or any `OSError`), guaranteeing `< 0.3s` startup latency in cloud environments.
  - `is_localhost_url(base_url: str) -> bool`: checks if URL host is in `{"localhost", "127.0.0.1", "::1"}`.
  - `build_deterministic_memo_schema(snapshot, valuation, peers) -> InvestmentMemoSchema`: builds all 6 sections with explicit threshold-driven institutional rules:
    - **Executive Thesis**: current price vs. Perpetuity DCF, Exit Multiple DCF, Peer Comps median, and market-implied 5Y FCF CAGR (strictly `<= 60` words).
    - **Valuation & The Debate**: opens with market tension (anti-echoing compliant), contrasts Trailing vs. Forward P/E compression (`pe_compression_pct`), Wall Street consensus target (`analyst_target_mean`), Exit Multiple DCF, Reverse DCF (`implied_fcf_cagr_5y` + `implied_y5_fcf`), and Peer Comps (`<= 150` words).
    - **Profitability & Cash Quality**: opens with business/segment driver (anti-echoing compliant), highlights EBITDA/FCF margin durability when `ebitda_margin_ttm - operating_margin_ttm > 0.15`, interprets ROIC, SBC-adjusted FCF, and `ocf_net_income_gap_driver` (`<= 120` words).
    - **Bull Case (3 bullets, `<= 90` words)**: dynamically prioritizes threshold rules: (a) segment driver from `business_summary` + ROIC durability (calling out elite capital efficiency when `roic_ttm > 0.15`), (b) Forward P/E compression > 20% (`pe_compression_pct < -0.20`) or 3Y revenue CAGR outperformance, (c) high FCF margin / OCF-to-NI cash conversion & CapEx discipline.
    - **Bear Case (3 bullets, `<= 90` words)**: dynamically prioritizes threshold rules: (a) segment demand risk from `business_summary`, (b) demanding market expectations when `implied_fcf_cagr_5y > 0.25` (without repeating exact CAGR %) or trailing multiple compression risk, (c) leverage/net-debt refinancing risk or SBC dilution drag.
    - **Key Downside Risks (3–4 bullets, `<= 90` words)**: exact Audit Trail baseline triggers (operating/gross margin, DSO/DIO working capital, +100 bps WACC shift, SBC-adjusted FCF conversion).
  - `build_deterministic_memo(audit_trail: Mapping[str, Any]) -> str`: hydrates `FinancialSnapshot`, `ValuationAnalysis`, `list[PeerComparable]`, and optional `DcfSensitivity` from `audit_trail`, generates the schema via `build_deterministic_memo_schema(...)`, and returns `render_investment_memo(...)` (which runs `sanitize_memo_prose`, `verify_memo_grounding_and_repetition`, and enforces `<= 750` words).
  - `MemoGenerationOutcome` dataclass (`memo_output: InvestmentMemoSchema`, `mode_label: str`, `used_deterministic: bool`, `fallback_notice: str | None`) returned by `generate_memo(...)`:
    - If `not use_ai_synthesis` → immediate deterministic engine (`mode_label = "Deterministic Rule Engine (Zero-LLM)"`, `fallback_notice = None`).
    - If `use_ai_synthesis` and `not is_localhost_url(base_url)` and `not api_key.strip()` → immediate deterministic engine (`mode_label = "Deterministic Rule Engine (Zero-LLM)"`, `fallback_notice = "Cloud API key not configured — running Deterministic Rule Engine"`).
    - If `use_ai_synthesis` → attempts `synthesize_memo_with_llm(..., api_key=resolved_key)`; on `SynthesisError` caused by connectivity/timeout (or unreachable endpoint), catches cleanly and returns deterministic engine with `fallback_notice = "Local LLM unreachable — switched to Deterministic Rule Engine"` (or `"LLM endpoint unreachable — switched to Deterministic Rule Engine"` for cloud URLs).
- **Rationale**: Reuses the exact `InvestmentMemoSchema` + `render_investment_memo` pipeline so deterministic memos automatically inherit all tables, ribbons, grounding audits, snake_case sanitization, and HTML report compatibility with zero duplicated Markdown formatting logic.
- **Alternatives Considered**: Writing a separate standalone string-concatenation Markdown template in `deterministic_memo.py` — rejected because it would drift from `renderer.py`'s valuation table, profitability ribbon, and grounding checks.

### 2. Pipeline Integration (`cli.py` & `memo_synthesizer.py`)
- **Decision**:
  - Update `SUPPORTED_MODELS` / `DEFAULT_MODEL` presets cleanly: keep `SUPPORTED_MODELS` (or add `CLOUD_AND_LOCAL_MODELS = ("qwen3.8:27b-mlx", "inkling-2-mini:latest", "gemma4:31b-mlx", "gemma4:26b-mlx", "llama-3.3-70b-versatile")`) while keeping `cli.py` backward-compatible!
  - Extend `PipelineResult` with `synthesis_mode: str` (e.g., `"Deterministic Rule Engine (Zero-LLM)"` or `"AI Synthesis (qwen3.8:27b-mlx)"`), `fallback_notice: str | None = None`, and `data_fallback_notice: str | None = None`.
  - Extend `run_memo_pipeline(...)` with optional keyword args `use_ai_synthesis: bool | None = None`, `api_key: str = "ollama"`, `allow_llm_fallback: bool = False`, and `preloaded_bundle: MarketDataBundle | None = None` (so Streamlit's `@st.cache_data` cached bundle can be passed straight in without double-fetching!). When `use_ai_synthesis is None`, preserve exact existing CLI semantics (`not (mock_data and not live_llm)`).

### 3. Adaptive Hybrid Sidebar & Cached `yfinance` Resilience (`streamlit_app.py`)
- **Decision**:
  - Probe `probe_local_llm_endpoint(DEFAULT_BASE_URL, timeout=0.25)` once per session (`st.session_state["local_llm_detected"]` & default `st.session_state["enable_ai_synthesis"]`).
  - Sidebar `### Narrative Synthesis`:
    - `st.checkbox("Enable AI Narrative Synthesis (Ollama / Cloud API)", key="enable_ai_synthesis")`.
    - `with st.expander("LLM Endpoint & Model Settings", expanded=False):`
      - `Base URL` (`st.text_input`, default `http://localhost:11434/v1`)
      - `Model` (`st.selectbox(..., options=HYBRID_MODEL_OPTIONS, accept_new_options=True)` defaulting to `"qwen3.8:27b-mlx"` so both local Ollama models and arbitrary BYOK cloud models like `llama-3.3-70b-versatile` or `gpt-4o-mini` work effortlessly)
      - `API Key` (`st.text_input("API Key", type="password", value=_get_secret_api_key(), help="Optional for localhost Ollama; required for cloud endpoints (Groq / OpenRouter / OpenAI).")`) where `_get_secret_api_key()` safely reads `st.secrets.get("LLM_API_KEY", "")` wrapped in `try/except` (since `st.secrets` raises `StreamlitSecretNotFoundError` when no `secrets.toml` exists locally!).
  - Cached live data helpers in `streamlit_app.py`:
    - `@st.cache_data(ttl=3600, show_spinner=False) def _cached_fetch_live_bundle(ticker: str, peers_tuple: tuple[str, ...]) -> dict[str, Any]:` serializes `MarketDataBundle.model_dump(mode="json", by_alias=True)` (plain JSON-serializable dict for rock-solid Streamlit pickle/cache stability!) and re-validates on read.
    - If `_cached_fetch_live_bundle` raises `DataFetchError` and `ticker` is in the bundled demo tickers (`{"AVGO", "NVDA", "AMD", "MRVL", "QCOM"}`), automatically load `load_mock_market_data(ticker, peer_list)` and attach `data_fallback_notice` displayed as a prominent `st.warning(...)` banner!
    - Also cache single-ticker live snapshots (`@st.cache_data(ttl=3600, show_spinner=False)`) for Watchlist Quick-Scan Screener so repeated scans on Streamlit Cloud are instantaneous!
  - Status caption above download buttons displays:
    - `Word Count: **X / 750** | Mode: **Deterministic Rule Engine (Zero-LLM)** | Grounding Audit: **Passed**` (or `Mode: **AI Synthesis (<model>)**`)
    - Plus subtle `st.caption(stored_result.fallback_notice)` if an automatic LLM fallback occurred.
  - Add a tiny `sys.path` safety guard at the top of `streamlit_app.py` (or ensure `-e ./fundamental_memo` in root `requirements.txt`) so both `streamlit run fundamental_memo/src/fundamental_memo/streamlit_app.py` and Streamlit Community Cloud work cleanly.

### 4. Root Deployment Artifacts (`requirements.txt`, `.streamlit/config.toml`)
- **Decision**:
  - Create root `/requirements.txt` with the exact requested minimum version pins (`streamlit>=1.38.0`, `yfinance>=0.2.48`, `pandas>=2.2.0`, `numpy>=1.26.0`, `scipy>=1.13.0`, `plotly>=5.24.0`, `pydantic>=2.8.0`, `openai>=1.45.0`, `markdown>=3.7`) plus `-e ./fundamental_memo` so Streamlit Community Cloud installs the `fundamental_memo` package cleanly.
  - Create root `/.streamlit/config.toml` with the exact `[theme]` (`base = "dark"`, `primaryColor = "#3B82F6"`, `backgroundColor = "#0E1117"`, `secondaryBackgroundColor = "#161B22"`, `textColor = "#F8FAFC"`) and `[server]` (`headless = true`).

## Risks / Trade-offs

- **[Risk] Calling `st.secrets` locally when no `.streamlit/secrets.toml` exists raises `FileNotFoundError` / `StreamlitSecretNotFoundError`** → **Mitigation**: Wrap `st.secrets.get("LLM_API_KEY", "")` in a defensive helper returning `""` on any exception.
- **[Risk] `probe_local_llm_endpoint` slowing down every Streamlit rerun if called unconditionally** → **Mitigation**: Probe only once per session (stored in `st.session_state["local_llm_detected"]`) with a strict `0.25s` socket timeout, and skip probing entirely for non-localhost URLs.
- **[Risk] Existing `test_cli_e2e.py` asserts sidebar `selectbox` options / checkbox indices** → **Mitigation**: Update `test_cli_e2e.py` alongside `streamlit_app.py` to test the new hybrid Narrative Synthesis sidebar (auto-detect default `False` when Ollama offline, `< 2s` zero-LLM memo generation, collapsible LLM settings expander, and `Mode: Deterministic Rule Engine (Zero-LLM) | Grounding Audit: Passed`).
