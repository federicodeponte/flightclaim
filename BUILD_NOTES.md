# Build notes

## Built

- A standard-library-only `flightclaim` package for Python 3.10+ with:
  - explainable eligibility verdicts for cancellation, denied boarding, delay,
    downgrade, and missed connection;
  - Article 7 compensation bands, both forms of 50% reduction, and a
    great-circle distance helper;
  - Article 9 care reported independently from fixed compensation;
  - selected official National Enforcement Body links;
  - conservative Germany and Spain deadline entries plus an explicit fallback;
  - three country-neutral plain-text claim letters; and
  - an interactive and flag-driven CLI.
- A credential-free, read-only mailbox watcher with external secret loading,
  expected-mailbox verification, atomic owner-only state, non-zero blind
  failures, notification retry safety, and no automatic replies.
- Product documentation covering evidence, direct claims, escalation through
  enforcement bodies, ECC-Net, ADR and court routes, and an honest DIY cost
  comparison.
- A pytest suite covering the required Article 4 versus Article 5 distinction,
  cumulative cancellation timing limbs, all distance bands, Article 7(2)
  boundaries, Sturgeon reduction, Folkerts missed connections, Article 9 care,
  downgrade calculation, CLI behavior, letters, deadline fallbacks, and watcher
  failure paths.

## Legal points requiring confirmation

- EU institutions completed political and Council approval of revised
  air-passenger-rights rules in 2026. The Council states that the revised rules
  apply 12 months and 20 days after Official Journal publication. This release
  implements the currently applicable Regulation 261/2004 rules as checked on
  28 July 2026; users with later incidents must confirm the applicable text.
- Regulation 261/2004 has no uniform limitation period. Only Germany and Spain
  are bundled because their primary or official sources were verified. Even
  those entries require confirmation of governing law, interruption,
  suspension, and forum-specific filing windows.
- National Enforcement Body powers and territorial competence differ. The
  selected directory links were live during the build, but every entry carries
  a verify-before-filing note and points to the Commission directory.
- Article 9 establishes categories of care, but reimbursement of self-funded
  expenses remains fact-specific. McDonagh uses the necessary, appropriate, and
  reasonable standard.
- Article 10 amounts require the fare attributable to the downgraded flight,
  excluding class-independent taxes and charges. When that input is missing,
  the engine reports entitlement without inventing an amount.

## Deliberately left out

- Personal examples, real itineraries, carrier disputes, booking or case
  identifiers, contact details, identity records, and payment information
- Network lookups in the decision package, automatic claim submission, and
  automatic mailbox replies
- Unsourced limitation periods or padded enforcement-body rows
- Baggage and Montreal Convention claims, package-travel claims, national
  consequential damages, court jurisdiction analysis, and litigation drafting
- A claim-outcome prediction; the engine applies entered facts and exposes its
  reasoning rather than estimating how a carrier or tribunal will decide

## Verification record

- `python3 -m pytest`: 62 tests passed.
- `ruff check .` and `ruff format --check .`: passed.
- `mypy --python-version 3.10 flightclaim watcher/watch_claim.py`: passed.
- `python3 -m build --wheel`: built `flightclaim-0.1.0-py3-none-any.whl`.
- The wheel installed and its console entry point ran successfully in a clean
  Python 3.13 virtual environment.
- Flag-driven and interactive CLI flows were executed for the decisive
  denied-boarding and cancellation timing scenarios.
- All selected regulator URLs returned HTTP 200 during the final link check.
- Gitleaks found no secrets, and the targeted privacy scan found only
  `you@example.com` placeholder addresses.
