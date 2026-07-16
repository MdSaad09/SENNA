"""The F02 fitting battery — gate, fit, write physics_params.yaml.

Stages run in dependency order: the joint pace fit feeds degradation its
partial residuals and t0; degradation, energy and pit loss feed the cluster
features; clusters feed the T5 transfer for circuits the 2026 season has not
reached. `--only` and `--circuit` narrow a run for iteration, and a narrowed
run never writes the yaml — a partial battery must not masquerade as the
full artifact.

Run it: python -m senna.physics.fits.run   (or `make fit`)
"""

import argparse
import asyncio
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from senna import config
from senna.data.db import database_url, engine_for
from senna.physics.fits import frames
from senna.physics.fits.clusters import assign_clusters, transfer_degradation
from senna.physics.fits.degradation import fit_degradation
from senna.physics.fits.energy import session_energy_frame
from senna.physics.fits.fuel import session_fuel
from senna.physics.fits.gate import assert_quality_reports
from senna.physics.fits.hazards import (
    per_lap_hazard,
    per_race_events,
    status_multipliers,
    wilson_band,
)
from senna.physics.fits.joint_pace import age_partial_residuals, fit_joint_pace, pool_k_m
from senna.physics.fits.params_writer import render_params, validate_complete
from senna.physics.fits.pit_loss import fit_pit_loss

log = logging.getLogger(__name__)

MODULES = ("joint_pace", "degradation", "hazards", "pit_loss", "energy", "clusters")
SLICKS = ("SOFT", "MEDIUM", "HARD")

JOINT_NB = "fitted: notebooks/fit_joint_pace.ipynb"
DEG_NB = "fitted: notebooks/fit_degradation.ipynb"
HAZARD_NB = "fitted: notebooks/fit_hazards_pit_loss.ipynb"
ENERGY_NB = "fitted: notebooks/fit_energy_integrals.ipynb"
CLUSTER_NB = "fitted: notebooks/fit_tyre_clusters.ipynb"


async def run_battery(args: argparse.Namespace) -> dict:
    fits_cfg = config.load("fits")
    ingest_cfg = config.load("ingest")
    split = config.load("data_split")
    calibration_rounds = config.get(split, "calibration_rounds")
    seasons = config.get(ingest_cfg, "seasons")

    assert_quality_reports(seasons, config.REPO_ROOT / config.get(ingest_cfg, "quality.report_dir"))

    only = set(args.only.split(",")) if args.only else set(MODULES)
    unknown = only - set(MODULES)
    if unknown:
        raise SystemExit(f"unknown --only module(s): {', '.join(sorted(unknown))}")

    engine = engine_for(database_url())
    try:
        async with engine.connect() as conn:
            index = await frames.circuit_index(conn, calibration_rounds)
            if args.circuit:
                index = index[index["slug"] == args.circuit]
                if index.empty:
                    raise SystemExit(f"no ingested sessions for circuit '{args.circuit}'")
            battery = _Battery(conn, index, fits_cfg, ingest_cfg, calibration_rounds)
            for module in MODULES:  # declaration order is dependency order
                if module in only:
                    await battery.run(module)
    finally:
        await engine.dispose()

    params = battery.params()
    narrowed = bool(args.only or args.circuit)
    if narrowed:
        log.info("narrowed run (--only/--circuit): physics_params.yaml not written")
    else:
        validate_complete(params)
        text = render_params(params, generated_at=battery.data_through())
        args.params_out.write_text(text)
        log.info("wrote %s", args.params_out)
    return params


class _Battery:
    """One full pass over the ingested data; stages share results in memory."""

    def __init__(self, conn, index: pd.DataFrame, fits_cfg: dict, ingest_cfg: dict, rounds):
        self.conn = conn
        self.index = index
        self.fits_cfg = fits_cfg
        self.ingest_cfg = ingest_cfg
        self.calibration_rounds = rounds
        self.eras = sorted(index["era"].unique())
        self.fuel_by_era = {
            era: config.get(config.load(f"physics_{era}"), "mass.race_fuel_kg")
            for era in self.eras
        }
        self.car_kg_by_era = {
            era: config.get(config.load(f"physics_{era}"), "mass.minimum_car_kg")
            for era in self.eras
        }
        self.joint: dict[tuple[str, str], object] = {}
        self.residuals: dict[tuple[str, str], pd.DataFrame] = {}
        self.deg: dict[tuple[str, str], dict] = {}
        self.hazards: dict[str, dict] = {}
        self.status_pace: dict[str, dict] = {}
        self.pit: dict[str, object] = {}
        self.energy: dict[tuple[str, str], dict] = {}
        self.clustering = None
        self.transferred: dict[tuple[str, str], dict] = {}
        self.pooled_k_m: dict[str, float] = {}
        self.pooled_fallback_eras: set[str] = set()

    async def run(self, module: str) -> None:
        await getattr(self, f"_run_{module}")()

    def _slugs(self, era: str | None = None) -> list[str]:
        rows = self.index if era is None else self.index[self.index["era"] == era]
        return sorted(rows["slug"].unique())

    def _event_name(self, slug: str) -> str:
        return self.index.loc[self.index["slug"] == slug, "event_name"].iloc[0]

    def data_through(self) -> str:
        # identifies the ingest state, not the wall clock, so a rerun on the
        # same data renders byte-identically
        last_season = int(self.index["season"].max())
        last_round = int(self.index.loc[self.index["season"] == last_season, "round"].max())
        return f"seasons {int(self.index['season'].min())}-{last_season}, round {last_round}"

    async def _run_joint_pace(self) -> None:
        vif_max = float(config.get(self.fits_cfg, "joint_pace.vif_max"))
        sc_burn = float(config.get(self.fits_cfg, "fuel.sc_burn_factor"))
        pending: list[tuple[str, str, pd.DataFrame, pd.Series]] = []
        for era in self.eras:
            for slug in self._slugs(era):
                laps = await frames.pace_laps(
                    self.conn, self._event_name(slug), era, self.calibration_rounds
                )
                laps = _slick_laps(laps)
                if laps.empty:
                    log.info("joint_pace %s/%s: no dry slick laps, skipped", slug, era)
                    continue
                fuel_kg = session_fuel(laps, self.fuel_by_era[era], sc_burn)
                fit = fit_joint_pace(
                    laps, fuel_kg, vif_max=vif_max, calibration_rounds=self.calibration_rounds
                )
                self.joint[(slug, era)] = fit
                self.residuals[(slug, era)] = age_partial_residuals(
                    laps, fuel_kg, calibration_rounds=self.calibration_rounds
                )
                pending.append((slug, era, laps, fuel_kg))
                log.info(
                    "joint_pace %s/%s: k_m=%s identified=%s vif=%.1f n=%d",
                    slug, era, fit.k_m_s_per_kg, fit.identified, fit.vif_fuel, fit.n_laps,
                )

        self.pooled_k_m, self.pooled_fallback_eras = _pool_k_m(dict(self.joint))
        for slug, era, laps, fuel_kg in pending:
            fit = self.joint[(slug, era)]
            if not fit.identified and era in self.pooled_k_m:
                # the honest decomposition: borrow the pooled attribution,
                # keep the circuit's own well-identified trend (E-10)
                self.joint[(slug, era)] = fit_joint_pace(
                    laps,
                    fuel_kg,
                    vif_max=float(config.get(self.fits_cfg, "joint_pace.vif_max")),
                    calibration_rounds=self.calibration_rounds,
                    k_m_pooled_s_per_kg=self.pooled_k_m[era],
                )

    async def _run_degradation(self) -> None:
        if not self.residuals:
            raise SystemExit("degradation needs joint_pace in the same run (partial residuals)")
        deg_cfg = config.get(self.fits_cfg, "degradation")
        bounds = (
            [deg_cfg["curve_bounds"]["a"][0], deg_cfg["curve_bounds"]["b"][0]],
            [deg_cfg["curve_bounds"]["a"][1], deg_cfg["curve_bounds"]["b"][1]],
        )
        for (slug, era), residuals in self.residuals.items():
            self.deg[(slug, era)] = fit_degradation(
                residuals,
                self.joint[(slug, era)].t0_s,
                bounds=bounds,
                min_laps=deg_cfg["min_laps"],
                min_stints=deg_cfg["min_stints"],
                min_drivers=deg_cfg["min_drivers"],
                min_max_age=deg_cfg["min_max_age"],
                p0=deg_cfg["curve_p0"],
                maxfev=deg_cfg["curve_maxfev"],
            )
            log.info("degradation %s/%s: %s", slug, era, sorted(self.deg[(slug, era)]))

    async def _run_hazards(self) -> None:
        z = float(config.get(self.fits_cfg, "hazards.wilson_z"))
        for slug in self._slugs():
            laps = await frames.hazard_laps(
                self.conn, self._event_name(slug), self.calibration_rounds
            )
            if laps.empty:
                continue
            events = per_race_events(laps)
            race_laps = float(laps.groupby("session_id")["lap_number"].max().median())
            self.hazards[slug] = {
                kind: {
                    "n_races": len(events),
                    "n_with": int(events[kind].sum()),
                    "p_per_race": float(events[kind].mean()),
                    "band": wilson_band(int(events[kind].sum()), len(events), z=z),
                    "lambda_per_lap": per_lap_hazard(
                        int(events[kind].sum()), len(events), race_laps
                    ),
                }
                for kind in ("sc", "vsc", "red")
            }
        for era in self.eras:
            era_laps = await frames.status_laps(self.conn, era, self.calibration_rounds)
            self.status_pace[era] = status_multipliers(era_laps)
            log.info("status multipliers %s: %s", era, self.status_pace[era])

    async def _run_pit_loss(self) -> None:
        max_s = float(config.get(self.fits_cfg, "pit_loss.max_duration_s"))
        for slug in self._slugs():
            stops = await frames.pit_stops(
                self.conn, self._event_name(slug), self.calibration_rounds
            )
            if stops.empty:  # OpenF1 has no 2022 data; a 2022-only circuit has no stops
                continue
            fit = fit_pit_loss(stops, max_duration_s=max_s)
            self.pit[slug] = fit
            log.info("pit_loss %s: mean=%.1f n=%d", slug, fit.mean_s, fit.n_stops)

    async def _run_energy(self) -> None:
        from senna.data import fastf1_loader

        fastf1_loader.enable_cache(
            config.REPO_ROOT / config.get(self.ingest_cfg, "fastf1.cache_dir")
        )
        gap_split_s = float(config.get(self.ingest_cfg, "cleaning.telemetry_gap_split_s"))
        throttle_full = float(config.get(self.fits_cfg, "energy.throttle_full_pct"))
        sc_burn = float(config.get(self.fits_cfg, "fuel.sc_burn_factor"))
        races = self.index[
            (self.index["session_name"] == "Race") & (self.index["is_dry"].fillna(False))
        ]
        for (slug, era), sessions in races.groupby(["slug", "era"]):
            lap_frames = []
            for row in sessions.itertuples():
                try:
                    car_data, session_laps = fastf1_loader.load_car_data(
                        int(row.season), int(row.round), "Race"
                    )
                except Exception as err:
                    # deliberately broad, mirroring run_ingest: fastf1 raises a
                    # zoo of cache/parse errors and one broken weekend must not
                    # kill an hour-long battery — the warning is the record
                    log.warning("energy %s %s: telemetry load failed: %r", row.season, slug, err)
                    continue
                lap_frames.append(
                    session_energy_frame(
                        car_data,
                        session_laps,
                        gap_split_s=gap_split_s,
                        throttle_full_pct=throttle_full,
                        car_mass_kg=float(self.car_kg_by_era[era]),
                        race_fuel_kg=float(self.fuel_by_era[era]),
                        sc_burn_factor=sc_burn,
                    )
                )
            per_lap = pd.concat(lap_frames, ignore_index=True) if lap_frames else pd.DataFrame()
            if per_lap.empty:
                log.info("energy %s/%s: no usable telemetry laps", slug, era)
                continue
            self.energy[(slug, era)] = {
                "braking_energy_mj_per_lap": float(per_lap["braking_energy_mj"].median()),
                "full_throttle_s_per_lap": float(per_lap["full_throttle_s"].median()),
                "full_throttle_frac": float(
                    (per_lap["full_throttle_s"] / per_lap["lap_time_s"]).median()
                ),
                "median_cadence_hz": float(per_lap["cadence_hz"].median()),
                "n_laps": len(per_lap),
            }
            log.info("energy %s/%s: %d laps integrated", slug, era, len(per_lap))

    async def _run_clusters(self) -> None:
        features = self._cluster_features()
        if len(features) < 3:
            raise SystemExit("clusters need degradation, pit_loss and energy from the same run")
        self.clustering = assign_clusters(
            features,
            k_range=tuple(config.get(self.fits_cfg, "clusters.k_range")),
            seed=int(config.get(self.fits_cfg, "clusters.seed")),
        )
        log.info("clusters: k=%d over %d circuits", self.clustering.k, len(features))
        self._transfer_missing_2026(features)

    def _cluster_features(self) -> pd.DataFrame:
        rows = {}
        for slug in self._slugs("2024"):
            deg = self.deg.get((slug, "2024"))
            energy = self.energy.get((slug, "2024"))
            pit = self.pit.get(slug)
            if not (deg and energy and pit):
                log.info("clusters: %s lacks a 2024 fit and is left unclustered", slug)
                continue
            rows[slug] = {
                "deg_a_2024": float(np.mean([fit.a for fit in deg.values()])),
                "full_throttle_frac": energy["full_throttle_frac"],
                "braking_energy_mj_per_lap": energy["braking_energy_mj_per_lap"],
                "pit_loss_s": self.pit[slug].mean_s,
            }
        return pd.DataFrame.from_dict(rows, orient="index")

    def _transfer_missing_2026(self, features: pd.DataFrame) -> None:
        fitted_2026 = {slug for (slug, era) in self.deg if era == "2026"}
        for slug in features.index:
            if slug in fitted_2026:
                continue
            mates = [
                other
                for other, label in self.clustering.assignments.items()
                if label == self.clustering.assignments[slug] and other in fitted_2026
            ]
            transferred = {}
            for compound in SLICKS:
                donors = [
                    mate
                    for mate in mates
                    if compound in self.deg[(mate, "2026")]
                    and compound in self.deg.get((mate, "2024"), {})
                ]
                target_2024 = self.deg.get((slug, "2024"), {}).get(compound)
                if not donors or target_2024 is None:
                    continue
                transferred[compound] = transfer_degradation(
                    target_era2024_a=target_2024.a,
                    donor_era2024_a=self._donor_mean(donors, "2024", compound, "a"),
                    donor_2026_a=self._donor_mean(donors, "2026", compound, "a"),
                    donor_2026_b=self._donor_mean(donors, "2026", compound, "b"),
                    source_circuit=",".join(sorted(donors)),
                )
            if transferred:
                self.transferred[(slug, "2026")] = transferred
                log.info("clusters: %s 2026 degradation transferred from %s", slug,
                         ",".join(sorted(mates)))

    def _donor_mean(self, donors: list[str], era: str, compound: str, coefficient: str) -> float:
        return float(np.mean([getattr(self.deg[(d, era)][compound], coefficient) for d in donors]))

    def params(self) -> dict:
        params: dict = {"globals": {}, "circuits": {}}
        # the 2026 pool is grade C through the AR-10 fuel construction, and so
        # is anything that borrowed it — the flag travels with the value
        grade_c_pool_eras = {"2026"} | self.pooled_fallback_eras
        for era, pooled in self.pooled_k_m.items():
            origin = f"{JOINT_NB} — inverse-variance mean over identified circuits"
            if era in self.pooled_fallback_eras:
                origin += " — cross-era fallback, no circuit of this era identified"
            if era in grade_c_pool_eras:
                origin += " (grade C via AR-10 fuel)"
            params["globals"][f"k_m_pooled_s_per_kg_{era}"] = (round(pooled, 6), origin)
        for era, multipliers in self.status_pace.items():
            params["globals"][f"status_pace_{era}"] = {
                f"{kind}_lap_time_mult": (round(value, 4), HAZARD_NB)
                for kind, value in multipliers.items()
            }
        for slug in self._slugs():
            circuit: dict = {}
            _put_joint(circuit, slug, self.joint, grade_c_pool_eras)
            _put_degradation(circuit, slug, self.deg, self.transferred)
            if slug in self.hazards:
                circuit["hazards"] = {
                    kind: {
                        "n_races": (row["n_races"], HAZARD_NB),
                        "n_with": (row["n_with"], HAZARD_NB),
                        "p_per_race": (round(row["p_per_race"], 4), HAZARD_NB),
                        "band_low": (round(row["band"][0], 4), HAZARD_NB + " — Wilson 95%"),
                        "band_high": (round(row["band"][1], 4), HAZARD_NB + " — Wilson 95%"),
                        "lambda_per_lap": (round(row["lambda_per_lap"], 5), HAZARD_NB),
                    }
                    for kind, row in self.hazards[slug].items()
                }
            if slug in self.pit:
                pit = self.pit[slug]
                circuit["pit_loss"] = {
                    "mean_s": (round(pit.mean_s, 3), HAZARD_NB),
                    "sigma_s": (round(pit.sigma_s, 3), HAZARD_NB),
                    "n_stops": (pit.n_stops, HAZARD_NB),
                    "n_excluded": (pit.n_excluded, HAZARD_NB),
                }
            for era in self.eras:
                if (slug, era) in self.energy:
                    values = self.energy[(slug, era)]
                    # braking mass = car + AR-10 fuel-at-lap, so 2026 rows are C too
                    origin = ENERGY_NB + (" (grade C via AR-10 fuel)" if era == "2026" else "")
                    circuit.setdefault("energy", {})[era] = {
                        key: (round(value, 4) if isinstance(value, float) else value, origin)
                        for key, value in values.items()
                    }
            if circuit:
                params["circuits"][slug] = circuit
        if self.clustering:
            params["clusters"] = {
                "k": (self.clustering.k, CLUSTER_NB + " — max silhouette"),
                "seed": (
                    int(config.get(self.fits_cfg, "clusters.seed")),
                    "sourced configs/fits.yaml — determinism provenance for transfer donors",
                ),
                "features": (
                    list(self._cluster_features().columns),
                    CLUSTER_NB,
                ),
                "silhouettes": {
                    f"k{k}": (round(score, 4), CLUSTER_NB)
                    for k, score in self.clustering.silhouettes.items()
                },
                "assignments": {
                    slug: (label, CLUSTER_NB)
                    for slug, label in self.clustering.assignments.items()
                },
            }
        return params


def _slick_laps(laps: pd.DataFrame) -> pd.DataFrame:
    if laps.empty:
        return laps
    return laps[laps["compound"].isin(SLICKS)]


def _pool_k_m(joint: dict) -> tuple[dict[str, float], set[str]]:
    """Pooled k_m per era, plus which eras borrowed the other era's pool.

    Mass sensitivity is a property of car physics more than of the season, so
    an era where no circuit identified (2024 has no sprint-plus-SC weekend
    clean enough) borrows the other era's pooled value — flagged in the yaml,
    never silently."""
    pooled = {}
    for era in {era for (_, era) in joint}:
        era_fits = [fit for (_, fit_era), fit in joint.items() if fit_era == era]
        value = pool_k_m(era_fits)
        if value is not None:
            pooled[era] = value
    fallback_eras = set()
    if len(pooled) == 1:  # with several candidate donors the borrow is ambiguous;
        [donor_era] = pooled  # leave the gap and let validate_complete fail loudly
        for era in {era for (_, era) in joint} - set(pooled):
            pooled[era] = pooled[donor_era]
            fallback_eras.add(era)
    return pooled, fallback_eras


def _put_joint(circuit: dict, slug: str, joint: dict, grade_c_pool_eras: set[str]) -> None:
    for (fit_slug, era), fit in joint.items():
        if fit_slug != slug:
            continue
        grade = " (grade C via AR-10 fuel)" if era == "2026" else ""
        attribution = "" if fit.identified else " — decomposed via pooled k_m"
        # an unidentified circuit's attribution inherits the pool's grade even
        # when its own era's fuel is verified (the 2024 borrow of the 2026 pool)
        attribution_grade = grade
        if not fit.identified and era in grade_c_pool_eras and not grade:
            attribution_grade = " (grade C via AR-10 fuel — through the pooled k_m)"
        circuit.setdefault("joint_pace", {})[era] = {
            "t0_s": (round(fit.t0_s, 3), JOINT_NB + grade),
            "k_m_s_per_kg": (
                None if fit.k_m_s_per_kg is None else round(fit.k_m_s_per_kg, 6),
                JOINT_NB + attribution + attribution_grade,
            ),
            "evolution_s_per_lap": (
                None if fit.evolution_s_per_lap is None else round(fit.evolution_s_per_lap, 6),
                JOINT_NB + attribution + attribution_grade,
            ),
            # trend, t_ref, s_ref and sigma_driver are computed from raw lap
            # times alone — fuel-free, so no AR-10 grade even in 2026
            "trend_s_per_lap": (round(fit.trend_s_per_lap, 6), JOINT_NB),
            "identified": (fit.identified, JOINT_NB),
            "vif_fuel": (round(fit.vif_fuel, 1) if np.isfinite(fit.vif_fuel) else "inf", JOINT_NB),
            "condition_number": (round(fit.condition_number, 1), JOINT_NB),
            "sigma_driver_s": (round(fit.sigma_driver_s, 4), JOINT_NB),
            "t_ref_s": (round(fit.t_ref_s, 3), JOINT_NB),
            "s_ref_s": (round(fit.s_ref_s, 4), JOINT_NB),
            "n_laps": (fit.n_laps, JOINT_NB),
            "compound_offsets_s": {
                compound: (round(offset, 4), JOINT_NB)
                for compound, offset in fit.compound_offsets_s.items()
            },
        }


def _put_degradation(circuit: dict, slug: str, deg: dict, transferred: dict) -> None:
    for (fit_slug, era), compounds in deg.items():
        if fit_slug != slug:
            continue
        circuit.setdefault("degradation", {})[era] = {
            compound: {
                "a": (round(fit.a, 6), DEG_NB),
                "b": (round(fit.b, 4), DEG_NB),
                "n_laps": (fit.n_laps, DEG_NB),
                "max_age_seen": (fit.max_age_seen, DEG_NB),
                "low_confidence": (fit.low_confidence, DEG_NB),
                # source_circuit appears only on cluster transfers (T5)
            }
            for compound, fit in compounds.items()
        }
    if (slug, "2026") in transferred:
        circuit.setdefault("degradation", {})["2026"] = {
            compound: {
                "a": (round(row["a"], 6), DEG_NB + " — cluster transfer (T5)"),
                "b": (round(row["b"], 4), DEG_NB + " — cluster transfer (T5)"),
                "low_confidence": (True, DEG_NB),
                "source_circuit": (row["source_circuit"], DEG_NB),
            }
            for compound, row in transferred[(slug, "2026")].items()
        }


def _cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SENNA physics fitting battery (F02)")
    parser.add_argument("--only", help=f"comma list of {', '.join(MODULES)}; skips the yaml write")
    parser.add_argument(
        "--circuit", help="one circuit slug, e.g. monaco_grand_prix; skips the yaml write"
    )
    parser.add_argument(
        "--params-out",
        type=Path,
        default=config.REPO_ROOT / "configs" / "physics_params.yaml",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(run_battery(_cli().parse_args(argv)))


if __name__ == "__main__":
    main()
