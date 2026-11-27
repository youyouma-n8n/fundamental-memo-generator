## Context

The application currently runs in hybrid mode (`hybrid-cloud-deterministic-memo-mode`): it auto-probes `http://localhost:11434` on startup, defaults to Deterministic Rule Engine (Zero-LLM) when Ollama is offline, and accepts a manual `Base URL`, `Model`, and `API Key` in the sidebar expander. While this allows zero-LLM cloud usage, deploying publicly on Streamlit Community Cloud reveals four usability and operational gaps:
1. No author attribution (`"Built by Josh Zhou @ UChicago"`) appears in the sidebar or main page.
2. Cloud users who want live AI narrative synthesis via Groq's free tier have to manually type `https://api.groq.com/openai/v1` and remember Groq model slugs, and `st.secrets` only reads `LLM_API_KEY` rather than standard `GROQ_API_KEY`.
3. `synthesize_memo_with_llm(...)` passes `reasoning_effort="none"` unconditionally when `disable_thinking=True` (causing a wasted `400 BadRequestError` round-trip against Groq free-tier RPM limits on Llama models) and collapses `AuthenticationError` (401) and `RateLimitError` (429) into a generic `APIError` message.
4. Root `.gitignore` does not yet ignore `.streamlit/secrets.toml`.

## Goals / Non-Goals

**Goals:**
- Display `"Built by Josh Zhou @ UChicago"` cleanly in both the sidebar footer and the main page subheader/footer without disrupting visual hierarchy or downloads.
- Add a clean `LLM Provider` selector (`Groq (Cloud Free Tier)`, `Local Ollama`, `Custom OpenAI-Compatible`) inside `LLM Endpoint & Model Settings`, with curated Groq free-tier presets (`llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `qwen/qwen3-32b`, `Custom model ID...`), masked `Groq API Key` input (`placeholder="gsk_..."`), and `st.secrets["GROQ_API_KEY"]` / `os.getenv("GROQ_API_KEY")` fallback.
- Handle `401 Unauthorized` and `429 Too Many Requests` with dedicated, actionable user-facing banners while still rendering all deterministic charts, Audit Trail JSON, and Deterministic Rule Engine memo fallback.
- Avoid sending `reasoning_effort="none"` to non-reasoning Groq Llama models to conserve Groq free-tier RPM quota.
- Enforce `.streamlit/secrets.toml` exclusion in `.gitignore` and automated verification of Linux-safe `requirements.txt` and dark `.streamlit/config.toml`.

**Non-Goals:**
- Do not add a separate Groq SDK dependency (`groq`); continue using the existing OpenAI-compatible `openai` SDK against `https://api.groq.com/openai/v1`.
- Do not remove or alter Local Ollama (`http://localhost:11434/v1`, `qwen3.8:27b-mlx`), CLI flags, Watchlist Quick-Scan, or Deterministic Rule Engine behavior.
- Do not relax the Grounding Audit (`verify_memo_grounding_and_repetition`) or the `<= 750` word ceiling for Groq models.

## Decisions

### 1. Provider Constants & Key Resolution Helper (`deterministic_memo.py`)
Centralize provider configuration constants and key resolution in `fundamental_memo/src/fundamental_memo/deterministic_memo.py` (exported from `__init__.py`) so both the Streamlit UI and unit tests share a single source of truth:
- `PROVIDER_GROQ = "Groq (Cloud Free Tier)"`
- `PROVIDER_OLLAMA = "Local Ollama"`
- `PROVIDER_CUSTOM = "Custom OpenAI-Compatible"`
- `LLM_PROVIDERS = (PROVIDER_GROQ, PROVIDER_OLLAMA, PROVIDER_CUSTOM)`
- `GROQ_BASE_URL = "https://api.groq.com/openai/v1"`
- `GROQ_CUSTOM_MODEL_OPTION = "Custom model ID..."`
- `GROQ_MODEL_PRESETS = ("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "qwen/qwen3-32b", GROQ_CUSTOM_MODEL_OPTION)`
- `OLLAMA_MODEL_PRESETS = ("qwen3.8:27b-mlx", "inkling-2-mini:latest", "gemma4:26b-mlx")`
- `resolve_provider_api_key(provider: str, user_input: str, secrets_lookup: Callable[[str], str | None] | None = None) -> tuple[str, bool]`
  - Returns `(resolved_key, from_secret_or_env)`:
    - If `user_input.strip()` is non-empty, return `(user_input.strip(), False)`.
    - For `PROVIDER_GROQ`, check in order: `secrets("GROQ_API_KEY")`, `os.getenv("GROQ_API_KEY")`, `secrets("LLM_API_KEY")`, `os.getenv("LLM_API_KEY")`.
    - For `PROVIDER_CUSTOM`, check `secrets("LLM_API_KEY")`, `os.getenv("LLM_API_KEY")`.
    - For `PROVIDER_OLLAMA`, return `("", False)` (caller falls back to `"ollama"` placeholder).

**Rationale:** Pure-Python helper with injectable `secrets_lookup` is trivially unit-testable without mocking Streamlit's runtime globals and prevents `StreamlitSecretNotFoundError` locally.

### 2. Groq-Safe Request Parameters & Explicit 401/429 Handling (`memo_synthesizer.py`)
In `fundamental_memo/src/fundamental_memo/memo_synthesizer.py`:
- Add `_should_send_reasoning_effort(base_url: str, model: str, disable_thinking: bool) -> bool`:
  - Returns `False` when `disable_thinking` is `False`.
  - When `"api.groq.com"` is in `base_url.lower()`, only send `reasoning_effort="none"` for reasoning-capable Groq models (`"qwen3"` or `"gpt-oss"` or `"deepseek-r1"` in `model.lower()`), and omit it for non-reasoning Llama/Mixtral/Gemma models (`llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, etc.) to prevent a wasted `400 BadRequestError` round-trip per call against Groq's free-tier RPM quota.
  - Keep `reasoning_effort="none"` enabled for localhost Ollama/MLX endpoints (with existing `BadRequestError` retry fallback preserved).
- In `synthesize_memo_with_llm(...)`, catch `AuthenticationError` and `RateLimitError` *before* `APIError` (since both subclass `APIStatusError` → `APIError`):
  - `AuthenticationError`: raise `SynthesisError(f"LLM authentication failed (401 Unauthorized) at {base_url} for model '{model}': invalid or missing API key. Details: {exc}")`
  - `RateLimitError`: raise `SynthesisError(f"LLM rate limit exceeded (429 Too Many Requests) at {base_url} for model '{model}': free-tier quota or RPM limit reached. Details: {exc}")`

**Rationale:** Explicit HTTP status tags (`401 Unauthorized`, `429 Too Many Requests`) allow `generate_memo(...)` to classify the failure cleanly and present the exact root cause to users instead of a vague "unreachable" notice.

### 3. Differentiated Fallback Banners (`deterministic_memo.py` & `streamlit_app.py`)
Extend `MemoGenerationOutcome` and `generate_memo(...)` in `deterministic_memo.py`:
- Add helper `_classify_fallback_error(exc: Exception, *, is_local: bool) -> tuple[str, str] | None` returning `(notice_text, severity)` where `severity` is `"warning"` or `"caption"`:
  - Returns `None` for `GroundingAuditError` (strict hallucination failures still surface rather than silently masking bugs).
  - If `"401 unauthorized"` or `"authentication failed"` in message: return `("API authentication failed (401 Unauthorized) — check your API key. Switched to Deterministic Rule Engine.", "warning")`.
  - If `"429 too many requests"` or `"rate limit"` in message: return `("LLM rate limit reached (429 Too Many Requests) — wait briefly or switch to llama-3.1-8b-instant. Switched to Deterministic Rule Engine.", "warning")`.
  - If connectivity / timeout / endpoint API error markers match: return existing subtle notice with `"caption"` severity (`"Local LLM unreachable — switched to Deterministic Rule Engine"` or `"LLM endpoint unreachable — switched to Deterministic Rule Engine"`).
- Store optional `fallback_severity: Literal["caption", "warning"] = "caption"` on `MemoGenerationOutcome` (and `PipelineResult` in `cli.py`).
- In `streamlit_app.py`, render `st.warning(result.llm_fallback_notice, icon=":material/warning:")` when severity is `"warning"` (e.g., 401/429/missing key) and `st.caption(result.llm_fallback_notice)` for subtle unreachable local Ollama fallback — always **above** the memo while keeping all 5 KPI cards, valuation charts, sensitivity table, Audit Trail JSON, and `.md`/`.html` download buttons fully rendered.

### 4. Sidebar Provider UX & Author Attribution (`streamlit_app.py`)
- **Initialization (`_init_dcf_session_state`)**:
  - Probe `localhost:11434` (`timeout=0.25s`).
  - Set default `llm_provider` to `PROVIDER_OLLAMA` if local Ollama is detected, else `PROVIDER_GROQ`.
  - Set default `enable_ai_synthesis`: `True` if local Ollama is detected **or** if a `GROQ_API_KEY` secret/env var is already configured on cloud; otherwise `False` (instant Zero-LLM cloud default with zero connection errors).
- **Sidebar `LLM Endpoint & Model Settings` expander**:
  - `LLM Provider` selectbox (`key="llm_provider"`).
  - Branch cleanly per provider:
    - `PROVIDER_GROQ`: show `Base URL` pre-filled with `GROQ_BASE_URL` (`disabled=True`), `Model` selectbox with `GROQ_MODEL_PRESETS` (if `Custom model ID...` is selected, show `"Custom Groq Model ID"` text input), password-masked `"Groq API Key"` (`type="password"`, `placeholder="gsk_..."`). If `enable_ai_synthesis` is checked and resolved key is empty, display `st.warning("Paste a Groq API key (`gsk_...`), configure `GROQ_API_KEY` in Streamlit Secrets, or uncheck **Enable AI Narrative Synthesis** for instant Zero-LLM mode.")`. If key comes from `st.secrets` / env, show subtle `st.caption("Using configured GROQ_API_KEY secret.")`.
    - `PROVIDER_OLLAMA`: editable `Base URL` defaulting to `http://localhost:11434/v1`, editable/selectable `Model` defaulting to `qwen3.8:27b-mlx`, optional password-masked `API Key` (`placeholder="Optional (defaults to 'ollama')"`).
    - `PROVIDER_CUSTOM`: editable `Base URL`, editable `Model`, password-masked `API Key`.
- **Author Attribution**:
  - Define constant `AUTHOR_ATTRIBUTION = "Built by Josh Zhou @ UChicago"`.
  - Main page header caption directly under `st.title(...)`:
    `"Deterministic pure-Python valuation engine, Reverse DCF, and strictly grounded hybrid LLM synthesis (zero financial hallucination) · Built by Josh Zhou @ UChicago"`
  - Sidebar footer below the `Generate one-page memo` button: `st.divider()` followed by `st.caption(AUTHOR_ATTRIBUTION)`.
  - Main page footer at the bottom of `render_app()` (after both Deep-Dive and Watchlist modes): `st.divider()` followed by `st.caption(f"{AUTHOR_ATTRIBUTION} · Equity Fundamental Deep-Dive & One-Page Memo Generator")` so attribution is always visible at the top and bottom without obstructing charts or export buttons.

### 5. Deployment Hygiene (`.gitignore`, `requirements.txt`, `.streamlit/config.toml`)
- Append `.streamlit/secrets.toml` under a `# Streamlit local secrets` section in root `.gitignore`.
- Keep root `requirements.txt` pinned and Linux-safe (verify zero `mlx` / `mlx-lm` entries via unit test) and `.streamlit/config.toml` configured with `base = "dark"` and `headless = true`.

## Risks / Trade-offs

- **Risk: Groq `qwen/qwen3-32b` reasoning traces inside JSON content** → *Mitigation*: `_should_send_reasoning_effort` keeps `reasoning_effort="none"` enabled for `qwen3` models on Groq while skipping it for non-reasoning Llama models, and `_parse_memo_json_response` already strips `<think>...</think>` blocks if any reasoning tokens appear.
- **Risk: Groq free-tier rate limits (`llama-3.3-70b-versatile` TPM/RPM limits)** → *Mitigation*: Default `llama-3.3-70b-versatile` works cleanly in 1 request (~1,500–2,000 tokens); `llama-3.1-8b-instant` is offered right below it as a high-rate-limit option, and any `429` falls back seamlessly to the Deterministic Rule Engine with an actionable warning banner.
- **Risk: Streamlit widget state when switching `LLM Provider`** → *Mitigation*: Use distinct widget keys per provider (`groq_model_preset`, `groq_custom_model`, `groq_api_key`, `ollama_base_url`, `ollama_model`, `custom_base_url`, `custom_model`, `custom_api_key`) so toggling between Groq and Local Ollama never leaks `http://localhost:11434/v1` into Groq or `gsk_...` into Ollama.
