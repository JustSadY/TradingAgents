from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import threading
import time
from pathlib import Path

_logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATUS_FILE = PROJECT_ROOT / ".update.json"
UPDATE_UNIT = os.environ.get("TRADINGAGENTS_UPDATE_UNIT", "")
SYSTEMCTL = os.environ.get("TRADINGAGENTS_SYSTEMCTL", "systemctl")
UPDATE_SUPPORTED = platform.system() == "Linux" and bool(UPDATE_UNIT)
_FETCH_TTL = 60.0
_last_fetch = 0.0
_fetch_lock = threading.Lock()
_fetching = False


def _git(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        return subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except Exception as exc:

        class MockCompletedProcess:
            returncode = -1
            stdout = ""
            stderr = str(exc)

        return MockCompletedProcess()


def _bg_fetch():
    global _last_fetch, _fetching
    try:
        _git("fetch", "--quiet", timeout=15)
    except Exception as exc:
        _logger.debug("Background git fetch failed: %s", exc)
    finally:
        _last_fetch = time.time()
        with _fetch_lock:
            _fetching = False


def _read_status() -> dict | None:
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as exc:
        _logger.warning("Could not read update status file %s: %s", STATUS_FILE, exc)
        return None


def _write_status(data: dict) -> None:
    try:
        STATUS_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception as exc:
        _logger.warning("Could not write update status file %s: %s", STATUS_FILE, exc)


def get_status(do_fetch: bool = True) -> dict:
    global _last_fetch, _fetching
    if not (PROJECT_ROOT / ".git").is_dir():
        status = _read_status() or {}
        return {
            "git": False,
            "update_supported": UPDATE_SUPPORTED,
            "current": None,
            "current_short": None,
            "latest_short": None,
            "behind": 0,
            "update_available": False,
            "updating": status.get("state") == "running",
            "last_update": status,
            "commits": [],
        }
    head = _git("rev-parse", "HEAD")
    if head.returncode != 0:
        status = _read_status() or {}
        return {
            "git": False,
            "update_supported": UPDATE_SUPPORTED,
            "current": None,
            "current_short": None,
            "latest_short": None,
            "behind": 0,
            "update_available": False,
            "updating": status.get("state") == "running",
            "last_update": status,
            "commits": [],
        }
    current = head.stdout.strip()
    up = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    upstream = up.stdout.strip() if up.returncode == 0 else ""
    if do_fetch and upstream and (time.time() - _last_fetch) > _FETCH_TTL:
        should_start = False
        with _fetch_lock:
            if not _fetching:
                _fetching = True
                should_start = True
        if should_start:
            threading.Thread(target=_bg_fetch, daemon=True).start()
    latest, behind, commits = current, 0, []
    if upstream:
        lt = _git("rev-parse", upstream)
        if lt.returncode == 0:
            latest = lt.stdout.strip()
        rc = _git("rev-list", "--count", f"HEAD..{upstream}")
        if rc.returncode == 0:
            behind = int(rc.stdout.strip() or "0")
        if behind:
            lg = _git("log", "--pretty=format:%h %s", f"HEAD..{upstream}", "-n", "15")
            if lg.returncode == 0:
                commits = [line for line in lg.stdout.splitlines() if line.strip()]
    status = _read_status() or {}

    # Eğer "running" durumu çok uzun sürüyorsa otomatik olarak "failed" yap
    if status.get("state") == "running":
        at_str = status.get("at", "")
        if at_str:
            try:
                import datetime
                started = datetime.datetime.fromisoformat(at_str.replace("Z", "+00:00"))
                elapsed = (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds()
                if elapsed > _UPDATE_STUCK_TIMEOUT:
                    status = {
                        "state": "failed",
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "error": f"Update timed out after {int(elapsed // 60)} minutes.",
                    }
                    _write_status(status)
            except Exception:
                pass

    return {
        "git": True,
        "update_supported": UPDATE_SUPPORTED,
        "current": current,
        "current_short": current[:9],
        "latest_short": latest[:9],
        "behind": behind,
        "update_available": behind > 0,
        "updating": status.get("state") == "running",
        "last_update": status,
        "commits": commits,
    }


def request_update() -> dict:
    if not UPDATE_SUPPORTED:
        raise RuntimeError(
            "Automatic updates are not configured or not supported in this environment "
            "(only works on Linux systems installed with deploy/install.sh)."
        )
    status = _read_status()
    if status and status.get("state") == "running":
        raise RuntimeError("Update is already in progress.")
    _write_status({"state": "running", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    try:
        subprocess.run(
            ["sudo", "-n", SYSTEMCTL, "start", "--no-block", UPDATE_UNIT],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        _write_status({"state": "failed", "error": detail})
        raise RuntimeError(f"Could not start update: {detail}") from exc
    return {"started": True}


_UPDATE_STUCK_TIMEOUT = 15 * 60  # 15 dakika


def reset_stuck_update() -> None:
    """Reset the update state if it was left in 'running' state on server startup or timed out."""
    status = _read_status()
    if not status or status.get("state") != "running":
        return

    # Zaman damgasına bakarak gerçekten takılıp takılmadığını kontrol et
    stuck_reason = "Server restarted during update."
    at_str = status.get("at", "")
    if at_str:
        try:
            import datetime
            started = datetime.datetime.fromisoformat(at_str.replace("Z", "+00:00"))
            elapsed = (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds()
            if elapsed < _UPDATE_STUCK_TIMEOUT:
                # Henüz çok yeni, belki hâlâ devam ediyor — dokunma
                return
            stuck_reason = f"Update timed out after {int(elapsed // 60)} minutes."
        except Exception:
            pass

    _logger.info("Resetting stuck update state to 'failed': %s", stuck_reason)
    _write_status(
        {
            "state": "failed",
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "error": stuck_reason,
        }
    )
