"""Runs the search every day with launchd (the macOS scheduler). If the Mac is asleep at that time,
launchd runs it when the Mac wakes."""
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from . import config

LABEL = "com.jobhunt.daily"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _launchctl(*args):
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def _require_macos():
    if sys.platform != "darwin":
        sys.exit("The daily schedule uses macOS launchd. On Linux add a cron line such as:\n"
                 f"  0 9 * * * cd {config.ROOT} && {sys.executable} -m jobhunt search\n"
                 "On Windows use Task Scheduler with the same command.")


def install(hour, minute):
    _require_macos()
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = str(config.LOG_DIR / "search.log")
    job = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-m", "jobhunt", "search", "--notify"],
        "WorkingDirectory": str(config.ROOT),
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": log,
        "StandardErrorPath": log,
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
    }
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    with open(PLIST, "wb") as handle:
        plistlib.dump(job, handle)
    domain = f"gui/{os.getuid()}"
    _launchctl("bootout", f"{domain}/{LABEL}")  # replace an older schedule if there is one
    result = _launchctl("bootstrap", domain, str(PLIST))
    if result.returncode != 0:
        sys.exit(f"launchctl could not load {PLIST}: {result.stderr.strip()}")
    print(f"The search now runs every day at {hour:02d}:{minute:02d} and shows a notification when done.")
    print(f"Log: {log}")
    print("The first run may ask whether python3 can access your Documents folder. Allow it, or the log will "
          "show 'Operation not permitted'.")


def uninstall():
    _require_macos()
    _launchctl("bootout", f"gui/{os.getuid()}/{LABEL}")
    if PLIST.exists():
        PLIST.unlink()
    print("Daily search removed.")
