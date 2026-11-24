## Purpose

Polish the Streamlit UI and Plotly visualizations to eliminate KPI card text truncation, prevent Football Field label clipping and callout overlap, improve Peer Scatter bubble readability with a Peer Median reference line, and present an interactive color-coded 5×5 DCF Sensitivity Table.

## ADDED Requirements

### Requirement: Non-truncating five-card KPI header row
The system SHALL format the 5-column KPI header row concisely so labels and deltas render without `...` ellipsis truncation at desktop viewports (`>= 1280px`):
1. `Current Price` (`$X.XX` | delta: `52W: $L–$H`)
2. `DCF Intrinsic Value` (`$X.XX` | delta: `±X.X% vs. price`)
3. `Market-Implied CAGR` (`X.X%` | delta: `±X.X% vs. base`)
4. `ROIC (TTM)` (`X.X%` | delta: `OpM X.X% | GM X.X%`)
5. `Earnings Quality` (`High`/`Moderate`/`Low` | delta: `OCF/NI X.XXx | Adj $X.XB`)

#### Scenario: KPI labels and compact deltas render cleanly
- **WHEN** an analysis completes in Streamlit
- **THEN** the 5 KPI cards display the exact compact labels (`Current Price`, `DCF Intrinsic Value`, `Market-Implied CAGR`, `ROIC (TTM)`, `Earnings Quality`) and formatted deltas without oversized strings that trigger truncation

### Requirement: Football Field label padding and non-overlapping Current Price callout
The system SHALL configure the Valuation Football Field Plotly chart with dynamic `xaxis.range = [max(0, min_val * 0.75), max_val * 1.22]` to prevent right-edge dollar label clipping, and SHALL place the `Current Price: $XXX.XX` annotation cleanly above the top bar (`yref="paper", y=1.08, showarrow=False`).

#### Scenario: Football Field bounds and callout placement verified
- **WHEN** the Valuation Football Field figure is constructed
- **THEN** `layout.xaxis.range` spans `[max(0, min_val * 0.75), max_val * 1.22]` and the `Current Price` annotation sits at `yref="paper"` with `y >= 1.05` and `showarrow=False` so it does not overlap the `52-Week Trading Range` bar

### Requirement: Peer Scatter area bubble contrast and Peer Median reference line
The system SHALL size bubbles in the Peer Valuation vs. Growth Scatter Plot using `sizemode="area"` and `sizeref = 2.0 * max(market_caps) / (42**2)` (when market caps are available), and SHALL draw a horizontal dashed reference line (`add_hline`) at `peer_median_ev_ebitda` labeled `Peer Median (XX.Xx)` whenever `peer_median_ev_ebitda` is available.

#### Scenario: Peer Scatter displays area-scaled bubbles and Peer Median line
- **WHEN** the Peer Scatter figure is built with positive peer `market_cap` and `peer_median_ev_ebitda`
- **THEN** scatter markers use `sizemode="area"` with `sizeref = 2.0 * max(market_caps) / (42**2)` and the figure contains a horizontal dashed line at `peer_median_ev_ebitda` annotated `Peer Median (<median>x)`

### Requirement: Interactive 5×5 DCF Sensitivity Table with implied exit multiple caption
The system SHALL render the 5×5 `dcf_sensitivity_matrix` in an expandable block directly below the Plotly charts, highlighting the Base Case center cell, coloring cells above `current_price` in muted green and cells below `current_price` in muted red/neutral, and displaying a caption comparing the Perpetuity DCF implied exit EV/EBITDA multiple against the user's Exit Multiple assumption.

#### Scenario: Sensitivity table and exit multiple caption render in Streamlit UI
- **WHEN** an analysis completes in Streamlit with a valid `dcf_sensitivity_matrix` and `implied_exit_ev_ebitda`
- **THEN** the UI displays the 5×5 table with WACC columns and 5Y FCF CAGR rows, matches the headline DCF Intrinsic Value in the center cell, and shows the caption `"Perpetuity DCF (<g>% terminal growth) implies an exit EV/EBITDA of <implied>x vs. your Exit Multiple assumption of <target>x."`
