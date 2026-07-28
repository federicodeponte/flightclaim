#!/usr/bin/env python3
"""Fail-loud IMAP watcher for passenger-rights claim correspondence.

The watcher never replies. It reads a password from the environment named by
``password_env`` in the local config, scans with IMAP in read-only mode, and
sends a notification only for newly seen matching messages. A broken
connection, mailbox mismatch, or inconsistent search exits non-zero and tries
to send a self-alert, so silence is never reported as success.
"""

from __future__ import annotations

import argparse
import email
import imaplib
import json
import os
import smtplib
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Sequence

HERE = Path(__file__).resolve().parent


class ConfigurationError(ValueError):
    """Raised when local watcher configuration is invalid."""


class WatcherBlindError(RuntimeError):
    """Raised when the watcher cannot prove that it can see the mailbox."""


@dataclass(frozen=True)
class Config:
    """Validated watcher configuration."""

    imap_host: str
    imap_port: int
    imap_user: str
    password: str
    expected_mailbox: str
    mailbox: str
    smtp_host: str
    smtp_port: int
    notify_to: str
    watch_senders: tuple[str, ...]
    subject_keywords: tuple[str, ...]
    state_file: Path
    log_file: Path


def _required_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"config key '{key}' must be a non-empty string")
    return value.strip()


def _safe_search_term(value: str, key: str) -> str:
    if any(character in value for character in ('"', "\\", "\r", "\n")):
        raise ConfigurationError(
            f"config key '{key}' contains characters unsafe for an IMAP search"
        )
    return value


def _string_list(raw: dict[str, Any], key: str) -> tuple[str, ...]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ConfigurationError(
            f"config key '{key}' must be a list of non-empty strings"
        )
    return tuple(_safe_search_term(item.strip(), key) for item in value)


def load_config(path: Path) -> Config:
    """Load local config and resolve the password from its named environment variable."""

    if not path.is_file():
        raise ConfigurationError(
            f"missing config: {path} (copy config.example.json to config.json)"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError("config root must be a JSON object")

    password_env = _required_string(raw, "password_env")
    password = os.environ.get(password_env)
    if not password:
        raise ConfigurationError(
            f"environment variable named by password_env is missing: {password_env}"
        )

    senders = _string_list(raw, "watch_senders")
    keywords = _string_list(raw, "subject_keywords")
    if not senders and not keywords:
        raise ConfigurationError(
            "configure at least one watch_senders or subject_keywords entry"
        )

    return Config(
        imap_host=_required_string(raw, "imap_host"),
        imap_port=int(raw.get("imap_port", 993)),
        imap_user=_required_string(raw, "imap_user"),
        password=password,
        expected_mailbox=_required_string(raw, "expected_mailbox"),
        mailbox=_required_string(raw, "mailbox"),
        smtp_host=_required_string(raw, "smtp_host"),
        smtp_port=int(raw.get("smtp_port", 587)),
        notify_to=_required_string(raw, "notify_to"),
        watch_senders=senders,
        subject_keywords=keywords,
        state_file=Path(raw.get("state_file", HERE / "state.json")).expanduser(),
        log_file=Path(raw.get("log_file", HERE / "run.log")).expanduser(),
    )


def log(config: Config, message: str) -> None:
    """Write one UTC timestamped line to stdout and the local log."""

    line = f"{datetime.now(timezone.utc).isoformat()} {message}"
    print(line)
    config.log_file.parent.mkdir(parents=True, exist_ok=True)
    with config.log_file.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def load_state(config: Config) -> dict[str, Any]:
    """Load state, failing loudly on corruption instead of silently reseeding."""

    if not config.state_file.exists():
        return {"seen": [], "seeded": False}
    try:
        state = json.loads(config.state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WatcherBlindError(
            f"cannot read state file {config.state_file}: {exc}"
        ) from exc
    if not isinstance(state, dict) or not isinstance(state.get("seen"), list):
        raise WatcherBlindError(f"invalid state structure in {config.state_file}")
    return state


def save_state(config: Config, state: dict[str, Any]) -> None:
    """Atomically save state with owner-only permissions."""

    config.state_file.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=".flightclaim-state-",
        dir=config.state_file.parent,
        text=True,
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_name, config.state_file)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def notify(config: Config, subject: str, body: str) -> None:
    """Send a plain-text notification to the configured address."""

    message = EmailMessage()
    message["From"] = config.imap_user
    message["To"] = config.notify_to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=60) as server:
        server.starttls()
        server.login(config.imap_user, config.password)
        server.send_message(message)


def build_criteria(config: Config) -> str:
    """Build a parenthesised IMAP OR tree from validated terms."""

    terms = [f'FROM "{sender}"' for sender in config.watch_senders]
    terms.extend(f'SUBJECT "{keyword}"' for keyword in config.subject_keywords)
    if not terms:
        raise ConfigurationError("no search terms configured")
    criteria = terms[0]
    for term in terms[1:]:
        criteria = f"OR ({criteria}) ({term})"
    return f"({criteria})"


def _header(message: email.message.Message, name: str) -> str:
    return str(make_header(decode_header(message.get(name, "") or "")))


def _fetch_items(
    connection: imaplib.IMAP4_SSL, message_uids: list[bytes]
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for uid in message_uids[-40:]:
        response_type, data = connection.uid(
            "fetch",
            uid.decode("ascii"),
            "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])",
        )
        if response_type != "OK" or not data or not data[0]:
            raise WatcherBlindError(f"failed to fetch matching message UID {uid!r}")
        payload = data[0][1]
        if not isinstance(payload, bytes):
            raise WatcherBlindError(f"unexpected IMAP response for UID {uid!r}")
        message = email.message_from_bytes(payload)
        identifier = (message.get("Message-ID") or "").strip()
        if not identifier:
            identifier = f"uid-{uid.decode('ascii', 'replace')}"
        items.append(
            {
                "id": identifier,
                "from": _header(message, "From"),
                "subject": _header(message, "Subject"),
                "date": message.get("Date", ""),
            }
        )
    return items


def scan(config: Config, state: dict[str, Any]) -> list[dict[str, str]]:
    """Read matching message headers while preserving mailbox flags."""

    if config.imap_user.casefold() != config.expected_mailbox.casefold():
        raise WatcherBlindError("configured IMAP user does not match expected_mailbox")
    try:
        connection = imaplib.IMAP4_SSL(config.imap_host, config.imap_port, timeout=60)
        connection.login(config.imap_user, config.password)
    except (OSError, imaplib.IMAP4.error) as exc:
        raise WatcherBlindError(
            f"cannot connect or authenticate to {config.imap_host}: {exc}"
        ) from exc

    try:
        response_type, _ = connection.select(config.mailbox, readonly=True)
        if response_type != "OK":
            raise WatcherBlindError(
                f"cannot select configured mailbox {config.mailbox!r}"
            )
        response_type, data = connection.uid(
            "search",
            None,  # type: ignore[arg-type]  # imaplib uses None for no CHARSET.
            build_criteria(config),
        )
        if response_type != "OK" or not data:
            raise WatcherBlindError("IMAP search failed")
        message_uids = data[0].split() if data[0] else []
        if state.get("seeded") and state.get("seen") and not message_uids:
            raise WatcherBlindError(
                "search returned zero results although prior matching messages are recorded"
            )
        return _fetch_items(connection, message_uids)
    finally:
        try:
            connection.logout()
        except (OSError, imaplib.IMAP4.error):
            pass


def alert_blind(config: Config, state: dict[str, Any], reason: str) -> None:
    """Try one self-alert per UTC day and always log the blind condition."""

    today = datetime.now(timezone.utc).date().isoformat()
    if state.get("last_alert_day") == today:
        log(config, f"BLIND: {reason}; alert already attempted today")
        return
    body = (
        "The FlightClaim mailbox watcher cannot verify that it can read the "
        "configured mailbox.\n\n"
        f"Reason: {reason}\n\n"
        "Treat watcher silence as unreliable. Check the mailbox manually and "
        "repair the local configuration.\n"
    )
    try:
        notify(config, "[flightclaim-watcher] ACTION NEEDED: watcher is blind", body)
    except (OSError, smtplib.SMTPException) as exc:
        log(config, f"BLIND: {reason}; ALERT DELIVERY FAILED: {exc}")
    else:
        state["last_alert_day"] = today
        save_state(config, state)
        log(config, f"BLIND: {reason}; alert sent")


def run(config: Config) -> int:
    """Execute one poll and return a process exit code."""

    try:
        state = load_state(config)
        items = scan(config, state)
    except WatcherBlindError as exc:
        state = locals().get("state", {"seen": [], "seeded": False})
        alert_blind(config, state, str(exc))
        return 2

    if not state.get("seeded"):
        state["seen"] = sorted({item["id"] for item in items})
        state["seeded"] = True
        save_state(config, state)
        log(
            config,
            f"seeded with {len(items)} existing matching messages; no notification sent",
        )
        return 0

    seen = set(state.get("seen", []))
    new_items = [item for item in items if item["id"] not in seen]
    if not new_items:
        log(config, f"no new matching message ({len(items)} in scan window)")
        return 0

    lines = [f"{len(new_items)} new claim-related message(s):", ""]
    for item in new_items:
        lines.extend(
            (
                f"From: {item['from']}",
                f"Date: {item['date']}",
                f"Subject: {item['subject']}",
                "",
            )
        )
    lines.append(
        "Nothing was answered automatically. Review the thread before replying."
    )
    try:
        notify(
            config,
            f"[flightclaim-watcher] {len(new_items)} new message(s)",
            "\n".join(lines),
        )
    except (OSError, smtplib.SMTPException) as exc:
        log(config, f"notification failed; state not advanced: {exc}")
        return 3

    state["seen"] = sorted(seen | {item["id"] for item in new_items})
    save_state(config, state)
    log(config, f"notified for {len(new_items)} new message(s)")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run one watcher poll."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=HERE / "config.json",
        help="path to ignored local JSON config",
    )
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigurationError as exc:
        print(f"CONFIGURATION ERROR: {exc}", file=sys.stderr)
        return 2
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
