# scatter-label-positioning Specification

## Purpose

Ensure the Peer Valuation vs. Growth scatter chart places its horizontal `Peer Median` reference label in the low-growth left margin so it never collides with high-growth peer bubbles on the right side of the plot.

## Requirements

### Requirement: Left-aligned Peer Median reference label on scatter plot
The Peer Valuation vs. Growth scatter chart SHALL place its horizontal `Peer Median` reference line annotation at `top left` with font size `11` so the label sits cleanly above the dashed reference line in the left margin rather than colliding with high-growth peer bubbles.

#### Scenario: Peer Median annotation renders at top left with font size 11
- **WHEN** the Peer Valuation vs. Growth scatter chart is generated with a valid `peer_median_ev_ebitda`
- **THEN** the `Peer Median` annotation is left-anchored on the left edge of the plot (`xanchor="left"`, `x=0`, `xref="paper"`) with font size `11` and displays the formatted median multiple
