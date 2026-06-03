"""
Phase K — independent Windows runtime tests.

Guarantees:
  1. bot/ Python source contains no Claude / Anthropic tokens
  2. pyproject.toml lists no anthropic packages
  3. KiteBot-Control/*.bat files contain no `claude` invocations
  4. runtime_audit() returns 0 on a clean install
  5. install_windows writes the 4 expected .bat files (no EMERGENCY)
  6. RUN_BOT.bat references runtime-audit gate before run-all
"""

from pathlib import Path
import importlib
import pytest

BOT_PKG_DIR  = Path(__file__).parent.parent / "bot"
ENGINE_FILE  = Path(__file__).parent.parent / "paper_engine.py"
PYPROJECT    = Path(__file__).parent.parent / "pyproject.toml"
CONTROL_DIR  = Path(r"C:\Users\krish\OneDrive\Desktop\KiteBot-Control")


FORBIDDEN_TOKENS = (
    "anthropic", "claude_api", "claude-cli", "claude.exe",
    "CLAUDE_API_KEY", "ANTHROPIC_API_KEY",
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1 — bot/ source contains no Claude tokens
# ═══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("token", FORBIDDEN_TOKENS)
def test_bot_source_has_no_claude_token(token):
    hits = []
    for py in BOT_PKG_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if token.lower() in text.lower():
            hits.append(py.relative_to(BOT_PKG_DIR).as_posix())
    assert hits == [], f"token {token!r} found in bot/: {hits}"


def test_engine_source_does_not_shell_out_to_claude():
    text = ENGINE_FILE.read_text(encoding="utf-8").lower()
    # Forbidden as actual invocation; tokens listed in audit helper are OK
    # because they sit inside the audit's CLAUDE_FORBIDDEN_TOKENS tuple.
    for forbidden in ("subprocess.run([\"claude", "os.system(\"claude",
                       "popen([\"claude"):
        assert forbidden not in text, f"engine invokes claude: {forbidden}"


# ═══════════════════════════════════════════════════════════════════════════════
# 2 — pyproject lists no anthropic packages
# ═══════════════════════════════════════════════════════════════════════════════
def test_pyproject_has_no_anthropic_dep():
    text = PYPROJECT.read_text(encoding="utf-8").lower()
    for tok in ("anthropic", "claude-sdk", "claude_agent"):
        assert tok not in text, f"pyproject.toml depends on {tok!r}"


# ═══════════════════════════════════════════════════════════════════════════════
# 3 — KiteBot-Control/*.bat have no `claude` invocations
# ═══════════════════════════════════════════════════════════════════════════════
def test_control_bat_files_have_no_claude_invocation():
    if not CONTROL_DIR.exists():
        pytest.skip("KiteBot-Control not present on this host")
    hits = []
    for bat in CONTROL_DIR.glob("*.bat"):
        text = bat.read_text(encoding="utf-8").lower()
        for tok in ("claude", "anthropic"):
            if tok in text:
                hits.append(f"{bat.name}:{tok}")
    assert hits == [], f"control .bat files reference Claude: {hits}"


# ═══════════════════════════════════════════════════════════════════════════════
# 4 — runtime_audit returns 0 on a clean install
# ═══════════════════════════════════════════════════════════════════════════════
def test_runtime_audit_passes_clean(capsys, monkeypatch):
    """Drive the audit function directly; expect exit code 0."""
    import paper_engine
    rc = paper_engine.cmd_runtime_audit()
    out = capsys.readouterr().out
    assert "result: PASS" in out
    assert rc == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 5 — install_windows writes the 4 .bat files (no EMERGENCY)
# ═══════════════════════════════════════════════════════════════════════════════
def test_install_writes_four_bats_no_emergency(tmp_path, monkeypatch):
    """We don't run the full install (would touch the venv); we exercise the
    .bat-writing helper directly and verify its outputs."""
    import paper_engine
    monkeypatch.setattr(paper_engine, "CONTROL_DIR", tmp_path / "KiteBot-Control")
    monkeypatch.setattr(paper_engine, "LOG_DIR", tmp_path / "KiteBot-Control" / "logs")
    paper_engine._write_bat_files()
    written = {p.name for p in (tmp_path / "KiteBot-Control").glob("*.bat")}
    assert written == {"RUN_BOT.bat", "PAUSE_BOT.bat",
                        "RESUME_BOT.bat", "STATUS_BOT.bat"}
    # Explicitly: no EMERGENCY file
    assert not (tmp_path / "KiteBot-Control" / "EMERGENCY_FLATTEN.bat").exists()


def test_install_bats_reference_venv_python(tmp_path, monkeypatch):
    import paper_engine
    monkeypatch.setattr(paper_engine, "CONTROL_DIR", tmp_path / "KiteBot-Control")
    monkeypatch.setattr(paper_engine, "LOG_DIR", tmp_path / "KiteBot-Control" / "logs")
    paper_engine._write_bat_files()
    run_bot = (tmp_path / "KiteBot-Control" / "RUN_BOT.bat").read_text()
    assert ".venv\\Scripts\\python.exe" in run_bot
    assert "claude" not in run_bot.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 6 — RUN_BOT.bat runs runtime-audit before run-all
# ═══════════════════════════════════════════════════════════════════════════════
def test_run_bot_runs_audit_before_supervisor(tmp_path, monkeypatch):
    import paper_engine
    monkeypatch.setattr(paper_engine, "CONTROL_DIR", tmp_path / "KiteBot-Control")
    monkeypatch.setattr(paper_engine, "LOG_DIR", tmp_path / "KiteBot-Control" / "logs")
    paper_engine._write_bat_files()
    body = (tmp_path / "KiteBot-Control" / "RUN_BOT.bat").read_text()
    # runtime-audit must appear BEFORE run-all in the script
    audit_idx = body.find("runtime-audit")
    runall_idx = body.find("run-all")
    assert audit_idx >= 0, "runtime-audit not invoked in RUN_BOT.bat"
    assert runall_idx >  audit_idx, "run-all called before runtime-audit"


def test_run_bot_opens_selected_chart_not_bare_tradingview_protocol(tmp_path, monkeypatch):
    import paper_engine
    monkeypatch.setattr(paper_engine, "CONTROL_DIR", tmp_path / "KiteBot-Control")
    monkeypatch.setattr(paper_engine, "LOG_DIR", tmp_path / "KiteBot-Control" / "logs")
    paper_engine._write_bat_files()
    body = (tmp_path / "KiteBot-Control" / "RUN_BOT.bat").read_text()
    assert "paper_engine.py open-charts 3" in body
    assert 'start "" "tradingview:"' not in body.lower()


def test_tradingview_url_maps_crypto_inr_to_liquid_chart_symbol():
    import paper_engine
    assert paper_engine.tradingview_symbol_for("LINK-INR") == "BINANCE:LINKUSDT"
    assert "BINANCE%3ALINKUSDT" in paper_engine.tradingview_url_for("LINK-INR")


# ═══════════════════════════════════════════════════════════════════════════════
# Bonus — process-environment audit doesn't crash even with mock keys present
# ═══════════════════════════════════════════════════════════════════════════════
def test_runtime_audit_handles_env_vars(capsys, monkeypatch):
    monkeypatch.setenv("CLAUDE_API_KEY", "fake-for-test")
    import paper_engine
    rc = paper_engine.cmd_runtime_audit()
    out = capsys.readouterr().out
    # Env-var presence is a warning, not a blocker (we don't read it)
    assert rc == 0
    assert "Warnings" in out
    assert "CLAUDE_API_KEY" in out
