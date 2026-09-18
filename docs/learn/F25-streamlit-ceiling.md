# F25 — the petrol design system, and a palette that arrived with rules

## What we built and why

F23 ended with a palette sampled from screenshots, and Saad's verdict on it was two
words: "do not like this". What he supplied instead was not another mood board. The two
sheets in `docs/reference_images/` — `SENNA_petrol_palette_reference.png` and
`SENNA_gradient_system.png` — carry rules as well as colours: a set of petrol core
tokens, an accent axis where aqua means harvest and ember means deployment (one axis,
two temperatures), a five-step state-of-charge ramp that must climb in brightness from
empty to full, ten constructor pairs with a stated teammate-lift rule, and limits on
gradients (nothing under 40px wears one, one ambient glow at a time, saturation only
inside a data fill).

F25 is those sheets built, across the whole Streamlit interface. `app/theme.py` holds
the tokens and the CSS; `app/story.py` composes a deterministic race headline and a
moments strip from stored frames; `app/trackmap.py` puts each car's `s_track` on a
stylised stadium loop; the three pages were restyled around all of it; and
`.streamlit/config.toml` exists because Streamlit paints its widgets from a theme layer
that injected CSS cannot reach. No `senna/`, `api/` or `configs/` file changed — the
frozen chain is untouched.

The two most examinable parts of this feature are not visual at all. First, the
headline over the race page is template assembly, never text generation, because the
5.8.3 honesty rule for decision cards applies just as hard to a sentence as to a card.
Second, the ship repeated F23's hardest lesson on purpose: a screenshot pass ran as an
explicit acceptance step and caught three defects no test in the suite could see, and
the review then caught a fourth of exactly the shape F23 warned about.

## New ideas in this feature

**A palette is a system with roles, not a list of colours.** A design token is a named
constant with a job: `ACCENT` is not "a nice teal", it is the harvest side of the
energy axis and the interface's resting accent. The sheets assign every colour a role
and F25 keeps the assignment as law: team colour answers WHO, the aqua/ember axis
answers WHAT the energy is doing, and `DANGER` is reserved for limit breach — which is
why the soft compound could not keep the alert hex it briefly wore. The corollary is
one token, one role: a hex holding two meanings in one view has no provenance, because
"sourced from the sheet" is only true for the meaning the sheet gave it. The mental
model is a vocabulary — you can coin new words (`CHART_GRID` is ours, marked stylised),
but you may not use an existing word to mean two things. This is the interpretability
contract (F-12, the provenance comment rule) applied to pixels: every hex in `theme.py`
carries `sourced` with the sheet's name, or `stylised` with the choice stated.

**Computational palette validation.** Colours are measurable, so the sheet's claims
were checked by computation, not by eye: the SOC ramp's five steps were verified
luminance-monotone (the test now pins it with the WCAG luminance formula), the accent
axis was checked for contrast and colour-vision-deficiency separation (coast reads grey
by design — it is the neutral of the axis, so "indistinct" is its job), and the eleven
team pairs were checked pairwise. That last check failed, honestly: the palette has
near pairs — Red Bull's and Racing Bulls' blues, Mercedes silver against Haas white —
exactly as real F1 liveries do. The answer is not new hues (the sheet is the source);
it is a secondary encoding, so identity is never colour alone: a car number rides every
dot and every table row, teammates draw hollow, the ego wears an aqua ring. Contrast
as a correctness property was F23's lesson; the new step is running the checks up
front, on the whole system, and designing the redundancy in rather than lifting hexes
after a failure.

**Template assembly, applied to prose.** The decision card rule (5.8.3) is that every
sentence shown to a reader is slot-filling over served data — same input, same words,
every clause traceable to a field. `race_headline` extends that rule from cards to the
page's lead sentence: it is a `parts` list joined with separators, and a clean race
produces a headline that says nothing about events because there is no slot for an
event that did not happen. A generative model could produce a nicer sentence; it could
also produce a claim the frames do not contain, and nobody could say afterwards which
field any given word came from. The viva answer, two sentences: **the headline is
deterministic template assembly because the interface's credibility rests on every
statement being a projection of stored data; generation would trade traceability for
fluency in the one artifact whose entire job is traceability.**

**A piecewise parametric curve, walked by distance.** You have met arc length twice —
F04 resampled the ribbon by it, F11 rebuilt the centreline with a lookup table. The new
piece is building a curve *from* segments rather than measuring one: `loop_point(s)`
turns a lap fraction into a point by converting `s` to a distance along the perimeter,
then subtracting each segment's length (straight, arc, straight, arc) until the
remainder falls inside one. The mental model is walking a running track with a trip
meter: the only state you need is how far you have walked, and the segment you are on
is whichever one the remaining distance fits in. The smallest example is the top
straight: `d < STRAIGHT` means the answer is just `(-half + d, RADIUS)`.

**Streamlit's theme layer sits below CSS.** `theme.page()` injects a `<style>` block
and that styles everything that is HTML — cards, headings, the sidebar. But Streamlit
paints its widget primitives (buttons, radios, sliders) from its own theme
configuration, and with no `.streamlit/config.toml` that theme is the stock one, so
every widget arrived in Streamlit's default red on an otherwise petrol page. The fix is
to state the same sourced hexes in the theme layer too. This is not a DRY violation to
engineer away; it is two rendering paths that each need to be told, and the config file
says so in its header comment.

**AppTest stops at the widget tree — the vega-lite proto goes further.** Streamlit's
`AppTest` runs a page for real and hands back its elements, which is the closest thing
to looking at the page that CI can do. It has accessors for markdown, captions and
warnings, but none for charts. The `_chart_rows` helper in `test_pages_render.py`
reaches past that: each chart element carries its vega-lite proto, and the proto holds
the spec plus the inlined datasets as Arrow streams, so `pyarrow` can decode exactly
the rows the reader's chart draws. The distinction that matters is spec versus dataset:
the SOC-gauge test asserts the ramp's five hexes inside one chart's *spec*, because a
team hex sitting in the track-map *data* had made the first version of that assertion
vacuously true — the review found it, and F14's vacuous-tests lesson names the failure
mode.

## The code, guided

### app/theme.py — the tokens and the primitives

The module docstring states where every hex comes from and quotes the sheet's rules;
that docstring is the file's provenance comment. Then the tokens:

```python
# core tokens — sourced, SENNA_petrol_palette_reference.png
GROUND = "#0A1014"
...
ACCENT = "#2ED9C3"
DEPLOY = "#FF7A3D"
COAST = "#7A8C99"
DANGER = "#FF3B5C"
```

Four accent names, four roles. `COAST` exists so that "no energy event" has a token of
its own rather than borrowing grey from the text scale — role vocabulary again.

`TEAMS` is the eleven-tuple with SENNA first, and the decision deserves its own
paragraph. The grid is 22 cars in 11 teams (the 2026 physics table; the 5.9.2
bounds), and the sheets supply exactly ten constructor pairs. Making SENNA itself the
eleventh team solves three problems at once: the two-seats-per-team invariant stays
exact, no eleventh constructor has to be invented, and the ego carries the aqua harvest
identity — the interface's own accent — so the agent is findable in any view without a
special-case marker. The comment above the tuple adds the review's refinement: SENNA's
teammate hex was moved off the SOC ramp's step, because one hex may not answer "who" on
the map and "what" on the gauge in the same view.

`team_of` is three lines and each earns its place:

```python
def team_of(car_id: int) -> tuple[str, str, bool]:
    name, primary, teammate = TEAMS[car_id // 2]
    is_teammate = car_id % 2 == 1
    return name, (teammate if is_teammate else primary), is_teammate
```

`car_id // 2` pairs seats into teams because the simulator models seats, not
constructors — the pairing is a display convention, and every view that uses it says so
on screen. `car_id % 2` makes the odd seat the teammate, and the boolean rides along so
callers can draw the hollow shape rather than trusting the lifted hex to be visible.

`COMPOUND_COLOURS` is marked stylised, names no supplier (F-29), and its soft is a rose
that is deliberately *not* `DANGER` — that hex spent one commit on the soft compound and
the screenshot pass evicted it, because a reserved status token was moonlighting as a
tyre.

The rest of the file is block-level: `page()` injects the CSS classes every page uses
(cards, stat tiles, eyebrow, notes, footer) and hides Streamlit's chrome; `ambient()`
re-keys the canvas glow per the gradient sheet, painting the destination state directly
because an 800ms cross-fade cannot survive Streamlit's rerender; `headline()` renders
its string verbatim with no injected markup, because tests match the composed sentence
exactly and the string is the artifact. `note()` and `footer()` carry 5.10.2 and R-07.
`require_run()` gives every page after the first one place to ask for a race.

### .streamlit/config.toml — the layer CSS cannot reach

Twelve lines: the petrol tokens restated for the widget primitives, `toolbarMode =
"minimal"` so a research interface has no Deploy button, and telemetry off. It exists
because of the red-widget defect; its header comment says so.

### app/story.py — the headline, line by line

```python
_EVENT_RANK = ("red", "sc", "vsc", "weather")
```

The ranking is severity order and it is data, not code — the headline names *one*
event, so a tie-break rule has to exist and be visible. Red flag over safety car over
virtual over weather.

```python
def race_headline(frames, summary, grid_position):
    start = f"P{grid_position}" if grid_position else "—"
```

A run row can lack its grid (older runs, partial configs); the honest render is a dash,
not `PNone` — that literal `PNone` is what the first version printed, and the review
fix commit names it.

```python
    finish = "DNF" if summary.get("dnf") else f"P{summary.get('final_position')}"
```

The summary still carries the frozen classification for a DNF, and the headline must
not use it: `test_a_dnf_headline_says_dnf_instead_of_a_finishing_position` pins that
`P18` never appears.

```python
    stops = len(_ego_stops(frames))
    parts = [f"{start} → {finish}", _COUNTS.get(stops, f"{stops} stops")]
```

Stops are counted from frames rather than trusted from anywhere else, and `_COUNTS`
spells out zero to three ("no stops", "one stop") with a numeric fallback beyond —
prose slots, not string arithmetic.

```python
    headliner = _headline_event(frames)
    if headliner is not None:
        kind, lap = headliner
        parts.append(f"through {_EVENT_PHRASE[kind].format(lap=lap)}")
    return " · ".join(parts)
```

The event clause only exists when an event does; a clean race gets a two-part headline
and `test_a_clean_race_headline_mentions_no_event` walks a word list to prove nothing
was invented.

`_ego_stops` reads the ego's own `in_pit` flag rather than the stream's pit events,
because pit events cover all 22 cars and the pit-lap frame already carries the new
compound — which is the detail worth showing ("pit for HARD"). This is F23's
authoritative-signal lesson applied a second time: derive from the flag that *is* the
fact, not a correlate. `_headline_event` records the first lap of each ranked kind with
`setdefault` (first occurrence wins) and then returns the highest-ranked kind present.

`race_moments` merges every stored non-pit event with the ego's stops, sorted by lap.
Rival stops are excluded on purpose — `test_rival_pit_stops_are_not_moments` pins the
exclusion — because the strip is the ego's race plot, and 21 rivals' stops would bury
it.

### app/trackmap.py — the loop, line by line

```python
STRAIGHT = 2.2
RADIUS = 0.75
_PERIMETER = 2 * STRAIGHT + 2 * math.pi * RADIUS
```

Stylised, and the docstring says why that is legal: the environment is lap-quantised
and holds no geometry; `s_track` is the serve layer's display-only synthesis (F11), so
the loop's proportions are a visual choice and every view drawing it says so on screen.

```python
def loop_point(s: float) -> tuple[float, float]:
    d = (s % 1.0) * _PERIMETER
```

`s % 1.0` makes lap fractions wrap — `loop_point(1.25) == loop_point(0.25)`, pinned by
`test_lap_fractions_wrap`, including negative inputs, because Python's `%` returns a
non-negative result for a positive modulus.

```python
    half = STRAIGHT / 2
    if d < STRAIGHT:  # top straight, left to right
        return -half + d, RADIUS
```

The start line sits at the top straight's left end and the walk runs clockwise, so the
leader crossing the line reads left-to-right the way a timing screen does — that is a
stated reason in the docstring, not an accident of the maths.

```python
    d -= STRAIGHT
    if d < math.pi * RADIUS:  # right arc, down
        angle = d / RADIUS
        return half + math.sin(angle) * RADIUS, math.cos(angle) * RADIUS
```

Each segment consumes its own length from `d` before the next test, so every branch
works in local coordinates. On the arc, `angle = d / RADIUS` is arc length over radius
— radians by definition — and the sin/cos pair starts at the straight's endpoint
(`angle = 0` gives `(half, RADIUS)`), which is what makes the join seamless.
`test_adjacent_samples_never_jump` walks 400 samples and asserts no step exceeds twice
the expected spacing; that test, not the closure test, is the one carrying the load, as
one of the exercises will show. The bottom straight and left arc mirror the first two
segments with signs flipped.

`outline()` samples 200 segments (an operational constant with its sizing comment) and
`field_rows()` joins `loop_point` to `theme.team_of` per car — its docstring restates
the secondary-encoding rule: label on every dot, teammate hollow, ego ringed, because
the palette has known near pairs by its own reference sheet.

### app/Home.py — the race page

Block level: the sidebar builds the run request (weather, era, rival band, grid, seed)
and posts it through `app/client.py` — Streamlit calls the API, the browser calls
Streamlit, which is F-27's boundary kept. The result panel leads with the eyebrow, the
composed headline, and the stat tiles; the comment above `theme.stats` explains why
points are absent (the served value is the FIA table over `points_divisor` 2.5, so
printing it would read as wrong — and the render test bans the word).

`moments_strip` is where the token-role rule got enforced by review. As shipped, safety
cars wore ember. The review took ember off:

```python
"colour": theme.ACCENT if m["kind"] == "pit" else (
    theme.DANGER if m["kind"] == "red" else theme.COAST)
```

Aqua is the agent's own action, alert is the red flag, and everything else the track
did is coast — because ember is an energy word by the sheet, and a token that means
"deployment" on the gauge and "safety car" on the strip has two meanings and therefore
no sourced provenance. The examiner version: **ember's provenance is "sourced,
deployment accent, per the reference sheet"; putting it on a safety-car tick would make
that comment false for half its uses, so track status wears the neutral and only limit
breach saturates.** The strip's labels alternate two heights so a pit under its own
safety car stays legible — a screenshot-pass fix, not a test-driven one.

`race_story` draws the whole field in team colour at low opacity with the agent's aqua
line over it — team colour answers who, aqua answers the agent — and the closing
`theme.note` states the seats-not-constructors convention, the read-back stints, and
why service time is not shown (the simulator never serves it).

### app/pages/2_Playback.py — the field on the loop

The glow decision is short enough to read whole:

```python
NEUTRAL_FLOOR_MJ = 0.05  # operational — flows under this read as no energy event
if energy["harvest_mj"] < NEUTRAL_FLOOR_MJ and energy["deploy_mj"] < NEUTRAL_FLOOR_MJ:
    glow_state = "neutral"
elif energy["harvest_mj"] >= energy["deploy_mj"]:
    glow_state = "harvesting"
else:
    glow_state = "deploying"
```

The floor exists because the review asked whether neutral was reachable at all: without
it, any lap with a microjoule of flow picks a side, and "neutral" is defined away.
`>=` breaks the exact tie toward harvest, the resting accent.

The track chart layers one dataset five ways — loop line, ego ring, filled primaries,
hollow teammates, pit ring in text ink, and the car number riding every dot. Each layer
is a `transform_filter` over the same rows so the chart carries one dataset in its
proto, which is what lets `_chart_rows` find "the chart with 22 x/y points per car".
The battery gauge is the one saturated gradient the sheet allows (a data fill), its bar
sits at the sheet's 40px floor, and its stops are the SOC ramp in order. The page's
`theme.note` restates the F11 caveat (s_track is display-only synthesis, the loop is
not circuit geometry) and E-16 (scrubbing reads stored frames; nothing is
re-simulated).

### app/pages/1_Explainability.py — picking the lap on the race

The page keeps the proposal's hierarchy — reward decomposition primary, alternatives
secondary, SHAP exploratory and collapsed (the F09 surrogate honesty, restated in the
expander's note). What F25 adds is lap selection on the race itself, and the dots that
draw it are where the review caught the fourth defect:

```python
dots = pd.DataFrame([
    {"lap": lap, "frame_lap": lap + 1,
     "position": position_at.get(lap + 1, last_position),
     "pit": by_lap[lap]["action"]["pit"] > 0}
    for lap in laps
])
```

Cards count laps from 0 and frames from 1 — the exact join F23's RewardPanel fell into,
the seam a unit test cannot see. The first version applied the `+1` to the y lookup and
not to x, so every dot drew one lap left of the position it claimed. The fix keeps two
columns: `frame_lap` (where the dot draws) and `lap` (what a click selects, the card's
own key), and a card past the final frame parks at the last known position instead of
vanishing. The slider stays as the accessible path and the fallback when nothing is
picked.

### The tests, and what only looking found

`test_theme_tokens.py` pins the hexes to the sheets, the ramp's luminance monotonicity,
the eleven-team structure and the seat convention. `test_story.py` pins the template's
obligations, including the negative ones (no invented events, no rival stops).
`test_trackmap.py` pins the geometry a render test cannot see. `test_pages_render.py`
runs all three pages under AppTest with the client stubbed and reaches into the
vega-lite protos for the moments strip, the track map and the gauge.

And still, the screenshot pass (the F23 ledger row, now an explicit acceptance step in
the plan) caught three defects outside every test's reach: Streamlit's red widget theme
below CSS, `make app` dying on the missing `PYTHONPATH` (Streamlit puts the script's
directory on `sys.path`, not the repo root — AppTest hides this by injecting the root
itself, the same hole F24 patched in the API Dockerfile), and the soft compound wearing
the reserved alert hex. The review added the dot join. Four defects, four different
reasons a green suite said nothing about them.

## How it connects

```
configs/, models/, senna/          api/ (FastAPI)          app/ (Streamlit, F25)
  frozen chain — untouched   -->   /simulations      <--   client.py (HTTP, F-27)
                                   /runs/{id}/frames -->   story.py --> headline, moments
                                   /runs/{id}/decisions->  pages/1 (cards, lap pick)
                                                           trackmap.py --> pages/2 (loop)
                                                           theme.py + .streamlit/config.toml
                                                             (tokens over everything drawn)
```

Frames and decision cards flow in; nothing flows back but run requests. Every number on
screen is a served field, and every colour it wears is a token with a role.

## Try it yourself

1. **Change a team hex and predict the catch.** In `theme.py`, change Ferrari's primary
   `#E4243C` to anything else. Before running, write down which tests fail. Run
   `python -m pytest tests/app -q`. You'll know it worked when exactly two go red —
   `test_the_grid_has_eleven_teams_with_senna_first` (the `REFERENCE_TEAMS` equality)
   and `test_the_even_car_of_each_pair_carries_the_primary_hex` — and the track-map
   render test stays green, because it only pins the ego's hex.

2. **Make neutral unreachable, then always-on.** In `2_Playback.py`, set
   `NEUTRAL_FLOOR_MJ` to `10.0`, run `make app`, and play a race. Predict what the glow
   does before you look. You'll know it worked when the canvas never leaves the cold
   neutral state — and when you can explain why the review insisted the floor exist at
   `0.05` rather than `0.0`.

3. **Break the left arc and learn which test carries the load.** In `loop_point`, flip
   the final return's y from `-math.cos(angle) * RADIUS` to `math.cos(angle) * RADIUS`,
   so the left arc starts a full loop-height away from where the bottom straight ended.
   Predict the fate of all three trackmap tests, then run them. You'll know it worked
   when only `test_adjacent_samples_never_jump` fails — and when you can say why
   `test_the_loop_closes` cannot fail while `s % 1.0` exists (it compares two calls
   that take the same code path — an identity, the F14 vacuous-test shape hiding in a
   geometry file). Bonus: work out why flipping the *sin* term instead breaks nothing
   at all — the reflected arc is still continuous and still meets both endpoints, a
   mutation the suite genuinely cannot see (F16's mutation-testing lesson, run against
   geometry).

4. **Add a headline kind.** Write a failing test first: a race whose only event is
   `{"kind": "yellow"}` should produce a headline naming it. Watch it fail with a
   `KeyError`-free silence (the kind is simply ignored), then add `"yellow"` to
   `_EVENT_RANK` below `vsc` and a phrase to `_EVENT_PHRASE`. While you are there,
   check `race_moments` against the same fixture and notice it already passes unknown
   kinds through — then ask what F23's generator-support lesson says about a test you
   write *after* discovering it passes. You'll know it worked when your ranking test
   proves an sc still outranks a yellow.

5. **Run the palette validator yourself.** In the scratchpad, write a script that
   computes WCAG contrast `(L1 + 0.05) / (L2 + 0.05)` for the four accent tokens
   against `GROUND`, using proper relative luminance (channels to [0, 1], then the
   gamma step — note the test's `_luminance` skips gamma, which is fine for the ramp's
   monotonicity check but wrong for contrast), and prints the pairwise luminance gap
   of the eleven team primaries. You'll know it worked when your script flags the same
   near pairs the plan's amendment names — the two blues and silver/white — and you
   can point at the lines of `trackmap.field_rows` that answer them.

## Check yourself

1. Why is SENNA the eleventh team, rather than the ego getting a special colour
   outside the team system?
2. The headline could be one API call to a language model and read better. Defend the
   template.
3. Defend the design: why validate colours computationally at all, and why is the
   teammate hollow rather than given a more distinct hue?
4. `.streamlit/config.toml` repeats four hexes that `theme.py` already owns. Is that a
   DRY violation to refactor away?
5. Ember was on the safety-car ticks and the review removed it. What is the argument,
   and what does it have to do with provenance?

## Ledger update

| Concept | First taught in | One-line definition |
|---|---|---|
| Design tokens (roles, not colours) | F25 | Named colour constants with jobs — team colour answers WHO, the aqua/ember axis answers WHAT the energy is doing, `DANGER` stays reserved for limit breach — and one hex never holds two roles in a view, because a token with two meanings has no sourced provenance (the ember-off-the-SC-ticks review fix). |
| Computational palette validation and secondary encoding | F25 | Contrast, luminance monotonicity and CVD separation are computed, not eyeballed; where a palette carries known near pairs (the two blues, silver/white) identity is never colour alone — a car number rides every dot and row, teammates draw hollow, the ego wears the aqua ring. |
| Template assembly for prose (5.8.3 applied) | F25 | The race headline is slot-filling over stored frames — same input, same sentence, every clause traceable to a field, and a clean race gets no event clause — because generated prose could claim things the data does not contain. |
| Piecewise parametric curve by perimeter distance | F25 | `loop_point(s)` converts a lap fraction to a distance and subtracts each segment's length until the remainder falls inside one; joins, the `s % 1` wrap and sample continuity are pinned as geometry tests, and the closure test is an identity the wrap makes unfailable. |
| Streamlit's theme layer vs CSS injection | F25 | Widget primitives (buttons, radios, sliders) are painted from `.streamlit/config.toml`'s theme below the reach of injected CSS — without it every widget arrives in stock red — so the sourced petrol hexes are stated in both rendering paths, with the duplication explained where it lives. |
| Reading the vega-lite proto under AppTest | F25 | AppTest has no chart accessor, but each chart's proto carries its spec plus inlined Arrow datasets, so tests decode what the reader's chart actually draws — and pin gradient stops in the *spec*, because a matching hex in some dataset made the first gauge assertion vacuously true. |

---

## Answers

1. The grid is 22 cars in 11 teams and the sheets supply exactly ten constructor pairs,
   so an eleventh team is needed either way; making it SENNA keeps the
   two-seats-per-team invariant exact, invents no constructor, and gives the ego the
   aqua harvest identity — the interface's own resting accent — so the agent is
   findable in every view without a special-case marker. `test_car_zero_is_sennas_first_seat`
   pins it.

2. The interface's credibility rests on every on-screen statement being a projection of
   served data, which is 5.8.3's rule for decision cards applied to prose: same frames,
   same sentence, every clause traceable to a field. A generative model would trade
   that traceability for fluency and could assert things the frames do not contain —
   in a dissertation about interpretability, the one defect the project cannot survive.

3. Eyes adapt, projectors and video compression do not, and F23 already shipped a
   2.79:1 disclaimer nobody could read — so contrast, luminance monotonicity and CVD
   separation are computed, where a failure is a number, not an opinion. The teammate
   stays on the sheet's lifted hex rather than a new hue because the sheet is the
   sourced provenance and inventing hues forks it; shape (hollow versus filled) plus
   the car number on every dot carries identity through every deficiency and every
   bad screen, which no amount of hue tuning can promise.

4. No. They are two rendering paths: injected CSS styles the HTML, but Streamlit
   paints widget primitives from its own theme layer, which is why every button
   arrived red until `config.toml` existed. Collapsing them is not possible from
   inside the app; the honest move is stating the tokens in both places with a comment
   saying why, and the token tests pin the Python side.

5. Ember's provenance comment says "sourced — deployment accent, per the gradient
   sheet". Put it on a safety-car tick and the token means two things, so that comment
   is false for half its uses and an examiner asking "what does ember mean here?" gets
   two answers. Track status wears coast, only the red flag saturates (`DANGER`), and
   the strip's aqua is reserved for the agent's own stops — one token, one role.
