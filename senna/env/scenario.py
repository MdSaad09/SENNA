""
from dataclasses import dataclass, field
from pathlib import Path

from senna import config
from senna.env.lineup import Lineup, resolve

# Observation one-hot order (#4-8) and the pit head's compound choices (1..5).
COMPOUNDS = ("SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET")
SLICKS = ("SOFT", "MEDIUM", "HARD")
START_COMPOUND = "MEDIUM"  # the grid rule (5.5): the whole field starts here


def compound_code(name: str) -> int:
    return COMPOUNDS.index(name)


def cliff_age_laps(max_age_seen: int | None, env_cfg: dict) -> int:
    
    horizon = env_cfg["obs"]["tyre_age_norm_laps"]
    margin = env_cfg["tyre_failure"]["cliff_age_margin_laps"]
    base = horizon if max_age_seen is None else max_age_seen
    return int(base) + int(margin)


@dataclass(frozen=True)
class CircuitScenario:
    circuit: str
    era: str
    total_laps: int
    grid_size: int
    usable_soc_mj: float
    race_fuel_kg: float
    t0_s: float
    t_ref_s: float
    s_ref_s: float
    sigma_driver_s: float
    k_m_s_per_kg: float
    evolution_s_per_lap: float
    compound_offset_s: dict
    deg_a: dict
    deg_b: dict
    deg_max_age: dict
    available_compounds: tuple
    h_max_mj: float
    e_dep_mj: float
    harvest_braking_mj: float
    harvest_clipping_mj: float
    conserve_pace_cost_s_per_mj: float
    attack_pace_gain_s: float
    derate_penalty_s_per_mj: float
    dirty_air_threshold_s: float
    attack_soc_floor_mj: float
    aero_traffic_scale: float
    override_gap_s: float
    status_mult: dict
    hazards: dict
    pit_loss_mean_s: float
    pit_loss_sigma_s: float
    sc_burn_factor: float
    env: dict = field(repr=False)
    # who is driving, when anyone said (F17). None is the default everywhere the project
    # trains and evaluates, and it is the only value the frozen model has ever seen.
    lineup: Lineup | None = None


def build_scenario(
    circuit: str, era: str = "2026", *, drivers=None, configs_dir: Path | None = None
) -> CircuitScenario:
    
    def load(name):
        return config.load(name, configs_dir)

    envc = load("env")
    circuits = load("circuits")
    physics = load(f"physics_{era}")
    params = load("physics_params")["circuits"][circuit]  # KeyError names an unknown circuit
    era_int = int(era)

    joint = params["joint_pace"]
    jp = joint.get(era_int) or joint.get(2024) or joint.get(2026)
    deg_block = params["degradation"]
    deg = deg_block.get(era_int) or deg_block.get(2024) or deg_block.get(2026)

    offsets = jp["compound_offsets_s"]
    age_fallback = config.get(envc, "obs.tyre_age_norm_laps")
    
    allow_zero_deg = bool(config.get(envc, "race.allow_zero_deg_compounds"))
    available = tuple(
        c for c in SLICKS
        if c in deg and (allow_zero_deg or float(deg[c]["a"]) > 0.0)
    )
    min_dry = int(config.get(envc, "race.min_dry_compounds"))
    if len(available) < min_dry:
        raise ValueError(
            f"{circuit} ({era}): only {available} wearing dry compounds — the "
            "two-compound rule (F-20) is unsatisfiable below race.min_dry_compounds"
        )
    if START_COMPOUND not in available:
        raise ValueError(
            f"{circuit} ({era}): the grid compound {START_COMPOUND} is not servable "
            f"here (available: {available}) — a race cannot start on a refused tyre"
        )
    deg_a = {c: float(deg[c]["a"]) for c in available}
    deg_b = {c: float(deg[c]["b"]) for c in available}
    deg_max_age = {c: int(deg[c].get("max_age_seen", age_fallback)) for c in available}
    compound_offset = {c: float(offsets.get(c, 0.0)) for c in available}

 
    fitted = load("physics_2026")["fitted"]

    if era == "2026":
        transforms = load("transforms")["circuits"][circuit]
        residual = _dig(transforms, "t8_residual", "c_circuit_s") or 0.0
        t0_s = float(transforms["base"]["t0_2026_s"]) + float(residual)
        energy = transforms["t4_energy"]
        h_max_mj = float(config.get(circuits, f"{circuit}.h_max_mj"))
        e_dep_mj = float(energy["e_dep_mj"])
        harvest_braking_mj = float(energy["harvest_braking_mj"])
        harvest_clipping_mj = float(energy["harvest_clipping_mj"])
        conserve_cost = max(0.0, float(energy["c_lc_s_per_mj"]))  # a negative fit is unphysical
        override_gap_s = float(config.get(physics, "power_unit.manual_override.detection_gap_s"))
        aero_scale = float(config.get(physics, "aero.downforce_vs_2024"))
    else:
        t0_s = float(jp["t0_s"])
        energy_2024 = params.get("energy", {}).get(2024, {})
        braking_default = config.get(physics, "harvest.braking_energy_mj_per_lap_default")
        harvest_braking_mj = float(energy_2024.get("braking_energy_mj_per_lap", braking_default))
        harvest_clipping_mj = 0.0  # no super-clipping in the 2024 MGU-K era
        h_max_mj = float(config.get(physics, "harvest.mgu_k_per_lap_cap_mj"))
        e_dep_mj = h_max_mj  # the 2024 MGU-K per-lap budget bounds deployment
        conserve_cost = float(fitted["conserve_pace_cost_s_per_mj"])
        override_gap_s = float(config.get(physics, "sporting.drs_detection_gap_s"))
        aero_scale = 1.0  # the 2026 close-following gain does not apply to 2024 cars

    status = load("physics_params")["globals"][f"status_pace_{era}"]
    hazards = params["hazards"]
    grid_size = int(config.get(physics, "sporting.grid_size"))

    return CircuitScenario(
        circuit=circuit,
        era=era,
        total_laps=int(config.get(circuits, f"{circuit}.race_laps")),
        grid_size=grid_size,
        usable_soc_mj=float(config.get(physics, "energy_store.usable_capacity_mj")),
        race_fuel_kg=float(config.get(physics, "mass.race_fuel_kg")),
        t0_s=t0_s,
        t_ref_s=float(jp.get("t_ref_s", t0_s)),
        s_ref_s=float(jp["s_ref_s"]),
        sigma_driver_s=float(jp["sigma_driver_s"]),
        k_m_s_per_kg=float(jp["k_m_s_per_kg"]),
        evolution_s_per_lap=float(jp["evolution_s_per_lap"]),
        compound_offset_s=compound_offset,
        deg_a=deg_a,
        deg_b=deg_b,
        deg_max_age=deg_max_age,
        available_compounds=available,
        h_max_mj=h_max_mj,
        e_dep_mj=e_dep_mj,
        harvest_braking_mj=harvest_braking_mj,
        harvest_clipping_mj=harvest_clipping_mj,
        conserve_pace_cost_s_per_mj=conserve_cost,
        attack_pace_gain_s=float(fitted["attack_pace_gain_s"]),
        derate_penalty_s_per_mj=float(fitted["derate_penalty_s_per_mj"]),
        dirty_air_threshold_s=float(fitted["dirty_air_threshold_s"]),
        attack_soc_floor_mj=float(fitted["attack_soc_floor_mj"]),
        aero_traffic_scale=aero_scale,
        override_gap_s=override_gap_s,
        status_mult={
            "sc": float(status["sc_lap_time_mult"]),
            "vsc": float(status["vsc_lap_time_mult"]),
        },
        hazards={
            "sc": float(hazards["sc"]["lambda_per_lap"]),
            "vsc": float(hazards["vsc"]["lambda_per_lap"]),
            "red": float(hazards["red"]["lambda_per_lap"]),
        },
        pit_loss_mean_s=float(params["pit_loss"]["mean_s"]),
        pit_loss_sigma_s=float(params["pit_loss"]["sigma_s"]),
        sc_burn_factor=float(config.get(load("fits"), "fuel.sc_burn_factor")),
        env=envc,
        lineup=None if drivers is None else resolve(
            drivers, circuit=circuit, era=era, n_cars=grid_size, configs_dir=configs_dir
        ),
    )


def _dig(tree: dict, *keys):
    for key in keys:
        if not isinstance(tree, dict) or key not in tree:
            return None
        tree = tree[key]
    return tree
