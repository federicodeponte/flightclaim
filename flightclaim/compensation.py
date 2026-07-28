"""Compensation calculations from Articles 7 and 10 of EC 261/2004."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6_371.0088


class DistanceBand(str, Enum):
    """Article 7 distance categories."""

    SHORT = "short"
    MIDDLE = "middle"
    LONG = "long"


def _validate_distance(distance_km: float) -> None:
    if distance_km <= 0:
        raise ValueError("distance_km must be greater than zero")


def distance_band(
    distance_km: float, *, intra_community_flight: bool = False
) -> DistanceBand:
    """Return the Article 7 band for a great-circle distance.

    Intra-Community flights longer than 1,500 km remain in the EUR 400 band.
    Other flights longer than 3,500 km fall in the EUR 600 band.
    """

    _validate_distance(distance_km)
    if distance_km <= 1_500:
        return DistanceBand.SHORT
    if intra_community_flight or distance_km <= 3_500:
        return DistanceBand.MIDDLE
    return DistanceBand.LONG


def base_compensation_eur(
    distance_km: float, *, intra_community_flight: bool = False
) -> Decimal:
    """Return the fixed amount in Article 7(1)."""

    band = distance_band(distance_km, intra_community_flight=intra_community_flight)
    return {
        DistanceBand.SHORT: Decimal("250"),
        DistanceBand.MIDDLE: Decimal("400"),
        DistanceBand.LONG: Decimal("600"),
    }[band]


def rerouting_arrival_limit_minutes(
    distance_km: float, *, intra_community_flight: bool = False
) -> int:
    """Return the Article 7(2) arrival threshold for alternative transport."""

    band = distance_band(distance_km, intra_community_flight=intra_community_flight)
    return {
        DistanceBand.SHORT: 120,
        DistanceBand.MIDDLE: 180,
        DistanceBand.LONG: 240,
    }[band]


def article_7_rerouting_reduction_applies(
    distance_km: float,
    arrival_difference_minutes: float,
    *,
    intra_community_flight: bool = False,
    rerouting_offered: bool,
) -> bool:
    """Return whether Article 7(2) permits a 50% reduction.

    The reduction is available only when the passenger was offered re-routing
    under Article 8 and the alternative arrival does not exceed the original
    scheduled arrival by the applicable two, three, or four-hour threshold.
    An early arrival therefore meets the arrival-time part of Article 7(2).
    """

    if not rerouting_offered:
        return False
    limit = rerouting_arrival_limit_minutes(
        distance_km, intra_community_flight=intra_community_flight
    )
    return arrival_difference_minutes <= limit


def long_delay_reduction_applies(
    distance_km: float,
    arrival_delay_minutes: float,
    *,
    intra_community_flight: bool = False,
) -> bool:
    """Return whether Sturgeon permits a 50% reduction for a long delay.

    For a non-Intra-Community journey over 3,500 km, compensation for an
    arrival delay of at least three but less than four hours may be halved.
    """

    band = distance_band(distance_km, intra_community_flight=intra_community_flight)
    return band is DistanceBand.LONG and 180 <= arrival_delay_minutes < 240


def reduced_compensation_eur(amount_eur: Decimal) -> Decimal:
    """Apply the maximum 50% reduction permitted by Article 7(2)."""

    if amount_eur < 0:
        raise ValueError("amount_eur cannot be negative")
    return (amount_eur / Decimal("2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def downgrade_percentage(
    distance_km: float,
    *,
    intra_community_flight: bool = False,
    french_overseas_route: bool = False,
) -> Decimal:
    """Return the Article 10(2) downgrade reimbursement percentage.

    ``french_overseas_route`` handles the Article 10 exception that places
    flights between EU territory and French overseas departments in the 75%
    category.
    """

    _validate_distance(distance_km)
    if distance_km <= 1_500:
        return Decimal("0.30")
    if french_overseas_route:
        return Decimal("0.75")
    if intra_community_flight or distance_km <= 3_500:
        return Decimal("0.50")
    return Decimal("0.75")


def downgrade_reimbursement_eur(
    affected_flight_fare_eur: Decimal,
    distance_km: float,
    *,
    intra_community_flight: bool = False,
    french_overseas_route: bool = False,
) -> Decimal:
    """Calculate Article 10 reimbursement for the downgraded flight.

    The input is the fare attributable to the affected flight, excluding taxes
    and charges that do not depend on travel class, following CJEU C-255/15.
    """

    if affected_flight_fare_eur < 0:
        raise ValueError("affected_flight_fare_eur cannot be negative")
    percentage = downgrade_percentage(
        distance_km,
        intra_community_flight=intra_community_flight,
        french_overseas_route=french_overseas_route,
    )
    return (affected_flight_fare_eur * percentage).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def great_circle_distance_km(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:
    """Return the haversine great-circle distance in kilometres."""

    for label, value, lower, upper in (
        ("latitude_1", latitude_1, -90, 90),
        ("latitude_2", latitude_2, -90, 90),
        ("longitude_1", longitude_1, -180, 180),
        ("longitude_2", longitude_2, -180, 180),
    ):
        if not lower <= value <= upper:
            raise ValueError(f"{label} must be between {lower} and {upper}")

    lat_1, lon_1, lat_2, lon_2 = map(
        radians, (latitude_1, longitude_1, latitude_2, longitude_2)
    )
    delta_latitude = lat_2 - lat_1
    delta_longitude = lon_2 - lon_1
    haversine = (
        sin(delta_latitude / 2) ** 2
        + cos(lat_1) * cos(lat_2) * sin(delta_longitude / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * asin(sqrt(haversine))
