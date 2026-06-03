"""
Operational control — kill switch + pause flag, file-persistent.

State lives in a JSON file (default: <project>/control_state.json) so it
survives process restarts and is not lost if the bot crashes or is killed.

Semantics:
  killed   — hard stop. Blocks all NEW BUY entries. Never blocks SELL/exits.
             Manual clear required (unkill). Includes reason + timestamp.
  paused   — soft stop. Blocks NEW BUY entries. Cleared by resume().
             Use for "stop trading for the rest of the day" without flattening.

These flags MUST be checked only on the entry path (BUY). The exit path
(SELL, stop-loss, target, flatten) must NEVER consult them — exits are
always allowed so risk can be unwound.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
import json
import os
import tempfile

# Default location — same dir as the SQLite DB by convention.
DEFAULT_CONTROL_PATH = Path(__file__).parent.parent / "control_state.json"

_control_path: Path = DEFAULT_CONTROL_PATH


def set_control_path(path: Path) -> None:
    """Override the on-disk control file (tests use this)."""
    global _control_path
    _control_path = Path(path)


def get_control_path() -> Path:
    return _control_path


@dataclass
class ControlState:
    killed:        bool = False
    kill_reason:   Optional[str] = None
    killed_at:     Optional[str] = None        # ISO 8601
    paused:        bool = False
    pause_reason:  Optional[str] = None
    paused_at:     Optional[str] = None

    def can_enter(self) -> bool:
        """True iff a new BUY entry is permitted by control flags alone."""
        return not (self.killed or self.paused)

    def block_reason(self) -> Optional[str]:
        if self.killed:
            return f"killed: {self.kill_reason or 'no reason'} (at {self.killed_at})"
        if self.paused:
            return f"paused: {self.pause_reason or 'no reason'} (at {self.paused_at})"
        return None


def _read() -> ControlState:
    path = _control_path
    if not path.exists():
        return ControlState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Corrupt file — fail closed: treat as killed so no entries fire
        return ControlState(
            killed=True,
            kill_reason=f"control file corrupt at {path}",
            killed_at=datetime.now().isoformat(timespec="seconds"),
        )
    # Tolerate unknown extra keys for forward compat
    fields = {k: raw.get(k) for k in ControlState.__dataclass_fields__}
    return ControlState(**fields)


def _write_atomic(state: ControlState) -> None:
    """Atomic write — temp file + rename — so a crash mid-write can't corrupt."""
    path = _control_path
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".ctrl_", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(state), f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── Public API ───────────────────────────────────────────────────────────────
def read_state() -> ControlState:
    return _read()


def is_killed() -> bool:
    return _read().killed


def is_paused() -> bool:
    return _read().paused


def can_enter() -> bool:
    """Convenience: True iff neither killed nor paused."""
    return _read().can_enter()


def kill(reason: str) -> ControlState:
    """Trip the kill switch. Persists across restarts until unkill()."""
    state = _read()
    state.killed = True
    state.kill_reason = reason
    state.killed_at = datetime.now().isoformat(timespec="seconds")
    _write_atomic(state)
    return state


def unkill() -> ControlState:
    """Manually clear the kill switch. Pause state is independent."""
    state = _read()
    state.killed = False
    state.kill_reason = None
    state.killed_at = None
    _write_atomic(state)
    return state


def pause(reason: str) -> ControlState:
    state = _read()
    state.paused = True
    state.pause_reason = reason
    state.paused_at = datetime.now().isoformat(timespec="seconds")
    _write_atomic(state)
    return state


def resume() -> ControlState:
    state = _read()
    state.paused = False
    state.pause_reason = None
    state.paused_at = None
    _write_atomic(state)
    return state
