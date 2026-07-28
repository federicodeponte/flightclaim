from decimal import Decimal

import pytest

from flightclaim.compensation import (
    DistanceBand,
    article_7_rerouting_reduction_applies,
    base_compensation_eur,
    distance_band,
    downgrade_percentage,
    downgrade_reimbursement_eur,
    great_circle_distance_km,
    long_delay_reduction_applies,
)


@pytest.mark.parametrize(
    ("distance", "intra_community", "band", "amount"),
    (
        (1_500, False, DistanceBand.SHORT, Decimal("250")),
        (1_500.01, False, DistanceBand.MIDDLE, Decimal("400")),
        (3_500, False, DistanceBand.MIDDLE, Decimal("400")),
        (3_500.01, False, DistanceBand.LONG, Decimal("600")),
        (5_000, True, DistanceBand.MIDDLE, Decimal("400")),
    ),
)
def test_article_7_distance_bands(
    distance: float,
    intra_community: bool,
    band: DistanceBand,
    amount: Decimal,
) -> None:
    assert distance_band(distance, intra_community_flight=intra_community) is band
    assert (
        base_compensation_eur(distance, intra_community_flight=intra_community)
        == amount
    )


@pytest.mark.parametrize(
    ("distance", "arrival_difference", "expected"),
    (
        (1_000, 120, True),
        (1_000, 120.01, False),
        (2_000, 180, True),
        (2_000, 180.01, False),
        (4_000, 240, True),
        (4_000, 240.01, False),
        (4_000, -300, True),
    ),
)
def test_article_7_2_rerouting_reduction_thresholds(
    distance: float, arrival_difference: float, expected: bool
) -> None:
    assert (
        article_7_rerouting_reduction_applies(
            distance,
            arrival_difference,
            rerouting_offered=True,
        )
        is expected
    )


def test_article_7_2_requires_rerouting_offer() -> None:
    assert not article_7_rerouting_reduction_applies(
        1_000,
        60,
        rerouting_offered=False,
    )


@pytest.mark.parametrize(
    ("delay", "expected"),
    (
        (179.99, False),
        (180, True),
        (239.99, True),
        (240, False),
    ),
)
def test_sturgeon_long_delay_reduction(delay: float, expected: bool) -> None:
    assert long_delay_reduction_applies(4_000, delay) is expected
    assert not long_delay_reduction_applies(3_000, delay)


@pytest.mark.parametrize(
    ("distance", "intra", "overseas", "rate"),
    (
        (1_500, False, False, Decimal("0.30")),
        (2_000, False, False, Decimal("0.50")),
        (4_000, False, False, Decimal("0.75")),
        (4_000, True, False, Decimal("0.50")),
        (4_000, True, True, Decimal("0.75")),
    ),
)
def test_downgrade_percentages(
    distance: float, intra: bool, overseas: bool, rate: Decimal
) -> None:
    assert (
        downgrade_percentage(
            distance,
            intra_community_flight=intra,
            french_overseas_route=overseas,
        )
        == rate
    )


def test_downgrade_reimbursement_rounds_to_cents() -> None:
    assert downgrade_reimbursement_eur(Decimal("123.45"), 1_000) == Decimal("37.04")


def test_great_circle_distance() -> None:
    assert great_circle_distance_km(0, 0, 0, 1) == pytest.approx(111.195, abs=0.01)


@pytest.mark.parametrize(
    "coordinates",
    (
        (91, 0, 0, 0),
        (0, 181, 0, 0),
        (0, 0, -91, 0),
        (0, 0, 0, -181),
    ),
)
def test_great_circle_rejects_invalid_coordinates(
    coordinates: tuple[float, float, float, float],
) -> None:
    with pytest.raises(ValueError):
        great_circle_distance_km(*coordinates)
