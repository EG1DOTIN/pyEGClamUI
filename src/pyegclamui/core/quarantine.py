"""
Quarantine vault manager for pyEGClamUI.
Safely stores, isolates, inspects, and restores detected threat files.
"""

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pyegclamui.core.config import AppPaths


class QuarantineItem:
    """Represents a single quarantined threat file with its metadata."""

    def __init__(
        self,
        item_id: str,
        original_path: str,
        threat_name: str,
        quarantine_date: str,
        file_size_bytes: int,
        sha256: str,
        quarantined_filename: str,
        status: str = "quarantined"
    ):
        self.item_id = item_id
        self.original_path = original_path
        self.filename = Path(original_path).name
        self.threat_name = threat_name
        self.quarantine_date = quarantine_date
        self.file_size_bytes = file_size_bytes
        self.sha256 = sha256
        self.quarantined_filename = quarantined_filename
        self.status = status

    @classmethod
    def from_dict(cls, data: dict) -> "QuarantineItem":
        return cls(
            item_id=data.get("id", ""),
            original_path=data.get("original_path", ""),
            threat_name=data.get("threat_name", "Unknown"),
            quarantine_date=data.get("quarantine_date", ""),
            file_size_bytes=data.get("file_size_bytes", 0),
            sha256=data.get("sha256", ""),
            quarantined_filename=data.get("quarantined_filename", ""),
            status=data.get("status", "quarantined")
        )

    def to_dict(self) -> dict:
        return {
            "id": self.item_id,
            "original_path": self.original_path,
            "filename": self.filename,
            "threat_name": self.threat_name,
            "quarantine_date": self.quarantine_date,
            "file_size_bytes": self.file_size_bytes,
            "sha256": self.sha256,
            "quarantined_filename": self.quarantined_filename,
            "status": self.status
        }


class QuarantineManager:
    """Manages the quarantine storage directory and operations."""

    def __init__(self, quarantine_dir: Optional[Path] = None):
        self.quarantine_dir = quarantine_dir or AppPaths.get_quarantine_dir()
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

    def quarantine_file(self, file_path: str, threat_name: str = "Threat.Detected") -> Optional[QuarantineItem]:
        """
        Moves an infected file into quarantine vault with unique ID and SHA-256 hash.
        Returns None if file does not exist, is a directory, or cannot be accessed.
        """
        try:
            src = Path(file_path).resolve()
            if not src.exists() or not src.is_file():
                return None

            item_id = uuid.uuid4().hex[:12]
            safe_name = f"{item_id}_{src.name}.quarantine"
            metadata_name = f"{item_id}_{src.name}.json"

            dest_file = self.quarantine_dir / safe_name
            dest_meta = self.quarantine_dir / metadata_name

            # 1. Compute SHA-256 hash before moving
            sha256_hash = hashlib.sha256()
            with open(src, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    sha256_hash.update(chunk)
            file_hash = sha256_hash.hexdigest()
            file_size = src.stat().st_size

            # 2. Move file safely into quarantine directory
            shutil.move(str(src), str(dest_file))

            # 3. Create metadata item
            item = QuarantineItem(
                item_id=item_id,
                original_path=str(src),
                threat_name=threat_name,
                quarantine_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                file_size_bytes=file_size,
                sha256=file_hash,
                quarantined_filename=safe_name,
                status="quarantined"
            )

            with open(dest_meta, "w", encoding="utf-8") as f:
                json.dump(item.to_dict(), f, indent=2)

            return item
        except Exception as e:
            print(f"[Quarantine] Failed to quarantine {file_path}: {e}")
            return None

    def list_items(self) -> List[QuarantineItem]:
        """Retrieves all quarantined items currently in vault, gracefully ignoring corrupted files."""
        items = []
        for meta_path in self.quarantine_dir.glob("*.json"):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    item = QuarantineItem.from_dict(data)
                    # Check if actual quarantined file still exists
                    if (self.quarantine_dir / item.quarantined_filename).exists():
                        items.append(item)
            except Exception:
                continue
        items.sort(key=lambda x: x.quarantine_date, reverse=True)
        return items

    def restore_item(self, item_id: str, overwrite: bool = False) -> Tuple[bool, str]:
        """
        Restores a quarantined file back to its original location.
        Returns: (success, message)
        """
        for meta_path in self.quarantine_dir.glob(f"{item_id}_*.json"):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                item = QuarantineItem.from_dict(data)

                src_quarantine = self.quarantine_dir / item.quarantined_filename
                dest_original = Path(item.original_path)

                if not src_quarantine.exists():
                    return False, f"Quarantined data file missing: {item.quarantined_filename}"

                # Ensure parent destination directory exists
                dest_original.parent.mkdir(parents=True, exist_ok=True)

                if dest_original.exists():
                    if overwrite:
                        try:
                            dest_original.unlink()
                        except Exception as e:
                            return False, f"Cannot overwrite existing destination: {e}"
                    else:
                        return False, f"Destination file already exists: {dest_original}"

                # Move back
                shutil.move(str(src_quarantine), str(dest_original))

                # Delete metadata
                meta_path.unlink(missing_ok=True)
                return True, f"Restored to {dest_original}"
            except Exception as e:
                return False, f"Error restoring: {e}"

        return False, f"Item {item_id} not found in quarantine."

    def delete_item(self, item_id: str) -> Tuple[bool, str]:
        """
        Permanently deletes a file and its metadata from quarantine vault.
        """
        for meta_path in self.quarantine_dir.glob(f"{item_id}_*.json"):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                item = QuarantineItem.from_dict(data)

                src_quarantine = self.quarantine_dir / item.quarantined_filename
                if src_quarantine.exists():
                    src_quarantine.unlink()
                meta_path.unlink(missing_ok=True)
                return True, f"Deleted {item.filename} from quarantine."
            except Exception as e:
                return False, f"Error deleting: {e}"

        return False, f"Item {item_id} not found in quarantine."

    def clear_vault(self) -> int:
        """Removes all files from quarantine. Returns count of deleted items."""
        count = 0
        for item in self.list_items():
            success, _ = self.delete_item(item.item_id)
            if success:
                count += 1
        return count
