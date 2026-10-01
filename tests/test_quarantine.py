"""
Unit tests for QuarantineManager.
"""

import tempfile
from pathlib import Path
from pyegclamui.core.quarantine import QuarantineManager


def test_quarantine_lifecycle():
    mgr = QuarantineManager()

    # Create temporary dummy test file (benign test payload)
    f = tempfile.NamedTemporaryFile("w", delete=False)
    f.write("BENIGN-TEST-SAMPLE-pyEGClamUI-SAFE-PAYLOAD-FOR-UNIT-TESTS")
    f.close()
    dummy_path = f.name

    assert Path(dummy_path).exists()

    # 1. Quarantine file
    item = mgr.quarantine_file(dummy_path, threat_name="Test.Benign.Sample")
    assert item is not None
    assert not Path(dummy_path).exists()  # Original moved away
    assert item.threat_name == "Test.Benign.Sample"

    # 2. List items
    items = mgr.list_items()
    item_ids = [i.item_id for i in items]
    assert item.item_id in item_ids

    # 3. Restore file
    success, msg = mgr.restore_item(item.item_id)
    assert success
    assert Path(dummy_path).exists()  # Restored to original path

    # Cleanup restored file
    Path(dummy_path).unlink()
