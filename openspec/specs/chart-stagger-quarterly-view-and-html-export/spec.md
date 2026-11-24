# chart-stagger-quarterly-view-and-html-export Specification

## Purpose

Eliminate overlapping reference annotations on the Valuation Football Field across all price spreads, expose recent 4-quarter momentum alongside the 3-year annual trajectory in the web interface, and allow analysts to export a standalone print-friendly HTML research report containing interactive charts, quantitative tables, and the audited investment memo.

## Requirements

### Requirement: Non-overlapping Valuation Football Field top reference annotations
The Valuation Football Field chart SHALL permanently stagger its `Current Price` and `Analyst Consensus Target` top reference annotations in both vertical paper coordinates and opposite horizontal alignment (`Current Price` higher and right-anchored left of its dashed line; `Analyst Consensus Target` lower and left-anchored right of its dotted line) with sufficient top and right layout margins so the labels never collide or clip regardless of how close or far apart the two prices are.

#### Scenario: Close Current Price and Analyst Consensus Target have zero overlap
- **WHEN** the Valuation Football Field is rendered for a ticker whose `current_price` and `analyst_target_mean` are within 2% of each other (or equal)
- **THEN** the `Current Price` annotation is placed at `yref="paper"`, `y=1.12`, `xanchor="right"`, `xshift=-4` and the `Analyst Consensus Target` annotation is placed at `yref="paper"`, `y=1.03`, `xanchor="left"`, `xshift=4`, with top margin `>= 65` and right margin `>= 40`

#### Scenario: Wide price spread preserves staggered layout without clipping
- **WHEN** the Valuation Football Field is rendered for a ticker whose `analyst_target_mean` is substantially above or below `current_price`
- **THEN** both annotations maintain their distinct vertical tiers and anchor offsets without overlapping the chart title or clipping at the right plot boundary

### Requirement: Tabbed Annual and Quarterly Trajectory view in Streamlit
The Streamlit application's Historical Trajectory panel SHALL present a two-tab view (`Annual (3Y)` and `Quarterly (4Q)`) showing the 3-year dual-axis trajectory chart on the Annual tab and a compact formatted 4-quarter momentum table (`Quarter`, `Revenue ($B)`, `Gross Margin (%)`, `Operating Margin (%)`, `FCF ($B)`) on the Quarterly tab, falling back gracefully when quarterly data is unavailable.

#### Scenario: Both annual and quarterly series render in dedicated tabs
- **WHEN** an analysis completes with both `historical_trajectory` and `quarterly_trajectory` populated
- **THEN** the Historical Trajectory panel renders an `Annual (3Y)` tab containing the 3-year dual-axis chart and a `Quarterly (4Q)` tab containing the formatted 4-quarter momentum table

#### Scenario: Missing quarterly history degrades cleanly
- **WHEN** an analysis completes with an empty `quarterly_trajectory`
- **THEN** the `Quarterly (4Q)` tab displays a concise notice that quarterly statement data was unavailable rather than raising an error

### Requirement: Self-contained interactive HTML report export
The system SHALL generate a standalone, print-friendly HTML report (`report_<TICKER>.html`) containing zero external local file dependencies, embedding the report header and 5-card KPI summary grid, interactive Plotly charts powered by a single Plotly.js CDN script tag in `<head>`, the Reverse DCF Reality Check callout, the color-coded 5×5 DCF Sensitivity Matrix table, the 4-quarter momentum table (when available), the rendered HTML body of the one-page investment memo, and a `Grounding Audit: Passed` badge, accessible via a download button placed directly beside `Download memo_<TICKER>.md` in the Streamlit UI.

#### Scenario: Standalone HTML export contains all institutional sections and interactive figures
- **WHEN** an analyst clicks `Download report_<TICKER>.html` after generating a memo
- **THEN** the downloaded `.html` document is valid HTML5 with print-friendly centered CSS (`max-width: 960px`), includes exactly one Plotly.js CDN `<script>` tag in `<head>`, embeds interactive Plotly chart markup (`full_html=False`) for the Football Field, Peer Scatter, and 3-Year Historical Trajectory, renders the 5-card KPI grid, Reverse DCF Reality Check, 5×5 DCF sensitivity table, 4-quarter momentum table, HTML memo body, and `Grounding Audit: Passed` badge

#### Scenario: HTML export safely escapes raw text and handles optional sections gracefully
- **WHEN** the HTML exporter is invoked for a snapshot missing optional fields (such as `analyst_target_mean`, `historical_trajectory`, or `quarterly_trajectory`) or containing HTML-special characters (`&`, `<`, `>`) in company names
- **THEN** HTML-special characters are properly escaped and omitted optional sections degrade cleanly without raising exceptions
