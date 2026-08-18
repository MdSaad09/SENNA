"""The three-archetype view of the evaluation.

The proposal promises an agent evaluated across three circuit archetypes. The frozen
bank is 24 circuits by 20 seeds, so this does not re-run anything: it slices the stored
480-pair result by circuit. Same races, same seeds, same model — a narrower lens on the
evidence that already exists, which is why the headline figures in this table and in
docs/results/F14-evaluation.md agree by construction.

The three were chosen on the fits, not on reputation. Only four circuits have native
2026 degradation curves for all three slicks — the rest are T5-transferred from cluster
donors — and of those four, Canada's three compounds decay identically, so the model
cannot tell them apart there. That leaves Shanghai, Melbourne and Monaco.

Not every metric can be sliced. M4, M5, M9 and M10 store bank-level aggregates with no
per-race breakdown, so they are reported whole and said to be whole. Inventing a
per-archetype figure for them would mean re-running the suite, which is a different
experiment from the one the numbers came from.
"""

import argparse
import json
import logging
from collections import defaultdict
from pathlib import Path

from senna import config
from senna.eval import store
from senna.eval.bootstrap import mean_interval

log = logging.getLogger(__name__)

# The archetypes, with the character each is standing for. Ordered as the write-up
# reads them: the balanced reference first, then the two that pull away from it.
ARCHETYPES = {
    "chinese_grand_prix": "balanced",
    "australian_grand_prix": "flowing",
    "monaco_grand_prix": "street",
}

# metrics whose stored payload has no per-circuit breakdown; reported whole, and named
# here so the write-up cannot quietly imply otherwise
BANK_LEVEL = ("m4_energy", "m5_windows", "m9_failures", "m10_legality")

SLICKS = ("SOFT", "MEDIUM", "HARD")
# stylised — a one-number stand-in for "how much does this circuit punish a long stint":
# the grip a MEDIUM has lost by this age under the 2026 fit
DEG_PROBE_AGE = 25


def fit_provenance(slug: str, fits: dict) -> str:
    """How much of a circuit's 2026 tyre model came from the circuit itself.

    calibrated  — all three slicks fitted here, none flagged low-confidence, and the
                  three compounds are actually distinguishable. Since F24 no 2026
                  circuit clears this: the soft's wear was unidentifiable everywhere,
                  even pooled, and saying so is the class's job.
    repaired    — every slick carries this circuit's own data, but at least one took
                  its curve from the F24 ladder (pooled or cross-era) because the
                  circuit's fit was bound-clipped. The calibration rounds (E-14) land
                  here now — the most-measured circuits the era has.
    synthesised — at least one slick borrowed from a cluster donor (T5). No 2026 race
                  has happened there, or E-14 holds it out, so the transform supplies it.
    unusable    — fitted here but the fit cannot carry a strategy: a low-confidence
                  own slick, or a spread of zero, which means the model cannot tell
                  the compounds apart at all.
    """
    deg = (fits.get(slug) or {}).get("degradation") or {}
    block = deg.get("2026") or deg.get(2026) or {}
    if not all(compound in block for compound in SLICKS):
        return "incomplete"
    if any(block[compound].get("source_circuit") for compound in SLICKS):
        return "synthesised"
    # repaired rows are low-confidence BY construction (the substitution says so),
    # so the repair check must come before the low-confidence one or F24's own
    # marker would reclassify every repaired circuit as unusable
    if any(block[compound].get("source") for compound in SLICKS):
        if any(block[c].get("low_confidence") and not block[c].get("source")
               for c in SLICKS):
            return "unusable"
        return "repaired"
    if any(block[compound].get("low_confidence") for compound in SLICKS):
        return "unusable"
    losses = [block[c]["a"] * DEG_PROBE_AGE ** block[c]["b"] for c in SLICKS]
    if max(losses) - min(losses) == 0:
        return "unusable"
    return "calibrated"


def _payload(store_dir: Path, name: str) -> dict | None:
    path = Path(store_dir) / f"{name}.json"
    if not path.is_file():
        log.warning("%s is not in the store — skipping", name)
        return None
    return json.loads(path.read_text())


def m1_by_archetype(payload: dict, cfg: dict) -> dict:
    """Paired position delta per circuit, with the headline's own bootstrap."""
    by_circuit: dict[str, list[float]] = defaultdict(list)
    for pair in payload["per_pair"]:
        by_circuit[pair["circuit"]].append(float(pair["baseline"] - pair["agent"]))

    boot = cfg["bootstrap"]
    out = {}
    for slug in ARCHETYPES:
        deltas = by_circuit.get(slug, [])
        if not deltas:
            continue
        interval = mean_interval(deltas, level=boot["ci_level"],
                                 resamples=boot["resamples"], seed=boot["seed"])
        out[slug] = {
            "n": len(deltas),
            "mean_delta": sum(deltas) / len(deltas),
            "ci_low": interval.low,
            "ci_high": interval.high,
            "finish_ahead_rate": sum(d > 0 for d in deltas) / len(deltas),
        }
    return out


def m3_by_archetype(payload: dict) -> dict:
    """Regret is the agent's race time above the oracle's on the same event trace."""
    by_circuit: dict[str, list[float]] = defaultdict(list)
    for race in payload["per_race"]:
        by_circuit[race["circuit"]].append(
            float(race["agent_time_s"]) - float(race["oracle_time_s"]))
    out = {}
    for slug in ARCHETYPES:
        values = sorted(by_circuit.get(slug, []))
        if not values:
            continue
        middle = len(values) // 2
        median = (values[middle] if len(values) % 2
                  else (values[middle - 1] + values[middle]) / 2)
        out[slug] = {"n": len(values), "median_regret_s": median,
                     "mean_regret_s": sum(values) / len(values)}
    return out


def m6_by_archetype(payload: dict, cfg: dict) -> dict:
    """A stop counts if it fell within the tolerance of any post-hoc optimal lap. The
    excluded stops (no corridor, red flag) carry `excluded` and are left out here too,
    so the per-archetype denominator matches the headline's rule."""
    tolerance = cfg["m6"]["tolerance_laps"]
    hit: dict[str, list[bool]] = defaultdict(list)
    for stop in payload["per_stop"]:
        if stop.get("excluded"):
            continue
        optimal = stop.get("optimal_laps") or []
        hit[stop["circuit"]].append(
            any(abs(int(stop["stop_lap"]) - int(lap)) <= tolerance for lap in optimal))
    return {
        slug: {"n": len(flags), "accuracy": sum(flags) / len(flags)}
        for slug in ARCHETYPES if (flags := hit.get(slug))
    }


def _scalar_by_archetype(payload: dict, key: str, field: str) -> dict:
    """One named field out of a per-circuit block, for the three archetypes."""
    per = payload.get(key) or {}
    return {slug: {field: per[slug][field]} for slug in ARCHETYPES
            if slug in per and field in per[slug]}


def conditional_advantage(m1: dict, m3: dict, fits: dict) -> dict:
    """Whether the agent's advantage depends on the tyre model being synthesised.

    This exists because slicing M1 to the three archetypes made the headline vanish, and
    the reason turned out to be worth more than the slice: the advantage is carried by
    the circuits whose 2026 degradation the T5 transform invented. That held before the
    F24 repair (+2.279, parity on measured circuits) and holds after it (+3.19
    synthesised, slightly behind on the repaired class) — the retrain moved the
    mechanism, not the split: pre-repair the agent under-stopped everywhere; now it
    over-stops on the measured circuits instead. The sim-optimism caveat this feeds is
    the chapter's, not a footnote.
    """
    deltas: dict[str, list[float]] = defaultdict(list)
    for pair in m1["per_pair"]:
        deltas[fit_provenance(pair["circuit"], fits)].append(
            float(pair["baseline"] - pair["agent"]))

    regret: dict[str, list[float]] = defaultdict(list)
    agent_stops: dict[str, list[int]] = defaultdict(list)
    oracle_stops: dict[str, list[int]] = defaultdict(list)
    for race in m3["per_race"]:
        group = fit_provenance(race["circuit"], fits)
        regret[group].append(float(race["agent_time_s"]) - float(race["oracle_time_s"]))
        agent_stops[group].append(len(race["agent_stops"]))
        oracle_stops[group].append(len(race["oracle_stops"]))

    def median(values):
        ordered = sorted(values)
        middle = len(ordered) // 2
        return (ordered[middle] if len(ordered) % 2
                else (ordered[middle - 1] + ordered[middle]) / 2)

    out = {}
    for group, values in deltas.items():
        row = {"n_pairs": len(values), "mean_delta": sum(values) / len(values)}
        if regret.get(group):
            row |= {
                "median_regret_s": median(regret[group]),
                "mean_regret_s": sum(regret[group]) / len(regret[group]),
                "agent_stops": sum(agent_stops[group]) / len(agent_stops[group]),
                "oracle_stops": sum(oracle_stops[group]) / len(oracle_stops[group]),
            }
        out[group] = row
    return out


def build(store_dir=None, configs_dir=None) -> dict:
    store_dir = Path(store_dir or config.REPO_ROOT / "docs" / "results" / "F14" / "store")
    cfg = config.load("eval", configs_dir)

    result: dict = {"archetypes": ARCHETYPES, "bank_level_only": list(BANK_LEVEL),
                    "sliced": {}}

    if (m1 := _payload(store_dir, "m1_pairs")) is not None:
        result["sliced"]["m1_paired_position_delta"] = m1_by_archetype(m1["payload"], cfg)
    if (m3 := _payload(store_dir, "m3_regret")) is not None:
        result["sliced"]["m3_oracle_regret"] = m3_by_archetype(m3["payload"])
    if (m6 := _payload(store_dir, "m6_pits")) is not None:
        result["sliced"]["m6_pit_window_accuracy"] = m6_by_archetype(m6["payload"], cfg)
    if (m7 := _payload(store_dir, "m7_entropy")) is not None:
        result["sliced"]["m7_strategy_diversity"] = _scalar_by_archetype(
            m7["payload"], "per_circuit", "entropy_nats")
    if (m11 := _payload(store_dir, "m11_decomposition")) is not None:
        result["sliced"]["m11_luck_share"] = _scalar_by_archetype(
            m11["payload"], "per_circuit", "share")

    fits = config.load("physics_params", configs_dir)["circuits"]
    if m1 is not None and m3 is not None:
        result["conditional_advantage"] = conditional_advantage(
            m1["payload"], m3["payload"], fits)
    result["fit_provenance"] = {
        slug: fit_provenance(slug, fits) for slug in sorted(config.load("circuits", configs_dir))
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    store_dir = Path(args.store) if args.store else (
        config.REPO_ROOT / "docs" / "results" / "F14" / "store")
    payload = build(store_dir)

    source = json.loads((store_dir / "m1_pairs.json").read_text())["envelope"]
    envelope = store.envelope(
        model_versions=source["model_versions"], config_hash=source["config_hash"],
        seeds_fingerprint=source["seeds_fingerprint"],
        # the same bank, read three circuits at a time — stated so this row can never be
        # mistaken for a fresh three-circuit evaluation
        scope={"circuits": len(ARCHETYPES), "sliced_from": source.get("scope"),
               "rerun": False},
    )
    out = Path(args.out) if args.out else store_dir
    written = store.write_metric(out, "archetypes", payload, envelope=envelope)
    log.info("wrote %s", written)


if __name__ == "__main__":
    main()
