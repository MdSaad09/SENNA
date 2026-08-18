# F25 — the Streamlit ceiling, reached on purpose (approved 18 Aug 2026)

Saad's verdict on the current interface, verbatim gaps: it looks like a data
tool, nothing moves, and the info is there but the story is not. Scope he
chose: max out Streamlit — no React resurrection, no 3D, no new stack.

## Objective & spec anchors

Make the three pages read as a race product within Streamlit's ceiling. 5.10.2
(every view carries its honesty note) binds every new element; F-27 keeps the
browser boundary (Streamlit calls the API, the browser calls Streamlit); the
F23 lesson (a green suite is not a working page) becomes an explicit
look-at-the-screenshot acceptance step. No number reaches a screen that the
API did not serve, and the s_track caveat (F11: display-only synthesis,
illustrative) stays on screen wherever s_track is drawn.

## Deliverables

- `app/theme.py` — from a palette to a small design system: Streamlit chrome
  hidden (header, hamburger, footer), custom metric styling to replace the
  stock `st.metric` look, card/panel primitives, a bundled local display face
  for headlines (no CDN), the mono eyebrow kept as the signature.
- `app/Home.py` — leads with an auto-composed race headline ("P8 -> P2 · one
  stop · +4 places through the lap-30 safety car"): deterministic template
  over stored frames and events, decision-card honesty rules, no generation.
  A race-moments strip (SC/VSC/red/weather/pit markers on one timeline) above
  the story chart.
- `app/pages/2_Playback.py` — the track map: a stylised closed curve with 22
  dots placed by each car's s_track, compound-coloured, agent highlighted,
  visibly circulating during autoplay; a battery gauge draining/refilling per
  lap beside it; the story chart's playhead truncation framed as the chart
  drawing itself.
- `app/pages/1_Explainability.py` — lap selection moves onto the race chart
  (click/select a lap there, not a naked slider); the decision presented as a
  styled card with the call line set large.
- `tests/app/test_pages_render.py` — extended for the new elements.

## Constants & configs

Colours and layout tokens stay in `app/theme.py` (stylised, the F23
convention: sampled 11 Aug palette). The track-map curve geometry is stylised
and says so on screen. No senna/, api/ or configs/ change — this feature
cannot touch the frozen chain.

## Tests first

- headline template: given frames+events fixtures, the composed sentence is
  exact (position path, stop count, event mention)
- moments strip: every stored event kind appears once, in lap order
- track map: 22 dots, dot-per-car, agent flagged; s_track note present
- AppTest render pass for all three pages with the client stubbed (existing
  pattern), plus the F23-lesson step: a screenshot of each page reviewed by a
  human (Saad or me in a browser) before the review battery runs

## Edge cases handled

- DNF races: headline says so instead of a finishing position
- races with no stops / no events: strip and headline degrade to what happened
- retired cars on the track map: parked at their frozen s_track (frames
  already encode this)

## Acceptance checklist

- [ ] All three pages pass the AppTest suite
- [ ] Screenshots of all three pages reviewed by eye before review
- [ ] No stock Streamlit chrome visible; no stock st.metric anywhere
- [ ] Track map circulates during autoplay; battery gauge moves with it
- [ ] Every new visual carries its honesty note (5.10.2)
- [ ] No number on screen the API did not serve

## Out of scope

React/3D resurrection; API changes; any senna/ change; new metrics or
numbers; the F24 evaluation artifacts.

## Questions for Saad

None blocking. Defaults taken: local-bundled font (no CDN); track-map curve is
a stylised closed loop, not circuit-accurate geometry (the ribbon pipeline is
not on this branch, and the honesty note says so).

## Sequencing

Builds after F24 lands, on its own branch (`feature/F25-streamlit-ceiling`),
its own session per the workflow. This plan rode the F24 branch as a docs-only
commit because the F24 fine-tune was reading this working tree's configs when
approval arrived — switching branches would have swapped the physics under a
live training process.

## Amendment — ship-time, Saad (19 Aug 2026)

Saad rejected the sampled F23 palette outright ("do not like this") and supplied two
reference sheets into docs/reference_images/: `SENNA_petrol_palette_reference.png`
(core petrol tokens, the harvest/deploy accent axis, a five-step state-of-charge ramp,
ten constructor pairs with a teammate-lift rule) and `SENNA_gradient_system.png`
(ambient canvas glow keyed to energy state with stated limits, surface lift gradients,
the team rule as a 3px top border, saturated gradients in data fills only). These
replace the F23 palette wholesale and are the `sourced` provenance for every colour
F25 ships.

Decisions taken under the amendment:
- The 11th team is SENNA itself: the ego carries the aqua harvest identity, the ten
  reference constructors take teams 1-10. Team grouping (car pairs) is a display
  convention over a simulator that models seats, not constructors — stated on screen.
- Team colour answers who; aqua/ember answer what; never the same role in one view
  (the reference's own rule). Ember stays out of navigation chrome.
- Palettes validated with the dataviz validator: accent axis passes (coast reads
  grey by design); the SOC ramp is luminance-monotonic; the 11 team colours carry
  known near pairs (the two blues, silver/white) and are therefore never the sole
  identity channel — car numbers ride every dot and row, teammates are hollow.
