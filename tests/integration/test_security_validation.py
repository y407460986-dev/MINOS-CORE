"""Integration tests for security and validation modules."""


import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from minos_core.validation import FileValidationError, InputValidator
from minos_desktop.security import (
    AuthMiddleware,
    SecretStr,
    SecureAPIKeyStore,
    require_auth,
)


class TestSecurityIntegration:
    """Integration tests for security module."""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up test keys after each test."""
        # Clean up before test
        try:
            SecureAPIKeyStore.delete_api_key("test-integration")
            SecureAPIKeyStore.delete_api_key("openai")
            SecureAPIKeyStore.delete_api_key("anthropic")
            SecureAPIKeyStore.delete_api_key("google")
        except Exception:
            pass

        yield

        # Clean up after test
        try:
            SecureAPIKeyStore.delete_api_key("test-integration")
            SecureAPIKeyStore.delete_api_key("openai")
            SecureAPIKeyStore.delete_api_key("anthropic")
            SecureAPIKeyStore.delete_api_key("google")
        except Exception:
            pass

    def test_end_to_end_api_key_workflow(self):
        """Test complete API key storage and retrieval workflow."""
        # 1. Create a secret
        api_key = "sk-test-key-12345"
        secret = SecretStr(api_key)

        # 2. Store it securely
        SecureAPIKeyStore.store_api_key("test-integration", secret)

        # 3. Verify it exists
        assert SecureAPIKeyStore.has_api_key("test-integration")

        # 4. Retrieve it
        retrieved = SecureAPIKeyStore.get_api_key("test-integration")
        assert retrieved is not None
        assert retrieved.get_secret_value() == api_key

        # 5. Delete it
        SecureAPIKeyStore.delete_api_key("test-integration")

        # 6. Verify it's gone
        assert not SecureAPIKeyStore.has_api_key("test-integration")

    def test_multiple_providers_workflow(self):
        """Test managing multiple API providers."""
        # Store keys for multiple providers
        providers = {
            "openai": "sk-openai-key",
            "anthropic": "sk-anthropic-key",
            "google": "sk-google-key",
        }

        for provider, key in providers.items():
            SecureAPIKeyStore.store_api_key(provider, SecretStr(key))

        # Verify all exist
        for provider in providers:
            assert SecureAPIKeyStore.has_api_key(provider)

        # Retrieve and verify
        for provider, expected_key in providers.items():
            retrieved = SecureAPIKeyStore.get_api_key(provider)
            assert retrieved.get_secret_value() == expected_key

        # Clean up
        for provider in providers:
            SecureAPIKeyStore.delete_api_key(provider)

    def test_fastapi_protected_endpoint(self):
        """Test FastAPI endpoint with authentication."""
        app = FastAPI()
        auth = AuthMiddleware(token="test-token-123")

        @app.get("/public")
        async def public_endpoint():
            return {"message": "public"}

        @app.get("/protected")
        @require_auth(auth)
        async def protected_endpoint(request: Request):
            return {"message": "protected"}

        client = TestClient(app)

        # Public endpoint should work without auth
        response = client.get("/public")
        assert response.status_code == 200
        assert response.json() == {"message": "public"}

        # Protected endpoint should fail without auth
        response = client.get("/protected")
        assert response.status_code == 401

        # Protected endpoint should work with valid token
        response = client.get(
            "/protected", headers={"Authorization": "Bearer test-token-123"}
        )
        assert response.status_code == 200
        assert response.json() == {"message": "protected"}

        # Protected endpoint should fail with invalid token
        response = client.get(
            "/protected", headers={"Authorization": "Bearer wrong-token"}
        )
        assert response.status_code == 401


class TestValidationIntegration:
    """Integration tests for validation module."""

    def test_file_upload_validation_workflow(self, tmp_path):
        """Test complete file upload validation workflow."""
        # Create a base directory for uploads
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()

        # Create a valid PDF file
        pdf_file = tmp_path / "document.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\n" + b"x" * 1000)

        # Validate the file comprehensively
        validated_path = InputValidator.validate_file(
            pdf_file,
            allowed_extensions={".pdf"},
            max_size=10 * 1024 * 1024,  # 10MB
            base_dir=tmp_path,
            check_magic=True,
        )

        assert validated_path == pdf_file.resolve()

        # Try to upload a file that's too large
        large_file = tmp_path / "large.pdf"
        large_file.write_bytes(b"%PDF-1.4\n" + b"x" * (11 * 1024 * 1024))

        with pytest.raises(FileValidationError, match="exceeds maximum"):
            InputValidator.validate_file(
                large_file,
                allowed_extensions={".pdf"},
                max_size=10 * 1024 * 1024,
                base_dir=tmp_path,
                check_magic=True,
            )

    def test_path_traversal_prevention(self, tmp_path):
        """Test path traversal attack prevention."""
        # Create a safe directory
        safe_dir = tmp_path / "safe"
        safe_dir.mkdir()

        # Create a file in safe directory
        safe_file = safe_dir / "document.pdf"
        safe_file.write_bytes(b"%PDF-1.4\n")

        # This should work
        validated = InputValidator.validate_path_traversal(safe_file, safe_dir)
        assert validated == safe_file.resolve()

        # Try to escape using ../
        from minos_core.validation import PathValidationError

        with pytest.raises(PathValidationError):
            InputValidator.validate_path_traversal(
                safe_dir / ".." / ".." / "etc" / "passwd", safe_dir
            )

    def test_filename_sanitization_workflow(self):
        """Test filename sanitization workflow."""
        dangerous_filenames = [
            "../../../etc/passwd",
            "file/with/slashes.txt",
            "file\\with\\backslashes.txt",
            "file\x00with\x00nulls.txt",
            "~/.ssh/id_rsa",
            "$HOME/file.txt",
        ]

        for dangerous in dangerous_filenames:
            sanitized = InputValidator.sanitize_filename(dangerous)

            # Should not contain dangerous patterns
            assert ".." not in sanitized
            assert "/" not in sanitized
            assert "\\" not in sanitized
            assert "\x00" not in sanitized
            assert "~" not in sanitized
            assert "$" not in sanitized


class TestSecurityValidationIntegration:
    """Integration tests combining security and validation."""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up test keys after each test."""
        yield
        try:
            SecureAPIKeyStore.delete_api_key("file-service")
        except Exception:
            pass

    def test_secure_file_upload_api(self, tmp_path):
        """Test secure file upload API with authentication and validation."""
        app = FastAPI()
        auth = AuthMiddleware(token="upload-token")

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()

        @app.post("/upload")
        @require_auth(auth)
        async def upload_file(request: Request, filename: str):
            # Sanitize filename
            safe_filename = InputValidator.sanitize_filename(filename)

            # Validate filename
            InputValidator.validate_filename(safe_filename)

            # Create file path
            file_path = upload_dir / safe_filename

            # Validate path traversal
            validated_path = InputValidator.validate_path_traversal(
                file_path, upload_dir
            )

            return {"filename": safe_filename, "path": str(validated_path)}

        client = TestClient(app)

        # Should fail without authentication
        response = client.post("/upload?filename=test.pdf")
        assert response.status_code == 401

        # Should work with authentication and safe filename
        response = client.post(
            "/upload?filename=test.pdf",
            headers={"Authorization": "Bearer upload-token"},
        )
        assert response.status_code == 200
        assert response.json()["filename"] == "test.pdf"

        # Should sanitize dangerous filename
        response = client.post(
            "/upload?filename=../../../etc/passwd",
            headers={"Authorization": "Bearer upload-token"},
        )
        assert response.status_code == 200
        sanitized = response.json()["filename"]
        assert ".." not in sanitized
        assert "/" not in sanitized

    def test_api_key_protected_file_processing(self, tmp_path):
        """Test file processing with API key authentication."""
        # Store API key
        api_key = "sk-file-processor-key"
        SecureAPIKeyStore.store_api_key("file-service", SecretStr(api_key))

        # Create a file to process
        input_file = tmp_path / "input.pdf"
        input_file.write_bytes(b"%PDF-1.4\n" + b"test content")

        # Retrieve API key
        stored_key = SecureAPIKeyStore.get_api_key("file-service")
        assert stored_key is not None

        # Validate file
        validated_path = InputValidator.validate_file(
            input_file,
            allowed_extensions={".pdf"},
            max_size=10 * 1024 * 1024,
            base_dir=tmp_path,
            check_magic=True,
        )

        # Process file (simulated)
        assert validated_path.exists()
        assert stored_key.get_secret_value() == api_key

        # Clean up
        SecureAPIKeyStore.delete_api_key("file-service")

    def test_multi_layer_security(self, tmp_path):
        """Test multiple layers of security working together."""
        app = FastAPI()
        auth = AuthMiddleware(token="secure-token")

        upload_dir = tmp_path / "secure-uploads"
        upload_dir.mkdir()

        # Store service API key
        SecureAPIKeyStore.store_api_key("processing-service", SecretStr("sk-proc-key"))

        @app.post("/secure-upload")
        @require_auth(auth)
        async def secure_upload(request: Request, filename: str):
            # Layer 1: Authentication (handled by decorator)

            # Layer 2: Filename validation
            InputValidator.validate_filename(filename)

            # Layer 3: Filename sanitization
            safe_filename = InputValidator.sanitize_filename(filename)

            # Layer 4: Path traversal prevention
            file_path = upload_dir / safe_filename
            validated_path = InputValidator.validate_path_traversal(
                file_path, upload_dir
            )

            # Layer 5: Retrieve processing API key securely
            api_key = SecureAPIKeyStore.get_api_key("processing-service")

            return {
                "filename": safe_filename,
                "path": str(validated_path),
                "has_api_key": api_key is not None,
            }

        client = TestClient(app)

        # Should work with all security layers
        response = client.post(
            "/secure-upload?filename=document.pdf",
            headers={"Authorization": "Bearer secure-token"},
        )
        assert response.status_code == 200
        assert response.json()["has_api_key"] is True

        # Clean up
        SecureAPIKeyStore.delete_api_key("processing-service")
