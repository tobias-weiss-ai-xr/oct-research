"""Unit tests for repos_common.http_get_with_retry / _retry_after_seconds."""

import unittest.mock as mock

import pytest

from repos_common import _retry_after_seconds, http_get_with_retry, DEFAULT_USER_AGENT


class _FakeResp:
    def __init__(self, status_code=200, headers=None, text="ok"):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text


def _fake_session(sequence):
    """Return a Session stub whose .get() consumes ``sequence`` of responses."""
    responses = iter(sequence)
    sess = mock.Mock()
    sess.get = mock.Mock(side_effect=lambda *a, **k: next(responses))
    return sess


NOOP = lambda _s: None  # noqa: E731  -- injected sleep keeps tests instant


def test_returns_response_on_200():
    sess = _fake_session([_FakeResp(200)])
    resp = http_get_with_retry(sess, "http://x", max_retries=2, sleep_fn=NOOP)
    assert resp.status_code == 200


def test_retries_on_429_then_succeeds():
    sess = _fake_session([_FakeResp(429, {"Retry-After": "1"}), _FakeResp(200)])
    resp = http_get_with_retry(sess, "http://x", max_retries=3,
                               rate_limit_wait=10, sleep_fn=NOOP)
    assert resp.status_code == 200
    assert sess.get.call_count == 2


def test_returns_none_after_exhausting_retries():
    resp429 = _FakeResp(429, {"Retry-After": "1"})
    sess = _fake_session([resp429] * 2)
    resp = http_get_with_retry(sess, "http://x", max_retries=2,
                               rate_limit_wait=5, sleep_fn=NOOP)
    assert resp is None


def test_retries_on_5xx_then_succeeds():
    sess = _fake_session([_FakeResp(500), _FakeResp(503), _FakeResp(200)])
    resp = http_get_with_retry(sess, "http://x", max_retries=3, sleep_fn=NOOP)
    assert resp.status_code == 200


def test_returns_none_after_exhausting_5xx():
    sess = _fake_session([_FakeResp(502)] * 3)
    resp = http_get_with_retry(sess, "http://x", max_retries=3, sleep_fn=NOOP)
    assert resp is None


def test_retry_after_numeric_capped():
    resp = _FakeResp(429, {"Retry-After": "9999"})
    assert _retry_after_seconds(resp, 60) == 60


def test_retry_after_small_value_respected():
    resp = _FakeResp(429, {"Retry-After": "5"})
    assert _retry_after_seconds(resp, 60) == 5


def test_retry_after_missing_uses_default():
    resp = _FakeResp(429, {})
    assert _retry_after_seconds(resp, 60) == 60


def test_retry_after_min_one():
    resp = _FakeResp(429, {"Retry-After": "0"})
    assert _retry_after_seconds(resp, 60) == 1


def test_default_user_agent_has_contact():
    # The default UA always carries a resolvable contact mailbox.
    assert "mailto:" in DEFAULT_USER_AGENT and "@" in DEFAULT_USER_AGENT
