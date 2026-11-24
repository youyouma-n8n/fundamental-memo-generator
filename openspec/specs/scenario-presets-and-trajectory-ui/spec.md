# scenario-presets-and-trajectory-ui Specification

## Purpose

Upgrade the Streamlit interface and Plotly visualizations with one-click Bear/Base/Bull DCF presets, an Analyst Consensus Target overlay on the Valuation Football Field, a dual-axis 3-Year Historical Trajectory chart, and a Reverse DCF Year-5 FCF Reality Check callout card.

## Requirements

### Requirement: Sidebar Bear / Base / Bull scenario presets
The system SHALL display a 3-column preset button bar (`Bear` | `Base` | `Bull`) at the top of the `DCF assumptions` sidebar section wired via `st.session_state` callbacks that immediately update all four DCF inputs:
- **Bear:** `WACC = 0.105`, `Terminal g = 0.020`, `5Y FCF CAGR = 0.080`, `Exit EV/EBITDA = 12.0`
- **Base:** `WACC = 0.095`, `Terminal g = 0.025`, `5Y FCF CAGR = 0.150`, `Exit EV/EBITDA = 15.0`
- **Bull:** `WACC = 0.085`, `Terminal g = 0.030`, `5Y FCF CAGR = 0.250`, `Exit EV/EBITDA = 20.0`

#### Scenario: Clicking scenario preset buttons updates all four DCF controls
- **WHEN** a user clicks `Bear`, `Base`, or `Bull` in the sidebar
- **THEN** all four DCF numeric inputs (`WACC`, `Terminal growth rate`, `5Y FCF CAGR`, `Terminal Exit EV/EBITDA Multiple`) immediately reflect that preset's exact values in `st.session_state` without runtime errors

### Requirement: Analyst Consensus Target overlay on Valuation Football Field
The system SHALL add a vertical dotted reference line (`#38BDF8`) and non-overlapping annotation for `Analyst Consensus Target ($XXX.XX)` alongside `Current Price ($XXX.XX)` on the Valuation Football Field whenever `financial_snapshot.analyst_target_mean` is available, dynamically factoring `analyst_target_mean` into the x-axis range padding.

#### Scenario: Consensus Target line rendered when available
- **WHEN** `financial_snapshot.analyst_target_mean` is populated
- **THEN** the Valuation Football Field includes a vertical dotted line in `#38BDF8` at `analyst_target_mean` with a clean annotation alongside the dashed `#FF4B4B` `Current Price` line

#### Scenario: Consensus Target omitted gracefully when None
- **WHEN** `financial_snapshot.analyst_target_mean` is `None`
- **THEN** the Valuation Football Field renders cleanly with only the `Current Price` reference line

### Requirement: Dual-axis 3-Year Historical Trajectory chart
The system SHALL render a 3rd Plotly chart (`3-Year Historical Trajectory`) displaying `Revenue ($B)` as bars (`#3B82F6`) on the primary y-axis and `Operating Margin (%)` as a line overlay (`#F59E0B`) on the secondary y-axis across the 3 fiscal years in `historical_trajectory`, accompanied by a caption summarizing 3-year/TTM Free Cash Flow progression.

#### Scenario: Three-year trajectory combo chart renders cleanly
- **WHEN** `financial_snapshot.historical_trajectory` contains historical fiscal year entries
- **THEN** the Streamlit UI renders the dual-axis Revenue + Operating Margin Plotly chart with a caption noting FCF progression

### Requirement: Reverse DCF Year-5 FCF Reality Check callout card
The system SHALL display a compact `Reverse DCF Reality Check` callout (`st.info`) directly above or beside the 5×5 DCF Sensitivity Matrix showing `current_price`, `implied_fcf_cagr_5y`, `implied_y5_fcf_multiple`, `free_cash_flow_ttm`, `implied_y5_fcf`, and `revenue_ttm`.

#### Scenario: Reverse DCF Reality Check callout displayed with exact figures
- **WHEN** `implied_fcf_cagr_5y` and `implied_y5_fcf` are computed
- **THEN** the UI displays the `Reverse DCF Reality Check` callout citing current price, market-implied 5Y FCF CAGR, Year-5 FCF multiple and dollar magnitude, and current TTM revenue comparison
