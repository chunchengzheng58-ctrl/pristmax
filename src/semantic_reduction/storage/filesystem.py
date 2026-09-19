# -*- coding: utf-8 -*-
"""
Storage Backend - FileSystem

Local filesystem storage implementation.
"""

import hashlib
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable


@dataclass
class StorageFile:
    """File information in storage"""
    file_id: str
    path: str
    size: int
    created_at: datetime
    modified_at: datetime
    checksum: str


class FileSystemBackend:
    """
    Local filesystem storage backend.

    Features:
    - Store and retrieve files
    - Checksum verification
    - Directory organization
    - Cleanup old files
    """

    def __init__(self, base_path: str):
        """
        Initialize filesystem backend.

        Args:
            base_path: Base directory for storage
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Statistics
        self._stats = {
            'files_stored': 0,
            'bytes_stored': 0,
            'bytes_retrieved': 0,
            'files_deleted': 0,
            'errors': 0
        }

    def store(
        self,
        file_path: str,
        target_path: Optional[str] = None,
        compute_checksum: bool = True
    ) -> StorageFile:
        """
        Store a file.

        Args:
            file_path: Source file path
            target_path: Target path within storage (optional)
            compute_checksum: Whether to compute checksum

        Returns:
            StorageFile with metadata
        """
        source = Path(file_path)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {file_path}")

        # Determine target
        if target_path:
            target = self.base_path / target_path
        else:
            target = self.base_path / source.name

        # Create parent directories
        target.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy2(source, target)

        # Calculate checksum
        checksum = ""
        if compute_checksum:
            checksum = self._calculate_checksum(target)

        # Get metadata
        stat = target.stat()

        file_info = StorageFile(
            file_id=checksum[:16] if checksum else hashlib.md5(str(target).encode()).hexdigest()[:16],
            path=str(target),
            size=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_ctime),
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            checksum=checksum
        )

        # Update stats
        self._stats['files_stored'] += 1
        self._stats['bytes_stored'] += stat.st_size

        return file_info

    def retrieve(self, file_path: str, destination: Optional[str] = None) -> str:
        """
        Retrieve a file.

        Args:
            file_path: Path within storage
            destination: Destination path (optional, returns original if None)

        Returns:
            Path to retrieved file
        """
        source = self.base_path / file_path
        if not source.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if destination:
            dest_path = Path(destination)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest_path)
            self._stats['bytes_retrieved'] += source.stat().st_size
            return str(dest_path)
        else:
            self._stats['bytes_retrieved'] += source.stat().st_size
            return str(source)

    def delete(self, file_path: str) -> bool:
        """
        Delete a file.

        Args:
            file_path: Path within storage

        Returns:
            True if deleted
        """
        target = self.base_path / file_path
        if not target.exists():
            return False

        size = target.stat().st_size
        target.unlink()

        self._stats['files_deleted'] += 1
        self._stats['bytes_stored'] -= size

        return True

    def list_files(self, directory: str = "") -> List[StorageFile]:
        """
        List files in directory.

        Args:
            directory: Directory within storage (empty = root)

        Returns:
            List of StorageFile objects
        """
        target_dir = self.base_path / directory
        if not target_dir.exists():
            return []

        files = []
        for item in target_dir.rglob('*'):
            if item.is_file():
                stat = item.stat()
                files.append(StorageFile(
                    file_id=item.stem,
                    path=str(item.relative_to(self.base_path)),
                    size=stat.st_size,
                    created_at=datetime.fromtimestamp(stat.st_ctime),
                    modified_at=datetime.fromtimestamp(stat.st_mtime),
                    checksum=""
                ))

        return files

    def get_usage(self) -> Dict:
        """Get storage usage statistics"""
        total_size = 0
        file_count = 0

        for item in self.base_path.rglob('*'):
            if item.is_file():
                total_size += item.stat().st_size
                file_count += 1

        return {
            'total_bytes': total_size,
            'total_files': file_count,
            'base_path': str(self.base_path)
        }

    def cleanup_old_files(self, days: int, directory: str = "") -> int:
        """
        Delete files older than specified days.

        Args:
            days: Delete files older than this many days
            directory: Directory to clean (empty = all)

        Returns:
            Number of files deleted
        """
        target_dir = self.base_path / directory
        if not target_dir.exists():
            return 0

        cutoff = datetime.now().timestamp() - (days * 86400)
        deleted = 0

        for item in target_dir.rglob('*'):
            if item.is_file() and item.stat().st_mtime < cutoff:
                item.unlink()
                deleted += 1

        return deleted

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate MD5 checksum of file"""
        md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                md5.update(chunk)
        return md5.hexdigest()

    def get_stats(self) -> Dict:
        """Get backend statistics"""
        return self._stats.copy()

    def verify_file(self, file_path: str, expected_checksum: str) -> bool:
        """
        Verify file checksum.

        Args:
            file_path: Path within storage
            expected_checksum: Expected checksum

        Returns:
            True if checksum matches
        """
        target = self.base_path / file_path
        if not target.exists():
            return False

        actual = self._calculate_checksum(target)
        return actual == expected_checksum
