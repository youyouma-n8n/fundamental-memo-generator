## Purpose

Provide an out-of-the-box `LLM Provider` selector inside the sidebar `LLM Endpoint & Model Settings` expander supporting `Groq (Cloud Free Tier)`, `Local Ollama`, and `Custom OpenAI-Compatible` backends, complete with curated Groq free-tier models, custom model ID override, secure API key entry with `st.secrets`/`os.getenv` fallback, and full backward compatibility with local Ollama workflows.

## ADDED Requirements

### Requirement: LLM Provider Selector with Smart Local/Cloud Default
The sidebar `LLM Endpoint & Model Settings` expander SHALL provide an `LLM Provider` selectbox offering `Groq (Cloud Free Tier)`, `Local Ollama`, and `Custom OpenAI-Compatible`, automatically defaulting to `Local Ollama` when `http://localhost:11434` responds to the fast startup probe and `Groq (Cloud Free Tier)` otherwise.

#### Scenario: Default provider on Streamlit Community Cloud (no local Ollama)
- **WHEN** the application initializes in an environment where `http://localhost:11434` does not respond within `< 0.3s`
- **THEN** `LLM Provider` MUST default to `Groq (Cloud Free Tier)`
- **AND** `Enable AI Narrative Synthesis (Ollama / Cloud API)` MUST remain safely unchecked by default (unless a `GROQ_API_KEY` or `LLM_API_KEY` secret is explicitly configured or the user enables it) so initial page loads never fail with connection-refused errors.

#### Scenario: Default provider on a developer machine with local Ollama running
- **WHEN** the application initializes while a local Ollama server responds on `http://localhost:11434` within `< 0.3s`
- **THEN** `LLM Provider` MUST default to `Local Ollama`
- **AND** `Enable AI Narrative Synthesis (Ollama / Cloud API)` MUST default to enabled, preserving the existing local workflow seamlessly.

### Requirement: Groq Cloud Free-Tier Configuration and Model Presets
When `Groq (Cloud Free Tier)` is selected as the `LLM Provider`, the application SHALL automatically configure Groq's OpenAI-compatible Base URL, present curated free-tier model presets plus a custom model option, and provide a password-masked `Groq API Key` input.

#### Scenario: Selecting Groq as the LLM provider
- **WHEN** the user selects `Groq (Cloud Free Tier)` in the `LLM Provider` selectbox
- **THEN** the Base URL MUST automatically be set to `https://api.groq.com/openai/v1` (displayed clearly as read-only/pre-filled)
- **AND** a `Model` selectbox MUST be presented containing current Groq free-tier models:
  - `llama-3.3-70b-versatile` (default, recommended for financial synthesis)
  - `llama-3.1-8b-instant` (fast / high rate-limit)
  - `qwen/qwen3-32b`
  - `Custom model ID...`
- **AND** a password-masked `Groq API Key` input (`type="password"`, placeholder `"gsk_..."`) MUST be displayed so the user can paste their Groq API key without exposing it on screen.

#### Scenario: Entering a custom Groq model slug
- **WHEN** the user selects `Custom model ID...` in the Groq `Model` selectbox
- **THEN** a text input MUST appear allowing the user to type any arbitrary Groq model slug
- **AND** that trimmed slug MUST be passed as the `model` parameter to the OpenAI-compatible client (falling back to `llama-3.3-70b-versatile` if left blank).

### Requirement: Streamlit Secrets and Environment Fallback for Groq API Key
The application SHALL resolve the active Groq API key in deterministic priority order from the sidebar input, `st.secrets`, and process environment variables, and warn inline when AI synthesis is enabled without any configured key.

#### Scenario: Resolving Groq API key from Streamlit Secrets or environment
- **WHEN** the user leaves the sidebar `Groq API Key` field blank while `Groq (Cloud Free Tier)` is selected
- **THEN** the application MUST safely inspect `st.secrets.get("GROQ_API_KEY")` (catching `StreamlitSecretNotFoundError` / `FileNotFoundError` / `KeyError` locally when no `secrets.toml` exists), followed by `os.getenv("GROQ_API_KEY")`, `st.secrets.get("LLM_API_KEY")`, and `os.getenv("LLM_API_KEY")`
- **AND** if a non-empty secret key is found, Groq synthesis MUST proceed seamlessly without requiring manual key entry.

#### Scenario: Missing Groq API key when AI synthesis is enabled
- **WHEN** `Groq (Cloud Free Tier)` is selected, `Enable AI Narrative Synthesis` is checked, and both the sidebar `Groq API Key` input and secret/environment fallbacks are empty
- **THEN** the sidebar MUST display a clear inline warning prompting the user to paste a Groq API key (`gsk_...`), configure `GROQ_API_KEY` in Streamlit Secrets, or uncheck `Enable AI Narrative Synthesis` for instant Zero-LLM Deterministic Rule Engine mode.

### Requirement: Preserved Local Ollama and Custom OpenAI-Compatible Workflows
Selecting `Local Ollama` or `Custom OpenAI-Compatible` SHALL preserve full backward compatibility with local Ollama/MLX servers and arbitrary OpenAI-compatible endpoints.

#### Scenario: Preserving Local Ollama workflow
- **WHEN** the user selects `Local Ollama` in the `LLM Provider` selector
- **THEN** the Base URL MUST default to `http://localhost:11434/v1` (editable)
- **AND** the Model input MUST default to `qwen3.8:27b-mlx` (editable or preset-selectable)
- **AND** the API Key field MUST remain optional, defaulting internally to `"ollama"` when left blank.

#### Scenario: Configuring Custom OpenAI-Compatible endpoint
- **WHEN** the user selects `Custom OpenAI-Compatible` in the `LLM Provider` selector
- **THEN** the sidebar MUST expose editable `Base URL`, `Model`, and password-masked `API Key` inputs supporting OpenRouter, OpenAI, vLLM, or MLX servers.
