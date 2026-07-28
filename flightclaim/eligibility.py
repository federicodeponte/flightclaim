"""Decision engine for common EC 261/2004 disruption categories."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from .compensation import (
    article_7_rerouting_reduction_applies,
    base_compensation_eur,
    distance_band,
    downgrade_percentage,
    downgrade_reimbursement_eur,
    long_delay_reduction_applies,
    reduced_compensation_eur,
    rerouting_arrival_limit_minutes,
)


class DisruptionType(str, Enum):
    """Disruptions handled by the decision engine."""

    CANCELLATION = "cancellation"
    DENIED_BOARDING = "denied_boarding"
    DELAY = "delay"
    DOWNGRADE = "downgrade"
    MISSED_CONNECTION = "missed_connection"


@dataclass(frozen=True)
class ClaimInputs:
    """Facts needed to evaluate one passenger's journey.

    Datetimes must include UTC offsets. For cancellation and denied boarding,
    actual times represent the offered replacement itinerary when
    ``rerouting_offered`` is true. Arrival means arrival at the final
    destination on the ticket.
    """

    disruption_type: DisruptionType
    distance_km: float
    departed_from_eu_eea: bool
    arrived_in_eu_eea: bool
    operating_carrier_is_eu_eea: bool
    intra_community_flight: bool = False
    notice_days_before_departure: float | None = None
    scheduled_departure: datetime | None = None
    actual_departure: datetime | None = None
    scheduled_arrival: datetime | None = None
    actual_arrival: datetime | None = None
    rerouting_offered: bool = False
    extraordinary_circumstances_proven: bool = False
    confirmed_reservation: bool = True
    presented_for_boarding_on_time: bool = True
    denied_boarding_was_voluntary: bool = False
    reasonable_denial_grounds: bool = False
    affected_flight_fare_eur: Decimal | None = None
    french_overseas_route: bool = False


@dataclass(frozen=True)
class Verdict:
    """A structured, explainable assessment.

    ``entitled`` concerns calculable Article 7 compensation or Article 10
    reimbursement. Article 9 care is reported independently because it can
    remain available even when Article 7 compensation is not.
    """

    entitled: bool
    compensation_entitled: bool
    care_entitled: bool | None
    amount_eur: Decimal | None
    amount_before_reduction_eur: Decimal | None
    reduction_applied: bool
    legal_basis: tuple[str, ...]
    reasoning: tuple[str, ...]
    evidence_to_collect: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""

        result = asdict(self)
        for key in ("amount_eur", "amount_before_reduction_eur"):
            value = result[key]
            result[key] = None if value is None else str(value)
        return result


COMMON_EVIDENCE = (
    "Booking confirmation or other proof of a confirmed reservation.",
    "Original itinerary showing scheduled departure and final-arrival times.",
    "Proof identifying the operating carrier, not only the ticket seller.",
    "All carrier notices and correspondence, with the original email thread preserved.",
)

DISCLAIMERS = (
    "Not legal advice. Verify the result with the competent national enforcement body or a qualified adviser.",
    "This assessment assumes the entered facts are accurate and that no exclusion in Article 3 applies.",
)


def _minutes(delta: timedelta) -> float:
    return delta.total_seconds() / 60


def _validate_datetime(value: datetime | None, name: str) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{name} must include a UTC offset")


def _validate(inputs: ClaimInputs) -> None:
    if inputs.distance_km <= 0:
        raise ValueError("distance_km must be greater than zero")
    if (
        inputs.notice_days_before_departure is not None
        and inputs.notice_days_before_departure < 0
    ):
        raise ValueError("notice_days_before_departure cannot be negative")
    if (
        inputs.affected_flight_fare_eur is not None
        and inputs.affected_flight_fare_eur < 0
    ):
        raise ValueError("affected_flight_fare_eur cannot be negative")
    for name in (
        "scheduled_departure",
        "actual_departure",
        "scheduled_arrival",
        "actual_arrival",
    ):
        _validate_datetime(getattr(inputs, name), name)


def _has_eu_nexus(inputs: ClaimInputs) -> bool:
    return inputs.departed_from_eu_eea or (
        inputs.arrived_in_eu_eea and inputs.operating_carrier_is_eu_eea
    )


def _required_pair(
    inputs: ClaimInputs, first: str, second: str, context: str
) -> tuple[datetime, datetime]:
    first_value = getattr(inputs, first)
    second_value = getattr(inputs, second)
    if first_value is None or second_value is None:
        raise ValueError(f"{first} and {second} are required {context}")
    return first_value, second_value


def _care_entitlement(inputs: ClaimInputs) -> tuple[bool | None, tuple[str, ...]]:
    if inputs.disruption_type in (
        DisruptionType.CANCELLATION,
        DisruptionType.DENIED_BOARDING,
    ):
        return True, (
            "Articles 4(3) or 5(1)(b) refer to Article 9 care independently of the final arrival time.",
        )
    if inputs.disruption_type is DisruptionType.DOWNGRADE:
        return False, (
            "A downgrade alone triggers Article 10 reimbursement, not Article 9 care.",
        )
    if inputs.scheduled_departure is None or inputs.actual_departure is None:
        return None, (
            "Article 6 care depends on the expected departure delay; provide scheduled and actual departure times to assess it.",
        )

    departure_delay = _minutes(inputs.actual_departure - inputs.scheduled_departure)
    band = distance_band(
        inputs.distance_km,
        intra_community_flight=inputs.intra_community_flight,
    )
    threshold = {"short": 120, "middle": 180, "long": 240}[band.value]
    entitled = departure_delay >= threshold
    comparison = "meets" if entitled else "does not meet"
    return entitled, (
        f"The expected departure delay is {departure_delay:.0f} minutes and {comparison} the Article 6 care threshold of {threshold} minutes.",
    )


def _evidence(inputs: ClaimInputs, care_entitled: bool | None) -> tuple[str, ...]:
    items = list(COMMON_EVIDENCE)
    if inputs.disruption_type is DisruptionType.CANCELLATION:
        items.extend(
            (
                "Cancellation notice showing when it was received.",
                "The complete re-routing offer, including replacement departure and final-arrival times.",
            )
        )
    elif inputs.disruption_type is DisruptionType.DENIED_BOARDING:
        items.extend(
            (
                "Proof of timely presentation for boarding and valid travel documents.",
                "A written reason for refusal and evidence showing whether the booked flight operated.",
            )
        )
    elif inputs.disruption_type in (
        DisruptionType.DELAY,
        DisruptionType.MISSED_CONNECTION,
    ):
        items.extend(
            (
                "Evidence of actual arrival at the final destination; door-opening time if available.",
                "For a connection, one ticket or reservation showing all directly connecting legs.",
            )
        )
    else:
        items.append(
            "Ticket and fare breakdown for the downgraded flight, including class-dependent fare and taxes."
        )
    if care_entitled is not False:
        items.append(
            "Itemised receipts for reasonable meals, accommodation, and airport-to-accommodation transport."
        )
    if inputs.extraordinary_circumstances_proven:
        items.append(
            "The carrier's specific proof of the extraordinary event and of all reasonable measures taken."
        )
    return tuple(items)


def _outside_scope(inputs: ClaimInputs) -> Verdict:
    reasoning = (
        "Article 3 nexus is absent: the journey neither departed from the EU/EEA nor arrived there on an EU/EEA operating carrier.",
        "The tool cannot assess rights under another passenger-rights regime.",
    )
    return Verdict(
        entitled=False,
        compensation_entitled=False,
        care_entitled=False,
        amount_eur=Decimal("0"),
        amount_before_reduction_eur=Decimal("0"),
        reduction_applied=False,
        legal_basis=("Regulation (EC) No 261/2004, Article 3",),
        reasoning=reasoning,
        evidence_to_collect=_evidence(inputs, False),
        warnings=DISCLAIMERS,
    )


def _cancellation_compensation(
    inputs: ClaimInputs,
) -> tuple[bool, list[str], list[str]]:
    if inputs.notice_days_before_departure is None:
        raise ValueError("notice_days_before_departure is required for cancellation")

    notice = inputs.notice_days_before_departure
    day_label = "day" if notice == 1 else "days"
    reasoning = [
        f"Cancellation notice was given {notice:g} {day_label} before departure."
    ]
    basis = ["Article 5(1)(c)", "Article 7(1)"]

    if inputs.extraordinary_circumstances_proven:
        reasoning.append(
            "The extraordinary-circumstances flag means the carrier has proved both an extraordinary event and that it could not be avoided despite all reasonable measures; Article 5(3) removes Article 7 compensation."
        )
        return False, reasoning, basis + ["Article 5(3)"]

    if notice >= 14:
        reasoning.append(
            "Article 5(1)(c)(i) exempts the carrier from Article 7 compensation when notice is given at least two weeks before departure."
        )
        return False, reasoning, basis

    if not inputs.rerouting_offered:
        reasoning.append(
            "No re-routing was offered, so the timing exemption in Article 5(1)(c)(ii) or (iii) is unavailable."
        )
        return True, reasoning, basis

    scheduled_departure, replacement_departure = _required_pair(
        inputs,
        "scheduled_departure",
        "actual_departure",
        "when cancellation re-routing was offered",
    )
    scheduled_arrival, replacement_arrival = _required_pair(
        inputs,
        "scheduled_arrival",
        "actual_arrival",
        "when cancellation re-routing was offered",
    )

    if notice >= 7:
        early_limit = timedelta(hours=2)
        late_limit = timedelta(hours=4)
        provision = "Article 5(1)(c)(ii)"
    else:
        early_limit = timedelta(hours=1)
        late_limit = timedelta(hours=2)
        provision = "Article 5(1)(c)(iii)"

    departure_limb = replacement_departure >= scheduled_departure - early_limit
    arrival_limb = replacement_arrival < scheduled_arrival + late_limit
    departure_difference = _minutes(replacement_departure - scheduled_departure)
    arrival_difference = _minutes(replacement_arrival - scheduled_arrival)
    reasoning.extend(
        (
            f"Replacement departure differs from the passenger's own originally scheduled departure by {departure_difference:+.0f} minutes; the {provision} departure limb is {'met' if departure_limb else 'not met'}.",
            f"Replacement final arrival differs from the originally scheduled final arrival by {arrival_difference:+.0f} minutes; the strict {provision} arrival limb is {'met' if arrival_limb else 'not met'}.",
        )
    )

    if departure_limb and arrival_limb:
        reasoning.append(
            f"Both limbs are met, so {provision} exempts the carrier from Article 7 compensation on the cancellation theory."
        )
        return False, reasoning, basis

    reasoning.append(
        f"Both timing limbs are required; because at least one fails, {provision} does not exempt the carrier."
    )
    return True, reasoning, basis


def _denied_boarding_compensation(
    inputs: ClaimInputs,
) -> tuple[bool, list[str], list[str]]:
    basis = ["Article 2(j)", "Article 4(3)", "Article 7(1)"]
    reasoning: list[str] = []
    if not inputs.confirmed_reservation:
        reasoning.append(
            "Article 3(2) requires a confirmed reservation; the entered facts do not establish one."
        )
        return False, reasoning, basis
    if inputs.denied_boarding_was_voluntary:
        reasoning.append(
            "Article 4 distinguishes volunteers from passengers denied boarding against their will; the entered surrender was voluntary."
        )
        return False, reasoning, basis
    if not inputs.presented_for_boarding_on_time:
        reasoning.append(
            "The Article 2(j) definition is not met because the passenger did not present for boarding under Article 3(2)."
        )
        return False, reasoning, basis
    if inputs.reasonable_denial_grounds:
        reasoning.append(
            "Article 2(j) excludes refusals based on reasonable grounds such as health, safety, security, or inadequate travel documentation."
        )
        return False, reasoning, basis

    reasoning.extend(
        (
            "The facts meet the Article 2(j) definition of involuntary denied boarding.",
            "Article 4(3) refers directly to Article 7 and contains no Article 5(1)(c) cancellation re-routing exemption.",
            "An early arrival therefore does not erase entitlement, although Article 7(2) may permit a 50% reduction.",
        )
    )
    if inputs.extraordinary_circumstances_proven:
        reasoning.append(
            "Article 5(3) is not an exemption to Article 4(3) denied-boarding compensation."
        )
    return True, reasoning, basis


def _delay_compensation(
    inputs: ClaimInputs,
) -> tuple[bool, list[str], list[str], float]:
    scheduled_arrival, actual_arrival = _required_pair(
        inputs,
        "scheduled_arrival",
        "actual_arrival",
        "for delay or missed-connection assessment",
    )
    arrival_delay = _minutes(actual_arrival - scheduled_arrival)
    basis = ["Article 7(1)", "Sturgeon, Joined Cases C-402/07 and C-432/07"]
    if inputs.disruption_type is DisruptionType.MISSED_CONNECTION:
        basis.append("Folkerts, C-11/11")
    reasoning = [
        f"Arrival at the final destination was delayed by {arrival_delay:.0f} minutes."
    ]
    if arrival_delay < 180:
        reasoning.append(
            "Sturgeon compensation requires an arrival delay of at least three hours."
        )
        return False, reasoning, basis, arrival_delay
    if inputs.disruption_type is DisruptionType.MISSED_CONNECTION:
        reasoning.append(
            "Under Folkerts, the delay at the final destination controls even when the first leg's departure delay was below Article 6 thresholds."
        )
    else:
        reasoning.append(
            "The three-hour final-arrival threshold established in Sturgeon is met."
        )
    if inputs.extraordinary_circumstances_proven:
        reasoning.append(
            "The extraordinary-circumstances flag means the carrier has proved the event and all reasonable measures; Article 5(3), as applied to long delay by Sturgeon, removes Article 7 compensation."
        )
        return False, reasoning, basis + ["Article 5(3)"], arrival_delay
    return True, reasoning, basis, arrival_delay


def _downgrade_verdict(
    inputs: ClaimInputs, care_entitled: bool | None, care_reasoning: tuple[str, ...]
) -> Verdict:
    percentage = downgrade_percentage(
        inputs.distance_km,
        intra_community_flight=inputs.intra_community_flight,
        french_overseas_route=inputs.french_overseas_route,
    )
    amount = None
    if inputs.affected_flight_fare_eur is not None:
        amount = downgrade_reimbursement_eur(
            inputs.affected_flight_fare_eur,
            inputs.distance_km,
            intra_community_flight=inputs.intra_community_flight,
            french_overseas_route=inputs.french_overseas_route,
        )
    reasoning = [
        f"Article 10(2) requires reimbursement of {percentage * 100:.0f}% of the fare attributable to the downgraded flight.",
        "CJEU C-255/15 limits the calculation to the affected flight and excludes taxes or charges unrelated to travel class.",
    ]
    if amount is None:
        reasoning.append(
            "No affected-flight fare was supplied, so the entitlement is established but the euro amount cannot be calculated."
        )
    else:
        reasoning.append(f"Applying the Article 10 percentage gives EUR {amount:.2f}.")
    reasoning.extend(care_reasoning)
    return Verdict(
        entitled=True,
        compensation_entitled=True,
        care_entitled=care_entitled,
        amount_eur=amount,
        amount_before_reduction_eur=amount,
        reduction_applied=False,
        legal_basis=("Article 10(2)", "CJEU C-255/15"),
        reasoning=tuple(reasoning),
        evidence_to_collect=_evidence(inputs, care_entitled),
        warnings=DISCLAIMERS,
    )


def evaluate_claim(inputs: ClaimInputs) -> Verdict:
    """Evaluate fixed compensation, downgrade reimbursement, and care rights."""

    _validate(inputs)
    if not _has_eu_nexus(inputs):
        return _outside_scope(inputs)

    care_entitled, care_reasoning = _care_entitlement(inputs)
    if inputs.disruption_type is DisruptionType.DOWNGRADE:
        return _downgrade_verdict(inputs, care_entitled, care_reasoning)

    arrival_delay: float | None = None
    if inputs.disruption_type is DisruptionType.CANCELLATION:
        compensation_entitled, reasoning, basis = _cancellation_compensation(inputs)
    elif inputs.disruption_type is DisruptionType.DENIED_BOARDING:
        compensation_entitled, reasoning, basis = _denied_boarding_compensation(inputs)
    else:
        (
            compensation_entitled,
            reasoning,
            basis,
            arrival_delay,
        ) = _delay_compensation(inputs)

    reasoning.extend(care_reasoning)
    if not compensation_entitled:
        return Verdict(
            entitled=False,
            compensation_entitled=False,
            care_entitled=care_entitled,
            amount_eur=Decimal("0"),
            amount_before_reduction_eur=Decimal("0"),
            reduction_applied=False,
            legal_basis=tuple(basis),
            reasoning=tuple(reasoning),
            evidence_to_collect=_evidence(inputs, care_entitled),
            warnings=DISCLAIMERS,
        )

    base_amount = base_compensation_eur(
        inputs.distance_km,
        intra_community_flight=inputs.intra_community_flight,
    )
    reduction = False
    if (
        inputs.disruption_type
        in (
            DisruptionType.CANCELLATION,
            DisruptionType.DENIED_BOARDING,
        )
        and inputs.rerouting_offered
    ):
        scheduled_arrival, actual_arrival = _required_pair(
            inputs,
            "scheduled_arrival",
            "actual_arrival",
            "to assess an Article 7(2) re-routing reduction",
        )
        arrival_difference = _minutes(actual_arrival - scheduled_arrival)
        reduction = article_7_rerouting_reduction_applies(
            inputs.distance_km,
            arrival_difference,
            intra_community_flight=inputs.intra_community_flight,
            rerouting_offered=True,
        )
        limit = rerouting_arrival_limit_minutes(
            inputs.distance_km,
            intra_community_flight=inputs.intra_community_flight,
        )
        reasoning.append(
            f"The alternative arrival difference is {arrival_difference:+.0f} minutes against the Article 7(2) limit of {limit} minutes; a 50% reduction is {'permitted' if reduction else 'not permitted'}."
        )
    elif (
        inputs.disruption_type
        in (DisruptionType.DELAY, DisruptionType.MISSED_CONNECTION)
        and arrival_delay is not None
    ):
        reduction = long_delay_reduction_applies(
            inputs.distance_km,
            arrival_delay,
            intra_community_flight=inputs.intra_community_flight,
        )
        if reduction:
            reasoning.append(
                "For a non-Intra-Community journey over 3,500 km delayed between three and four hours, Sturgeon permits the Article 7 amount to be reduced by 50%."
            )

    amount = reduced_compensation_eur(base_amount) if reduction else base_amount
    return Verdict(
        entitled=True,
        compensation_entitled=True,
        care_entitled=care_entitled,
        amount_eur=amount,
        amount_before_reduction_eur=base_amount,
        reduction_applied=reduction,
        legal_basis=tuple(basis + (["Article 7(2)"] if reduction else [])),
        reasoning=tuple(reasoning),
        evidence_to_collect=_evidence(inputs, care_entitled),
        warnings=DISCLAIMERS,
    )
