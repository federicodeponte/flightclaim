# FlightClaim

FlightClaim is an offline, open-source toolkit for checking common rights under
Regulation (EC) No 261/2004, preparing a documented claim, and choosing an
escalation route without assigning a percentage of the recovery to a claims
company.

> **Not legal advice.** FlightClaim provides a conservative rules-based
> assessment, not legal representation. Verify the result, limitation period,
> competent forum, and current law with the relevant National Enforcement Body,
> ADR body, court guidance, or a qualified adviser before acting.

It makes the cancellation versus denied-boarding distinction explicit:

- Cancellation compensation under Article 5 can be lost when the notice and
  re-routing conditions are all met.
- Involuntary denied boarding under Article 4(3) has no Article 5 re-routing
  exemption. Alternative arrival time can permit the Article 7(2) 50% reduction,
  but it does not erase compensation entitlement.
- Article 9 care is assessed separately from Article 7 compensation.

The package uses only the Python standard library at runtime, performs no
network calls, and stores nothing unless the user asks the CLI to write a letter.

## Features

- Explainable verdicts for cancellation, denied boarding, delay, downgrade, and
  missed connection
- Article 7 distance bands and great-circle distance calculation
- Correct Article 5(1)(c)(ii) and (iii) cumulative timing tests
- Article 7(2) re-routing reductions and the Sturgeon long-delay reduction
- Article 9 care reported independently from fixed compensation
- Article 10 downgrade calculations
- Selected, sourced enforcement-body and deadline lookups with explicit
  confirmation fallbacks
- Initial claim, in-thread rejection reply, and regulator escalation letters
- Optional fail-loud IMAP watcher with credentials kept outside its config file

## Quickstart

Python 3.10 or newer is required.

```bash
python -m flightclaim
```

For flag-driven use:

```bash
python -m flightclaim \
  --disruption denied_boarding \
  --distance-km 4200 \
  --departed-eu-eea \
  --rerouted \
  --scheduled-arrival 2030-01-02T18:00+01:00 \
  --actual-arrival 2030-01-02T16:00+01:00
```

Generate a placeholder letter without entering personal data into the command:

```bash
python -m flightclaim \
  --disruption delay \
  --distance-km 900 \
  --departed-eu-eea \
  --scheduled-departure 2030-01-01T08:00+01:00 \
  --actual-departure 2030-01-01T12:00+01:00 \
  --scheduled-arrival 2030-01-01T10:00+01:00 \
  --actual-arrival 2030-01-01T14:00+01:00 \
  --letter-kind initial \
  --letter-out claim-letter.txt
```

Fill the visible placeholders in the local output file. Do not commit personal
documents, booking details, identity documents, or correspondence to a public
repository.

## Python API

```python
from datetime import datetime, timezone

from flightclaim import ClaimInputs, DisruptionType, evaluate_claim

verdict = evaluate_claim(
    ClaimInputs(
        disruption_type=DisruptionType.DELAY,
        distance_km=900,
        departed_from_eu_eea=True,
        arrived_in_eu_eea=True,
        operating_carrier_is_eu_eea=False,
        scheduled_arrival=datetime(2030, 1, 1, 10, tzinfo=timezone.utc),
        actual_arrival=datetime(2030, 1, 1, 14, tzinfo=timezone.utc),
    )
)

print(verdict.to_dict())
```

## Development

The runtime package has no third-party dependencies. Tests use pytest.

```bash
python -m pytest
python -m compileall -q flightclaim watcher
```

## Mailbox watcher

The optional watcher never replies to messages. It scans matching headers in
read-only mode, notifies for new matches, and exits non-zero when it cannot prove
that it can see the expected mailbox.

```bash
cp watcher/config.example.json watcher/config.json
export FLIGHTCLAIM_MAIL_PASSWORD='set this only in your local shell or secret manager'
python watcher/watch_claim.py
```

`watcher/config.json`, state, and logs are ignored by Git. The example config
contains no credential. For providers that require an app-specific mail
credential, create it through that provider and keep it only in a local secret
manager or environment variable.

## Documentation

- [Claim playbook](docs/playbook.md)
- [Evidence checklist](docs/evidence-checklist.md)
- [Escalation routes](docs/escalation-routes.md)
- [DIY cost comparison](docs/why-diy.md)

## Scope and limitations

- The engine covers the core fact patterns listed above. It does not determine
  court jurisdiction, applicable national law, damages beyond EC 261, package
  travel rights, baggage claims, or Montreal Convention claims.
- “EU/EEA” is used as a convenient input label. Switzerland applies equivalent
  provisions through a separate arrangement; confirm the competent Swiss route.
- Denied boarding requires a confirmed reservation, timely presentation, an
  involuntary refusal, and no reasonable health, safety, security, or
  documentation ground.
- The extraordinary-circumstances input means the carrier has actually proved
  the event and that it could not have been avoided even if all reasonable
  measures had been taken. A bare assertion is not proof.
- Article 9 reimbursement remains fact-sensitive: expenses must be necessary,
  appropriate, reasonable, and evidenced.
- National limitation periods and complaint windows vary. The bundled deadline
  module deliberately lists only selected sourced rules and otherwise says to
  confirm.
- The regulator directory is intentionally selected rather than padded. Always
  check the European Commission's current directory before filing.
- A revised EU air-passenger-rights text received
  [final Council clearance in July 2026](https://www.consilium.europa.eu/en/press/press-releases/2026/07/13/council-gives-final-clearance-for-stronger-air-passenger-rights/)
  but, according to the Council, applies only 12 months and 20 days after
  publication in the Official Journal. This release implements the currently
  applicable Regulation 261/2004 and named CJEU case law as checked on 28 July
  2026. Re-verify the rules for later incidents.

## Primary legal sources

- [Regulation (EC) No 261/2004](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32004R0261)
- [Sturgeon, Joined Cases C-402/07 and C-432/07](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62007CJ0402)
- [Wallentin-Hermann, C-549/07](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62007CJ0549)
- [Folkerts, C-11/11](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62011CJ0011)
- [McDonagh, C-12/11](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62011CJ0012)
- [CJEU C-255/15 on downgrade fare calculation](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62015CJ0255)
- [CJEU C-139/11 on national limitation periods](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62011CJ0139)
- [European Commission interpretative guidelines](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:52024XC05687)
- [European Commission National Enforcement Body directory](https://transport.ec.europa.eu/transport-themes/passenger-rights/national-enforcement-bodies-neb_en)

## License

MIT. See [LICENSE](LICENSE).
