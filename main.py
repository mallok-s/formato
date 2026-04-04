import logging
import os
import re
import threading
import time

import requests
from AppKit import NSPasteboard, NSWorkspace

log = logging.getLogger(__name__)

GITHUB_PR_PATTERN = re.compile(
    r"^https://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?$"
)
POLL_INTERVAL = 0.1
PBOARD_TYPE = "public.utf8-plain-text"
SLACK_BUNDLE_ID = "com.tinyspeck.slackmacgap"


class State:
    def __init__(self):
        self._pending_url: str | None = None
        self._formatted: str | None = None
        self.swap_on_ready: bool = False  # True if Slack was already active when URL was copied
        self._lock = threading.Lock()

    def set_pending(self, url: str, swap_on_ready: bool = False) -> None:
        with self._lock:
            self._pending_url = url
            self._formatted = None
            self.swap_on_ready = swap_on_ready

    def set_formatted(self, url: str, formatted: str) -> None:
        with self._lock:
            if self._pending_url == url:  # discard if user already copied something else
                self._formatted = formatted

    def take_formatted(self) -> str | None:
        """Returns the formatted string and clears state, or None if not ready."""
        with self._lock:
            result = self._formatted
            if result:
                self._pending_url = None
                self._formatted = None
                self.swap_on_ready = False
            return result

    def clear(self) -> None:
        with self._lock:
            self._pending_url = None
            self._formatted = None
            self.swap_on_ready = False


_title_cache: dict[str, str] = {}


def fetch_and_store(url: str, owner: str, repo: str, number: str, token: str | None, state: State) -> None:
    if url in _title_cache:
        title = _title_cache[url]
        state.set_formatted(url, f"[{title}]({url})")
        log.debug("Cache hit: [%s](%s)", title, url)
        return

    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.get(api_url, headers=headers, timeout=5)
        response.raise_for_status()
        title = response.json().get("title")
        if title:
            _title_cache[url] = title
            state.set_formatted(url, f"[{title}]({url})")
            log.info("Pre-fetched: [%s](%s)", title, url)
    except requests.RequestException as e:
        log.error("GitHub API error: %s", e)


def is_slack_active() -> bool:
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return app is not None and app.bundleIdentifier() == SLACK_BUNDLE_ID


def get_clipboard(pb: NSPasteboard) -> str | None:
    return pb.stringForType_(PBOARD_TYPE)


def set_clipboard(pb: NSPasteboard, text: str) -> None:
    pb.clearContents()
    pb.setString_forType_(text, PBOARD_TYPE)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        log.warning("GITHUB_TOKEN not set. Rate limits may apply.")

    pb = NSPasteboard.generalPasteboard()
    state = State()
    last_count = pb.changeCount()
    slack_was_active = is_slack_active()

    log.info("formato running — watching clipboard for GitHub PR links...")

    while True:
        time.sleep(POLL_INTERVAL)

        # Detect clipboard changes
        current_count = pb.changeCount()
        if current_count != last_count:
            last_count = current_count
            content = get_clipboard(pb)
            if content:
                url = content.strip()
                match = GITHUB_PR_PATTERN.match(url)
                if match:
                    owner, repo, number = match.groups()
                    log.info("Detected PR: %s/%s#%s — pre-fetching...", owner, repo, number)
                    state.set_pending(url, swap_on_ready=slack_now_active)
                    threading.Thread(
                        target=fetch_and_store,
                        args=(url, owner, repo, number, token, state),
                        daemon=True,
                    ).start()
                else:
                    state.clear()

        # Detect Slack becoming active (transition) or fetch completing while already in Slack
        slack_now_active = is_slack_active()
        should_swap = (slack_now_active and not slack_was_active) or (slack_now_active and state.swap_on_ready)
        if should_swap:
            formatted = state.take_formatted()
            if formatted:
                set_clipboard(pb, formatted)
                last_count = pb.changeCount()  # absorb our own write
                log.info("Swapped clipboard for Slack: %s", formatted)
        slack_was_active = slack_now_active


if __name__ == "__main__":
    main()
