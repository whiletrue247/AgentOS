"""
單元測試 — _is_retryable()
==========================
測試 Engine API 錯誤分類邏輯：
  可重試: Timeout, ConnectionError, 429 Rate Limit, 5xx Server Error
  不可重試: 401/403 Auth, 400 Bad Request, 其他未知錯誤
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 直接 import engine 模組的 _is_retryable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "04_Engine"))

from engine import _is_retryable  # noqa: E402


# ============================================================
# 可重試的錯誤
# ============================================================

class TestRetryableErrors:
    def test_timeout_error(self):
        assert _is_retryable(TimeoutError("Connection timed out")) is True

    def test_timeout_in_message(self):
        assert _is_retryable(Exception("Request timeout after 30s")) is True

    def test_connection_error(self):
        assert _is_retryable(ConnectionError("Connection refused")) is True

    def test_connection_in_message(self):
        assert _is_retryable(Exception("Failed to establish connection")) is True

    def test_429_status_code_attr(self):
        err = Exception("Rate limit exceeded")
        err.status_code = 429
        assert _is_retryable(err) is True

    def test_429_in_message(self):
        assert _is_retryable(Exception("Error 429: Too Many Requests")) is True

    def test_rate_limit_in_message(self):
        assert _is_retryable(Exception("rate limit reached for model")) is True

    def test_500_status_code(self):
        err = Exception("Internal Server Error")
        err.status_code = 500
        assert _is_retryable(err) is True

    def test_502_status_code(self):
        err = Exception("Bad Gateway")
        err.status_code = 502
        assert _is_retryable(err) is True

    def test_503_status_code(self):
        err = Exception("Service Unavailable")
        err.status_code = 503
        assert _is_retryable(err) is True

    def test_500_in_message(self):
        assert _is_retryable(Exception("HTTP 500 Internal Server Error")) is True

    def test_502_in_message(self):
        assert _is_retryable(Exception("502 Bad Gateway")) is True


# ============================================================
# 不可重試的錯誤
# ============================================================

class TestNonRetryableErrors:
    def test_401_unauthorized(self):
        err = Exception("Unauthorized")
        err.status_code = 401
        assert _is_retryable(err) is False

    def test_403_forbidden(self):
        err = Exception("Forbidden")
        err.status_code = 403
        assert _is_retryable(err) is False

    def test_400_bad_request(self):
        err = Exception("Bad Request: invalid model")
        err.status_code = 400
        assert _is_retryable(err) is False

    def test_404_not_found(self):
        err = Exception("Not Found")
        err.status_code = 404
        assert _is_retryable(err) is False

    def test_generic_value_error(self):
        assert _is_retryable(ValueError("Invalid input format")) is False

    def test_generic_key_error(self):
        assert _is_retryable(KeyError("missing_key")) is False

    def test_generic_unknown_error(self):
        assert _is_retryable(Exception("Something went wrong")) is False
