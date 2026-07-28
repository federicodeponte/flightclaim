import json
import os
import smtplib
from pathlib import Path

import pytest

from watcher import watch_claim

WATCHER_PATH = Path(watch_claim.__file__).resolve()


def valid_config() -> dict[str, object]:
    return {
        "imap_host": "imap.example.com",
        "imap_user": "you@example.com",
        "password_env": "FLIGHTCLAIM_TEST_PASSWORD",
        "expected_mailbox": "you@example.com",
        "mailbox": "INBOX",
        "smtp_host": "smtp.example.com",
        "notify_to": "you@example.com",
        "watch_senders": ["regulator.example"],
        "subject_keywords": ["claim update"],
    }


def test_example_config_contains_no_password_value() -> None:
    example = json.loads(
        (WATCHER_PATH.parent / "config.example.json").read_text(encoding="utf-8")
    )
    assert "imap_password" not in example
    assert example["password_env"] == "FLIGHTCLAIM_MAIL_PASSWORD"


def test_config_requires_external_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(valid_config()), encoding="utf-8")
    monkeypatch.delenv("FLIGHTCLAIM_TEST_PASSWORD", raising=False)

    with pytest.raises(watch_claim.ConfigurationError, match="environment variable"):
        watch_claim.load_config(path)


def test_config_loads_password_without_storing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(valid_config()), encoding="utf-8")
    monkeypatch.setenv("FLIGHTCLAIM_TEST_PASSWORD", "local-test-value")

    config = watch_claim.load_config(path)
    assert config.password == "local-test-value"
    assert "local-test-value" not in path.read_text(encoding="utf-8")
    assert "OR" in watch_claim.build_criteria(config)


def test_search_term_injection_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = valid_config()
    raw["subject_keywords"] = ['claim" OR ALL']
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setenv("FLIGHTCLAIM_TEST_PASSWORD", "local-test-value")

    with pytest.raises(watch_claim.ConfigurationError, match="unsafe"):
        watch_claim.load_config(path)


def test_state_round_trip_is_owner_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = valid_config()
    raw["state_file"] = str(tmp_path / "state.json")
    raw["log_file"] = str(tmp_path / "run.log")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setenv("FLIGHTCLAIM_TEST_PASSWORD", "local-test-value")
    config = watch_claim.load_config(path)

    state = {"seen": ["message-1"], "seeded": True}
    watch_claim.save_state(config, state)

    assert watch_claim.load_state(config) == state
    assert os.stat(config.state_file).st_mode & 0o077 == 0


def loaded_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> watch_claim.Config:
    raw = valid_config()
    raw["state_file"] = str(tmp_path / "state.json")
    raw["log_file"] = str(tmp_path / "run.log")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setenv("FLIGHTCLAIM_TEST_PASSWORD", "local-test-value")
    return watch_claim.load_config(path)


def test_corrupt_state_fails_loud(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = loaded_config(tmp_path, monkeypatch)
    config.state_file.write_text("{broken", encoding="utf-8")
    with pytest.raises(watch_claim.WatcherBlindError, match="state file"):
        watch_claim.load_state(config)


def test_blind_scan_returns_nonzero_and_alerts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = loaded_config(tmp_path, monkeypatch)
    alerts: list[str] = []

    def blind(*_args: object) -> list[dict[str, str]]:
        raise watch_claim.WatcherBlindError("mailbox unavailable")

    def record_alert(
        _config: watch_claim.Config,
        _state: dict[str, object],
        reason: str,
    ) -> None:
        alerts.append(reason)

    monkeypatch.setattr(watch_claim, "scan", blind)
    monkeypatch.setattr(watch_claim, "alert_blind", record_alert)

    assert watch_claim.run(config) == 2
    assert alerts == ["mailbox unavailable"]


def test_first_run_seeds_without_notification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = loaded_config(tmp_path, monkeypatch)
    items = [
        {
            "id": "message-1",
            "from": "sender",
            "subject": "claim update",
            "date": "date",
        }
    ]
    monkeypatch.setattr(watch_claim, "scan", lambda *_args: items)
    monkeypatch.setattr(
        watch_claim,
        "notify",
        lambda *_args: pytest.fail("first run must not notify"),
    )

    assert watch_claim.run(config) == 0
    assert watch_claim.load_state(config)["seen"] == ["message-1"]


def test_notification_failure_does_not_advance_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = loaded_config(tmp_path, monkeypatch)
    watch_claim.save_state(config, {"seen": ["message-1"], "seeded": True})
    items = [
        {
            "id": "message-1",
            "from": "sender",
            "subject": "old",
            "date": "date",
        },
        {
            "id": "message-2",
            "from": "sender",
            "subject": "new",
            "date": "date",
        },
    ]
    monkeypatch.setattr(watch_claim, "scan", lambda *_args: items)

    def fail_notify(*_args: object) -> None:
        raise smtplib.SMTPException("delivery failed")

    monkeypatch.setattr(watch_claim, "notify", fail_notify)

    assert watch_claim.run(config) == 3
    assert watch_claim.load_state(config)["seen"] == ["message-1"]


def test_successful_notification_advances_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = loaded_config(tmp_path, monkeypatch)
    watch_claim.save_state(config, {"seen": ["message-1"], "seeded": True})
    items = [
        {
            "id": "message-2",
            "from": "sender",
            "subject": "new",
            "date": "date",
        }
    ]
    notifications: list[str] = []
    monkeypatch.setattr(watch_claim, "scan", lambda *_args: items)
    monkeypatch.setattr(
        watch_claim,
        "notify",
        lambda _config, subject, _body: notifications.append(subject),
    )

    assert watch_claim.run(config) == 0
    assert watch_claim.load_state(config)["seen"] == [
        "message-1",
        "message-2",
    ]
    assert len(notifications) == 1
