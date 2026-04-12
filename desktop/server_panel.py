"""root directory = cwd)."""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def start_uvicorn(host: str, port: int, log_queue: queue.Queue) -> tuple[subprocess.Popen | None, str | None]:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "API.main:app",
        f"--host={host}",
        f"--port={port}",
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return None, str(exc)

    threading.Thread(target=_read_stdout, args=(proc, log_queue), daemon=True).start()
    return proc, None


def _read_stdout(proc: subprocess.Popen, log_queue: queue.Queue) -> None:
    if proc.stdout is None:
        return
    for line in proc.stdout:
        log_queue.put(line)
    proc.stdout.close()
    code = proc.poll()
    log_queue.put(f"\n[strežnik] proces končan (koda {code}).\n")


def stop_process(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
