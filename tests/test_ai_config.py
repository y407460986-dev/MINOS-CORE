import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from minos_core.ai_config import load_openai_api_key, load_openai_responses_config
from minos_core.cli import main


class AIConfigTests(unittest.TestCase):
    def test_load_openai_config_prefers_minos_env_without_exposing_key(self):
        with patch.dict(
            os.environ,
            {
                "MINOS_OPENAI_API_KEY": "secret",
                "MINOS_OPENAI_MODEL": "gpt-test",
                "MINOS_OPENAI_BASE_URL": "https://proxy.example/v1",
            },
            clear=True,
        ):
            config = load_openai_responses_config(allow_codex_config=False)

        self.assertTrue(config.api_key_configured)
        self.assertEqual(config.api_key_env_name, "MINOS_OPENAI_API_KEY")
        self.assertEqual(config.api_key_source, "environment")
        self.assertEqual(config.model, "gpt-test")
        self.assertEqual(config.base_url, "https://proxy.example/v1")
        self.assertNotIn("secret", str(config.model_dump()))

    def test_load_openai_config_can_use_codex_session_ark_key(self):
        with patch.dict(os.environ, {"ARK_API_KEY": "secret"}, clear=True):
            config = load_openai_responses_config(allow_codex_config=False)

        self.assertTrue(config.api_key_configured)
        self.assertEqual(config.api_key_env_name, "ARK_API_KEY")
        self.assertEqual(config.api_key_source, "environment")

    def test_load_openai_config_can_use_codex_config_and_auth(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            (codex_home / "config.toml").write_text(
                '\n'.join(
                    [
                        'model_provider = "custom"',
                        'model = "gpt-5.5"',
                        'model_reasoning_effort = "high"',
                        'disable_response_storage = true',
                        '[model_providers.custom]',
                        'wire_api = "responses"',
                        'base_url = "https://codex-proxy.example"',
                    ]
                ),
                encoding="utf-8",
            )
            (codex_home / "auth.json").write_text(
                '{"OPENAI_API_KEY": "codex-secret"}',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                config = load_openai_responses_config(codex_home=codex_home)
                key = load_openai_api_key(codex_home=codex_home)

        self.assertTrue(config.api_key_configured)
        self.assertEqual(config.api_key_source, "codex_auth")
        self.assertEqual(config.api_key_env_name, "")
        self.assertEqual(config.model, "gpt-5.5")
        self.assertEqual(config.base_url, "https://codex-proxy.example")
        self.assertEqual(config.wire_api, "responses")
        self.assertEqual(config.responses_path, "responses")
        self.assertIs(config.store, False)
        self.assertEqual(config.reasoning_effort, "high")
        self.assertEqual(config.user_agent, "codex-cli")
        self.assertEqual(key, "codex-secret")
        self.assertNotIn("codex-secret", str(config.model_dump()))

    def test_env_model_overrides_default_when_using_codex_auth_and_proxy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            (codex_home / "config.toml").write_text(
                '\n'.join(
                    [
                        'model_provider = "custom"',
                        'model = "gpt-5.5"',
                        '[model_providers.custom]',
                        'wire_api = "responses"',
                        'base_url = "https://codex-proxy.example"',
                    ]
                ),
                encoding="utf-8",
            )
            (codex_home / "auth.json").write_text(
                '{"OPENAI_API_KEY": "codex-secret"}',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"MINOS_OPENAI_MODEL": "gpt-5.4"}, clear=True):
                config = load_openai_responses_config(codex_home=codex_home)

        self.assertEqual(config.model, "gpt-5.4")
        self.assertEqual(config.base_url, "https://codex-proxy.example")
        self.assertEqual(config.api_key_source, "codex_auth")

    def test_codex_requires_openai_auth_prefers_codex_auth_over_ark_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            (codex_home / "config.toml").write_text(
                '\n'.join(
                    [
                        'model_provider = "custom"',
                        'model = "gpt-5.5"',
                        '[model_providers.custom]',
                        'wire_api = "responses"',
                        'requires_openai_auth = true',
                        'base_url = "https://codex-proxy.example"',
                    ]
                ),
                encoding="utf-8",
            )
            (codex_home / "auth.json").write_text(
                '{"OPENAI_API_KEY": "codex-secret"}',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"ARK_API_KEY": "ark-secret"}, clear=True):
                config = load_openai_responses_config(codex_home=codex_home)
                key = load_openai_api_key(codex_home=codex_home)

        self.assertEqual(config.api_key_source, "codex_auth")
        self.assertEqual(config.api_key_env_name, "")
        self.assertEqual(key, "codex-secret")
        self.assertNotIn("codex-secret", str(config.model_dump()))
        self.assertNotIn("ark-secret", str(config.model_dump()))

    def test_minos_key_still_overrides_codex_auth(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            (codex_home / "config.toml").write_text(
                '\n'.join(
                    [
                        'model_provider = "custom"',
                        '[model_providers.custom]',
                        'wire_api = "responses"',
                        'requires_openai_auth = true',
                        'base_url = "https://codex-proxy.example"',
                    ]
                ),
                encoding="utf-8",
            )
            (codex_home / "auth.json").write_text(
                '{"OPENAI_API_KEY": "codex-secret"}',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"MINOS_OPENAI_API_KEY": "minos-secret"}, clear=True):
                config = load_openai_responses_config(codex_home=codex_home)
                key = load_openai_api_key(codex_home=codex_home)

        self.assertEqual(config.api_key_source, "environment")
        self.assertEqual(config.api_key_env_name, "MINOS_OPENAI_API_KEY")
        self.assertEqual(key, "minos-secret")

    def test_env_v1_base_url_uses_responses_path_without_duplicate_v1(self):
        with patch.dict(
            os.environ,
            {
                "MINOS_OPENAI_API_KEY": "secret",
                "MINOS_OPENAI_BASE_URL": "https://proxy.example/v1",
                "MINOS_DISABLE_CODEX_CONFIG": "1",
            },
            clear=True,
        ):
            config = load_openai_responses_config()

        self.assertEqual(config.base_url, "https://proxy.example/v1")
        self.assertEqual(config.responses_path, "responses")

    def test_env_root_base_url_keeps_openai_v1_path_even_when_codex_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            (codex_home / "config.toml").write_text(
                '\n'.join(
                    [
                        'model_provider = "custom"',
                        '[model_providers.custom]',
                        'wire_api = "responses"',
                        'base_url = "https://codex-proxy.example"',
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "MINOS_OPENAI_API_KEY": "secret",
                    "MINOS_OPENAI_BASE_URL": "https://env-proxy.example",
                },
                clear=True,
            ):
                config = load_openai_responses_config(codex_home=codex_home)

        self.assertEqual(config.base_url, "https://env-proxy.example")
        self.assertEqual(config.responses_path, "v1/responses")

    def test_ai_config_cli_returns_nonzero_without_key(self):
        with patch.dict(os.environ, {"MINOS_DISABLE_CODEX_CONFIG": "1"}, clear=True):
            self.assertEqual(main(["ai-config"]), 2)

    def test_ai_config_cli_returns_zero_with_key(self):
        with patch.dict(os.environ, {"ARK_API_KEY": "secret"}, clear=True):
            self.assertEqual(main(["ai-config"]), 0)

    def test_analyze_drawing_cli_fails_transparently_without_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "drawing.png"
            from PIL import Image

            Image.new("RGB", (10, 8), color="white").save(image_path)
            with patch.dict(os.environ, {"MINOS_DISABLE_CODEX_CONFIG": "1"}, clear=True):
                self.assertEqual(
                    main([
                        "analyze-drawing", "--input", str(image_path),
                        "--mode", "vision_only",
                    ]),
                    2,
                )


if __name__ == "__main__":
    unittest.main()
