from thrumely.validate_normalization import main, normalization_report


def test_report_is_explicitly_static_only() -> None:
    report = normalization_report()
    assert "STATIC_ONLY" in report
    assert "live provider calibration remains required" in report
    assert "openai:gpt-image-2" in report
    assert "google:gemini-3.1-flash-image" in report
    assert "bfl:flux-2-pro" in report


def test_cli_success_means_static_schema_coverage_only(capsys) -> None:
    assert main() == 0
    output = capsys.readouterr().out
    assert "STATIC_ONLY" in output
    assert "live provider calibration remains required" in output
