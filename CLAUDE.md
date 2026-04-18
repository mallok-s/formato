# formato

macOS clipboard tool that auto-formats GitHub PR URLs into hyperlinks when pasting into Slack.

## Running

```bash
uv run formato run
```

Or the legacy form still works: `uv run python main.py`

### Configuration

Config is read from `~/.config/formato/config.toml` (created manually):

```toml
github_token = "ghp_..."   # optional but recommended — 60 req/hr without it
# poll_interval = 0.1
# slack_poll_interval = 0.25
```

The `GITHUB_TOKEN` environment variable is also accepted as a fallback.

## Installing as a background service (no terminal)

```bash
uv tool install formato
formato install
```

`formato install` writes a LaunchAgent plist to `~/Library/LaunchAgents/com.formato.agent.plist` and loads it with `launchctl`. The agent starts automatically on login and restarts if it crashes. Logs go to `~/Library/Logs/formato.log`.

To uninstall:
```bash
launchctl unload ~/Library/LaunchAgents/com.formato.agent.plist
rm ~/Library/LaunchAgents/com.formato.agent.plist
```

## How it works

- Polls `NSPasteboard.changeCount()` every 100ms (cheap integer check)
- When a GitHub PR URL is copied, immediately fetches the PR title from the GitHub API in a background thread
- Uses `osascript` to detect when Slack becomes the frontmost app
- On Slack activation, swaps the clipboard to an HTML `<a href>` hyperlink — Slack's composer renders this as a clickable named link
- When leaving Slack, restores the original URL to the clipboard
- If the user copies something new while in Slack, the pending restore is discarded

## Key design decisions

- **`NSWorkspace` is not used for app detection** — it returns the terminal process instead of the actual frontmost app when run from CLI. `osascript` is used instead.
- **Slack detection runs in a background thread** — polling `osascript` on the main thread caused multi-monitor flakiness; the background thread updates a shared flag every 250ms.
- **HTML clipboard format** — Slack's `<url|title>` mrkdwn format only works in the API, not the composer. Pasting HTML `<a href>` is what renders as a hyperlink.
- **Pre-fetching** — the title is fetched the moment a PR URL is copied, so there's no delay at paste time.
- **`swap_on_ready` flag** — when the user switches to Slack before the GitHub fetch completes, the swap is deferred via this flag rather than dropped. The main loop retries every poll until the fetch finishes.
- **In-memory title cache** — repeated copies of the same PR URL skip the network request.
- **pydantic-settings config** — `Config` in `formato/config.py` reads `~/.config/formato/config.toml` via `TomlConfigSettingsSource`, with env vars as a higher-priority override.

## Package structure

```
formato/
  config.py    — pydantic-settings Config (toml + env vars)
  core.py      — clipboard monitoring logic
  cli.py       — `formato [run|install]` entry point
  install.py   — launchd plist generation and loading
tests/
  test_core.py
main.py        — thin shim for `uv run python main.py` backward compat
```

## Testing

```bash
uv run pytest
```

`AppKit` is mocked at import time in tests so they run without macOS frameworks.

## Dependencies

- `pyobjc-framework-Cocoa` — `NSPasteboard` for clipboard read/write
- `requests` — GitHub API calls
- `pydantic-settings[toml]` — config file parsing
