# financial-data-ingestion Specification

## Purpose

Ingest, normalize, and validate historical financial metrics, market prices, and peer valuation multiples from live market data or deterministic offline fixtures so that downstream valuation and synthesis never rely on unverified or memorized numbers.

## Requirements

### Requirement: Target financial snapshot ingestion
The system SHALL fetch and validate a complete target company financial snapshot containing ticker, company name, sector, current price, market capitalization, enterprise value, trailing twelve months (TTM) revenue, TTM EBITDA, TTM net income, TTM operating cash flow, TTM capital expenditures, TTM free cash flow, total debt, cash and equivalents, shares outstanding, and 3-year historical revenue growth rate.

#### Scenario: Successful live market data fetch
- **WHEN** a user requests live ingestion for a valid publicly traded ticker
- **THEN** the system retrieves current market and financial statement metrics and returns a validated financial snapshot with all required fields populated

#### Scenario: Missing free cash flow fallback derivation
- **WHEN** the upstream market data source omits Free Cash Flow but provides Operating Cash Flow and Capital Expenditures
- **THEN** the system computes TTM Free Cash Flow as `operating_cash_flow_ttm - abs(capex_ttm)` and populates the snapshot without failing

#### Scenario: Missing critical market data or network timeout
- **WHEN** a live data request times out, encounters a rate limit, or lacks required non-derivable fields such as current price or shares outstanding
- **THEN** the system raises a structured ingestion error explaining the missing field or network failure rather than substituting guessed values

### Requirement: Peer comparable ingestion
The system SHALL ingest valuation multiples (`ev_to_ebitda`, `pe_ratio`, and `fcf_yield`) for a configurable list of 3 to 5 peer tickers.

#### Scenario: Partial peer metrics available
- **WHEN** one or more peer tickers lack a specific multiple such as P/E or EV/EBITDA in the upstream feed
- **THEN** the system records `None` for the unavailable multiple while retaining all other available peer multiples

#### Scenario: Individual peer lookup failure
- **WHEN** fetching one peer ticker fails due to an invalid symbol or transient upstream error while other peers succeed
- **THEN** the system handles the failure gracefully without crashing the entire analysis and surfaces a clear warning or records null multiples for that peer

### Requirement: Deterministic offline fixture ingestion
The system SHALL support an offline mock-data mode and custom local JSON fixture input that load deterministic target and peer financial records without making external network calls.

#### Scenario: Built-in offline mock data load
- **WHEN** ingestion is invoked with offline mock-data mode enabled (for example for `AVGO` and semiconductor peers `NVDA,AMD,MRVL,QCOM`)
- **THEN** the system returns validated, deterministic target and peer records strictly from local fixture data with zero outbound network requests

#### Scenario: Custom local JSON fixture load
- **WHEN** a valid local JSON fixture file path is supplied
- **THEN** the system parses and validates the fixture against the financial snapshot and peer comparable contracts, rejecting malformed or incomplete fixtures with clear validation errors
