# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

ROOT = Path(__file__).resolve().parent.parent
LIBS = ROOT / "libs"
for p in (str(ROOT), str(LIBS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from claude_client import (
    CLAUDE_API_RETRY_ATTEMPTS,
    CLAUDE_API_RETRY_WAIT_SECONDS,
    claude_generate_text,
)


class ClaudeApiRetryTest(unittest.TestCase):
    def _ok_response(self) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "content": [{"type": "text", "text": '{"ok": true}'}],
        }
        resp.raise_for_status.return_value = None
        return resp

    @patch("claude_client.time.sleep")
    @patch("claude_client.requests.post")
    @patch("claude_client.get_anthropic_api_key", return_value="test-key")
    def test_retries_on_api_error_then_succeeds(self, _key, mock_post, mock_sleep):
        err_resp = MagicMock()
        err_resp.status_code = 503
        err_resp.raise_for_status.side_effect = requests.HTTPError(
            "503 Server Error", response=err_resp
        )
        mock_post.side_effect = [err_resp, err_resp, self._ok_response()]

        text, model = claude_generate_text("ping", MagicMock(), cache={})

        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_called_with(CLAUDE_API_RETRY_WAIT_SECONDS)
        self.assertIn("ok", text)
        self.assertTrue(model)

    @patch("claude_client.time.sleep")
    @patch("claude_client.requests.post")
    @patch("claude_client.get_anthropic_api_key", return_value="test-key")
    def test_raises_after_three_failed_attempts(self, _key, mock_post, mock_sleep):
        err_resp = MagicMock()
        err_resp.status_code = 503
        err_resp.raise_for_status.side_effect = requests.HTTPError(
            "503 Server Error", response=err_resp
        )
        mock_post.return_value = err_resp

        with self.assertRaises(requests.HTTPError):
            claude_generate_text("ping", MagicMock(), cache={})

        self.assertEqual(mock_post.call_count, CLAUDE_API_RETRY_ATTEMPTS)
        self.assertEqual(mock_sleep.call_count, CLAUDE_API_RETRY_ATTEMPTS - 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
