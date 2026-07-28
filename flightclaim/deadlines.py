"""Conservative limitation-period lookup.

Regulation (EC) No 261/2004 contains no uniform limitation period. National
rules, forum, interruption, and choice-of-law questions can change the answer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LimitationPeriod:
    """A sourced national rule or an explicit confirmation fallback."""

    country: str
    summary: str
    source: str
    confirmation_required: bool
    note: str


_PERIODS = {
    "germany": LimitationPeriod(
        country="Germany",
        summary="Three-year standard limitation period, generally beginning at the end of the relevant year.",
        source="German Civil Code (BGB), sections 195 and 199: https://www.gesetze-im-internet.de/englisch_bgb/",
        confirmation_required=True,
        note="Confirm that German law governs, calculate the year-end rule, and check any suspension or interruption.",
    ),
    "spain": LimitationPeriod(
        country="Spain",
        summary="Five years for personal actions without a special period.",
        source="Spanish Civil Code, Article 1964(2), and AESA ADR filing guidance: https://www.seguridadaerea.gob.es/es/ambitos/derechos-de-los-pasajeros/competencia-en-derechos-de-los-pasajeros/normativa-aplicable-a-derechos-de-pasajeros-en-el-transporte-aereo/procedimiento-para-reclamar/ral",
        confirmation_required=True,
        note="AESA also publishes a separate one-year window from the prior airline complaint for its ADR filing. Confirm both the court limitation and forum-specific filing window.",
    ),
}

_FALLBACK = LimitationPeriod(
    country="Varies",
    summary="No verified period is bundled for this country.",
    source="CJEU C-139/11 confirms that national law determines the time limit: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62011CJ0139",
    confirmation_required=True,
    note="Confirm immediately with the competent national enforcement body, ADR body, court guidance, or a qualified adviser. Do not infer a deadline from another country.",
)


def limitation_period(country: str) -> LimitationPeriod:
    """Return a verified selected rule or the explicit fallback."""

    normalized = " ".join(country.strip().lower().split())
    if not normalized:
        raise ValueError("country cannot be blank")
    return _PERIODS.get(normalized, _FALLBACK)


def listed_countries() -> tuple[str, ...]:
    """Return countries with a bundled selected rule."""

    return tuple(period.country for period in _PERIODS.values())
