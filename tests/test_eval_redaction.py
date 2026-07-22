from __future__ import annotations

import unittest

from agentkit.evals.redaction import redact


class EvaluationRedactionTests(unittest.TestCase):
    def test_redacts_secret_keys_and_common_tokens(self) -> None:
        payload = redact({"api_key": "secret", "message": "Bearer abcdefghijklmnop"})
        self.assertEqual(payload["api_key"], "[REDACTED]")
        self.assertNotIn("abcdefghijklmnop", payload["message"])


if __name__ == "__main__":
    unittest.main()
