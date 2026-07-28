"""Country-neutral plain-text EC 261 claim-letter generation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from textwrap import dedent

from .eligibility import Verdict


class LetterKind(str, Enum):
    """Supported letter templates."""

    INITIAL = "initial"
    REJECTION_REPLY = "rejection_reply"
    REGULATOR_ESCALATION = "regulator_escalation"


@dataclass(frozen=True)
class LetterFacts:
    """Structured facts inserted into a claim letter.

    Defaults are visible placeholders. The generator does not send messages or
    retain data.
    """

    passenger_name: str = "[YOUR NAME]"
    postal_address: str = "[YOUR POSTAL ADDRESS]"
    operating_carrier: str = "[OPERATING CARRIER]"
    flight_identifier: str = "[FLIGHT IDENTIFIER]"
    travel_date: str = "[TRAVEL DATE]"
    origin: str = "[ORIGIN]"
    final_destination: str = "[FINAL DESTINATION]"
    booking_reference: str = "[BOOKING REFERENCE]"
    scheduled_departure: str = "[ORIGINAL SCHEDULED DEPARTURE]"
    scheduled_arrival: str = "[ORIGINAL SCHEDULED FINAL ARRIVAL]"
    replacement_departure: str = "[REPLACEMENT OR ACTUAL DEPARTURE]"
    actual_arrival: str = "[ACTUAL FINAL ARRIVAL]"
    disruption_summary: str = "[FACTUAL DISRUPTION SUMMARY]"
    notice_timing: str = "[WHEN AND HOW NOTICE WAS RECEIVED]"
    care_expenses: str = "[ITEMISED REASONABLE EXPENSES AND TOTAL]"
    rejection_quote: str = "[EXACT REJECTION REASON]"
    prior_claim_date: str = "[DATE OF PRIOR AIRLINE CLAIM]"
    airline_response_date: str = "[DATE OF AIRLINE RESPONSE OR NO-RESPONSE DATE]"
    regulator_name: str = "[COMPETENT NATIONAL ENFORCEMENT OR ADR BODY]"


def _amount(verdict: Verdict) -> str:
    if verdict.amount_eur is None:
        return "[CALCULATE FROM THE ATTACHED FARE BREAKDOWN]"
    return f"EUR {verdict.amount_eur:.2f}"


def _basis(verdict: Verdict) -> str:
    return ", ".join(verdict.legal_basis)


def _reasoning(verdict: Verdict) -> str:
    return "\n".join(f"- {item}" for item in verdict.reasoning)


def _initial(facts: LetterFacts, verdict: Verdict) -> str:
    return dedent(
        f"""\
        NOT LEGAL ADVICE - verify the legal basis and filing deadline before sending.

        Subject: Claim under Regulation (EC) No 261/2004 - {facts.flight_identifier} - {facts.travel_date}

        Dear Customer Relations Team,

        I submit a claim to the operating carrier under Regulation (EC) No 261/2004.

        Passenger: {facts.passenger_name}
        Booking reference: {facts.booking_reference}
        Flight: {facts.flight_identifier}, {facts.origin} to {facts.final_destination}
        Travel date: {facts.travel_date}
        Original scheduled departure: {facts.scheduled_departure}
        Original scheduled final arrival: {facts.scheduled_arrival}
        Replacement or actual departure: {facts.replacement_departure}
        Actual final arrival: {facts.actual_arrival}
        Notice: {facts.notice_timing}

        Facts

        {facts.disruption_summary}

        Legal basis

        {_basis(verdict)}

        The assessment is:
        {_reasoning(verdict)}

        I claim {_amount(verdict)} in fixed compensation or downgrade reimbursement, as applicable.
        Separately, under Article 9, I request reimbursement of the following necessary, appropriate, and reasonable care expenses:
        {facts.care_expenses}

        Please respond in writing and, if relying on extraordinary circumstances, identify the specific event and the reasonable measures taken. I attach the itinerary, evidence of the disruption, relevant correspondence, and itemised receipts.

        Yours faithfully,

        {facts.passenger_name}
        {facts.postal_address}
        """
    )


def _rejection_reply(facts: LetterFacts, verdict: Verdict) -> str:
    return dedent(
        f"""\
        IMPORTANT: REPLY IN THE EXISTING EMAIL THREAD. Do not start a new message.
        Preserve the original subject, recipients, message history, and In-Reply-To metadata.

        NOT LEGAL ADVICE - verify the legal basis and filing deadline before sending.

        Dear Customer Relations Team,

        I reply to your response dated {facts.airline_response_date} concerning booking reference {facts.booking_reference}.

        Your stated reason was:
        "{facts.rejection_quote}"

        I do not accept that conclusion for the following reasons:
        {_reasoning(verdict)}

        The claim relies on {_basis(verdict)}. The amount claimed is {_amount(verdict)}, plus any separately documented Article 9 care expenses:
        {facts.care_expenses}

        Please reassess the claim and provide a reasoned written response. If you rely on Article 5(3), provide evidence of the specific extraordinary circumstance and the reasonable measures taken. If the matter is not resolved, I will submit the complete record to the competent enforcement or dispute-resolution body.

        Yours faithfully,

        {facts.passenger_name}
        """
    )


def _regulator_escalation(facts: LetterFacts, verdict: Verdict) -> str:
    return dedent(
        f"""\
        NOT LEGAL ADVICE - confirm this body's competence, procedure, filing window, and the effect of parallel proceedings before filing.

        To: {facts.regulator_name}
        Subject: Regulation (EC) No 261/2004 complaint - {facts.flight_identifier} - {facts.travel_date}

        Dear Sir or Madam,

        I ask you to review an unresolved complaint against the operating carrier {facts.operating_carrier}.

        Passenger: {facts.passenger_name}
        Booking reference: {facts.booking_reference}
        Journey: {facts.origin} to {facts.final_destination}
        Flight and date: {facts.flight_identifier}, {facts.travel_date}
        Original scheduled departure: {facts.scheduled_departure}
        Original scheduled final arrival: {facts.scheduled_arrival}
        Replacement or actual departure: {facts.replacement_departure}
        Actual final arrival: {facts.actual_arrival}

        Disruption

        {facts.disruption_summary}

        Prior attempt to resolve

        I submitted the claim to the carrier on {facts.prior_claim_date}. The carrier responded, or the response period ended, on {facts.airline_response_date}.

        Legal and factual position

        {_basis(verdict)}
        {_reasoning(verdict)}

        Requested outcome

        I request a determination or enforcement action within your statutory competence concerning {_amount(verdict)}, together with the documented Article 9 care expenses below:
        {facts.care_expenses}

        Enclosures: booking and itinerary evidence, disruption notice, re-routing details, proof of actual arrival, the complete airline correspondence, and itemised receipts.

        Yours faithfully,

        {facts.passenger_name}
        {facts.postal_address}
        """
    )


def generate_letter(kind: LetterKind, facts: LetterFacts, verdict: Verdict) -> str:
    """Render a plain-text letter without sending or retaining it."""

    renderers = {
        LetterKind.INITIAL: _initial,
        LetterKind.REJECTION_REPLY: _rejection_reply,
        LetterKind.REGULATOR_ESCALATION: _regulator_escalation,
    }
    return renderers[kind](facts, verdict).strip() + "\n"
