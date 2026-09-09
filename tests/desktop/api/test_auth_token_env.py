"""Auth token resolution: env var must take precedence over keyring.

Background: ``minos_desktop.api.cli`` writes the launch ``--token`` (or
``MINOS_DESKTOP_API_TOKEN``) into the process environment, while the auth
dependency historically read its expected token only from the system
keyring. This caused every request to be 401 because the Tauri sidecar
launches the API with a freshly generated token that never reaches the
keyring. The auth dependency must prefer the env-provided token and only
fall back to the keyring when no env value is set.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from minos_desktop.api import auth as auth_module
from minos_desktop.api.auth import require_api_token
from minos_desktop.api.schemas import APIError

ENV_VAR = "MINOS_DESKTOP_API_TOKEN"


class RequireApiTokenEnvPriorityTests(unittest.TestCase):
    """``require_api_token`` must honour ``MINOS_DESKTOP_API_TOKEN`` first."""

    def setUp(self) -> None:
        self._saved_env = os.environ.get(ENV_VAR)

    def tearDown(self) -> None:
        if self._saved_env is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = self._saved_env

    def test_env_token_is_accepted_without_touching_keyring(self) -> None:
        os.environ[ENV_VAR] = "env-token-from-sidecar-launch"

        # Keyring must NOT be consulted when env is set; if the code calls it,
        # this mock would explode and prove the regression.
        with patch.object(
            auth_module._token_manager,
            "get_or_create_token",
            side_effect=AssertionError("keyring must not be queried when env token is set"),
        ):
            require_api_token("Bearer env-token-from-sidecar-launch")

    def test_keyring_token_is_rejected_when_env_token_is_set(self) -> None:
        os.environ[ENV_VAR] = "env-token-from-sidecar-launch"

        with patch.object(
            auth_module._token_manager,
            "get_or_create_token",
            return_value="some-other-keyring-token",
        ):
            with self.assertRaises(APIError) as ctx:
                require_api_token("Bearer some-other-keyring-token")

        self.assertEqual(ctx.exception.status_code, 401)

    def test_keyring_is_used_when_env_var_absent(self) -> None:
        os.environ.pop(ENV_VAR, None)

        with patch.object(
            auth_module._token_manager,
            "get_or_create_token",
            return_value="keyring-fallback-token",
        ) as mock_get:
            require_api_token("Bearer keyring-fallback-token")

        mock_get.assert_called_once()

    def test_keyring_is_not_used_when_env_var_is_empty(self) -> None:
        """Explicit ``is None`` check: empty string is a valid token, not 'absent'."""
        os.environ[ENV_VAR] = ""

        with patch.object(
            auth_module._token_manager,
            "get_or_create_token",
            side_effect=AssertionError("keyring must not be queried when env var is set (even to empty)"),
        ):
            # Empty env token won't match "keyring-fallback-token" → 401
            with self.assertRaises(APIError) as ctx:
                require_api_token("Bearer keyring-fallback-token")

        self.assertEqual(ctx.exception.status_code, 401)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
