"""Tests for DesktopProjectStore."""

from pathlib import Path

import pytest

from minos_desktop.app_state import DesktopProjectState
from minos_desktop.services.project_store import DesktopProjectStore, _from_json_object


class TestDesktopProjectStore:
    """Test DesktopProjectStore class."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary database for testing."""
        db_path = tmp_path / "test_projects.sqlite3"
        return db_path

    @pytest.fixture
    def store(self, temp_db):
        """Create a DesktopProjectStore instance."""
        return DesktopProjectStore(temp_db)

    def test_create_project_basic(self, store):
        """Test creating a basic project."""
        state = DesktopProjectState(
            project_name="Test Project",
            drawing_path="/path/to/drawing.pdf",
            output_dir="/path/to/output",
            context={"key": "value"}
        )

        record = store.create_project(state)

        assert record.id > 0
        assert record.project_name == "Test Project"
        assert record.drawing_path == "/path/to/drawing.pdf"
        assert record.output_dir == "/path/to/output"
        assert record.context == {"key": "value"}
        assert record.created_at
        assert record.updated_at
        assert record.created_at == record.updated_at

    def test_create_project_without_output_dir(self, store):
        """Test creating project without output_dir uses default."""
        state = DesktopProjectState(
            project_name="Test Project",
            drawing_path="/path/to/drawing.pdf",
            output_dir=None,
            context={}
        )

        record = store.create_project(state)

        assert record.id > 0
        assert record.output_dir  # Should have default value
        assert Path(record.output_dir).exists() or record.output_dir  # Either exists or is a path string

    def test_create_project_with_empty_context(self, store):
        """Test creating project with empty context."""
        state = DesktopProjectState(
            project_name="Empty Context Project",
            drawing_path="/path/to/drawing.pdf",
            output_dir="/path/to/output",
            context={}
        )

        record = store.create_project(state)

        assert record.context == {}

    def test_get_project_exists(self, store):
        """Test getting an existing project."""
        state = DesktopProjectState(
            project_name="Get Test",
            drawing_path="/path/to/drawing.pdf",
            output_dir="/path/to/output",
            context={"test": "data"}
        )
        created = store.create_project(state)

        retrieved = store.get_project(created.id)

        assert retrieved.id == created.id
        assert retrieved.project_name == "Get Test"
        assert retrieved.drawing_path == "/path/to/drawing.pdf"
        assert retrieved.context == {"test": "data"}

    def test_get_project_not_exists_raises_key_error(self, store):
        """Test getting non-existent project raises KeyError."""
        with pytest.raises(KeyError, match="desktop project not found: 99999"):
            store.get_project(99999)

    def test_update_project_name(self, store):
        """Test updating project name."""
        state = DesktopProjectState(
            project_name="Original Name",
            drawing_path="/path/to/drawing.pdf",
            output_dir="/path/to/output",
            context={}
        )
        created = store.create_project(state)
        original_updated_at = created.updated_at

        updated = store.update_project(created.id, project_name="New Name")

        assert updated.project_name == "New Name"
        assert updated.drawing_path == created.drawing_path
        assert updated.output_dir == created.output_dir
        assert updated.updated_at >= original_updated_at

    def test_update_project_drawing_path(self, store):
        """Test updating drawing path."""
        state = DesktopProjectState(
            project_name="Test",
            drawing_path="/old/path.pdf",
            output_dir="/path/to/output",
            context={}
        )
        created = store.create_project(state)

        updated = store.update_project(created.id, drawing_path="/new/path.pdf")

        assert updated.drawing_path == "/new/path.pdf"
        assert updated.project_name == created.project_name

    def test_update_project_output_dir(self, store):
        """Test updating output directory."""
        state = DesktopProjectState(
            project_name="Test",
            drawing_path="/path/to/drawing.pdf",
            output_dir="/old/output",
            context={}
        )
        created = store.create_project(state)

        updated = store.update_project(created.id, output_dir="/new/output")

        assert updated.output_dir == str(Path("/new/output"))

    def test_update_project_context(self, store):
        """Test updating project context."""
        state = DesktopProjectState(
            project_name="Test",
            drawing_path="/path/to/drawing.pdf",
            output_dir="/path/to/output",
            context={"old": "data"}
        )
        created = store.create_project(state)

        updated = store.update_project(created.id, context={"new": "data", "extra": "field"})

        assert updated.context == {"new": "data", "extra": "field"}

    def test_update_project_multiple_fields(self, store):
        """Test updating multiple fields at once."""
        state = DesktopProjectState(
            project_name="Original",
            drawing_path="/old/path.pdf",
            output_dir="/old/output",
            context={"old": "data"}
        )
        created = store.create_project(state)

        updated = store.update_project(
            created.id,
            project_name="Updated",
            drawing_path="/new/path.pdf",
            context={"new": "data"}
        )

        assert updated.project_name == "Updated"
        assert updated.drawing_path == "/new/path.pdf"
        assert updated.context == {"new": "data"}

    def test_update_project_not_exists_raises_key_error(self, store):
        """Test updating non-existent project raises KeyError."""
        with pytest.raises(KeyError, match="desktop project not found: 99999"):
            store.update_project(99999, project_name="New Name")

    def test_update_project_with_none_values_preserves_existing(self, store):
        """Test that None values in update preserve existing values."""
        state = DesktopProjectState(
            project_name="Original",
            drawing_path="/path/to/drawing.pdf",
            output_dir="/path/to/output",
            context={"key": "value"}
        )
        created = store.create_project(state)

        updated = store.update_project(
            created.id,
            project_name=None,
            drawing_path=None,
            output_dir=None,
            context=None
        )

        assert updated.project_name == "Original"
        assert updated.drawing_path == "/path/to/drawing.pdf"
        assert updated.output_dir == created.output_dir
        assert updated.context == {"key": "value"}

    def test_timestamp_behavior(self, store):
        """Test that timestamps are properly managed."""
        state = DesktopProjectState(
            project_name="Timestamp Test",
            drawing_path="/path/to/drawing.pdf",
            output_dir="/path/to/output",
            context={}
        )
        created = store.create_project(state)

        # created_at and updated_at should be equal on creation
        assert created.created_at == created.updated_at

        # Update should change updated_at but not created_at
        updated = store.update_project(created.id, project_name="Updated Name")
        assert updated.created_at == created.created_at
        assert updated.updated_at >= created.updated_at


class TestFromJsonObject:
    """Test _from_json_object helper function."""

    def test_parse_valid_json_object(self):
        """Test parsing valid JSON object."""
        result = _from_json_object('{"key": "value", "number": 42}')
        assert result == {"key": "value", "number": 42}

    def test_parse_empty_string_returns_empty_dict(self):
        """Test parsing empty string returns empty dict."""
        result = _from_json_object("")
        assert result == {}

    def test_parse_empty_json_object(self):
        """Test parsing empty JSON object."""
        result = _from_json_object("{}")
        assert result == {}

    def test_parse_json_array_returns_empty_dict(self):
        """Test parsing JSON array returns empty dict (not a dict)."""
        result = _from_json_object('["item1", "item2"]')
        assert result == {}

    def test_parse_json_string_returns_empty_dict(self):
        """Test parsing JSON string returns empty dict (not a dict)."""
        result = _from_json_object('"just a string"')
        assert result == {}

    def test_parse_json_number_returns_empty_dict(self):
        """Test parsing JSON number returns empty dict (not a dict)."""
        result = _from_json_object('42')
        assert result == {}

    def test_parse_nested_json_object(self):
        """Test parsing nested JSON object."""
        result = _from_json_object('{"outer": {"inner": "value"}}')
        assert result == {"outer": {"inner": "value"}}

    def test_parse_json_with_special_characters(self):
        """Test parsing JSON with special characters."""
        result = _from_json_object('{"path": "/path/to/file.pdf", "name": "Test\\nProject"}')
        assert result == {"path": "/path/to/file.pdf", "name": "Test\nProject"}
