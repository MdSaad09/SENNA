# The demo — 90-second cut and the nine-minute tour

Choreographed against the F25 Streamlit interface and the retrained (post-F24)
agent, and verified against a live run on 19 Aug 2026: every on-screen string
quoted below was read off the running system, not predicted. The previous version
of this file choreographed the React dashboard the scoped build removed; git
history holds it (`docs: close out F25` and earlier). The nine-minute narration
that pairs with these beats is the published script artifact ("SENNA Nine-Minute
Script"); the deck is its sibling. This file is the *hands* — what to click and
what will appear.

Setup, once, before any recording:

    make up            # postgres, api, streamlit — or: make api & make app with .env sourced
    open http://localhost:8501

There is no cache and no warm step on this branch: every race runs inside its
request, measured at ~19 s. That is a feature on camera — the spinner line
("Racing — the agent decides every lap, so this takes a moment") is true, and the
wait is the simulation actually happening. Run the demo race once before
recording anyway, to confirm the stack is healthy and the model version in
`/health` is `senna-ppo-4b557848ff25-C-04177920` — cards are per-model (E-15),
and a stale API serves a warning instead of explanations.

## The demo pick

**Bahrain · start P8 · seed 55 · conditions dry · era 2026 · test band** (the
sidebar's defaults except circuit and seed). Verified result, deterministic for
this seed:

- Headline: **"P8 → P3 · three stops · through a lap-16 safety car"**
- Stints: MEDIUM 1–6, then SOFT at laps 7, 23 and 55
- Moments strip, in order: VSC 6 · PIT 7 · SC 16 · VSC 22 · PIT 23 · VSC 26 · VSC 39 · PIT 55
- Position arc: P8 falls as far as P21 right after the first stop, is P2 by lap
  20 out of the safety-car restart, finishes P3

This race was picked because it performs the two headline post-repair skills on
its own. Both early stops are decided on virtual-safety-car laps — the VSC tick
and the PIT tick sit side by side on the moments strip, twice — which is the M5
skill that was zero calls across 300 windows two evaluations ago. And the lap-55
stop is the M9 story: the second soft set is 32 laps old, cliff age, and the
agent banks a precautionary stop (and switches to defend) instead of running the
cliff. The pre-repair agent would have run it to the flag; 37 times in a hundred
races the tyre went first.

**The alternate race, same seed:** switch Conditions to *mixed* and rerun.
Headline: **"P8 → P2 · two stops · through lap-42 weather"** — a damp spell from
lap 42 to 51 survived on slicks, briefly P1 at lap 51. Use it if a weather beat
is wanted; note that *mixed* and *wet risk* produce the identical race by
design (two weather modes, not three — the limitation is documented, and this
demonstrates it honestly if anyone asks).

## The 90-second cut

| Time | Do | Say (one line) | It proves |
|---|---|---|---|
| 0:00 | Race page, config already set; press **Run race** | "This is a live simulator, not a video — twenty-two cars, the agent deciding every lap. It takes eighteen seconds because the race is actually running." | Real work, honestly waited for |
| 0:20 | The result lands: point at the headline, then the moments strip | "P8 to P3, three stops, through a safety car — and read the strip: VSC, pit. VSC, pit. The agent that once never reacted to a virtual safety car now boxes on the VSC lap, twice." | The repaired agent's reactive skill |
| 0:50 | Explainability page; click the **lap-22 aqua dot** on the trace | "A 52-percent pit call — genuinely marginal — and the card says why: tyre age pushed it over, and it flips if the set were about 13 laps younger. That flip line is computed on the real network, not the surrogate." | Explainability with stated honesty |
| 1:15 | Open the SHAP expander; point at the badge | "The SHAP panel is last and collapsed on purpose — it explains a surrogate that agrees with the policy 98.3 percent of the time, and that number is printed right here, not in an appendix." | The measured approximation |

## The nine-minute tour

Beats keyed to the published nine-minute script (140 wpm; say-lines live there).
Wall-clock targets in brackets. Slides 1–8 of the deck run before the interface
appears; the live segment replaces slides 9–10's static content if you demo
rather than present.

**[0:00–4:45] Slides 1–8.** Problem, rulebook, pipeline, compliance, reward,
training, explainability — no interface yet. During slide 7, optionally start
the demo race in a background tab so it is finished when you arrive (the run
lands in that tab's session; do the switch by tab, not by re-navigating).

**[4:45] Race page — the result panel.** Config: Bahrain, P8, seed 55, dry.
If racing live, press Run during the previous sentence; the spinner covers the
transition. When it lands: headline first ("P8 → P3 · three stops · through a
lap-16 safety car" — composed by template assembly over stored frames, never
generated), then the moments strip (VSC-then-PIT twice), then the race story
chart — the aqua line falling to P21 and cutting through the grey field to P2 by
lap 20. The pit table has four columns and no service time, because the
simulator never serves one; say so if asked, it is a pinned test.

**[5:20] Explainability page.** The run follows in the session — no id to type.
Three beats on one screen, in the page's own order:

1. Click the **lap-22 dot** (aqua = a pit call). The card reads *"Lap 22 — pit
   for Soft, run balanced (probability 0.52)"*. Marginal on purpose — stay-out
   still held 20%. Top driver: tyre age. The reward decomposition above it is a
   recording; the alternatives table beside it is the network's own output, with
   Intermediate and Wet marked **masked** — it did not reject them, it was never
   offered them.
2. Read the flip lines aloud — *"flips if tyre age crossed 0.32 (about 13 laps
   old)"* and *"flips if last-lap harvest crossed 0.60 (about 5.1 MJ)"* —
   computed on the true network under a rebuilt mask, walking outward from the
   recorded value.
3. Then the boundary moving in real time: pick **lap 53** (*stay out, 0.57 — "the
   call held despite tyre age pushing against it"*), then **lap 54** (*pit for
   Soft, defend, 0.71* — tyre age +3.4, grip fading, a car closing behind).
   One lap apart, opposite calls, same physics reading. Open the SHAP expander
   last: the 98.32 / 97.72 badge is on the caption line.

**[6:15–7:45] Slides 11–13.** Results, the conditional, robustness — the numbers
the race just illustrated.

**[7:45] Playback page.** Press **Play**: 57 laps at 0.35 s per lap is about
twenty seconds of the whole race circulating — 22 numbered dots on the loop, the
ego ringed in aqua, the battery gauge draining and refilling inside its 4 MJ
window. Then scrub deliberately: **lap 2** (harvesting — the page glows aqua,
8.5 MJ in) against **lap 6** (deploying under the VSC — ember glow, battery down
at 1.70 MJ). **Lap 16** shows the SC banner and the field bunched. The on-screen
note says the loop is not circuit geometry and playback never re-simulates;
point at it — the honesty is part of the demo.

**[8:05–9:00] Slides 14–15.** Reproducibility, close, disclaimer.

## Recording checklist

- `make up` green, `/health` returns the post-repair model version, and one
  throwaway race completed before recording.
- **Do not hard-refresh the browser mid-take** — `run_id` lives in Streamlit's
  session state; a refresh returns every page to "No race yet". Navigate by the
  sidebar page links only.
- The lap picker: a click on a dot selects it and shows *"lap N picked on the
  chart"*; the slider underneath is the fallback. To move between laps 53 and 54
  cleanly, use the slider — clearing a chart selection on camera is fiddly.
- Playback autoplay pauses itself if you touch the slider; that is by design
  (scrubbing wins). Press Play again to resume.
- 1080p window, sidebar open on the Race page, collapsed elsewhere if space is
  tight. Dark browser chrome sits better against the petrol ground.
- Every number spoken on camera comes from the committed post-repair results
  (`docs/results/F14-evaluation.md`) or from this file's verified run; do not
  improvise better ones.
- The seed-55 race is deterministic for this model and physics. After any
  retrain or refit, **re-verify every quoted string in this file** — headline,
  moments, card probabilities, flip thresholds — before pressing record; the
  choreography is model-specific by construction (E-15).
- End card, verbatim: "SENNA is an unofficial project and is not associated in
  any way with the Formula 1 companies, the FIA or any team."
