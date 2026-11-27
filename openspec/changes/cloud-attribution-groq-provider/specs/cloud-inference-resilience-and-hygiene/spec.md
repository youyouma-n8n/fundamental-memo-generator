## Purpose

Ensure Groq cloud inference integrates cleanly with the deterministic Grounding Audit, optimizes request parameters for Groq free-tier models, handles `401 Unauthorized` and `429 Too Many Requests` errors gracefully without hiding quantitative analytics, and enforces Streamlit Community Cloud repository hygiene (`.gitignore`, Linux-safe `requirements.txt`, dark `.streamlit/config.toml`).

## ADDED Requirements

### Requirement: Groq OpenAI-Compatible Inference and Grounding Audit Compatibility
The LLM synthesis pipeline SHALL execute against Groq's OpenAI-compatible Chat Completions endpoint (`https://api.groq.com/openai/v1`) without wasting free-tier RPM quota on unsupported Ollama parameters while enforcing the identical Pydantic schema, prose sanitizer, and Grounding Audit (`Grounding Audit: Passed`).

#### Scenario: Generating a memo with Groq on Streamlit Cloud
- **WHEN** a user provides a valid Groq API key (via sidebar input or `GROQ_API_KEY` secret), selects `llama-3.3-70b-versatile`, and clicks `Generate one-page memo`
- **THEN** the synthesizer MUST send the Audit Trail JSON synthesis prompt to `https://api.groq.com/openai/v1` without passing Ollama-only `reasoning_effort="none"` on non-reasoning Groq Llama models
- **AND** the resulting memo MUST pass `sanitize_memo_prose`, `verify_memo_grounding_and_repetition`, and the `<= 750` word ceiling
- **AND** the rendered page MUST display `Mode: AI Synthesis (llama-3.3-70b-versatile) | Grounding Audit: Passed` along with working `.md` and `.html` download buttons.

### Requirement: Graceful Handling of Groq Authentication (401) and Rate-Limit (429) Errors
The synthesis pipeline and Streamlit UI SHALL explicitly distinguish `401 Unauthorized` (invalid/expired API key) and `429 Too Many Requests` (Groq free-tier RPM/TPM rate limit) from generic connection errors, never crash the Streamlit session, and preserve all deterministic quantitative outputs.

#### Scenario: Invalid Groq API key (401 Unauthorized)
- **WHEN** Groq returns `401 Unauthorized` (`openai.AuthenticationError`) during memo generation
- **THEN** `synthesize_memo_with_llm(...)` MUST raise a descriptive `SynthesisError` identifying `401 Unauthorized` / invalid API key
- **AND** `generate_memo(..., allow_fallback=True)` MUST catch the error without crashing, fall back cleanly to the Deterministic Rule Engine memo (`Grounding Audit: Passed`), and return an explicit notice (`"API authentication failed (401 Unauthorized) — check your API key. Switched to Deterministic Rule Engine."`)
- **AND** the Streamlit UI MUST display a prominent warning banner showing that exact cause while still rendering all KPI cards, Valuation Bridge, Sensitivity Table, Peer Scatter, Cash Quality charts, Audit Trail JSON, and `.md`/`.html` exports.

#### Scenario: Groq free-tier rate limit exceeded (429 Too Many Requests)
- **WHEN** Groq returns `429 Too Many Requests` (`openai.RateLimitError`) during memo generation
- **THEN** `synthesize_memo_with_llm(...)` MUST raise a descriptive `SynthesisError` identifying `429 Too Many Requests` / rate limit exceeded
- **AND** `generate_memo(..., allow_fallback=True)` MUST catch the error without crashing, fall back cleanly to the Deterministic Rule Engine memo (`Grounding Audit: Passed`), and return an explicit notice (`"LLM rate limit reached (429 Too Many Requests) — wait briefly or try llama-3.1-8b-instant. Switched to Deterministic Rule Engine."`)
- **AND** the Streamlit UI MUST display that warning banner while preserving all quantitative metrics, charts, Audit Trail JSON, and downloads.

### Requirement: Streamlit Community Cloud Repository Hygiene
The repository SHALL exclude local Streamlit secrets from Git tracking, maintain a Linux x86_64–compatible root `requirements.txt` free of Apple Silicon `mlx` packages, and preserve institutional dark theme defaults in `.streamlit/config.toml`.

#### Scenario: Verifying `.gitignore`, `requirements.txt`, and `.streamlit/config.toml`
- **WHEN** the repository deployment hygiene suite is checked prior to pushing to Streamlit Community Cloud
- **THEN** root `.gitignore` MUST explicitly ignore `.streamlit/secrets.toml`
- **AND** root `requirements.txt` MUST include `streamlit`, `yfinance`, `pandas`, `numpy`, `scipy`, `plotly`, `pydantic`, `openai`, and `markdown`, and MUST contain zero `mlx` or `mlx-lm` dependencies
- **AND** root `.streamlit/config.toml` MUST configure `[theme]` with `base = "dark"` and `[server]` with `headless = true`.
