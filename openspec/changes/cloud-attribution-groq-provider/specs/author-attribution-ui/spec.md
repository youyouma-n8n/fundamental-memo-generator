## Purpose

Provide clear, non-intrusive author attribution crediting `"Built by Josh Zhou @ UChicago"` in both the Streamlit sidebar footer and the main page header/footer across local and Streamlit Community Cloud sessions without obstructing charts, tables, or memo exports.

## ADDED Requirements

### Requirement: Author Attribution in Sidebar and Main Page
The Streamlit application SHALL display the exact author attribution text `"Built by Josh Zhou @ UChicago"` visibly in both the sidebar footer and the main page header/footer area in local and cloud-deployed runs.

#### Scenario: Viewing attribution in the sidebar footer
- **WHEN** a user loads the application in either local or Streamlit Community Cloud mode
- **THEN** `"Built by Josh Zhou @ UChicago"` MUST be rendered in the sidebar below the `Data & offline mode` checkbox and `Generate one-page memo` button, separated cleanly by a subtle divider
- **AND** it MUST remain visible regardless of whether the user is in `Single-Stock Deep-Dive` or `Watchlist Quick-Scan Screener` mode.

#### Scenario: Viewing attribution in the main page header and footer
- **WHEN** a user views the main application workspace before or after running an analysis
- **THEN** `"Built by Josh Zhou @ UChicago"` MUST be visible in the main page subheader caption (or main footer) without overlapping, shifting, or obstructing KPI metric cards, Plotly charts, sensitivity tables, Watchlist tables, or `.md`/`.html` download buttons.
