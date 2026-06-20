from __future__ import annotations

from scripts import secret_scan


def _fake_secret_fixture() -> str:
    google = "AI" + "za" + ("A" * 30)
    openai = "sk" + "-" + ("B" * 30)
    aq_token = "AQ" + "." + ("C" * 24)
    bearer = "Bearer " + ("D" * 30)
    private_key = "-----BEGIN " + "RSA " + "PRIVATE KEY-----"
    password_line = "pass" + "word = " + '"super-secret-value"'
    return "\n".join(
        [
            f"GOOGLE_KEY={google}",
            f"OPENAI_KEY={openai}",
            f"SESSION_TOKEN={aq_token}",
            f"Authorization: {bearer}",
            private_key,
            password_line,
        ]
    )


def test_fake_secret_fixture_file_catches_each_pattern(tmp_path):
    fixture = tmp_path / "fake_secrets.txt"
    fixture.write_text(_fake_secret_fixture(), encoding="utf-8")

    findings = secret_scan.scan_paths([fixture], tmp_path)
    rules = {finding.rule for finding in findings}

    assert {
        "google_api_key",
        "openai_api_key",
        "aq_prefixed_token",
        "bearer_token",
        "private_key",
        "hardcoded_password",
    } <= rules
    assert all(finding.severity == secret_scan.HIGH for finding in findings)


def test_clean_fixture_file_has_no_false_positives(tmp_path):
    clean = "\n".join(
        [
            "API key is loaded from the environment.",
            "Authorization header is omitted from examples.",
            "password is provided interactively and never committed.",
            "-----BEGIN PUBLIC KEY-----",
            "token count is a model usage metric.",
        ]
    )
    fixture = tmp_path / "clean.txt"
    fixture.write_text(clean, encoding="utf-8")

    assert secret_scan.scan_paths([fixture], tmp_path) == []


def test_never_commit_tracked_paths_are_flagged(tmp_path):
    paths = [
        tmp_path / "kite_bot.db",
        tmp_path / ".env",
        tmp_path / "session_cookie.txt",
        tmp_path / "notes.md",
    ]
    for path in paths:
        path.write_text("safe text", encoding="utf-8")

    findings = secret_scan.scan_paths(paths, tmp_path)
    flagged_paths = {finding.path for finding in findings}

    assert "kite_bot.db" in flagged_paths
    assert ".env" in flagged_paths
    assert "session_cookie.txt" in flagged_paths
    assert "notes.md" not in flagged_paths
