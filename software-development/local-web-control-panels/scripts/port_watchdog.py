#!/usr/bin/env python
"""Watchdog for a localhost control-panel server (Windows Task Scheduler friendly).

Silent by design: if the port answers it exits with no output and no log line.
If the port is dead it relaunches the server DETACHED (outlives the caller) and logs one line.

Register it to run every minute + at logon -- see templates/windows-watchdog-task.xml.
NEVER register it with `schtasks /create /sc minute` (that form caps repetition at PT10M).

Usage:
    pythonw port_watchdog.py --server-dir C:\\path\\to\\server --script editor_server.py --port 8791
"""
import argparse
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DETACHED = 0x8 | 0x200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def port_alive(port, host="127.0.0.1", timeout=2.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--server-dir", required=True)
    ap.add_argument("--script", default="editor_server.py")
    ap.add_argument("--log", default=str(Path.home() / ".hermes" / "tmp" / "panel_watchdog.log"))
    a = ap.parse_args()

    if port_alive(a.port):
        return  # nothing to do -- stay silent

    log = Path(a.log)
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} port {a.port} dead - starting {a.script}\n")

    subprocess.Popen(
        [sys.executable, a.script, "--port", str(a.port)],
        cwd=a.server_dir,
        creationflags=DETACHED,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    main()
