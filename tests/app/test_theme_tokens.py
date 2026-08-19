"""The petrol design system's tokens, pinned to the reference sheets.

The F25 amendment replaced the sampled F23 palette with two reference images in
docs/reference_images/ (SENNA_petrol_palette_reference.png, SENNA_gradient_system.png).
Those sheets are the sourced provenance for every hex below; these tests keep the code
honest to them — including the teammate-lift rule and the luminance-monotonic SOC ramp
the dataviz validation relied on.
"""

from app import theme

# the ten reference constructors, in sheet order, after SENNA's own seat at index 0
REFERENCE_TEAMS = (
    ("Red Bull Racing", "#5A7FE8", "#93ABF0"),
    ("Ferrari", "#E4243C", "#ED7080"),
    ("Mercedes", "#A8B8C4", "#C6D0D8"),
    ("McLaren", "#FF9E1B", "#FFBF6A"),
    ("Aston Martin", "#2FA96B", "#77C79E"),
    ("Alpine", "#F05CA0", "#F595C1"),
    ("Williams", "#2C9CDB", "#75BEE7"),
    ("Racing Bulls", "#93A9F5", "#B8C7F8"),
    ("Kick Sauber", "#6FD84A", "#A1E589"),
    ("Haas", "#E2E6EA", "#ECEEF1"),
)


def _luminance(hex_colour: str) -> float:
    r, g, b = (int(hex_colour.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_the_petrol_tokens_match_the_reference_sheet():
    assert theme.GROUND == "#0A1014"
    assert theme.SURFACE == "#101A20"
    assert theme.RAISED == "#17242C"
    assert theme.LINE == "#22333D"
    assert theme.TEXT == "#E4EDF2"
    assert theme.MUTED == "#93A8B4"
    assert theme.FAINT == "#5E7583"
    assert theme.ACCENT == "#2ED9C3"
    assert theme.DEPLOY == "#FF7A3D"
    assert theme.COAST == "#7A8C99"
    assert theme.DANGER == "#FF3B5C"


def test_the_soc_ramp_climbs_in_luminance_from_empty_to_full():
    assert len(theme.SOC_RAMP) == 5
    steps = [_luminance(colour) for colour in theme.SOC_RAMP]
    assert steps == sorted(steps)
    assert len(set(steps)) == 5, "two ramp steps read as the same brightness"


def test_the_grid_has_eleven_teams_with_senna_first():
    assert len(theme.TEAMS) == 11
    name, primary, teammate = theme.TEAMS[0]
    assert name == "SENNA"
    assert primary == theme.ACCENT, "the ego carries the aqua harvest identity"
    assert teammate.startswith("#") and teammate != primary
    assert theme.TEAMS[1:] == REFERENCE_TEAMS


def test_car_zero_is_sennas_first_seat():
    assert theme.team_of(0) == ("SENNA", theme.ACCENT, False)


def test_the_odd_car_of_each_pair_is_the_teammate_on_the_lifted_hex():
    name, colour, is_teammate = theme.team_of(1)
    assert (name, colour, is_teammate) == ("SENNA", theme.TEAMS[0][2], True)
    assert theme.team_of(21) == ("Haas", "#ECEEF1", True)


def test_the_even_car_of_each_pair_carries_the_primary_hex():
    assert theme.team_of(4) == ("Ferrari", "#E4243C", False)


def test_twenty_two_cars_cover_exactly_eleven_teams_two_seats_each():
    seats: dict[str, list[bool]] = {}
    for car in range(22):
        name, _, is_teammate = theme.team_of(car)
        seats.setdefault(name, []).append(is_teammate)
    assert len(seats) == 11
    assert all(sorted(pair) == [False, True] for pair in seats.values()), \
        "every team fields one primary seat and one teammate seat"


def test_car_labels_keep_the_c01_to_c22_convention():
    assert theme.car_label(0) == "C01"
    assert theme.car_label(9) == "C10"
    assert theme.car_label(21) == "C22"
