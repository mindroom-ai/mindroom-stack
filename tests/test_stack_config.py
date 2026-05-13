from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from stack_smoke_test import _is_meaningful_assistant_body  # noqa: E402


def _load_compose_config(test_case: unittest.TestCase) -> dict:
    docker = shutil.which("docker")
    if docker is None:
        test_case.skipTest("docker executable not available in PATH")

    result = subprocess.run(
        [docker, "compose", "config", "--format", "json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


class StackConfigTest(unittest.TestCase):
    def test_mindroom_waits_for_writable_storage_preparation(self) -> None:
        config = _load_compose_config(self)

        services = config["services"]
        self.assertIn("mindroom-permissions", services)
        self.assertEqual(
            services["mindroom"]["depends_on"]["mindroom-permissions"]["condition"],
            "service_completed_successfully",
        )

    def test_permissions_service_owner_is_configurable(self) -> None:
        config = _load_compose_config(self)
        permissions = config["services"]["mindroom-permissions"]

        self.assertEqual(permissions["environment"]["MINDROOM_RUNTIME_UID"], "1000")
        self.assertEqual(permissions["environment"]["MINDROOM_RUNTIME_GID"], "1000")
        self.assertIn("MINDROOM_RUNTIME_UID", " ".join(permissions["command"]))
        self.assertIn("MINDROOM_RUNTIME_GID", " ".join(permissions["command"]))

    def test_smoke_test_rejects_provider_error_replies(self) -> None:
        provider_error = (
            "ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN not set. "
            "Please set the ANTHROPIC_API_KEY environment variable."
        )

        self.assertFalse(_is_meaningful_assistant_body(provider_error, "MARKER-123"))
        self.assertTrue(_is_meaningful_assistant_body("done MARKER-123", "MARKER-123"))


if __name__ == "__main__":
    unittest.main()
