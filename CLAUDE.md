# formato

macOS clipboard tool that auto-formats GitHub PR URLs into hyperlinks when pasting into Slack.

## Running

```bash
GITHUB_TOKEN=your_token uv run python main.py
```

`GITHUB_TOKEN` is optional but recommended — unauthenticated GitHub API requests are limited to 60/hour.

## How it works

- Polls `NSPasteboard.changeCount()` every 100ms (cheap integer check)
- When a GitHub PR URL is copied, immediately fetches the PR title from the GitHub API in a background thread
- Uses `osascript` to detect when Slack becomes the frontmost app
- On Slack activation, swaps the clipboard to an HTML `<a href>` hyperlink — Slack's composer renders this as a clickable named link
- When leaving Slack, restores the original URL to the clipboard
- If the user copies something new while in Slack, the pending restore is discarded

## Key design decisions

- **`NSWorkspace` is not used for app detection** — it returns the terminal process instead of the actual frontmost app when run from CLI. `osascript` is used instead.
- **HTML clipboard format** — Slack's `<url|title>` mrkdwn format only works in the API, not the composer. Pasting HTML `<a href>` is what renders as a hyperlink.
- **Pre-fetching** — the title is fetched the moment a PR URL is copied, so there's no delay at paste time.
- **In-memory title cache** — repeated copies of the same PR URL skip the network request.

## Testing

```bash
uv run pytest
```

`AppKit` is mocked at import time in tests so they run without macOS frameworks.

## Dependencies

- `pyobjc-framework-Cocoa` — `NSPasteboard` for clipboard read/write
- `requests` — GitHub API calls
