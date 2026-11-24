## Purpose

Enable analysts to screen a basket of equity tickers rapidly using only the deterministic Python valuation engine—without local LLM latency—and seamlessly hand off any selected ticker into the full Single-Stock Deep-Dive memo workflow.

## ADDED Requirements

### Requirement: Pure-Python batch watchlist valuation scan
The system SHALL provide a deterministic batch screening runner that evaluates a list of tickers using supplied DCF parameters (`wacc`, `terminal_growth`, `base_cagr`, `exit_multiple`, and offline mock toggle) without invoking any LLM endpoint, returning one summary record per ticker containing `ticker`, `company_name`, `current_price`, `dcf_value`, `dcf_upside_pct`, `implied_fcf_cagr_5y`, `forward_pe`, `ev_to_ebitda`, `roic_ttm`, `fcf_margin_ttm`, and `earnings_quality_flag`.

#### Scenario: Offline mock watchlist scan evaluates multiple tickers rapidly without LLM calls
- **WHEN** a batch scan is invoked for a basket of 5 tickers (`NVDA,AMD,MRVL,QCOM,AVGO`) with offline mock mode enabled
- **THEN** the runner returns 5 populated summary records containing all 11 valuation and quality metrics in well under 5 seconds without making network or LLM requests

#### Scenario: Per-ticker fetch or valuation failure is isolated cleanly
- **WHEN** one ticker in a multi-ticker watchlist fails data retrieval or has negative base FCF
- **THEN** the remaining valid tickers still complete and return full valuation records while the failed ticker is surfaced cleanly with its error status rather than crashing the entire batch

### Requirement: Two-mode Streamlit navigation with one-click deep-dive handoff
The Streamlit application SHALL provide top two-mode navigation switching between `Single-Stock Deep-Dive` and `Watchlist Quick-Scan Screener`: Tab 1 preserves the full existing deep-dive dashboard and exports, while Tab 2 provides a comma-separated watchlist input (defaulting to the current target and peer tickers), a `Run Batch Valuation Scan` button bound to the active sidebar DCF assumptions, a sortable color-formatted comparison table, and a quick-select dropdown with a `Load Selected Ticker into Deep-Dive` button that sets the target ticker and triggers a full memo run.

#### Scenario: Watchlist Screener tab displays formatted multi-ticker comparison table
- **WHEN** a user opens `Watchlist Quick-Scan Screener` and clicks `Run Batch Valuation Scan`
- **THEN** the application renders a sortable formatted comparison table displaying `Price`, `Base DCF`, `DCF Upside %`, `Implied 5Y FCF CAGR`, `Forward P/E`, `EV/EBITDA`, `ROIC`, `FCF Margin`, and `Earnings Quality` for every scanned ticker

#### Scenario: Selecting a watchlist ticker hands off cleanly into Single-Stock Deep-Dive
- **WHEN** a user chooses a ticker from the quick-select dropdown in `Watchlist Quick-Scan Screener` and clicks `Load Selected Ticker into Deep-Dive`
- **THEN** the application updates the active target ticker in session state and runs the full Single-Stock Deep-Dive memo pipeline for that selected ticker
