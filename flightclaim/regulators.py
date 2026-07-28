"""Selected National Enforcement Bodies for Regulation (EC) No 261/2004."""

from __future__ import annotations

from dataclasses import dataclass

COMMISSION_DIRECTORY_URL = (
    "https://transport.ec.europa.eu/transport-themes/passenger-rights/"
    "national-enforcement-bodies-neb_en"
)
VERIFY_NOTE = (
    "Verify the body, territorial competence, procedure, and current URL before "
    f"filing. The European Commission directory is authoritative: {COMMISSION_DIRECTORY_URL}"
)


@dataclass(frozen=True)
class Regulator:
    """A selected official enforcement-body entry."""

    country: str
    name: str
    website: str
    note: str = VERIFY_NOTE


REGULATORS = (
    Regulator(
        "Denmark",
        "Danish Civil Aviation and Railway Authority",
        "https://www.en.flypassager.dk/",
    ),
    Regulator(
        "France",
        "Direction générale de l'aviation civile (DGAC)",
        "https://www.ecologie.gouv.fr/politiques-publiques/que-faire-cas-retard-depart-annulation-dun-vol-refus-dembarquement",
    ),
    Regulator(
        "Germany",
        "Luftfahrt-Bundesamt (LBA)",
        "https://www.lba.de/DE/Fluggastrechte/Fluggastrechte_node.html",
    ),
    Regulator(
        "Ireland",
        "Irish Aviation Authority",
        "https://www.iaa.ie/consumer-protection/air-passenger-rights",
    ),
    Regulator(
        "Italy",
        "Ente Nazionale per l'Aviazione Civile (ENAC)",
        "https://www.enac.gov.it/en/passengers/passengers-rights/passengers-rights-in-case-of-denied-boarding-cancellation-or-long-delay-of/",
    ),
    Regulator(
        "Romania",
        "National Authority for Consumer Protection",
        "https://anpc.ro/",
    ),
    Regulator(
        "Spain",
        "Agencia Estatal de Seguridad Aérea (AESA)",
        "https://www.seguridadaerea.gob.es/es/ambitos/derechos-de-los-pasajeros/inicia-tu-reclamacion-con-aesa",
    ),
    Regulator(
        "Sweden",
        "Swedish Consumer Agency (Konsumentverket)",
        "https://www.konsumentverket.se/omrade/flyg/",
    ),
)


def regulator_for(country: str) -> Regulator | None:
    """Return a selected entry by case-insensitive country name."""

    normalized = " ".join(country.strip().casefold().split())
    return next(
        (
            regulator
            for regulator in REGULATORS
            if regulator.country.casefold() == normalized
        ),
        None,
    )
