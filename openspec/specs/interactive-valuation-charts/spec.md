# interactive-valuation-charts Specification

## Purpose

Upgrade the Streamlit web interface with expanded DCF parameter controls, a 5-metric institutional KPI banner, and interactive Plotly Valuation Football Field and Peer Valuation-Growth Scatter visualizations rendered above the investment memo.

## Requirements

### Requirement: Expanded DCF assumption sidebar controls
The system SHALL provide sidebar controls under DCF Assumptions for `5Y FCF CAGR` (numeric input, default `0.15`, step `0.01`, format `"%.3f"`) and `Terminal Exit EV/EBITDA Multiple` (numeric input, default `15.0`, step `0.5`, format `"%.1f"`), passing both values into the shared valuation pipeline alongside WACC and Terminal Growth Rate.

#### Scenario: Default sidebar DCF values displayed
- **WHEN** a user opens the Streamlit application
- **THEN** the DCF Assumptions sidebar displays `5Y FCF CAGR` defaulting to `0.150` and `Terminal Exit EV/EBITDA Multiple` defaulting to `15.0` alongside WACC (`0.095`), Terminal Growth (`0.025`), and the 3-model selector dropdown

#### Scenario: Adjusting sidebar DCF inputs updates valuation outputs
- **WHEN** a user modifies `5Y FCF CAGR` or `Terminal Exit EV/EBITDA Multiple` and runs analysis
- **THEN** the resulting DCF intrinsic value, Exit Multiple DCF valuation, and charts reflect the updated inputs

### Requirement: Five-metric KPI header banner
The system SHALL display a 5-column KPI header row above the charts and memo showing: (1) `Current Price`, (2) `DCF Intrinsic Value` with `% upside/downside` delta, (3) `Market-Implied FCF CAGR` with `vs. Base CAGR` delta, (4) `ROIC / Operating Margin`, and (5) `Earnings Quality` with `OCF/NI` and `SBC-Adj FCF` delta context.

#### Scenario: All five KPI cards render cleanly in offline and live modes
- **WHEN** an analysis completes successfully
- **THEN** the Streamlit UI renders all five KPI metric cards, formatting unavailable optional metrics as `N/A` without raising exceptions

### Requirement: Interactive Plotly Valuation Football Field chart
The system SHALL render an interactive Plotly horizontal range chart (`Valuation Football Field`) above the Markdown memo comparing: `52-Week Trading Range` (`52w_low` to `52w_high`), `Perpetuity DCF Sensitivity` (`WACC +1%` to `WACC -1%`), `Exit Multiple DCF Valuation`, and `Peer Comps Valuation Range` (25th to 75th percentile implied share price), overlaid with a vertical dashed reference line at `Current Price`.

#### Scenario: Valuation Football Field displays available ranges and current price line
- **WHEN** an analysis produces valid valuation ranges and `current_price`
- **THEN** the Streamlit UI renders the Valuation Football Field Plotly figure containing the horizontal range bars and a vertical dashed line at `Current Price`, gracefully omitting any bar whose inputs are `None`

### Requirement: Interactive Plotly Peer Valuation vs. Growth scatter plot
The system SHALL render an interactive Plotly scatter chart above the Markdown memo plotting `Historical Revenue Growth (%)` on the X-axis against `EV / EBITDA (x)` on the Y-axis, sizing bubbles by `Market Cap` (falling back to `FCF Yield` or uniform size if unavailable), highlighting the target ticker in `#FF4B4B` and peer tickers in `#64748B` with visible ticker labels on all plotted points.

#### Scenario: Target and peers rendered with distinct styling and labels
- **WHEN** target and peer records include positive EV/EBITDA and revenue growth metrics
- **THEN** the Plotly scatter figure plots the target in `#FF4B4B` and peers in `#64748B` with text labels on all points above the rendered Markdown memo
