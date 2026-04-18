import subprocess
import sys
from pathlib import Path

from formato.config import CONFIG_PATH

PLIST_LABEL = "com.formato.agent"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"
LOG_PATH = Path.home() / "Library" / "Logs" / "formato.log"

PLIST_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{binary}</string>
        <string>run</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log}</string>
    <key>StandardErrorPath</key>
    <string>{log}</string>
</dict>
</plist>
"""


def install() -> None:
    binary = Path(sys.argv[0]).resolve()

    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    plist = PLIST_TEMPLATE.format(label=PLIST_LABEL, binary=binary, log=LOG_PATH)
    PLIST_PATH.write_text(plist)
    print(f"Wrote {PLIST_PATH}")

    # Unload first in case it's already registered (reinstall)
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    result = subprocess.run(["launchctl", "load", str(PLIST_PATH)], capture_output=True, text=True)

    if result.returncode != 0:
        print(f"launchctl load failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    print("formato installed and running. Starts automatically on login.")
    print(f"Logs: {LOG_PATH}")
    print()
    print(f"To set your GitHub token, create {CONFIG_PATH}:")
    print('  github_token = "ghp_..."')
