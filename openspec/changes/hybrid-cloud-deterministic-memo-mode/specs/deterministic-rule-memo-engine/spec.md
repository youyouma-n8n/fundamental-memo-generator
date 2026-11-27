## Purpose

Generate a complete, threshold-driven, zero-hallucination one-page investment memo purely in Python from the verified Audit Trail JSON whenever AI narrative synthesis is disabled, unconfigured for external cloud APIs, or unreachable, ensuring instant sub-second institutional reports without external LLM dependencies.

## ADDED Requirements

### Requirement: Pure-Python deterministic rule-based memo generation
The system SHALL provide a deterministic rule-based memo generator accepting a canonical Audit Trail JSON dictionary and producing a rendered 6-section Markdown investment memo (`Executive Thesis`, `Valuation & The Debate`, `Profitability & Cash Quality`, `Bull Case`, `Bear Case`, `Key Downside Risks`) populated exclusively from verified Audit Trail values, using threshold rules (including ROIC > 15%, Forward P/E compression > 20%, Reverse DCF implied CAGR > 25%, amortization margin spread > 15pp, working-capital DSO/DIO triggers, and WACC sensitivity) and passing full prose sanitization, numeric grounding verification, and the 750-word ceiling.

#### Scenario: Deterministic memo generated from Audit Trail JSON passes grounding audit
- **WHEN** the deterministic rule engine is invoked with a verified Audit Trail JSON payload for any supported equity
- **THEN** it returns a complete 6-section Markdown memo of at most 750 words containing zero leaked `snake_case` JSON identifiers, passing numeric grounding and Single-Mention verification with zero external network or LLM calls

#### Scenario: Threshold rules adapt Bull and Bear bullets to company fundamentals
- **WHEN** a company exhibits high ROIC (> 15%) and steep Forward P/E compression (> 20%) alongside a demanding Reverse DCF implied 5Y FCF CAGR (> 25%)
- **THEN** the deterministic rule engine selects threshold-specific Bull and Bear bullets referencing those exact Audit Trail metrics rather than generic static placeholders

### Requirement: Graceful auto-fallback wrapper for hybrid synthesis
The memo generation wrapper SHALL bypass any OpenAI/Ollama network client immediately and return the Deterministic Rule Engine output when AI synthesis is disabled or when a non-localhost endpoint has an empty API key; when AI synthesis is enabled and the endpoint raises a connectivity or timeout error, the wrapper SHALL catch the error gracefully and return the Deterministic Rule Engine output alongside a non-blocking fallback notice (`"Local LLM unreachable — switched to Deterministic Rule Engine"`).

#### Scenario: Disabled AI synthesis or missing cloud API key bypasses LLM immediately
- **WHEN** memo generation runs with AI synthesis disabled, OR with AI synthesis enabled against a non-localhost cloud base URL and an empty API key
- **THEN** no network call is made to any LLM endpoint, the Deterministic Rule Engine produces the memo in under 2 seconds, and the result indicates `Deterministic Rule Engine (Zero-LLM)` mode

#### Scenario: Unreachable local LLM falls back gracefully instead of failing
- **WHEN** AI synthesis is enabled against an unreachable local endpoint (`http://localhost:11434/v1` offline) and a connection or timeout error occurs
- **THEN** the wrapper catches the connectivity failure, returns a grounded Deterministic Rule Engine memo, and surfaces a non-blocking fallback notice rather than raising a fatal page error
