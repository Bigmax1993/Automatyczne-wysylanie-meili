# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
LIBS = ROOT / "libs"
for p in (str(ROOT), str(LIBS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import claude_client as cc


class ClaudeModelTierTest(unittest.TestCase):
    def test_resolve_fast_and_verify_defaults(self):
        self.assertEqual(
            cc.resolve_claude_model(model_tier="fast"),
            cc.DEFAULT_CLAUDE_MODEL_FAST,
        )
        self.assertEqual(
            cc.resolve_claude_model(model_tier="verify"),
            cc.DEFAULT_CLAUDE_MODEL_VERIFY,
        )

    @patch("claude_client.get_env_value", return_value="")
    @patch("claude_client.requests.post")
    @patch("claude_client.get_anthropic_api_key", return_value="test-key")
    def test_generate_text_uses_model_tier(self, _key, mock_post, _env):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"content": [{"type": "text", "text": "ok"}]}
        resp.raise_for_status.return_value = None
        mock_post.return_value = resp

        _, model_fast = cc.claude_generate_text(
            "ping", MagicMock(), cache={}, model_tier="fast"
        )
        _, model_verify = cc.claude_generate_text(
            "ping", MagicMock(), cache={}, model_tier="verify"
        )

        self.assertEqual(model_fast, cc.DEFAULT_CLAUDE_MODEL_FAST)
        self.assertEqual(model_verify, cc.DEFAULT_CLAUDE_MODEL_VERIFY)
        payloads = [call.kwargs["json"] for call in mock_post.call_args_list]
        self.assertEqual(payloads[0]["model"], cc.DEFAULT_CLAUDE_MODEL_FAST)
        self.assertEqual(payloads[1]["model"], cc.DEFAULT_CLAUDE_MODEL_VERIFY)


if __name__ == "__main__":
    unittest.main()
