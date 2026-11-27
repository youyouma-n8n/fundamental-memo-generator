## Purpose

Adapt the Streamlit interface seamlessly between local Ollama workstations and zero-LLM cloud deployments by auto-detecting local Ollama availability, organizing optional local/BYOK LLM settings in a collapsible sidebar panel, caching live market data fetches, and degrading cleanly to demo fixtures when cloud IP throttling occurs.

## ADDED Requirements

### Requirement: Auto-detected hybrid Narrative Synthesis sidebar controls
The Streamlit sidebar SHALL provide a `Narrative Synthesis` section featuring an `Enable AI Narrative Synthesis (Ollama / Cloud API)` checkbox that defaults to enabled when `localhost:11434` responds within `0.3s` and defaults to disabled when unreachable, paired with a collapsible `LLM Endpoint & Model Settings` expander exposing `Base URL` (default `http://localhost:11434/v1`), `Model` selector (default `qwen3.8:27b-mlx` with presets `inkling-2-mini:latest`, `gemma4:31b-mlx`, `gemma4:26b-mlx`, `llama-3.3-70b-versatile`, and custom model support), and a masked `API Key` input (reading `LLM_API_KEY` from Streamlit secrets when configured).

#### Scenario: Offline local Ollama defaults the app to instant zero-LLM cloud mode
- **WHEN** the Streamlit app initializes in an environment where `localhost:11434` is unreachable
- **THEN** `Enable AI Narrative Synthesis (Ollama / Cloud API)` defaults to unchecked, generating a memo produces a complete grounded report with all Plotly charts and `.md`/`.html` exports in under 2 seconds, and the status caption displays `Mode: Deterministic Rule Engine (Zero-LLM) | Grounding Audit: Passed`

#### Scenario: Running local Ollama preserves existing local AI workflow automatically
- **WHEN** the Streamlit app initializes on a machine where `localhost:11434` responds to the `< 0.3s` health ping
- **THEN** `Enable AI Narrative Synthesis (Ollama / Cloud API)` defaults to checked with `Base URL = http://localhost:11434/v1` and runs the local LLM synthesis pipeline cleanly

### Requirement: Cached cloud-resilient market data fetching with demo fallback
The Streamlit application SHALL cache live market data fetches for 1 hour (`ttl=3600`) to prevent upstream rate-limiting across concurrent users, and when live market data fetching fails for a supported demo ticker (`AVGO`, `NVDA`, `AMD`, `MRVL`, `QCOM`), SHALL automatically fall back to the bundled offline mock profile while displaying a clear warning banner instead of crashing the session.

#### Scenario: Live market data failure on a supported demo ticker falls back gracefully
- **WHEN** a live Yahoo Finance request fails due to IP throttling or network unavailability while analyzing `AVGO` or `NVDA`
- **THEN** the application automatically loads the bundled offline profile for that ticker, renders a clear non-fatal warning banner explaining the fallback, and completes the full analysis and charts cleanly
