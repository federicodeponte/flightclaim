from datetime import datetime, timedelta, timezone
from decimal import Decimal

from flightclaim.deadlines import limitation_period, listed_countries
from flightclaim.eligibility import ClaimInputs, DisruptionType, evaluate_claim
from flightclaim.letters import LetterFacts, LetterKind, generate_letter
from flightclaim.regulators import REGULATORS, regulator_for


def sample_verdict():
    scheduled = datetime(2030, 1, 1, 10, tzinfo=timezone.utc)
    return evaluate_claim(
        ClaimInputs(
            disruption_type=DisruptionType.DELAY,
            distance_km=1_000,
            departed_from_eu_eea=True,
            arrived_in_eu_eea=True,
            operating_carrier_is_eu_eea=False,
            scheduled_arrival=scheduled,
            actual_arrival=scheduled + timedelta(hours=4),
        )
    )


def test_all_letters_include_disclaimer_and_legal_basis() -> None:
    verdict = sample_verdict()
    for kind in LetterKind:
        letter = generate_letter(kind, LetterFacts(), verdict)
        assert "NOT LEGAL ADVICE" in letter
        assert "Article 7(1)" in letter
        assert letter.endswith("\n")


def test_rejection_letter_stresses_in_thread_reply() -> None:
    letter = generate_letter(
        LetterKind.REJECTION_REPLY, LetterFacts(), sample_verdict()
    )
    assert "REPLY IN THE EXISTING EMAIL THREAD" in letter
    assert "In-Reply-To" in letter


def test_deadline_lookup_is_conservative() -> None:
    germany = limitation_period(" Germany ")
    assert germany.country == "Germany"
    assert "Three-year" in germany.summary
    assert germany.confirmation_required
    assert set(listed_countries()) == {"Germany", "Spain"}

    fallback = limitation_period("Unlisted State")
    assert fallback.country == "Varies"
    assert fallback.confirmation_required
    assert "Confirm" in fallback.note


def test_regulator_directory_is_selected_and_officially_linked() -> None:
    assert 1 <= len(REGULATORS) < 30
    assert len({item.country for item in REGULATORS}) == len(REGULATORS)
    assert all(item.website.startswith("https://") for item in REGULATORS)
    assert all("Verify" in item.note for item in REGULATORS)
    assert regulator_for("spain") is not None
    assert regulator_for("not listed") is None


def test_verdict_to_dict_serializes_decimal() -> None:
    result = sample_verdict().to_dict()
    assert result["amount_eur"] == str(Decimal("250"))
