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


def _parse_scalar(value: str) -> object:
    if value == "[]":
        return []
    if value in {"true", "false"}:
        return value == "true"
    try:
        return int(value)
    except ValueError:
        return value


def _load_stack_config() -> dict:
    lines = []
    for raw_line in (ROOT / "config.yaml").read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append((len(raw_line) - len(raw_line.lstrip(" ")), stripped))

    def parse_block(index: int, indent: int) -> tuple[object, int]:
        if lines[index][1].startswith("- "):
            items = []
            while index < len(lines) and lines[index][0] == indent and lines[index][1].startswith("- "):
                items.append(_parse_scalar(lines[index][1][2:].strip()))
                index += 1
            return items, index

        data = {}
        while index < len(lines) and lines[index][0] == indent and not lines[index][1].startswith("- "):
            key, separator, value = lines[index][1].partition(":")
            if not separator:
                raise ValueError(f"Expected YAML mapping entry, got {lines[index][1]!r}")
            value = value.strip()
            index += 1
            if value:
                data[key] = _parse_scalar(value)
            elif index < len(lines) and lines[index][0] > indent:
                data[key], index = parse_block(index, lines[index][0])
            else:
                data[key] = None
        return data, index

    config, index = parse_block(0, 0)
    if index != len(lines) or not isinstance(config, dict):
        raise ValueError("Could not parse stack config")
    return config


class StackConfigTest(unittest.TestCase):
    def test_stack_config_documents_model_provider_alternatives(self) -> None:
        config_text = (ROOT / "config.yaml").read_text(encoding="utf-8")

        expected_snippets = [
            "Default stack model: Anthropic Claude Sonnet.",
            "openai_gpt:",
            "provider: openai",
            "id: gpt-5.5",
            "openrouter_sonnet:",
            "provider: openrouter",
            "id: anthropic/claude-sonnet-4.6",
            "codex_gpt:",
            "provider: codex",
            "reasoning_effort: medium",
            "ollama_gemma:",
            "provider: ollama",
            "id: gemma4",
            "ollama_qwen:",
            "id: qwen3.6:27b",
            "llama_cpp_gemma:",
            "base_url: http://localhost:8080/v1",
            "llama_cpp_qwen:",
            "id: unsloth/Qwen3.6-27B-GGUF:UD-Q4_K_XL",
            "azure_openai_deployment:",
            "provider: azure",
            "id: your-azure-openai-deployment",
            "bedrock_claude_opus:",
            "provider: bedrock_claude",
            "id: anthropic.claude-opus-4-8",
            "vertex_claude_sonnet:",
            "provider: vertexai_claude",
            "anthropic_opus:",
            "id: claude-opus-4-8",
            "anthropic_haiku:",
            "id: claude-haiku-4-5",
        ]

        for snippet in expected_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, config_text)
        self.assertNotIn("# default:", config_text)

    def test_stack_config_tracks_current_mindroom_starter_defaults(self) -> None:
        config = _load_stack_config()
        mind_tools = config["agents"]["mind"]["tools"]

        self.assertEqual(config["models"]["default"]["id"], "claude-sonnet-4-6")
        self.assertEqual(config["models"]["default"]["context_window"], 1000000)
        self.assertTrue(config["agents"]["assistant"]["accept_invites"])
        self.assertTrue(config["agents"]["mind"]["accept_invites"])
        self.assertTrue(config["router"]["accept_invites"])
        self.assertFalse(config["matrix_delivery"]["ignore_unverified_devices"])
        self.assertTrue(config["defaults"]["compaction"]["enabled"])
        self.assertNotIn("knowledge_bases", config)
        self.assertNotIn("knowledge_bases", config["agents"]["mind"])
        self.assertIn("memory", mind_tools)
        self.assertIn("thread_tags", mind_tools)
        self.assertNotIn("mind_memory", mind_tools)
        self.assertEqual(config["memory"]["embedder"]["provider"], "sentence_transformers")
        self.assertEqual(
            config["memory"]["embedder"]["config"]["model"],
            "sentence-transformers/all-MiniLM-L6-v2",
        )
        self.assertEqual(config["memory"]["search"]["mode"], "semantic")
        self.assertEqual(config["memory"]["search"]["include"], ["memory/**/*.md"])
        self.assertFalse(config["memory"]["search"]["include_entrypoint"])

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
