from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from flightclaim.eligibility import ClaimInputs, DisruptionType, evaluate_claim

UTC = timezone.utc
ORIGINAL_DEPARTURE = datetime(2030, 1, 1, 8, tzinfo=UTC)
ORIGINAL_ARRIVAL = datetime(2030, 1, 2, 18, tzinfo=UTC)


def base_inputs(disruption: DisruptionType, **overrides: object) -> ClaimInputs:
    values: dict[str, object] = {
        "disruption_type": disruption,
        "distance_km": 4_200,
        "departed_from_eu_eea": True,
        "arrived_in_eu_eea": False,
        "operating_carrier_is_eu_eea": False,
        "intra_community_flight": False,
    }
    values.update(overrides)
    return ClaimInputs(**values)  # type: ignore[arg-type]


def test_denied_boarding_with_early_arrival_is_still_owed() -> None:
    verdict = evaluate_claim(
        base_inputs(
            DisruptionType.DENIED_BOARDING,
            rerouting_offered=True,
            scheduled_arrival=ORIGINAL_ARRIVAL,
            actual_arrival=ORIGINAL_ARRIVAL - timedelta(hours=2),
        )
    )

    assert verdict.entitled
    assert verdict.compensation_entitled
    assert verdict.care_entitled
    assert verdict.amount_before_reduction_eur == Decimal("600")
    assert verdict.amount_eur == Decimal("300.00")
    assert verdict.reduction_applied
    assert "Article 4(3)" in verdict.legal_basis
    assert any("does not erase entitlement" in reason for reason in verdict.reasoning)


def test_cancellation_later_departure_earlier_arrival_is_exempt() -> None:
    verdict = evaluate_claim(
        base_inputs(
            DisruptionType.CANCELLATION,
            notice_days_before_departure=1,
            rerouting_offered=True,
            scheduled_departure=ORIGINAL_DEPARTURE,
            actual_departure=ORIGINAL_DEPARTURE + timedelta(hours=8),
            scheduled_arrival=ORIGINAL_ARRIVAL,
            actual_arrival=ORIGINAL_ARRIVAL - timedelta(hours=5),
        )
    )

    assert not verdict.entitled
    assert not verdict.compensation_entitled
    assert verdict.care_entitled
    assert verdict.amount_eur == Decimal("0")
    assert any("Both limbs are met" in reason for reason in verdict.reasoning)


def test_cancellation_test_uses_strict_arrival_boundary() -> None:
    verdict = evaluate_claim(
        base_inputs(
            DisruptionType.CANCELLATION,
            notice_days_before_departure=1,
            rerouting_offered=True,
            scheduled_departure=ORIGINAL_DEPARTURE,
            actual_departure=ORIGINAL_DEPARTURE,
            scheduled_arrival=ORIGINAL_ARRIVAL,
            actual_arrival=ORIGINAL_ARRIVAL + timedelta(hours=2),
        )
    )

    assert verdict.entitled
    assert verdict.reduction_applied
    assert verdict.amount_eur == Decimal("300.00")


def test_cancellation_beyond_article_7_2_window_is_full_amount() -> None:
    verdict = evaluate_claim(
        base_inputs(
            DisruptionType.CANCELLATION,
            notice_days_before_departure=1,
            rerouting_offered=True,
            scheduled_departure=ORIGINAL_DEPARTURE,
            actual_departure=ORIGINAL_DEPARTURE,
            scheduled_arrival=ORIGINAL_ARRIVAL,
            actual_arrival=ORIGINAL_ARRIVAL + timedelta(hours=4, seconds=1),
        )
    )

    assert verdict.entitled
    assert not verdict.reduction_applied
    assert verdict.amount_eur == Decimal("600")


def test_cancellation_exactly_seven_days_uses_two_and_four_hour_rule() -> None:
    verdict = evaluate_claim(
        base_inputs(
            DisruptionType.CANCELLATION,
            notice_days_before_departure=7,
            rerouting_offered=True,
            scheduled_departure=ORIGINAL_DEPARTURE,
            actual_departure=ORIGINAL_DEPARTURE - timedelta(hours=1, minutes=30),
            scheduled_arrival=ORIGINAL_ARRIVAL,
            actual_arrival=ORIGINAL_ARRIVAL + timedelta(hours=3),
        )
    )

    assert not verdict.entitled


def test_extraordinary_circumstances_remove_article_7_not_article_9() -> None:
    verdict = evaluate_claim(
        base_inputs(
            DisruptionType.CANCELLATION,
            notice_days_before_departure=0,
            extraordinary_circumstances_proven=True,
        )
    )

    assert not verdict.compensation_entitled
    assert verdict.care_entitled
    assert verdict.amount_eur == Decimal("0")
    assert "Article 5(3)" in verdict.legal_basis


def test_extraordinary_delay_keeps_care_when_departure_threshold_met() -> None:
    verdict = evaluate_claim(
        base_inputs(
            DisruptionType.DELAY,
            distance_km=1_000,
            scheduled_departure=ORIGINAL_DEPARTURE,
            actual_departure=ORIGINAL_DEPARTURE + timedelta(hours=4),
            scheduled_arrival=ORIGINAL_ARRIVAL,
            actual_arrival=ORIGINAL_ARRIVAL + timedelta(hours=4),
            extraordinary_circumstances_proven=True,
        )
    )

    assert not verdict.compensation_entitled
    assert verdict.care_entitled


def test_long_delay_between_three_and_four_hours_is_halved() -> None:
    verdict = evaluate_claim(
        base_inputs(
            DisruptionType.DELAY,
            scheduled_arrival=ORIGINAL_ARRIVAL,
            actual_arrival=ORIGINAL_ARRIVAL + timedelta(hours=3, minutes=30),
        )
    )

    assert verdict.compensation_entitled
    assert verdict.reduction_applied
    assert verdict.amount_eur == Decimal("300.00")


def test_long_delay_at_four_hours_is_full_amount() -> None:
    verdict = evaluate_claim(
        base_inputs(
            DisruptionType.DELAY,
            scheduled_arrival=ORIGINAL_ARRIVAL,
            actual_arrival=ORIGINAL_ARRIVAL + timedelta(hours=4),
        )
    )

    assert verdict.compensation_entitled
    assert not verdict.reduction_applied
    assert verdict.amount_eur == Decimal("600")


def test_folkerts_final_destination_delay_controls() -> None:
    verdict = evaluate_claim(
        base_inputs(
            DisruptionType.MISSED_CONNECTION,
            distance_km=2_000,
            scheduled_departure=ORIGINAL_DEPARTURE,
            actual_departure=ORIGINAL_DEPARTURE + timedelta(minutes=30),
            scheduled_arrival=ORIGINAL_ARRIVAL,
            actual_arrival=ORIGINAL_ARRIVAL + timedelta(hours=3),
        )
    )

    assert verdict.compensation_entitled
    assert verdict.amount_eur == Decimal("400")
    assert not verdict.care_entitled
    assert "Folkerts, C-11/11" in verdict.legal_basis


def test_downgrade_amount() -> None:
    verdict = evaluate_claim(
        base_inputs(
            DisruptionType.DOWNGRADE,
            distance_km=2_000,
            affected_flight_fare_eur=Decimal("200"),
        )
    )

    assert verdict.entitled
    assert verdict.amount_eur == Decimal("100.00")
    assert not verdict.care_entitled
    assert "Article 10(2)" in verdict.legal_basis


def test_outside_scope() -> None:
    verdict = evaluate_claim(
        ClaimInputs(
            disruption_type=DisruptionType.DELAY,
            distance_km=1_000,
            departed_from_eu_eea=False,
            arrived_in_eu_eea=True,
            operating_carrier_is_eu_eea=False,
        )
    )
    assert not verdict.entitled
    assert not verdict.care_entitled
    assert "Article 3" in verdict.legal_basis[0]


def test_denied_boarding_reasonable_ground_is_not_eligible() -> None:
    verdict = evaluate_claim(
        base_inputs(
            DisruptionType.DENIED_BOARDING,
            reasonable_denial_grounds=True,
        )
    )
    assert not verdict.compensation_entitled


def test_cancellation_requires_notice() -> None:
    with pytest.raises(ValueError, match="notice_days"):
        evaluate_claim(base_inputs(DisruptionType.CANCELLATION))


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="UTC offset"):
        evaluate_claim(
            base_inputs(
                DisruptionType.DELAY,
                scheduled_arrival=datetime(2030, 1, 1),
                actual_arrival=datetime(2030, 1, 2),
            )
        )
