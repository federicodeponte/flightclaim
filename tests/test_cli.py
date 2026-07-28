import json
from pathlib import Path

import pytest

from flightclaim.cli import main


DENIED_BOARDING_ARGS = [
    "--disruption",
    "denied_boarding",
    "--distance-km",
    "4200",
    "--departed-eu-eea",
    "--rerouted",
    "--scheduled-arrival",
    "2030-01-02T18:00+01:00",
    "--actual-arrival",
    "2030-01-02T16:00+01:00",
]


def test_flag_cli_outputs_structured_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([*DENIED_BOARDING_ARGS, "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["entitled"] is True
    assert output["amount_eur"] == "300.00"
    assert output["care_entitled"] is True


def test_cli_writes_placeholder_letter(tmp_path: Path) -> None:
    output = tmp_path / "claim.txt"
    assert (
        main(
            [
                *DENIED_BOARDING_ARGS,
                "--letter-kind",
                "initial",
                "--letter-out",
                str(output),
                "--json",
            ]
        )
        == 0
    )
    content = output.read_text(encoding="utf-8")
    assert "NOT LEGAL ADVICE" in content
    assert "[YOUR NAME]" in content
    assert "Article 4(3)" in content


def test_cli_refuses_to_overwrite_letter(tmp_path: Path) -> None:
    output = tmp_path / "claim.txt"
    output.write_text("existing", encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                *DENIED_BOARDING_ARGS,
                "--letter-kind",
                "initial",
                "--letter-out",
                str(output),
            ]
        )
    assert exc_info.value.code == 2
    assert output.read_text(encoding="utf-8") == "existing"


def test_cli_rejects_naive_datetime() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--disruption",
                "delay",
                "--distance-km",
                "800",
                "--departed-eu-eea",
                "--scheduled-arrival",
                "2030-01-01T10:00",
                "--actual-arrival",
                "2030-01-01T14:00+01:00",
            ]
        )
    assert exc_info.value.code == 2
