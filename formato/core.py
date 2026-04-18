import logging
import re
import subprocess
import threading
import time

import requests
from AppKit import NSPasteboard

from formato.config import Config

log = logging.getLogger(__name__)

GITHUB_PR_PATTERN = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?$")
PBOARD_TYPE = "public.utf8-plain-text"
SLACK_BUNDLE_ID = "com.tinyspeck.slackmacgap"


class State:
    def __init__(self):
        self._pending_url: str | None = None
        self._title: str | None = None
        self._html: str | None = None
        self._swapped_url: str | None = None
        self.swap_on_ready: bool = False
        self._lock = threading.Lock()

    def set_pending(self, url: str, swap_on_ready: bool = False) -> None:
        with self._lock:
            self._pending_url = url
            self._title = None
            self._html = None
            self._swapped_url = None
            self.swap_on_ready = swap_on_ready

    def set_formatted(self, url: str, title: str, html: str) -> None:
        with self._lock:
            if self._pending_url == url:
                self._title = title
                self._html = html

    def take_formatted(self) -> tuple[str, str, str] | None:
        """Returns (original_url, title, html) and clears state, or None if not ready."""
        with self._lock:
            if self._title is None:
                return None
            result = (self._pending_url, self._title, self._html)
            self._pending_url = None
            self._title = None
            self._html = None
            self.swap_on_ready = False
            return result

    def set_swapped(self, url: str) -> None:
        with self._lock:
            self._swapped_url = url

    def set_swap_on_ready(self) -> None:
        with self._lock:
            if self._pending_url is not None:
                self.swap_on_ready = True

    def take_swapped(self) -> str | None:
        with self._lock:
            url = self._swapped_url
            self._swapped_url = None
            return url

    def clear(self) -> None:
        with self._lock:
            self._pending_url = None
            self._title = None
            self._html = None
            self._swapped_url = None
            self.swap_on_ready = False


_title_cache: dict[str, str] = {}


def fetch_and_store(
    url: str, owner: str, repo: str, number: str, token: str | None, state: State
) -> None:
    if url in _title_cache:
        title = _title_cache[url]
        state.set_formatted(url, title, f'<a href="{url}">{title}</a>')
        log.debug("Cache hit: %s (%s)", title, url)
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
            state.set_formatted(url, title, f'<a href="{url}">{title}</a>')
            log.info("Pre-fetched: [%s](%s)", title, url)
    except requests.RequestException as e:
        log.error("GitHub API error: %s", e)


_slack_active = False
_slack_lock = threading.Lock()


def _slack_monitor(poll_interval: float) -> None:
    global _slack_active
    while True:
        try:
            result = subprocess.run(
                ["osascript", "-e", "tell application \"System Events\" to get bundle identifier of first application process whose frontmost is true"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            active = result.stdout.strip() == SLACK_BUNDLE_ID
        except Exception:
            active = False
        with _slack_lock:
            _slack_active = active
        time.sleep(poll_interval)


def is_slack_active() -> bool:
    with _slack_lock:
        return _slack_active


def get_clipboard(pb: NSPasteboard) -> str | None:
    return pb.stringForType_(PBOARD_TYPE)


def set_clipboard(pb: NSPasteboard, text: str, html: str | None = None) -> None:
    pb.clearContents()
    if html:
        pb.setString_forType_(html, "public.html")
    pb.setString_forType_(text, PBOARD_TYPE)


def run() -> None:
    config = Config()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    threading.Thread(target=_slack_monitor, args=(config.slack_poll_interval,), daemon=True).start()

    if not config.github_token:
        log.warning("github_token not set — unauthenticated requests are limited to 60/hour.")

    pb = NSPasteboard.generalPasteboard()
    state = State()
    last_count = pb.changeCount()
    slack_was_active = is_slack_active()

    log.info("formato running — watching clipboard for GitHub PR links...")

    while True:
        time.sleep(config.poll_interval)

        slack_now_active = is_slack_active()
        current_count = pb.changeCount()
        if current_count != last_count:
            last_count = current_count
            state.take_swapped()
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
                        args=(url, owner, repo, number, config.github_token, state),
                        daemon=True,
                    ).start()
                else:
                    state.clear()

        if slack_now_active and not slack_was_active:
            state.set_swap_on_ready()

        if slack_now_active and state.swap_on_ready:
            result = state.take_formatted()
            if result:
                original_url, title, html = result
                set_clipboard(pb, title, html)
                last_count = pb.changeCount()
                state.set_swapped(original_url)
                log.info("Swapped clipboard for Slack: %s", title)

        if slack_was_active and not slack_now_active:
            original_url = state.take_swapped()
            if original_url:
                set_clipboard(pb, original_url)
                last_count = pb.changeCount()
                log.info("Restored clipboard: %s", original_url)

        slack_was_active = slack_now_active
