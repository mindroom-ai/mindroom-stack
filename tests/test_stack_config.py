from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from stack_smoke_test import _is_meaningful_assistant_body  # noqa: E402


class StackConfigTest(unittest.TestCase):
    def test_mindroom_waits_for_writable_storage_preparation(self) -> None:
        result = subprocess.run(
            ["docker", "compose", "config", "--format", "json"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        config = json.loads(result.stdout)

        services = config["services"]
        self.assertIn("mindroom-permissions", services)
        self.assertEqual(
            services["mindroom"]["depends_on"]["mindroom-permissions"]["condition"],
            "service_completed_successfully",
        )

    def test_smoke_test_rejects_provider_error_replies(self) -> None:
        provider_error = (
            "ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN not set. "
            "Please set the ANTHROPIC_API_KEY environment variable."
        )

        self.assertFalse(_is_meaningful_assistant_body(provider_error, "MARKER-123"))
        self.assertTrue(_is_meaningful_assistant_body("done MARKER-123", "MARKER-123"))


if __name__ == "__main__":
    unittest.main()
