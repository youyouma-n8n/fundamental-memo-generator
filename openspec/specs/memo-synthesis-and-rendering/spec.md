# memo-synthesis-and-rendering Specification

## Purpose

Synthesize concise, schema-enforced investment narratives strictly grounded in deterministic financial JSON outputs and render a validated, institutional-grade one-page Markdown investment memo under strict word-count limits.

## Requirements

### Requirement: Structured LLM synthesis contract
The system SHALL validate synthesized memo narratives against the `InvestmentMemoOutput` contract enforcing: `executive_thesis` (max 80 words), `valuation_summary` (max 100 words), `earnings_quality_assessment` (max 80 words), `bull_case` (exactly 3 concise bullet strings), `bear_case` (exactly 3 concise bullet strings), and `key_risks` (3 to 4 specific operational/macro risks).

#### Scenario: Valid structured memo output accepted
- **WHEN** the synthesizer receives a JSON payload satisfying all field types, list lengths, and per-section word limits
- **THEN** validation succeeds and returns an `InvestmentMemoOutput` instance

#### Scenario: Oversized section or wrong bullet count rejected
- **WHEN** an LLM payload exceeds 80 words in `executive_thesis` or `earnings_quality_assessment`, exceeds 100 words in `valuation_summary`, supplies fewer or more than 3 bullets for `bull_case`/`bear_case`, or supplies fewer than 3 or more than 4 items for `key_risks`
- **THEN** schema validation rejects the payload with field-specific error details

### Requirement: Grounded local OpenAI-compatible LLM synthesis with retries
The system SHALL call a configurable local OpenAI-compatible chat completions endpoint (default `http://localhost:11434/v1` for Ollama, also supporting MLX endpoints such as `http://localhost:8080/v1`), pass serialized financial snapshot and valuation analysis JSON into the prompt, instruct the model to cite only provided JSON metrics without inventing external numbers, and automatically retry up to 2 times when JSON parsing or schema/word-count validation fails.

#### Scenario: Retry succeeds after initial validation failure
- **WHEN** the first LLM response fails JSON parsing or violates a word-limit/list-length rule, and a subsequent retry (within max 2 retries) returns a valid payload
- **THEN** the system includes the validation error feedback in the retry prompt and returns the validated `InvestmentMemoOutput`

#### Scenario: Retries exhausted or endpoint unreachable
- **WHEN** all retry attempts fail validation or the local LLM endpoint is unreachable or times out
- **THEN** the system raises a clear, actionable synthesis error describing the connectivity failure or last validation error

### Requirement: Deterministic offline mock synthesis
The system SHALL provide a deterministic offline synthesizer that constructs a valid `InvestmentMemoOutput` directly from the computed financial snapshot and valuation analysis without calling an external LLM server when offline mock mode is enabled (unless live LLM override is explicitly requested).

#### Scenario: Offline mock synthesis produces grounded output
- **WHEN** synthesis runs in offline mock mode for any validated snapshot and valuation analysis
- **THEN** the system deterministically produces a valid `InvestmentMemoOutput` referencing the exact computed figures and passing all schema and word-limit validations with zero network requests

### Requirement: One-page Markdown memo rendering and word-count enforcement
The system SHALL render a single Markdown document containing: (1) Header Block (Company Name, Ticker, Current Price, DCF Intrinsic Value, Implied Upside/Downside, Earnings Quality Rating), (2) Executive Thesis, (3) Valuation & Comps Summary Table (Target vs. Peer Median multiples plus DCF sensitivity note), (4) Earnings Quality & Cash Conversion, (5) Bull Case vs. Bear Case, and (6) Key Downside Risks, targeting 450–600 words and strictly verifying post-render word count is $\le 650$ words.

#### Scenario: Rendered memo passes one-page bound
- **WHEN** valid snapshot, valuation analysis, peer comparables, and `InvestmentMemoOutput` are rendered
- **THEN** the renderer returns formatted Markdown containing all six required sections and confirms total word count is $\le 650$ words

#### Scenario: Rendered memo exceeds 650-word limit
- **WHEN** the post-render Markdown document exceeds 650 words
- **THEN** the renderer raises a word-limit validation error rather than silently writing an over-length memo
