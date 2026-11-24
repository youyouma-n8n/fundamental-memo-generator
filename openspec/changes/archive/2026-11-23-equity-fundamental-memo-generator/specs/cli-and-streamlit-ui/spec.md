## Purpose

Expose the end-to-end fundamental analysis and one-page memo generation pipeline through both a scriptable Python CLI and an interactive Streamlit web application with local model selection.

## ADDED Requirements

### Requirement: Command-line interface execution
The system SHALL expose a runnable module `python -m fundamental_memo.cli` accepting `--ticker`, `--peers` (comma-separated ticker list), `--wacc` (default `0.095`), `--terminal-growth` (default `0.025`), `--model` (default `inkling-2-mini:latest`), `--base-url` (default `http://localhost:11434/v1`), `--output` (output Markdown path), `--mock-data` (boolean flag for offline fixture + deterministic offline synthesis), `--fixture-path` (optional local JSON fixture file), and `--live-llm` (optional boolean flag allowing live LLM synthesis when combined with `--mock-data`).

#### Scenario: Offline CLI end-to-end dry run
- **WHEN** a user runs `python -m fundamental_memo.cli --ticker AVGO --peers NVDA,AMD,MRVL,QCOM --mock-data --output memo_AVGO.md`
- **THEN** the CLI runs end-to-end offline without external network or live LLM calls, writes `memo_AVGO.md` containing a valid memo of $\le 650$ words, and exits with status code 0

#### Scenario: Mock data combined with live LLM override
- **WHEN** a user passes both `--mock-data` and `--live-llm` along with `--model` and `--base-url`
- **THEN** the CLI loads financial data from local fixtures and invokes the configured local OpenAI-compatible LLM endpoint for synthesis

#### Scenario: Invalid CLI arguments or runtime failure
- **WHEN** a user supplies invalid numerical parameters (such as `--wacc 0.02 --terminal-growth 0.03`) or encounters an unrecoverable fetch/synthesis error
- **THEN** the CLI prints a concise, human-readable error message to stderr and exits with a non-zero status code

### Requirement: Interactive Streamlit UI with model selection dropdown
The system SHALL provide a Streamlit web UI allowing users to enter target ticker and peer tickers, adjust WACC and terminal growth rate, select the analysis model from a dropdown containing `inkling-2-mini:latest`, `gemma4:31b-mlx`, and `qwen3.8:27b-mlx`, edit the OpenAI-compatible base URL (defaulting to `http://localhost:11434/v1`), toggle offline mock mode (with optional live-LLM toggle), trigger memo generation, inspect key quantitative metrics and the rendered Markdown memo, and download the generated `.md` file.

#### Scenario: Model dropdown options in Streamlit UI
- **WHEN** a user opens the Streamlit application
- **THEN** the model selector dropdown presents exactly the three configured model options `inkling-2-mini:latest`, `gemma4:31b-mlx`, and `qwen3.8:27b-mlx` alongside an editable base URL input defaulting to `http://localhost:11434/v1`

#### Scenario: Running analysis and downloading memo in Streamlit UI
- **WHEN** a user configures parameters (including either live or offline mock mode) and clicks the generate action
- **THEN** the UI runs the shared pipeline, displays headline valuation metrics and the rendered one-page Markdown memo with word count, and offers a one-click download button for `memo_<TICKER>.md`

#### Scenario: Error presentation in Streamlit UI
- **WHEN** data fetching, valuation validation, or LLM synthesis fails during a Streamlit run
- **THEN** the UI displays a clear error banner with actionable remediation hints (such as verifying the local Ollama server URL or enabling offline mock mode) without crashing the app session
