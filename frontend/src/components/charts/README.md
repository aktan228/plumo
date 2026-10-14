# Bklit UI charts

Area Chart and its registry dependencies were installed from the official Bklit UI registry on 2026-10-08:

- https://ui.bklit.com/r/area-chart.json
- https://ui.bklit.com/r/y-axis.json
- https://bklit.com/docs/components/area-chart

Source: https://github.com/bklit/bklit-ui (MIT; see LICENSE.bklit).
Registry source is vendored here, with `components/shimmering-text.tsx` and `lib/utils.ts` also supplied by Bklit. The registry specifies Visx 4.0.1-alpha.0 for React 19 compatibility; exact installed versions are recorded in package-lock.json.

Local adaptations:
- Fixed the registry's relative ShimmeringText import for this directory layout.
- Touch handlers do not prevent default scrolling; interaction surface uses pan-y. Selection/zoom is not exposed on the landing page.
- Plumo chart colours and CSS are scoped in landing/statistics.css.
- Dates and tooltip content are localized by the landing component, using fixed UTC sample dates.

The statistics preview uses deterministic fictional data. Period totals and the meeting-request percentage are derived from the same daily records. A range input provides access to every daily value with touch and keyboard.
