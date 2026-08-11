"""The E-10 joint fuel/evolution regression.

lap_time ~ session FE + driver FE + compound FE + per-compound (age + age^2)
         + k_m * fuel_mass + b * lap_number

Fitting fuel and track evolution separately double-counts the shared downward
trend; fitting them jointly is only honest if the design can actually tell
them apart. Constructed fuel is nearly affine in lap_number, so this module
measures the collinearity (VIF, condition number) and, when identification is
weak, refits without fuel, reports the combined trend the data does pin down,
and — given a pooled k_m from circuits where identification succeeded —
decomposes the trend instead of pretending the race resolved it. Either way
the fitted trend reproduces what was observed; only the attribution moves.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

# E-14: the season the frozen split governs. One code home — frames.py imports
# this — mirroring configs/data_split.yaml `season`, which stays the paper trail.
FIRST_2026_SEASON = 2026


@dataclass(frozen=True)
class JointPaceFit:
    t0_s: float
    k_m_s_per_kg: float | None
    k_m_se_s_per_kg: float | None
    evolution_s_per_lap: float | None
    trend_s_per_lap: float
    identified: bool
    vif_fuel: float
    condition_number: float
    sigma_driver_s: float
    compound_offsets_s: dict[str, float]
    t_ref_s: float
    s_ref_s: float
    n_laps: int
    # counted, not silent — the same convention PitLossFit.n_excluded uses, so a season
    # whose tyre ages are patchy shows up in the fit report instead of just shrinking n
    n_excluded_no_tyre_age: int
    # the raw OLS attribution, kept even when too weak to report per circuit —
    # not for pooling (weak fits are confounded by post-SC pace effects, see
    # pool_k_m) but for the notebook's diagnostic that demonstrates exactly that
    k_m_ols_s_per_kg: float | None = None
    k_m_ols_se_s_per_kg: float | None = None


def fit_joint_pace(
    laps: pd.DataFrame,
    fuel_kg: pd.Series,
    *,
    vif_max: float,
    calibration_rounds: list[int] | None = None,
    k_m_pooled_s_per_kg: float | None = None,
) -> JointPaceFit:
    if calibration_rounds is not None:
        _refuse_validation_rounds(laps, calibration_rounds)

    clean, n_ageless = _clean_mask(laps)
    fit_laps = laps[clean].copy()
    fit_laps["fuel_kg"] = fuel_kg[clean]
    if fit_laps.empty:
        raise ValueError(
            f"no laps left to fit: every otherwise-clean lap was dropped, {n_ageless} of "
            "them for having no tyre age. A lap with no tyre life cannot enter a "
            "regression on tyre life (5.3.4, E-09) — check the ingest for this circuit"
        )

    columns, names = _design_matrix(fit_laps)
    lap_time_s = fit_laps["lap_time_s"].to_numpy(dtype=float)

    coef, rank = _lstsq(columns, lap_time_s)
    vif_fuel = _vif(columns, names.index("fuel_kg"))
    condition_number = _condition_number(columns, names)

    fuel_slope_kg_per_lap = _within_session_slope(fit_laps)
    full_rank = rank == len(names) and np.isfinite(vif_fuel)
    k_m_ols = float(coef[names.index("fuel_kg")]) if full_rank else None
    k_m_ols_se = (
        _coefficient_se(columns, lap_time_s, coef, names.index("fuel_kg")) if full_rank else None
    )
    # separable is not the same as physical. VIF asks whether the design can tell fuel
    # from track evolution; it cannot ask whether the answer means anything, and a
    # lighter-is-slower coefficient means nothing. An attribution that fails either test
    # is withheld and the circuit takes the pooled decomposition like any weak fit — the
    # trend it does pin down is unaffected either way (E-10).
    separable = bool(np.isfinite(vif_fuel) and vif_fuel <= vif_max and rank == len(names))
    identified = bool(separable and k_m_ols is not None and k_m_ols > 0.0)
    if identified:
        k_m = k_m_ols
        evolution = float(coef[names.index("lap_number")])
        trend = evolution + k_m * fuel_slope_kg_per_lap
        k_m_se = k_m_ols_se
    else:
        # refit without the fuel column: the lap coefficient is the combined
        # trend, which stays well identified when the attribution is not
        no_fuel = [i for i, name in enumerate(names) if name != "fuel_kg"]
        trend_coef, _ = _lstsq(columns[:, no_fuel], lap_time_s)
        trend = float(trend_coef[[names[i] for i in no_fuel].index("lap_number")])
        coef = _splice_fuel_zero(trend_coef, names, no_fuel)
        k_m_se = None
        if k_m_pooled_s_per_kg is None:
            k_m, evolution = None, None
        else:
            k_m = k_m_pooled_s_per_kg
            evolution = trend - k_m * fuel_slope_kg_per_lap

    driver_effects = _effects(coef, names, prefix="driver=", n_groups=fit_laps["driver"].nunique())
    session_effects = _effects(
        coef, names, prefix="session=", n_groups=fit_laps["session_id"].nunique()
    )
    compound_offsets_s = {
        compound: float(coef[names.index(f"compound={compound}")])
        if f"compound={compound}" in names
        else 0.0  # the dropped reference level
        for compound in sorted(fit_laps["compound"].unique())
    }

    return JointPaceFit(
        t0_s=float(coef[names.index("intercept")] + driver_effects.mean() + session_effects.mean()),
        k_m_s_per_kg=k_m,
        k_m_se_s_per_kg=k_m_se,
        evolution_s_per_lap=evolution,
        trend_s_per_lap=trend,
        identified=identified,
        vif_fuel=vif_fuel,
        condition_number=condition_number,
        sigma_driver_s=float(np.std(driver_effects, ddof=1)) if len(driver_effects) > 1 else 0.0,
        compound_offsets_s=compound_offsets_s,
        t_ref_s=float(np.median(lap_time_s)),
        s_ref_s=float(np.std(lap_time_s, ddof=1)),
        n_laps=int(clean.sum()),
        n_excluded_no_tyre_age=n_ageless,
        k_m_ols_s_per_kg=k_m_ols,
        k_m_ols_se_s_per_kg=k_m_ols_se,
    )


def age_partial_residuals(
    laps: pd.DataFrame,
    fuel_kg: pd.Series,
    *,
    calibration_rounds: list[int] | None = None,
) -> pd.DataFrame:
    """The degradation fitter's input: clean laps with the joint fit's age
    contribution added back after everything else is removed (partial
    residuals), so the power law is not refitting what E-10 already explained."""
    if calibration_rounds is not None:
        _refuse_validation_rounds(laps, calibration_rounds)
    clean, _ = _clean_mask(laps)
    fit_laps = laps[clean].copy()
    fit_laps["fuel_kg"] = fuel_kg[clean]
    design, names = _design_matrix(fit_laps)
    lap_time_s = fit_laps["lap_time_s"].to_numpy(dtype=float)
    coef, _ = _lstsq(design, lap_time_s)
    age_columns = [i for i, name in enumerate(names) if name.startswith(("age:", "age2:"))]
    age_contribution_s = design[:, age_columns] @ coef[age_columns]
    raw_residual_s = lap_time_s - design @ coef
    return fit_laps.assign(
        pace_residual_s=raw_residual_s + age_contribution_s,
        residual_s=raw_residual_s,  # for the notebook's flat-cloud checks
    )


def pool_k_m(fits: list[JointPaceFit]) -> float | None:
    """Inverse-variance pooled k_m over one era's identified circuits only.

    Weak fits stay out: their k_m is not merely noisy but confounded — the
    post-interruption laps that bend the fuel line also carry cold tyres and
    a bunched field, and pooling them yields a negative mass sensitivity
    (the fit_joint_pace notebook shows that diagnostic). Identified circuits
    are the ones where the instrument was strong enough to trust (E-10)."""
    usable = [fit for fit in fits if fit.identified and fit.k_m_se_s_per_kg]
    if not usable:
        return None
    weights = np.array([1.0 / fit.k_m_se_s_per_kg**2 for fit in usable])
    values = np.array([fit.k_m_s_per_kg for fit in usable])
    pooled = float(np.sum(weights * values) / np.sum(weights))
    if pooled <= 0.0:
        # a heavier car cannot be faster, so a non-positive pool is not a small
        # number — it is the confounding above, arriving at scale. Refusing it
        # hands the era to the same fallback an unidentified era already uses,
        # which is a borrowed physical value instead of a published impossible one.
        # F18 found this the hard way: one circuit crossed the VIF gate on the
        # wider data, became the era's only identified fit, and inverted the sign
        # of the 2026 mass transform for every circuit downstream.
        return None
    return pooled


def _clean_mask(laps: pd.DataFrame) -> tuple[pd.Series, int]:
    """The 5.3.4 laps this regression may see, and how many were dropped for having no
    tyre age. Both callers must use the identical mask: the degradation fitter works on
    this one's partial residuals, so a lap in one frame and not the other would silently
    misattribute the age term.

    `tyre_life` earns its place in the mask because it is a regressor here, not merely a
    column. FastF1's TyreLife is patchy on the older seasons, and an absent age reached
    LAPACK as a NaN and took the whole battery down rather than excluding one lap (E-09).
    """
    usable = (
        laps["is_green"]
        & laps["is_accurate"]
        & laps["lap_time_s"].notna()
        & laps["pit_in_time_s"].isna()
        & laps["pit_out_time_s"].isna()
    )
    has_age = laps["tyre_life"].notna()
    return usable & has_age, int((usable & ~has_age).sum())


def _refuse_validation_rounds(laps: pd.DataFrame, calibration_rounds: list[int]) -> None:
    held_out = laps["season"].ge(FIRST_2026_SEASON) & ~laps["round"].isin(calibration_rounds)
    if held_out.any():
        rounds = sorted(laps.loc[held_out, "round"].unique())
        raise ValueError(
            f"2026 round(s) {', '.join(map(str, rounds))} are held-out validation "
            f"data — the frozen split calibrates on rounds {calibration_rounds} (E-14)"
        )


def _design_matrix(fit_laps: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    n = len(fit_laps)
    columns: list[np.ndarray] = [np.ones(n)]
    names = ["intercept"]

    for field in ("session_id", "driver", "compound"):
        levels = sorted(fit_laps[field].unique())
        for level in levels[1:]:  # drop-one: the first level is the baseline
            columns.append((fit_laps[field] == level).to_numpy(dtype=float))
            names.append(f"{field.replace('session_id', 'session')}={level}")

    age = fit_laps["tyre_life"].to_numpy(dtype=float)
    for compound in sorted(fit_laps["compound"].unique()):
        on_compound = (fit_laps["compound"] == compound).to_numpy(dtype=float)
        columns += [age * on_compound, age**2 * on_compound]
        names += [f"age:{compound}", f"age2:{compound}"]

    columns.append(fit_laps["fuel_kg"].to_numpy(dtype=float))
    names.append("fuel_kg")
    columns.append(fit_laps["lap_number"].to_numpy(dtype=float))
    names.append("lap_number")
    return np.column_stack(columns), names


def _lstsq(design: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, int]:
    coef, _, rank, _ = np.linalg.lstsq(design, target, rcond=None)
    return coef, int(rank)


def _vif(design: np.ndarray, fuel_index: int) -> float:
    """VIF of the fuel column: 1 / (1 - R^2) against every other regressor."""
    fuel = design[:, fuel_index]
    others = np.delete(design, fuel_index, axis=1)
    fitted = others @ np.linalg.lstsq(others, fuel, rcond=None)[0]
    ss_res = float(np.sum((fuel - fitted) ** 2))
    ss_tot = float(np.sum((fuel - fuel.mean()) ** 2))
    if ss_tot == 0.0:
        return np.inf
    r_squared = 1.0 - ss_res / ss_tot
    return np.inf if r_squared >= 1.0 - 1e-12 else 1.0 / (1.0 - r_squared)


def _condition_number(design: np.ndarray, names: list[str]) -> float:
    """Condition number of the z-scored continuous block (fuel, lap, age terms)."""
    continuous = [
        i
        for i, name in enumerate(names)
        if name in ("fuel_kg", "lap_number") or name.startswith(("age:", "age2:"))
    ]
    block = design[:, continuous]
    spread = block.std(axis=0)
    varying = spread > 0
    z_scored = (block[:, varying] - block[:, varying].mean(axis=0)) / spread[varying]
    return float(np.linalg.cond(z_scored))


def _within_session_slope(fit_laps: pd.DataFrame) -> float:
    """Pooled OLS slope of constructed fuel on lap_number, kg per lap (< 0)."""
    numerator = 0.0
    denominator = 0.0
    for _, session in fit_laps.groupby("session_id"):
        lap = session["lap_number"].to_numpy(dtype=float)
        fuel = session["fuel_kg"].to_numpy(dtype=float)
        numerator += float(np.sum((lap - lap.mean()) * (fuel - fuel.mean())))
        denominator += float(np.sum((lap - lap.mean()) ** 2))
    return numerator / denominator


def _coefficient_se(
    design: np.ndarray, target: np.ndarray, coef: np.ndarray, index: int
) -> float:
    residuals = target - design @ coef
    dof = max(design.shape[0] - design.shape[1], 1)
    sigma_squared = float(residuals @ residuals) / dof
    covariance = sigma_squared * np.linalg.pinv(design.T @ design)
    return float(np.sqrt(covariance[index, index]))


def _splice_fuel_zero(trend_coef: np.ndarray, names: list[str], kept: list[int]) -> np.ndarray:
    coef = np.zeros(len(names))
    coef[kept] = trend_coef
    return coef


def _effects(coef: np.ndarray, names: list[str], prefix: str, n_groups: int) -> np.ndarray:
    fitted = [coef[i] for i, name in enumerate(names) if name.startswith(prefix)]
    if n_groups > len(fitted):  # the dropped baseline level sits at zero
        fitted = [0.0, *fitted]
    return np.asarray(fitted)
