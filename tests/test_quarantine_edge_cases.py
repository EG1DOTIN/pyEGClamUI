"""
Edge case tests for QuarantineManager.
"""

import tempfile
from pathlib import Path
from pyegclamui.core.quarantine import QuarantineManager


def test_quarantine_nonexistent_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = QuarantineManager(quarantine_dir=Path(tmpdir))
        result = mgr.quarantine_file("C:/nonexistent_file_path_12345.xyz")
        assert result is None


def test_quarantine_directory_instead_of_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = QuarantineManager(quarantine_dir=Path(tmpdir))
        # Passing a directory must be rejected
        result = mgr.quarantine_file(tmpdir)
        assert result is None


def test_quarantine_empty_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = QuarantineManager(quarantine_dir=Path(tmpdir))

        # Create empty file
        empty_file = Path(tmpdir) / "empty.bin"
        empty_file.touch()

        item = mgr.quarantine_file(str(empty_file), "Benign.Empty")
        assert item is not None
        assert item.file_size_bytes == 0
        # SHA-256 for empty file
        assert item.sha256 == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_restore_destination_already_exists():
    with tempfile.TemporaryDirectory() as vault_dir:
        mgr = QuarantineManager(quarantine_dir=Path(vault_dir))

        with tempfile.TemporaryDirectory() as target_dir:
            file_to_quarantine = Path(target_dir) / "test.txt"
            file_to_quarantine.write_text("Infected Payload Sample", encoding="utf-8")

            item = mgr.quarantine_file(str(file_to_quarantine), "Threat.Test")
            assert item is not None
            assert not file_to_quarantine.exists()

            # Now simulate recreating a file at the original path
            file_to_quarantine.write_text("New file created at same location", encoding="utf-8")

            # Restore without overwrite should fail gracefully
            success, msg = mgr.restore_item(item.item_id, overwrite=False)
            assert not success
            assert "already exists" in msg

            # Restore with overwrite should succeed
            success_ow, msg_ow = mgr.restore_item(item.item_id, overwrite=True)
            assert success_ow
            assert file_to_quarantine.read_text(encoding="utf-8") == "Infected Payload Sample"


def test_corrupted_json_in_quarantine_vault():
    with tempfile.TemporaryDirectory() as vault_dir:
        mgr = QuarantineManager(quarantine_dir=Path(vault_dir))

        # Create a corrupted JSON file in vault
        bad_meta = Path(vault_dir) / "corrupt_123.json"
        bad_meta.write_text("{ this is invalid json ::: }", encoding="utf-8")

        # Listing items should not crash and return empty list
        items = mgr.list_items()
        assert items == []


def test_delete_nonexistent_item():
    with tempfile.TemporaryDirectory() as vault_dir:
        mgr = QuarantineManager(quarantine_dir=Path(vault_dir))
        success, msg = mgr.delete_item("nonexistent_id_9999")
        assert not success
        assert "not found" in msg
