# F15 — Demo, docs, reproducibility pack and the freeze

## What we built and why

F15 adds no capability. Every feature before it built something the system could not do
before; this one makes the system presentable, provable and frozen. It is still real
engineering, because the three things it delivers are all easy to fake and F15 refuses
to fake any of them.

The pit wall version: race day. The car is built and the numbers are in. What is left is
the part teams rehearse — the garage tour for the sponsors runs on the real car, not a
mock-up; the FIA scrutineer gets a sealed spec sheet they can check against the car
itself; and at the end of the season the whole package is homologated so that "which car
scored those points" has exactly one answer.

The software version, in the same order. The 5.13 demo storyboard becomes a set of URLs
against real, pre-warmed simulation runs, with a Playwright check that prices its first
beat at 15 seconds. The served counterfactual view finally drops its `pending-F14`
caveat, because the 2024 model's SHAP surrogate now exists — the last unexplained thing
in the system gets its explainer. And the A-09 reproducibility pack closes: `make eval`
means what the spec's enumeration says, `make verify` proves from a clean clone that the
committed results chapter regenerates byte-for-byte and that the provenance chain holds,
a pg_dump snapshot with a committed manifest freezes the data, and a ±50% sensitivity
run prices the one physics borrow M2 had been carrying as an assumption.

One thing went wrong during the build, and it is the best advert the feature has: the
new byte-for-byte report guard failed on its very first CI-shaped run, because the
committed chapter had been hand-assembled a blank line off what `report.py` actually
emits. The guard's first catch was its own authors. That is what a good guard's first
week should look like.

## New ideas in this feature

**The engineered demo (5.13, E-15).** A demo you record by hoping the app behaves is a
demo that fails on the day. F15's demo is a storyboard compiled into URLs: every beat is
a deep link into a run that already exists. The trick is E-15, the versioned result
cache (F10 ledger: *Versioned cache keys*): a simulation is cached under model version +
config hash + request body + seed, so `make demo-warm` POSTs the exact requests the demo
links will POST and waits for them to complete. When the link opens later, it is a cache
hit, and here is the honest part — it is not a canned recording, because the warmed run
*is* the run. Same model, same config hash, same seed, same key. The warm changes when
the simulation happens, never what it is.

In the viva: "The demo is pre-warmed because a cold deep link blocks until the whole
simulation completes, which busts the 15-second first beat. This is not staging: E-15
caches by model version, config hash and request body, so the warmed run is byte-for-
byte the run the link resolves to — I moved the compute, not the content."

**Deep-link params that stay off the cache key (E-15 + E-16).** The demo URL carries
`?lap=18&speed=30`, and neither value may enter the POST body — the body is the cache
key, and forking it would orphan every pre-warmed run. Instead they ride the WebSocket
after connect, as the same `client:seek` and `client:speed` messages the player already
speaks. That is legal because of E-16, the playback contract (F10 ledger: *WebSocket
playback clock*): the server replays persisted frames on its own clock, so a seek is a
read, never a re-simulation. The mental model: the URL has two halves. Everything that
defines *which race* goes in the request body and therefore the key; everything that
defines *how you watch it* goes over the socket and touches nothing cached.

**Deployable means explainable.** `models/era2024` sat committed in the repo for days
while the served counterfactual view still said `pending-F14`. Not a bug — a refusal.
The serving registry treats a triplet without its SHAP surrogate as not baked, because
the E-15 pairing check (F09 ledger: *Surrogate distillation and the fidelity gate*)
would otherwise fail mid-job, deep inside a worker, after a run had already been
promised to a user. Weights alone are not a servable model in this system; weights plus
their explainer are. The flip that cleared the caveat was therefore not a config edit
but a real run: `make explain TRIPLET=models/era2024 ERA=2024`.

**The freeze chain: consistency, not recomputation.** The plan's first idea for `make
verify` was "recompute the config fingerprints from the yaml files on disk and compare
against the committed envelopes". That check would fail today, and it *should*: the
suite envelopes copied their `config_hash` from the headline manifest at eval time, and
the configs have been legitimately comment-edited since training. The manifest hash is a
training-time record, not a claim about today's bytes. So the guard checks what can
honestly be checked: every suite row names the exact model and hash the repo serves
(internal consistency), and the one file that is genuinely frozen — `configs/seeds.yaml`,
untouched since F07 — gets the one live recompute. Drift there is a freeze violation and
can never be a comment edit.

**A guard proven on its authors.** `test_report_reproduces_committed_doc` regenerates
the chapter from the committed store and diffs it byte-for-byte against the committed
markdown, in CI. Byte determinism is F02 (ledger: *Byte-deterministic artifacts*) and
the pure-function report is F14 (*Committed run store*); the new idea is closing the
loop in CI and letting it bite. It bit immediately: the review found the committed
chapter differed from its regeneration because a paragraph had been hand-placed during
this very ship. A guard that catches strangers is nice. A guard that catches you is
working.

**The split artifact: gitignored dump, committed manifest (A-09).** The frozen data
snapshot is two halves. The `pg_dump -Fc` archive is hundreds of megabytes and rides the
v1.0.0 GitHub release, gitignored. What gets committed is `data/snapshot/MANIFEST.md`:
the file name, sha256, size and exact per-table row counts. An examiner downloads the
asset, runs `shasum -a 256`, and has verified the frozen data without connecting to
anything. And restore routes through `require_disposable` (F14 ledger: *Enforced
convention*), because `pg_restore --clean` drops every table first — restore is the
db-wipe incident with a new spelling, and the guard fires before any subprocess exists.

**Pricing a borrow against the metric's own spread.** The 2024 counterfactual scenario
borrows four fitted energy-mode coefficients from the 2026 physics, because no 2024 fit
of them exists. Since F14 that borrow was a stated assumption; F15 prices it. Re-roll
the ten M2 races with the borrowed block at ×1.5 and at ×0.5 — a huge perturbation — and
compare the movement against M2's own uncertainty. The yardstick is the point: a
sensitivity number means nothing in isolation, but "the borrow moves M2 by less than
M2's own confidence interval is wide" is a complete argument that the borrow is a
documented coarseness rather than a load-bearing unknown.

Already taught, one line each: config overlays are F08 (*Config overlays and the
write-ahead run ledger*), the paired-arm overlay discipline is F14 (*Overlay sensitivity
as a paired experiment*), the era fine-tune itself is F14 (*Era-matched fine-tune*), the
client frame buffer the seek lands in is F13 (*The E-16 client buffer*), and the
StrictMode one-POST ref guard on the deep link is F13 (*StrictMode double effects*).

## The code, guided

### `scripts/warm_demo.sh` and `docs/demo/script.md` — the storyboard as URLs

The script is forty lines of curl: POST the demo simulation (Bahrain, seed 42, grid 8)
and the counterfactual pair (2024 round 1, VER), poll both until `status: complete`,
print the links. The circuit pick is stylised and documented in all three places that
must agree — script, Playwright spec, demo doc — because a mismatch means the check
measures a cold link. Bahrain won on boring grounds: committed ribbon, native 2024 fits,
ASCII slug (`são_paulo_grand_prix` is a URL-encoding hazard), and the real 2024 winner
pitted on lap 18, which hands the storyboard its pit-call beat. The canonical URL:

    http://localhost:5173/live?circuit=bahrain_grand_prix&seed=42&lap=18&speed=30&year=2024&round=1&driver=VER

The query string deliberately carries the union of every view's params. Nav clicks
preserve it, each view reads what it needs and ignores the rest, so "one click to the
Counterfactual view" lands configured. `docs/demo/script.md` holds the 90-second beat
table, the ten-minute tour (authored fresh with 5.13's four required edits), and the
recording checklist — including the bloom quality toggle for Intel renderer strings and
the E-18 context-loss rule: reload and re-take, don't debug on camera.

### `frontend/src/views/live/LiveSimulationView.tsx` — params in, POST body untouched

The view already knew how to turn `?circuit&seed` into a POST and write `?run=` back
(F13). F15 adds the two watch-time params, and the placement is the whole point:

```tsx
    // ?lap= and ?speed= ride the socket, never the POST body: the E-15 cache key is
    // circuit + grid + seed alone, so a pre-warmed demo run stays a hit whatever
    // lap or speed the link opens at
    const query = new URLSearchParams(window.location.search);
    const startLap = positiveIntParam(query, "lap");
    const startSpeed = speedParam(query);
    if (startSpeed !== null) useLiveStore.getState().setSpeed(startSpeed);
    const socket = new LiveSocket(runId, {
      ...(startLap !== null ? { startLap } : {}),
      ...(startSpeed !== null ? { speed: startSpeed } : {}),
    });
```

`speedParam` only honours values from the 5.9.3 `PLAYBACK_SPEEDS` set — the server
would reject anything else, and silently dropping a bad value beats surfacing an error
over a shareable link. The store's speed is set *before* the socket exists, so the
reconnect resync (next file) restores the deep link's tempo without the opts. The rest
of the diff in this file is the SOC bar's data plumbing: `useEnergyProfile` supplies
`usable_soc_mj`, so the bar's ceiling is served, never a client-side 4 MJ literal.

### `frontend/src/api/liveSocket.ts` — handleOpen, line by line

This is the seam where the deep link and the reconnect logic could fight, so it earns
line-by-line treatment:

```ts
    const { frames, speed, playing } = useLiveStore.getState();
    const head = frames.length === 0 ? 0 : frames[frames.length - 1].lap;
    if (head === 0) {
      // an empty buffer has nothing to resync, so the deep link speaks: a mid-race
      // entry rides the same client:seek the resync uses (E-16). Once frames land,
      // the buffer owns every later open and these opts never speak again.
      if (this.startLap !== undefined) this.send({ type: "client:seek", lap: this.startLap });
      if (this.startSpeed !== undefined) this.send({ type: "client:speed", speed: this.startSpeed });
      return;
    }
    // resync in one path: jump past the buffer, restore the tempo, re-pause if the
    // viewer had paused (the replayed connection always starts unpaused at 1x)
    this.send({ type: "client:seek", lap: head + 1 });
    this.send({ type: "client:speed", speed });
    if (!playing) this.send({ type: "client:pause" });
```

`getState()` reads the store without subscribing — the F11 transient door, because a
socket callback must never trigger a render. `head` is the last buffered lap, and it
decides which of two situations this open is. Zero means a fresh mount: nothing to
resync, so the constructor's deep-link opts get their one chance to speak, seek first
(position) then speed (tempo), and the early `return` keeps the resync path from
overwriting them. Non-zero means a reconnect after a drop: the buffer is now the
authority, so seek to `head + 1` (the F13 idempotent `insertFrame` absorbs the one
duplicate this races into), restore the store's current speed — which is the deep link's
speed if the user never touched it, because the view seeded the store first — and
re-pause if the viewer had paused, since a replayed connection always starts unpaused at
1x. The opts never speak again after frames land, and that is correct: if you scrubbed
to lap 40 and the network blipped, resuming at the URL's lap 18 would throw away where
you actually are.

### `frontend/e2e/demo.spec.ts` — the beat as a test

Block level: one Playwright test, `test.setTimeout(15_000)` with the budget sourced to
5.13's first beat, asserts the canvas and then the scrub slider are visible. The slider
is the tell — it only mounts once the first frame is buffered, which is the closest
DOM-visible proxy for "cars on track" (the cars render inside WebGL, invisible to
selectors). It runs through `make demo-check` against a warmed local stack, never in CI,
and it doubles as the harness that closes the INDEX open item on the near-empty Chrome
canvas: the old symptom was a deep link at 1x, where only lap 1 exists for ninety
seconds and 22 cars sit stacked at the start line, viewed from over a kilometre away.
The seek makes the demo link open mid-race; the spec proves it in a real browser.

### `senna/serve/loader.py::era_model_version` — the refusal that was the caveat

```python
    for name in config.load("serving", configs_dir)["baked_models"]:
        manifest = root / name / "manifest.json"
        if not manifest.exists():
            continue
        payload = json.loads(manifest.read_text())
        if str(payload.get("era", "2026")) != str(era):
            continue
        version = payload["model_version"]
        if not (root / "explain" / version).is_dir():
            raise UnknownModelVersionError(
                f"{version} is baked for era {era} but has no surrogate under "
                f"models/explain/{version} — run make explain against that triplet "
                "before serving it (E-15)"
            )
        return version
```

Walk it. The loop reads `serving.yaml`'s `baked_models` list, because the registry
answers from the artifacts an image actually carries, never a database row that could
drift (F-26). A listed-but-absent directory is skipped, not fatal — a clone that never
ran the fine-tune must still serve the headline. The era comes from the manifest with a
`"2026"` default, so pre-F14 manifests that never heard of eras stay valid. Then the
line that held the caveat for days: a baked triplet whose surrogate directory does not
exist raises rather than returns, because the counterfactual route stamps this version
into every run, and a worker that later fails the E-15 surrogate-pairing check mid-job
turns a graceful fallback into a broken endpoint. The route catches this exception and
degrades: `era_matched = "pending-F14"`, headline serves both legs, and the dashboard
prints the caveat. So the caveat was never a string someone had to remember to delete —
it was the absence of an artifact, and producing the artifact deleted it.

The run that produced it: `make explain TRIPLET=models/era2024 ERA=2024` distilled the
era-matched policy into its own surrogate pair — pit head top-1 agreement 0.986, mode
head 0.963, both clear of the 0.90 fidelity gate — and carded 13,760 decisions across
230 races (23 native-fit circuits, 10 validation seeds each). `api/routes/agents.py` now
loops over `baked_triplets` instead of reading one manifest, so `GET /agents` lists both
models, each badge read from that model's own `fidelity.json`. Nothing in Chapter 7
moved: `m2_races.json`'s envelope had named the era2024 model since F14, because the
offline M2 already ran era-matched. The flip made the *served demo* honest, not the
numbers.

### `senna/explain/run.py` — threading the era, and the Canada trap

The F09 pipeline was hard-pinned to `_ERA = "2026"`. Running it against the 2024
triplet as-was would have distilled the 2024 model on 2026 physics — exactly F-24, the
era confound (F14 ledger), reappearing inside the explainability layer. The fix is one
choke point and one narrowing:

```python
def explain_env(circuit: str, era: str = _ERA, *, rival_band: str = "train") -> F1RaceEnv:
    """Every spaces, distillation and card env goes through here so the era can never
    fork between them — the F-24 trap is a surrogate distilled on physics the policy
    never raced."""
    return F1RaceEnv(circuit, era, rival_band=rival_band)
```

One constructor for every env the pipeline builds. Before this, three call sites built
envs independently, and an era that reached two of the three would produce a surrogate
whose fidelity badge was measured on the wrong physics — a lie with a confidence score.

```python
def era_circuits(banks, era: str) -> list[str]:
    circuits = sorted(banks.stage_c_validation)
    if era == _ERA:
        return circuits
    from senna.eval.traces import require_native_era_fits

    native = set(config.load("eval")["era_finetune"]["circuits"])
    narrowed = sorted(set(circuits) & native)
    for circuit in narrowed:
        require_native_era_fits(circuit, era)
    return narrowed
```

Line by line. 2026 keeps the whole Stage C validation bank, because its scenarios come
from the transform chain and every circuit is native by construction. Any other era
intersects the bank with the fine-tune's native-fit list from `configs/eval.yaml` — the
same 23 circuits M2 uses — and then re-checks each survivor against `require_native_era_fits`
anyway, belt and braces, because the list is config and config can rot. The trap this
closes is quiet: the Stage C bank includes `canadian_grand_prix`, which has no native
2024 fits, and `build_scenario` does not error on that — it silently falls back to the
2026 constants under a 2024 label. Without the narrowing, the 2024 run would have carded
Canada on borrowed physics and nothing would have failed. `load_headline` routes even
its throwaway spaces-only env through `era_circuits(banks, era)[0]`, because the bank's
alphabetically first circuit is exactly the kind of place the fallback hides.

Block level for the rest: `--era` is a CLI choice, and `main` refuses a mismatch between
the flag and the triplet manifest's own era field, so you cannot explain a model on
physics it never raced by typo. The Makefile threads `TRIPLET=`/`ERA=` through.

### The storyboard gaps: SocBar, the badge, the tooltip, the nav

Block level, four small edits that existed only because 5.13 needed them on screen.
`SocBar.tsx` renders the playhead frame's `soc_mj` against the *served* `usable_soc_mj`
— a client-side 4 MJ literal would lie about any run raced under a different store, and
client-side physics is banned outright (5.1 invariant 2). `DecisionCardPanel.tsx` moves
the surrogate agreement figures from the monospace footer line into a visually distinct
badge; same numbers, same honesty statement verbatim (A-03), just no longer hiding.
`SocPanel.tsx`'s tooltip joins the served `mode` to the SOC figure, because the demo's
"banked energy before an attack" hover needs the mode to say "banked". And `App.tsx`
passes `{ pathname, search }` to every `NavLink`, which is the entire mechanism behind
"one click to the Counterfactual view". The footer also changes to the canonical F-29
disclaimer wording, now identical in the app, the README and the video end card.

### `Makefile` — the truth pass

Block level. The old `eval` target rescored one checkpoint; the A-09 pack promises that
`make eval` runs the evaluation suite, and a name that quietly means something narrower
hands an examiner the wrong artifact. So the rescore became `rescore` and `eval: suite`
is now a two-word alias for the M1–M11 battery. New targets: `test` mirrors CI's exact
pytest spelling (the F03–F06 drift lesson), `snapshot`/`restore`, `verify`, and the
`demo-warm`/`demo-check` pair. The stale "each stub becomes real" header is now a
dependency-ordered map of the pipeline. `models/runs.json` — cited since F08 as the
ablation table's machine-readable twin, gitignored the whole time — is committed.

### `tests/eval/test_freeze.py` — the chain

The docstring states the design and the second test enforces it:

```python
    headline = json.loads(HEADLINE_MANIFEST.read_text())
    era2024 = json.loads(ERA2024_MANIFEST.read_text())
    seeds_now = config.fingerprint(["seeds"])

    suite_files = sorted(path for path in STORE.glob("*.json")
                         if path.stem not in _OWN_HASH_FILES)
    assert suite_files, "an empty store would make every check below vacuous"
    for path in suite_files:
        envelope = json.loads(path.read_text())["envelope"]
        assert envelope["config_hash"] == headline["fingerprint"], path.name
        assert envelope["model_versions"]["headline"] == headline["model_version"], path.name
        assert envelope["seeds_fingerprint"] == seeds_now, path.name
```

Line by line. Both manifests load from the real committed artifacts, not fixtures — this
test is *about* the working tree. `seeds_now` is the one live recompute, taken once. The
glob excludes the two overlay studies, which chain differently (below). The bare
`assert suite_files` is the F14 canary habit: a discovery loop that finds nothing passes
vacuously, so the discovery is asserted before the loop. Then three claims per metric
file: the results carry the fingerprint the headline manifest recorded at training time
(copied, remember, so this is consistency, not recomputation), they name the model
version the repo actually serves, and their seeds fingerprint matches the live hash of
the frozen `seeds.yaml`.

The overlay studies get the opposite regime:

```python
    harvest = json.loads((STORE / "harvest_sensitivity.json").read_text())["envelope"]
    assert harvest["config_hash"] == config.fingerprint(["circuits"])
    ...
    m2s = json.loads((STORE / "m2_sensitivity.json").read_text())["envelope"]
    assert m2s["config_hash"] == config.fingerprint(M2_CONFIG_FILES)
```

These two hashed their own input files at run time, and they ran during F14/F15 — after
any comment edits — so for them the live recompute is the honest check: their envelopes
claim the current bytes of the files they read. Two regimes, one rule underneath: verify
what an envelope actually recorded, at the time it recorded it. The `m2_sensitivity` leg
was missing until the review, which is worth remembering — the branch's newest artifact
was the one the chain never covered, because the chain was written before the artifact
existed.

And the byte check above it is three lines: `build_report` from the committed store,
figures rendered to a scratch directory (the page's bytes must not depend on where PNGs
landed, or CI could only pass by overwriting the committed figures), then
`page.encode() == COMMITTED_DOC.read_bytes()`. Its first catch was this ship: the
committed chapter carried an overlay-provenance note in a hand-chosen position that
`report.py` did not emit there. The fix regenerated the chapter from the code path and
moved the note into a `_overlay_note()` the renderer places itself, so the sentence can
never drift from the sections it introduces again.

### `senna/data/snapshot.py` — the dump and the guarded restore

Two functions carry the design. Restore first:

```python
def restore(dump_path, url: str) -> None:
    require_disposable(url)
    subprocess.run(
        ["pg_restore", "--clean", "--if-exists", "--no-owner", "--no-privileges",
         f"--dbname={_libpq_url(url)}", str(dump_path)],
        check=True,
    )
```

`require_disposable` on the first line, before any subprocess exists, because `--clean`
drops every table it is about to recreate — the F14 wipe incident wearing pg_restore's
clothes. Dumping takes no guard: reads destroy nothing, and a guard on the safe
direction teaches people to override guards. `_libpq_url` strips `+asyncpg`, since
pg_dump and pg_restore speak libpq URLs, not SQLAlchemy driver strings. In `main`, the
counts are taken *before* the dump on purpose: the manifest vouches for the archive, and
if anything writes between the two steps, counting first biases the race toward
under-claiming — the manifest can only ever promise rows the archive definitely holds.

One operational note that will matter at the freeze: `make verify` link-checks
`data/snapshot/MANIFEST.md`, and that file only exists after `make snapshot` runs
against your ingested store. Until that runs and the manifest is committed (freeze
runbook step 2, a `docs:` commit), the verify target reports the page missing — so
sequence the snapshot before you expect CI's verify job to be green.

### `senna/eval/coefficients.py` — pricing the borrow

The overlay builder is the harvest study's mould with a different mutation:

```python
    for label, factor in (("up", 1 + perturbation), ("down", 1 - perturbation)):
        dest = Path(tmp_root) / label
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(Path(base_configs_dir), dest)

        physics_path = dest / "physics_2026.yaml"
        physics = yaml.safe_load(physics_path.read_text())
        for key in BORROWED:
            physics["fitted"][key] = float(physics["fitted"][key]) * factor
        physics_path.write_text(yaml.safe_dump(physics, sort_keys=False))
        overlays[label] = dest
```

Line by line. Both arms are named tuples of label and factor, so the perturbation from
`configs/eval.yaml` (the key that carried "DEFERRED TO F15, no reader yet" in its own
comment for two weeks) appears exactly once. Each arm gets its own full copy of
`configs/` in scratch, keyed by label — the F14 review's both-arms-overlay discipline,
inherited whole. The file mutated is `physics_2026.yaml`, which looks wrong for a 2024
study until you remember what is being priced: `scenario.py` reads the four `BORROWED`
coefficients out of the 2026 fitted block *for both eras*, because no 2024 fit exists.
`BORROWED` names exactly the four borrowed keys and deliberately excludes
`dirty_air_threshold_s`, which lives in the same block but is a sourced 5.5.3 constant,
not part of the fit — perturbing it would price a different assumption. Everything else
in the tree is byte-identical, so a diff of an overlay is the complete statement of its
arm.

The writer refuses unpaired arms before a byte lands (`dropped["up"] != dropped["down"]`
raises — the harvest study's discipline again), and the envelope decision is the subtle
line:

```python
        config_hash=config.fingerprint(M2_CONFIG_FILES),
```

The envelope hashes the four *base* files the roll reads — the perturbed physics, the
2024 era constants, the circuit bank, the race list — never the overlays, which could
not share one hash between two arms anyway. The perturbation itself sits in the payload.
The run refuses to fall back to the headline when `models/era2024` is absent, because
the borrow exists in the 2024 scenario: perturbing coefficients the 2026 model actually
trained on is a different experiment wearing the same command line.

The result, and how to read it. Baseline M2 (F14): mean −0.60 places over the ten
races, descriptive bootstrap interval [−2.98, 1.76]. Arms: ×1.5 gives −0.14, ×0.5 gives
−0.52. Both arms sit well inside a baseline interval that spans four and a half places,
and both stay a wash under the sign test. So a ±50% shove on the borrowed block moves M2
by less than half a place, against a metric whose own ten-race spread is nearly ten
times that. The borrow is a documented coarseness, and the report now prints that
spread, with its own hash, beside M2.

In the viva: "The 2024 scenario borrows the 2026 energy-mode fit because no 2024 fit of
those coefficients exists. I priced the borrow at ±50% in paired overlay arms under the
era-matched model: M2 moved by at most 0.46 places while its own descriptive interval
spans 4.7, so the assumption is documented coarseness, not a load-bearing unknown."

### The provenance loose ends

Block level. `configs/physics_2024.yaml` gains the `# borrowed:` header naming the four
coefficients, where they really come from, and the command that prices them — the file
an examiner opens now tells the whole story. `scenario.py`'s docstring goes from
"pending its own fit (F14 refines it)" to "F15 keeps and prices". And
`senna/strategy/extract.py` finally does what its docstring had claimed since F06:
`--driver`/`--write` merge an extracted plan into `configs/real_strategies.yaml`, which
re-keys to `season_circuit_driver` because the ten M2 races include two British GPs
(2024 HAM, 2023 NOR) that a circuit-only key cannot hold. `merge_strategy` splices the
yaml by hand so the file's comment header survives — `safe_dump` would silently eat it —
and keeps each stop on one line so the committed record stays readable. M2's harness
keeps its Postgres path; its numbers are frozen, and the yaml is the human-readable
record beside them. `scripts/check_links.py` is fifty lines of relative-link checking,
offline only, wired into `make verify`; a page missing from its own list reports as rot
rather than crashing, so one absent file cannot mask findings in the rest.

## How it connects

```
  5.13 storyboard                       A-09 pack
       |                                    |
  scripts/warm_demo.sh --POST--> api --> worker --> lap_frames   Makefile: eval=suite,
       |                          (E-15 cache: model+hash+body)  verify, snapshot,
  demo URL ?circuit&seed  --------^                              rescore, demo pair
           ?lap&speed  --client:seek/speed--> api/ws.py (E-16)        |
       |                                                              v
  make demo-check (Playwright, 15 s)                    tests/eval/test_freeze.py
                                                        report bytes == committed doc
  serving flip:                                         envelopes name served manifests
  models/era2024 --make explain ERA=2024--> models/explain/<version>
        |                                        |               pg_dump -Fc
  serve/loader.era_model_version  (weights + surrogate, or       data/snapshot/*.dump
        |                          "pending" — never mid-job)    + committed MANIFEST.md
        v                                                        restore -> require_disposable
  /counterfactuals stamps the era model; /agents lists both

  m2 borrow: configs/physics_2026.yaml fitted block --x1.5/x0.5 overlays-->
  ten M2 races, paired --> docs/results/F14/store/m2_sensitivity.json --> make report
```

Inputs are the frozen models, the committed store, the ingested database and the
storyboard. Outputs are URLs that resolve, a chapter that regenerates, a dump that
verifies and a tag that pins all of it. Nothing in F15 touches the env, the reward, the
masks or the training loop — the property suite being frozen is the property suite F05
through F08 built.

## Try it yourself

1. **Run the demo end to end.** `make up`, wait for healthy, then `make demo-warm`
   (it prints dots until both runs complete), open the URL it prints in a fresh Chrome
   tab, then `make demo-check`. You'll know it worked when the tab opens mid-race with
   the SOC bar moving and the Playwright test passes inside its 15-second budget — and
   that pass is also the closing evidence for the INDEX item on the once-empty Chrome
   canvas.

2. **Prove the cache-key discipline.** With the stack warm from exercise 1, edit the
   demo URL's `lap=18` to `lap=30` and open it in a new tab. You'll know it worked when
   the `?run=` written back into the address bar is the *same* run id as before — the
   POST body never changed, so E-15 answered from cache — while playback starts at lap
   30. Then change `seed=42` to `seed=43` and confirm the opposite: a new run id, and a
   long wait, because you just asked for a race nobody warmed.

3. **Trip the byte guard.** Add one blank line to the end of
   `docs/results/F14-evaluation.md` and run
   `.venv/bin/python -m pytest tests/eval/test_freeze.py -q` (the same tests `make
   verify` runs; the full target also link-checks `data/snapshot/MANIFEST.md`, which
   stays red until freeze step 2 writes it). Predict which test fails before you run
   it. You'll know it worked when `test_report_reproduces_committed_doc` goes red on
   the byte comparison — the exact failure the review saw, in miniature — and
   `git checkout docs/results/F14-evaluation.md` turns it green again.

4. **Feel the two chaining regimes.** Edit a comment in `configs/circuits.yaml` and
   rerun the freeze tests: the harvest leg of
   `test_freeze_chain_is_internally_consistent` goes red, because that study's
   envelope claims the current bytes of the file it read. Restore it, then edit a
   comment in `configs/curriculum.yaml` and rerun: green, because the suite rows chain
   to the training-time manifest copy, not to disk. You'll know you've got it when you
   can say which regime `configs/seeds.yaml` falls under, and why it is the odd one
   out. Restore everything after.

5. **Ask the registry.** With the stack up: `curl -s localhost:8000/api/v1/agents | python3 -m json.tool`.
   You'll know it worked when two entries come back, each with its own fidelity pair
   (the era2024 entry reads pit 0.986 / mode 0.963), and the counterfactual view in the
   browser no longer prints the pending caveat. Then point `era_model_version` at an
   empty directory in a Python shell and read the two different refusals it can raise —
   one is "not baked", the other is "baked but unexplainable", and the route only
   degrades gracefully on the version of events the loader promises.

## Check yourself

1. Why does `make demo-warm` exist, and what stops the warmed demo from being a canned
   recording?
2. `?lap=` and `?speed=` ride the WebSocket after connect. Why must they never enter
   the POST body, and which spec rows make the socket path legal?
3. `models/era2024` was committed for days while the served view said `pending-F14`.
   What exactly was missing, and why does the loader refuse rather than serve weights
   without it?
4. Defend this: `make verify` does not recompute the eleven-file config fingerprint
   from the yaml on disk, even though "the configs in the tag are the configs the
   results came from" is exactly what an examiner wants proven. What does it check
   instead, and why is that more honest?
5. The M2 coefficient sensitivity moved the metric to −0.14 and −0.52 against a −0.60
   baseline. What claim does that license, and what would it not license?
6. `dump_snapshot` takes no guard and `restore` does. Why the asymmetry, and why do
   the row counts get taken before the dump rather than after?

### Answers

1. A cold deep link blocks until the whole simulation completes — the WebSocket only
   replays persisted frames (E-16) — so the 15-second first beat is impossible against
   a cold cache. The warm script POSTs the exact requests the demo links resolve to and
   waits for completion. It is not canned because E-15 keys the cache on model version,
   config hash, request body and seed: the link's request hits the identical key, so
   the run the audience watches is the run the warm produced — a real simulation whose
   compute happened earlier, not different content.

2. The POST body *is* the E-15 cache key. Adding lap or speed to it would give every
   watch position its own key, so the pre-warmed run would never be hit again and the
   demo beat would collapse back to a cold simulation. The socket path is legal because
   E-16 makes playback a read over stored frames on the server's clock: `client:seek`
   and `client:speed` change how you watch, never what was simulated, so they belong on
   the channel that owns watching. The split to remember: which race → body and key;
   how you watch it → socket.

3. The surrogate: `models/explain/senna-ppo-db031aead155-C-02211840/` did not exist.
   `era_model_version` refuses weights without their explainer because the
   counterfactual route stamps the returned version into runs; a worker would then fail
   the E-15 surrogate-pairing check mid-job, after accepting the request — a broken
   endpoint instead of a graceful, stated fallback to the headline. In this system a
   servable model is weights plus explainer, and clearing the caveat therefore required
   a real run (`make explain TRIPLET=models/era2024 ERA=2024`: pit 0.986, mode 0.963,
   13,760 cards over 230 races), not a string edit. No dissertation number moved — the
   offline M2 was already era-matched — the flip made the served demo honest.

4. Because the from-disk recompute would fail for a legitimate reason and pass only by
   forbidding legitimate work. The suite envelopes copied `config_hash` from the
   headline manifest at eval time — it is a training-time record — and the configs have
   been comment-edited since, which changes bytes without changing anything the results
   depend on. Recomputing would either go red on honest edits or pressure people to
   never touch a comment again. The honest guard is internal consistency (every
   envelope names the manifest and model version the repo actually serves) plus the one
   live recompute that is valid: `configs/seeds.yaml`, frozen since F07, where any
   drift really is a freeze violation. The overlay studies are the exception that
   proves the rule — they hashed their own inputs at run time, recently, so for them
   the live recompute is the correct check.

5. It licenses: "the borrowed 2026 energy-mode fit is a documented coarseness — a ±50%
   perturbation of it moves M2 by at most 0.46 places, well inside M2's own [−2.98,
   1.76] descriptive spread, and the wash verdict survives both arms". It does not
   license any claim about either era's true physics (the reading string in the payload
   says exactly this), and it does not tighten M2 itself — n is still 10, the sign test
   still does not clear, and 25 snapped stops still ride the baseline. The experiment
   prices an assumption; it proves nothing about the metric's answer.

6. `pg_restore --clean` drops every table before recreating them — it is the F14
   db-wipe with a different binary — so `require_disposable` runs before the subprocess
   exists, and restoring the real store requires the named escape hatch. Dumping only
   reads, and guarding the safe direction teaches operators to override guards. Counts
   come first because the manifest vouches for the archive: if a write lands between
   the two steps, counting first means the manifest can only under-claim rows the
   archive actually holds, never promise rows it does not.

## Ledger update

| Concept | First taught in | One-line definition |
|---|---|---|
| The engineered demo (5.13, E-15) | F15 | The storyboard compiled to URLs against pre-warmed cache entries: `make demo-warm` runs the exact requests the links resolve to (same model version, config hash, body, seed → same key), so the warm run IS the demo run, and a Playwright check prices the 15 s first beat. |
| Deep-link params off the cache key (E-15/E-16) | F15 | `?lap=`/`?speed=` ride the socket as `client:seek`/`client:speed` after connect and never enter the POST body — the body is the cache key, and forking it would orphan every warmed run; watch-time state belongs to the playback channel, race identity to the key. |
| Deployable means explainable | F15 | `era_model_version` refuses a baked triplet with no surrogate under `models/explain/<version>` so the E-15 pairing can never fail mid-job; the route degrades to a stated fallback, and clearing `pending-F14` was a real `make explain` run, not a string edit. |
| Freeze chain: consistency, not recomputation | F15 | Suite envelopes copied the training-time manifest hash and configs were comment-edited since, so `make verify` checks that envelopes name the served manifests, recomputes only the genuinely frozen `seeds.yaml`, and live-recomputes the overlay studies that hashed their own inputs at run time. |
| A guard proven on its authors | F15 | The CI byte-check regenerates the chapter from the committed store and diffs byte-for-byte; its first catch was this ship's own hand-ordered regeneration, and the fix moved the drifting sentence into the renderer so it cannot detach from the sections it introduces. |
| Split artifact: gitignored dump + committed manifest (A-09) | F15 | `pg_dump -Fc` rides the tagged release while `data/snapshot/MANIFEST.md` (sha256, size, exact per-table counts, counted before the dump so a race under-claims) is committed; restore routes through `require_disposable` because `--clean` is the db-wipe with a new spelling. |
| Pricing a borrow against the metric's own spread | F15 | Perturb the borrowed block ±50% in paired overlay arms and compare the movement to the metric's own interval: M2 moved ≤0.46 places against a 4.7-place spread, so the 2026-fit borrow in the 2024 scenario is documented coarseness, not a load-bearing unknown. |
