import sys
from unittest.mock import MagicMock, patch

# Mock AppKit before importing core since it requires macOS frameworks
sys.modules["AppKit"] = MagicMock()

import formato.core as core  # noqa: E402


# --- GITHUB_PR_PATTERN ---

class TestGithubPrPattern:
    def match(self, url):
        return core.GITHUB_PR_PATTERN.match(url)

    def test_valid_pr_url(self):
        m = self.match("https://github.com/owner/repo/pull/123")
        assert m is not None
        assert m.groups() == ("owner", "repo", "123")

    def test_valid_pr_url_trailing_slash(self):
        m = self.match("https://github.com/owner/repo/pull/123/")
        assert m is not None
        assert m.groups() == ("owner", "repo", "123")

    def test_issue_url_not_matched(self):
        assert self.match("https://github.com/owner/repo/issues/123") is None

    def test_non_github_url_not_matched(self):
        assert self.match("https://gitlab.com/owner/repo/pull/123") is None

    def test_plain_text_not_matched(self):
        assert self.match("hello world") is None

    def test_pr_url_with_extra_path_not_matched(self):
        assert self.match("https://github.com/owner/repo/pull/123/files") is None

    def test_org_with_hyphens_and_dots(self):
        m = self.match("https://github.com/my-org/my.repo/pull/99")
        assert m is not None
        assert m.groups() == ("my-org", "my.repo", "99")


# --- State ---

class TestState:
    def test_take_formatted_returns_none_when_empty(self):
        state = core.State()
        assert state.take_formatted() is None

    def test_set_and_take_formatted(self):
        state = core.State()
        url = "https://github.com/o/r/pull/1"
        state.set_pending(url)
        state.set_formatted(url, "Title", f'<a href="{url}">Title</a>')
        result = state.take_formatted()
        assert result == (url, "Title", f'<a href="{url}">Title</a>')

    def test_take_formatted_clears_state(self):
        state = core.State()
        url = "https://github.com/o/r/pull/1"
        state.set_pending(url)
        state.set_formatted(url, "Title", f'<a href="{url}">Title</a>')
        state.take_formatted()
        assert state.take_formatted() is None

    def test_set_formatted_discards_stale_url(self):
        state = core.State()
        state.set_pending("https://github.com/o/r/pull/1")
        state.set_pending("https://github.com/o/r/pull/2")
        state.set_formatted("https://github.com/o/r/pull/1", "Old", "<a>Old</a>")
        assert state.take_formatted() is None

    def test_swap_on_ready_set_when_slack_active(self):
        state = core.State()
        state.set_pending("https://github.com/o/r/pull/1", swap_on_ready=True)
        assert state.swap_on_ready is True

    def test_swap_on_ready_false_by_default(self):
        state = core.State()
        state.set_pending("https://github.com/o/r/pull/1")
        assert state.swap_on_ready is False

    def test_swap_on_ready_cleared_after_take(self):
        state = core.State()
        url = "https://github.com/o/r/pull/1"
        state.set_pending(url, swap_on_ready=True)
        state.set_formatted(url, "Title", f'<a href="{url}">Title</a>')
        state.take_formatted()
        assert state.swap_on_ready is False

    def test_clear_resets_all(self):
        state = core.State()
        url = "https://github.com/o/r/pull/1"
        state.set_pending(url, swap_on_ready=True)
        state.set_formatted(url, "Title", f'<a href="{url}">Title</a>')
        state.clear()
        assert state.take_formatted() is None
        assert state.swap_on_ready is False

    def test_set_pending_clears_previous_formatted(self):
        state = core.State()
        url = "https://github.com/o/r/pull/1"
        state.set_pending(url)
        state.set_formatted(url, "Title", f'<a href="{url}">Title</a>')
        state.set_pending("https://github.com/o/r/pull/2")
        assert state.take_formatted() is None

    def test_set_and_take_swapped(self):
        state = core.State()
        state.set_swapped("https://github.com/o/r/pull/1")
        assert state.take_swapped() == "https://github.com/o/r/pull/1"

    def test_take_swapped_returns_none_when_empty(self):
        state = core.State()
        assert state.take_swapped() is None

    def test_take_swapped_clears_state(self):
        state = core.State()
        state.set_swapped("https://github.com/o/r/pull/1")
        state.take_swapped()
        assert state.take_swapped() is None

    def test_set_swap_on_ready_sets_flag_when_pending(self):
        state = core.State()
        state.set_pending("https://github.com/o/r/pull/1")
        state.set_swap_on_ready()
        assert state.swap_on_ready is True

    def test_set_swap_on_ready_no_op_when_nothing_pending(self):
        state = core.State()
        state.set_swap_on_ready()
        assert state.swap_on_ready is False

    def test_set_pending_clears_swapped(self):
        state = core.State()
        state.set_swapped("https://github.com/o/r/pull/1")
        state.set_pending("https://github.com/o/r/pull/2")
        assert state.take_swapped() is None

    def test_clear_resets_swapped(self):
        state = core.State()
        state.set_swapped("https://github.com/o/r/pull/1")
        state.clear()
        assert state.take_swapped() is None


# --- fetch_and_store ---

class TestFetchAndStore:
    URL = "https://github.com/owner/repo/pull/42"

    def setup_method(self):
        core._title_cache.clear()

    def test_stores_formatted_on_success(self):
        state = core.State()
        state.set_pending(self.URL)
        mock_response = MagicMock()
        mock_response.json.return_value = {"title": "Fix the bug"}
        with patch("formato.core.requests.get", return_value=mock_response):
            core.fetch_and_store(self.URL, "owner", "repo", "42", None, state)
        assert state.take_formatted() == (self.URL, "Fix the bug", '<a href="https://github.com/owner/repo/pull/42">Fix the bug</a>')

    def test_includes_auth_header_with_token(self):
        state = core.State()
        state.set_pending(self.URL)
        mock_response = MagicMock()
        mock_response.json.return_value = {"title": "Fix"}
        with patch("formato.core.requests.get", return_value=mock_response) as mock_get:
            core.fetch_and_store(self.URL, "owner", "repo", "42", "mytoken", state)
        headers = mock_get.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer mytoken"

    def test_no_auth_header_without_token(self):
        state = core.State()
        state.set_pending(self.URL)
        mock_response = MagicMock()
        mock_response.json.return_value = {"title": "Fix"}
        with patch("formato.core.requests.get", return_value=mock_response) as mock_get:
            core.fetch_and_store(self.URL, "owner", "repo", "42", None, state)
        headers = mock_get.call_args.kwargs["headers"]
        assert "Authorization" not in headers

    def test_does_not_update_state_on_request_error(self):
        state = core.State()
        state.set_pending(self.URL)
        with patch("formato.core.requests.get", side_effect=core.requests.RequestException("timeout")):
            core.fetch_and_store(self.URL, "owner", "repo", "42", None, state)
        assert state.take_formatted() is None

    def test_does_not_update_state_when_title_missing(self):
        state = core.State()
        state.set_pending(self.URL)
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        with patch("formato.core.requests.get", return_value=mock_response):
            core.fetch_and_store(self.URL, "owner", "repo", "42", None, state)
        assert state.take_formatted() is None

    def test_cache_hit_skips_network_request(self):
        core._title_cache[self.URL] = "Cached Title"
        state = core.State()
        state.set_pending(self.URL)
        with patch("formato.core.requests.get") as mock_get:
            core.fetch_and_store(self.URL, "owner", "repo", "42", None, state)
        mock_get.assert_not_called()
        assert state.take_formatted() == (self.URL, "Cached Title", '<a href="https://github.com/owner/repo/pull/42">Cached Title</a>')

    def test_successful_fetch_populates_cache(self):
        core._title_cache.pop(self.URL, None)
        state = core.State()
        state.set_pending(self.URL)
        mock_response = MagicMock()
        mock_response.json.return_value = {"title": "New Title"}
        with patch("formato.core.requests.get", return_value=mock_response):
            core.fetch_and_store(self.URL, "owner", "repo", "42", None, state)
        assert core._title_cache[self.URL] == "New Title"
