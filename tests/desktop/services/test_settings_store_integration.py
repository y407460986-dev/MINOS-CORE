import os
import tempfile
import unittest
from unittest.mock import patch

from minos_core._paths import user_data_dir
from minos_desktop.api.schemas import settings_to_dict
from minos_desktop.services import DesktopSettingsStore


class TestSettingsStoreIntegration(unittest.TestCase):
    def test_ai_overrides_round_trip_and_settings_do_not_expose_api_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DesktopSettingsStore(os.path.join(tmpdir, "desktop.sqlite3"))

            saved = store.set_ai_overrides(
                base_url=" https://user-proxy.example/v1/ ",
                api_key=" user-secret ",
                model=" gpt-user ",
            )
            loaded = store.get_ai_overrides()
            with patch.dict(os.environ, {"MINOS_DISABLE_CODEX_CONFIG": "1"}, clear=True):
                settings = settings_to_dict(
                    store.get_default_output_dir(),
                    store.get_ai_config_state(),
                )

        self.assertEqual(
            saved,
            {
                "base_url": "https://user-proxy.example/v1/",
                "api_key": "user-secret",
                "model": "gpt-user",
            },
        )
        self.assertEqual(loaded, saved)
        ai = settings["ai_config"]
        self.assertEqual(ai["base_url_override"], "https://user-proxy.example/v1/")
        self.assertEqual(ai["model_override"], "gpt-user")
        self.assertTrue(ai["api_key_override_set"])
        self.assertEqual(ai["api_key_source"], "user_settings")
        self.assertNotIn("user-secret", str(settings))

    def test_ai_config_state_reports_overrides_and_environment_locks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DesktopSettingsStore(os.path.join(tmpdir, "desktop.sqlite3"))
            store.set_ai_overrides(
                base_url="https://user-proxy.example",
                api_key="user-secret",
                model="gpt-user",
            )
            with patch.dict(
                os.environ,
                {
                    "MINOS_OPENAI_BASE_URL": "https://env-proxy.example",
                    "MINOS_OPENAI_API_KEY": "env-secret",
                    "MINOS_OPENAI_MODEL": "gpt-env",
                    "MINOS_DISABLE_CODEX_CONFIG": "1",
                },
                clear=True,
            ):
                state = store.get_ai_config_state()

        self.assertEqual(state.base_url, "https://env-proxy.example")
        self.assertEqual(state.model, "gpt-env")
        self.assertEqual(state.api_key_source, "environment")
        self.assertEqual(state.base_url_override, "https://user-proxy.example")
        self.assertEqual(state.model_override, "gpt-user")
        self.assertTrue(state.api_key_override_set)
        self.assertTrue(state.base_url_locked_by_env)
        self.assertTrue(state.api_key_locked_by_env)
        self.assertTrue(state.model_locked_by_env)
        self.assertNotIn("user-secret", repr(state))
        self.assertNotIn("env-secret", repr(state))

    def test_ark_api_key_does_not_lock_user_settings_api_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DesktopSettingsStore(os.path.join(tmpdir, "desktop.sqlite3"))
            store.set_ai_overrides(api_key="user-secret")
            with patch.dict(
                os.environ,
                {
                    "ARK_API_KEY": "ark-secret",
                    "MINOS_DISABLE_CODEX_CONFIG": "1",
                },
                clear=True,
            ):
                state = store.get_ai_config_state()

        self.assertEqual(state.api_key_source, "user_settings")
        self.assertFalse(state.api_key_locked_by_env)
        self.assertTrue(state.api_key_override_set)

    def test_ai_base_url_rejects_remote_http_to_protect_api_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DesktopSettingsStore(os.path.join(tmpdir, "desktop.sqlite3"))

            with self.assertRaisesRegex(ValueError, "HTTPS"):
                store.set_ai_overrides(base_url="http://proxy.example/v1")

    def test_ai_base_url_allows_local_http_proxy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DesktopSettingsStore(os.path.join(tmpdir, "desktop.sqlite3"))

            store.set_ai_overrides(base_url="http://127.0.0.1:8080/v1")
            self.assertEqual(
                store.get_ai_overrides()["base_url"],
                "http://127.0.0.1:8080/v1",
            )

    def test_sqlite_settings_projects_and_runs_round_trip_without_qt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            settings = DesktopSettingsStore(db_path)

            self.assertEqual(
                settings.get_default_output_dir(),
                str(user_data_dir() / "out"),
            )
            settings.set_default_output_dir(os.path.join(tmpdir, "out"))
            self.assertEqual(settings.get_default_output_dir(), os.path.join(tmpdir, "out"))


if __name__ == "__main__":
    unittest.main()
