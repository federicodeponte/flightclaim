"""Command-line interface for the offline FlightClaim evaluator."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence

from .eligibility import ClaimInputs, DisruptionType, Verdict, evaluate_claim
from .letters import LetterFacts, LetterKind, generate_letter

DISCLAIMER = (
    "NOT LEGAL ADVICE. Verify the result, deadline, and filing route with the "
    "competent national body or a qualified adviser."
)


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "use ISO 8601 with a UTC offset, for example 2030-01-01T10:00+01:00"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("datetime must include a UTC offset")
    return parsed


def _parse_decimal(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("enter a decimal number") from exc
    if amount < 0:
        raise argparse.ArgumentTypeError("amount cannot be negative")
    return amount


def build_parser() -> argparse.ArgumentParser:
    """Create the public CLI parser."""

    parser = argparse.ArgumentParser(
        prog="flightclaim",
        description="Offline EC 261/2004 claim assessment and letter generator.",
    )
    parser.add_argument(
        "--disruption",
        choices=[item.value for item in DisruptionType],
        help="omit to use the interactive questionnaire",
    )
    parser.add_argument("--distance-km", type=float)
    parser.add_argument("--departed-eu-eea", action="store_true")
    parser.add_argument("--arrived-eu-eea", action="store_true")
    parser.add_argument("--eu-eea-carrier", action="store_true")
    parser.add_argument("--intra-community", action="store_true")
    parser.add_argument("--notice-days", type=float)
    parser.add_argument("--scheduled-departure", type=_parse_datetime)
    parser.add_argument("--actual-departure", type=_parse_datetime)
    parser.add_argument("--scheduled-arrival", type=_parse_datetime)
    parser.add_argument("--actual-arrival", type=_parse_datetime)
    parser.add_argument("--rerouted", action="store_true")
    parser.add_argument(
        "--extraordinary-proven",
        action="store_true",
        help="set only when the carrier has proved the event and reasonable measures",
    )
    parser.add_argument("--no-confirmed-reservation", action="store_true")
    parser.add_argument("--not-presented-on-time", action="store_true")
    parser.add_argument("--voluntary-denied-boarding", action="store_true")
    parser.add_argument("--reasonable-denial-grounds", action="store_true")
    parser.add_argument(
        "--affected-flight-fare-eur",
        type=_parse_decimal,
        help="downgraded flight fare excluding class-independent taxes and charges",
    )
    parser.add_argument("--french-overseas-route", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--letter-kind",
        choices=[item.value for item in LetterKind],
    )
    parser.add_argument("--letter-out", type=Path)
    parser.add_argument(
        "--force",
        action="store_true",
        help="permit overwriting an existing letter output file",
    )
    return parser


def _ask(prompt: str, *, required: bool = True) -> str:
    while True:
        value = input(f"{prompt}: ").strip()
        if value or not required:
            return value
        print("A value is required.", file=sys.stderr)


def _ask_bool(prompt: str) -> bool:
    while True:
        answer = _ask(f"{prompt} [y/n]").casefold()
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Enter y or n.", file=sys.stderr)


def _ask_datetime(prompt: str, *, required: bool) -> datetime | None:
    while True:
        value = _ask(f"{prompt} (ISO 8601 with UTC offset)", required=required)
        if not value:
            return None
        try:
            return _parse_datetime(value)
        except argparse.ArgumentTypeError as exc:
            print(str(exc), file=sys.stderr)


def _interactive_inputs() -> ClaimInputs:
    print(DISCLAIMER)
    print("All processing is local. Enter no data you do not want in terminal history.")
    disruption = DisruptionType(
        _ask(
            "Disruption type "
            "(cancellation/denied_boarding/delay/downgrade/missed_connection)"
        )
    )
    distance = float(_ask("Great-circle journey distance in kilometres"))
    departed = _ask_bool("Did the journey depart from the EU/EEA")
    arrived = _ask_bool("Did it arrive in the EU/EEA")
    eu_carrier = _ask_bool("Was the operating carrier EU/EEA-licensed")
    intra = _ask_bool("Was it an Intra-Community flight")

    notice = None
    rerouted = False
    scheduled_departure = None
    actual_departure = None
    scheduled_arrival = None
    actual_arrival = None
    extraordinary = False
    confirmed = True
    on_time = True
    voluntary = False
    reasonable_grounds = False
    fare = None
    french_overseas = False

    if disruption is DisruptionType.CANCELLATION:
        notice = float(_ask("Cancellation notice in days before departure"))
        rerouted = _ask_bool("Was re-routing offered")
        if rerouted and notice < 14:
            scheduled_departure = _ask_datetime(
                "Original scheduled departure", required=True
            )
            actual_departure = _ask_datetime("Replacement departure", required=True)
            scheduled_arrival = _ask_datetime(
                "Original scheduled final arrival", required=True
            )
            actual_arrival = _ask_datetime("Replacement final arrival", required=True)
        extraordinary = _ask_bool(
            "Has the carrier proved extraordinary circumstances and all reasonable measures"
        )
    elif disruption is DisruptionType.DENIED_BOARDING:
        confirmed = _ask_bool("Was there a confirmed reservation")
        on_time = _ask_bool("Did the passenger present for boarding on time")
        voluntary = _ask_bool("Did the passenger volunteer to surrender the seat")
        reasonable_grounds = _ask_bool(
            "Were there reasonable health, safety, security, or document grounds"
        )
        rerouted = _ask_bool("Was re-routing offered")
        if rerouted:
            scheduled_arrival = _ask_datetime(
                "Original scheduled final arrival", required=True
            )
            actual_arrival = _ask_datetime("Alternative final arrival", required=True)
    elif disruption in (
        DisruptionType.DELAY,
        DisruptionType.MISSED_CONNECTION,
    ):
        scheduled_departure = _ask_datetime(
            "Scheduled departure for the affected flight", required=False
        )
        if scheduled_departure is not None:
            actual_departure = _ask_datetime(
                "Actual departure for the affected flight", required=True
            )
        scheduled_arrival = _ask_datetime(
            "Original scheduled final arrival", required=True
        )
        actual_arrival = _ask_datetime("Actual final arrival", required=True)
        extraordinary = _ask_bool(
            "Has the carrier proved extraordinary circumstances and all reasonable measures"
        )
    else:
        fare_text = _ask(
            "Fare attributable to the downgraded flight in EUR "
            "(excluding class-independent taxes; blank if unknown)",
            required=False,
        )
        fare = _parse_decimal(fare_text) if fare_text else None
        french_overseas = _ask_bool(
            "Was this between EU territory and a French overseas department"
        )

    return ClaimInputs(
        disruption_type=disruption,
        distance_km=distance,
        departed_from_eu_eea=departed,
        arrived_in_eu_eea=arrived,
        operating_carrier_is_eu_eea=eu_carrier,
        intra_community_flight=intra,
        notice_days_before_departure=notice,
        scheduled_departure=scheduled_departure,
        actual_departure=actual_departure,
        scheduled_arrival=scheduled_arrival,
        actual_arrival=actual_arrival,
        rerouting_offered=rerouted,
        extraordinary_circumstances_proven=extraordinary,
        confirmed_reservation=confirmed,
        presented_for_boarding_on_time=on_time,
        denied_boarding_was_voluntary=voluntary,
        reasonable_denial_grounds=reasonable_grounds,
        affected_flight_fare_eur=fare,
        french_overseas_route=french_overseas,
    )


def _flag_inputs(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> ClaimInputs:
    if args.distance_km is None:
        parser.error("--distance-km is required with --disruption")
    return ClaimInputs(
        disruption_type=DisruptionType(args.disruption),
        distance_km=args.distance_km,
        departed_from_eu_eea=args.departed_eu_eea,
        arrived_in_eu_eea=args.arrived_eu_eea,
        operating_carrier_is_eu_eea=args.eu_eea_carrier,
        intra_community_flight=args.intra_community,
        notice_days_before_departure=args.notice_days,
        scheduled_departure=args.scheduled_departure,
        actual_departure=args.actual_departure,
        scheduled_arrival=args.scheduled_arrival,
        actual_arrival=args.actual_arrival,
        rerouting_offered=args.rerouted,
        extraordinary_circumstances_proven=args.extraordinary_proven,
        confirmed_reservation=not args.no_confirmed_reservation,
        presented_for_boarding_on_time=not args.not_presented_on_time,
        denied_boarding_was_voluntary=args.voluntary_denied_boarding,
        reasonable_denial_grounds=args.reasonable_denial_grounds,
        affected_flight_fare_eur=args.affected_flight_fare_eur,
        french_overseas_route=args.french_overseas_route,
    )


def _print_verdict(verdict: Verdict) -> None:
    print(DISCLAIMER)
    print(
        f"Entitled to fixed compensation/reimbursement: {'yes' if verdict.entitled else 'no'}"
    )
    if verdict.amount_eur is None:
        print("Calculated amount: requires fare information")
    else:
        print(f"Calculated amount: EUR {verdict.amount_eur:.2f}")
    care = (
        "unknown from the supplied facts"
        if verdict.care_entitled is None
        else ("yes" if verdict.care_entitled else "no")
    )
    print(f"Article 9 care entitlement: {care}")
    print(f"Legal basis: {', '.join(verdict.legal_basis)}")
    print("\nReasoning:")
    for item in verdict.reasoning:
        print(f"- {item}")
    print("\nEvidence to collect:")
    for item in verdict.evidence_to_collect:
        print(f"- {item}")


def _write_letter(
    args: argparse.Namespace, parser: argparse.ArgumentParser, verdict: Verdict
) -> None:
    if args.letter_kind and not args.letter_out:
        parser.error("--letter-kind requires --letter-out")
    if args.letter_out and not args.letter_kind:
        parser.error("--letter-out requires --letter-kind")
    if not args.letter_out:
        return
    if args.letter_out.exists() and not args.force:
        parser.error(f"{args.letter_out} already exists; use --force to overwrite it")
    letter = generate_letter(LetterKind(args.letter_kind), LetterFacts(), verdict)
    args.letter_out.parent.mkdir(parents=True, exist_ok=True)
    args.letter_out.write_text(letter, encoding="utf-8")
    print(f"Letter template written to {args.letter_out}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        inputs = (
            _flag_inputs(args, parser) if args.disruption else _interactive_inputs()
        )
        verdict = evaluate_claim(inputs)
        _write_letter(args, parser, verdict)
    except (ValueError, InvalidOperation) as exc:
        parser.error(str(exc))

    if args.as_json:
        print(json.dumps(verdict.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_verdict(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
