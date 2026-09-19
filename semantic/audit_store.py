"""
Immutable Audit Storage

Provides tamper-proof audit trail storage using append-only JSONL format.
Designed for compliance requirements (GDPR, SOC2, ISO27001).
"""

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Iterator
from threading import Lock
import shutil


class AuditEventType(Enum):
    """Types of auditable events"""
    DATA_INGEST = "data_ingest"           # New data ingested
    DATA_REDUCED = "data_reduced"         # Data processed/reduced
    DATA_RESTORED = "data_restored"       # Data restored
    DATA_DELETED = "data_deleted"         # Data deleted
    POLICY_CREATED = "policy_created"     # New policy created
    POLICY_UPDATED = "policy_updated"     # Policy modified
    POLICY_DELETED = "policy_deleted"     # Policy deleted
    SYSTEM_CONFIG = "system_config"       # System configuration change
    USER_ACCESS = "user_access"           # User accessed data
    COMPLIANCE_REPORT = "compliance_report"  # Compliance report generated
    ANOMALY_DETECTED = "anomaly_detected" # Anomaly detected


@dataclass
class AuditEntry:
    """
    Immutable audit record entry.

    Once created, entries should NEVER be modified.
    """
    entry_id: str = ""                     # Unique entry identifier
    timestamp: str = ""                    # ISO 8601 timestamp (UTC)
    event_type: AuditEventType = None     # Type of event
    actor: str = ""                        # Who/what triggered the event (system/user)
    data_id: str = ""                      # ID of the data affected
    data_type: str = ""                    # Type of data (video, log, image, etc.)
    action: str = ""                       # Action taken
    original_size: int = 0                # Original size in bytes
    new_size: int = 0                     # Size after action
    classification: str = ""               # Data classification (HIGH/MEDIUM/LOW)
    policy_id: str = ""                    # Policy applied
    policy_version: str = ""               # Version of policy at time of action
    result: str = "success"                # Result of action (success/failure/error)
    reason: str = ""                       # Reason for action
    metadata: Dict = field(default_factory=dict)  # Additional context

    # Integrity fields
    previous_hash: str = ""                # Hash of previous entry (chain integrity)
    entry_hash: str = ""                   # Hash of this entry

    def __post_init__(self):
        if not self.entry_id:
            self.entry_id = uuid.uuid4().hex
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + 'Z'
        if not self.entry_hash:
            self.entry_hash = self._calculate_hash()

    def _calculate_hash(self) -> str:
        """Calculate hash of entry content (excluding previous_hash)"""
        content = f"{self.entry_id}|{self.timestamp}|{self.event_type.value}|{self.actor}|{self.data_id}|{self.data_type}|{self.action}|{self.original_size}|{self.new_size}|{self.classification}|{self.policy_id}|{self.policy_version}|{self.result}|{self.reason}|{json.dumps(self.metadata, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            'entry_id': self.entry_id,
            'timestamp': self.timestamp,
            'event_type': self.event_type.value,
            'actor': self.actor,
            'data_id': self.data_id,
            'data_type': self.data_type,
            'action': self.action,
            'original_size': self.original_size,
            'new_size': self.new_size,
            'classification': self.classification,
            'policy_id': self.policy_id,
            'policy_version': self.policy_version,
            'result': self.result,
            'reason': self.reason,
            'metadata': self.metadata,
            'previous_hash': self.previous_hash,
            'entry_hash': self.entry_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'AuditEntry':
        """Create from dictionary"""
        return cls(
            entry_id=data['entry_id'],
            timestamp=data['timestamp'],
            event_type=AuditEventType(data['event_type']),
            actor=data['actor'],
            data_id=data['data_id'],
            data_type=data['data_type'],
            action=data['action'],
            original_size=data.get('original_size', 0),
            new_size=data.get('new_size', 0),
            classification=data.get('classification', ''),
            policy_id=data.get('policy_id', ''),
            policy_version=data.get('policy_version', ''),
            result=data.get('result', 'success'),
            reason=data.get('reason', ''),
            metadata=data.get('metadata', {}),
            previous_hash=data.get('previous_hash', ''),
            entry_hash=data.get('entry_hash', ''),
        )

    def verify_integrity(self, previous_entry_hash: str = "") -> bool:
        """Verify entry integrity"""
        # Check previous hash matches
        if self.previous_hash != previous_entry_hash:
            return False

        # Check entry hash is valid
        expected_hash = self._calculate_hash()
        return self.entry_hash == expected_hash


class AuditStore:
    """
    Immutable audit storage using append-only JSONL.

    Features:
    - Append-only: Once written, entries cannot be modified
    - Hash chain: Each entry references previous entry hash
    - Integrity verification: Verify chain integrity on demand
    - Query: Query by time range, event type, data ID, etc.
    - Export: Export to JSON/CSV for reporting
    """

    def __init__(self, storage_path: str, config: Dict = None):
        """
        Args:
            storage_path: Directory for audit storage
            config: Configuration options
        """
        self.storage_path = Path(storage_path)
        self.config = config or {}

        # Ensure directory exists
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # File for current entries
        self.current_file = self.storage_path / "audit.jsonl"

        # Lock for thread safety
        self._lock = Lock()

        # Cache of entry hashes for chain
        self._last_hash = self._load_last_hash()

    def _load_last_hash(self) -> str:
        """Load the hash of the last entry in the chain"""
        if not self.current_file.exists():
            return ""

        try:
            with open(self.current_file, 'r') as f:
                last_line = None
                for line in f:
                    last_line = line.strip()
                if last_line:
                    entry = json.loads(last_line)
                    return entry.get('entry_hash', '')
        except:
            pass
        return ""

    def append(self, entry: AuditEntry) -> str:
        """
        Append an audit entry (immutable operation).

        Args:
            entry: AuditEntry to append

        Returns:
            entry_id of appended entry
        """
        with self._lock:
            # Set previous hash for chain
            entry.previous_hash = self._last_hash

            # Recalculate entry hash with previous hash
            entry.entry_hash = entry._calculate_hash()

            # Append to file
            with open(self.current_file, 'a') as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + '\n')

            # Update last hash
            self._last_hash = entry.entry_hash

            return entry.entry_id

    def append_many(self, entries: List[AuditEntry]) -> List[str]:
        """Append multiple entries"""
        return [self.append(e) for e in entries]

    def query(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        event_types: Optional[List[AuditEventType]] = None,
        data_ids: Optional[List[str]] = None,
        data_types: Optional[List[str]] = None,
        actors: Optional[List[str]] = None,
        limit: int = 1000,
        offset: int = 0
    ) -> List[AuditEntry]:
        """
        Query audit entries with filters.

        Args:
            start_time: ISO timestamp (inclusive)
            end_time: ISO timestamp (inclusive)
            event_types: Filter by event types
            data_ids: Filter by data IDs
            data_types: Filter by data types
            actors: Filter by actors
            limit: Maximum entries to return
            offset: Skip first N entries

        Returns:
            List of matching AuditEntry objects
        """
        results = []

        if not self.current_file.exists():
            return results

        with open(self.current_file, 'r') as f:
            for line in f:
                if not line.strip():
                    continue

                entry_data = json.loads(line)
                entry = AuditEntry.from_dict(entry_data)

                # Apply filters
                if start_time and entry.timestamp < start_time:
                    continue
                if end_time and entry.timestamp > end_time:
                    continue
                if event_types and entry.event_type not in event_types:
                    continue
                if data_ids and entry.data_id not in data_ids:
                    continue
                if data_types and entry.data_type not in data_types:
                    continue
                if actors and entry.actor not in actors:
                    continue

                results.append(entry)

        # Apply pagination
        return results[offset:offset+limit]

    def get_by_entry_id(self, entry_id: str) -> Optional[AuditEntry]:
        """Get a specific entry by ID"""
        results = self.query(data_ids=[entry_id], limit=1)
        return results[0] if results else None

    def verify_integrity(self) -> Dict[str, Any]:
        """
        Verify the integrity of the entire audit chain.

        Returns:
            Dict with verification results
        """
        result = {
            'valid': True,
            'total_entries': 0,
            'errors': [],
            'first_entry': None,
            'last_entry': None,
        }

        if not self.current_file.exists():
            return result

        previous_hash = ""
        entry_count = 0

        with open(self.current_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue

                try:
                    entry_data = json.loads(line)
                    entry = AuditEntry.from_dict(entry_data)

                    # Verify chain
                    if entry.previous_hash != previous_hash:
                        result['valid'] = False
                        result['errors'].append(
                            f"Line {line_num}: Chain broken (expected {previous_hash}, got {entry.previous_hash})"
                        )

                    # Verify entry hash
                    expected_hash = entry._calculate_hash()
                    if entry.entry_hash != expected_hash:
                        result['valid'] = False
                        result['errors'].append(
                            f"Line {line_num}: Hash mismatch (expected {expected_hash}, got {entry.entry_hash})"
                        )

                    previous_hash = entry.entry_hash
                    entry_count += 1

                    if entry_count == 1:
                        result['first_entry'] = entry.timestamp
                    result['last_entry'] = entry.timestamp

                except Exception as e:
                    result['valid'] = False
                    result['errors'].append(f"Line {line_num}: Parse error - {str(e)}")

        result['total_entries'] = entry_count
        return result

    def iterate(self, batch_size: int = 1000) -> Iterator[AuditEntry]:
        """Iterate over all entries in batches"""
        if not self.current_file.exists():
            return

        batch = []
        with open(self.current_file, 'r') as f:
            for line in f:
                if not line.strip():
                    continue

                entry = AuditEntry.from_dict(json.loads(line))
                batch.append(entry)

                if len(batch) >= batch_size:
                    yield batch
                    batch = []

        if batch:
            yield batch

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the audit store"""
        stats = {
            'total_entries': 0,
            'by_event_type': {},
            'by_data_type': {},
            'total_original_bytes': 0,
            'total_new_bytes': 0,
            'first_entry': None,
            'last_entry': None,
        }

        if not self.current_file.exists():
            return stats

        with open(self.current_file, 'r') as f:
            for line in f:
                if not line.strip():
                    continue

                entry = AuditEntry.from_dict(json.loads(line))

                stats['total_entries'] += 1

                # By event type
                evt_type = entry.event_type.value
                stats['by_event_type'][evt_type] = stats['by_event_type'].get(evt_type, 0) + 1

                # By data type
                data_type = entry.data_type
                stats['by_data_type'][data_type] = stats['by_data_type'].get(data_type, 0) + 1

                # Sizes
                stats['total_original_bytes'] += entry.original_size
                stats['total_new_bytes'] += entry.new_size

                if not stats['first_entry']:
                    stats['first_entry'] = entry.timestamp
                stats['last_entry'] = entry.timestamp

        return stats

    def export(self, output_path: str, format: str = "jsonl") -> int:
        """
        Export audit entries to a file.

        Args:
            output_path: Path to export file
            format: Export format (jsonl, json, csv)

        Returns:
            Number of entries exported
        """
        count = 0

        with open(self.current_file, 'r') as f:
            if format == "jsonl":
                with open(output_path, 'w') as out:
                    for line in f:
                        out.write(line)
                    count = sum(1 for line in f if line.strip())
            elif format == "json":
                entries = []
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))
                with open(output_path, 'w') as out:
                    json.dump(entries, out, indent=2)
                count = len(entries)
            elif format == "csv":
                import csv
                with open(output_path, 'w', newline='') as out:
                    writer = None
                    for line in f:
                        if not line.strip():
                            continue
                        entry = json.loads(line)
                        if writer is None:
                            writer = csv.DictWriter(out, fieldnames=entry.keys())
                            writer.writeheader()
                        writer.writerow(entry)
                        count += 1

        return count

    def archive_old_entries(self, before_date: str, archive_path: str) -> int:
        """
        Archive entries older than a date to a separate file.

        Args:
            before_date: ISO timestamp - entries before this are archived
            archive_path: Path to archive file

        Returns:
            Number of entries archived
        """
        archived = 0
        remaining = []

        if not self.current_file.exists():
            return 0

        with open(self.current_file, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry['timestamp'] < before_date:
                    # Archive it
                    with open(archive_path, 'a') as arch:
                        arch.write(line)
                    archived += 1
                else:
                    remaining.append(line)

        # Rewrite remaining entries
        with open(self.current_file, 'w') as f:
            for line in remaining:
                f.write(line)

        # Update last hash
        if remaining:
            last_entry = json.loads(remaining[-1])
            self._last_hash = last_entry['entry_hash']
        else:
            self._last_hash = ""

        return archived


# Integration example
if __name__ == '__main__':
    import tempfile

    print("Audit Store Demo")
    print("="*50)

    # Create temp storage
    temp_dir = tempfile.mkdtemp()
    store = AuditStore(temp_dir)

    print(f"\nStorage path: {temp_dir}")

    # Create some entries
    entries = [
        AuditEntry(
            event_type=AuditEventType.DATA_INGEST,
            actor="system",
            data_id="video_001",
            data_type="video",
            action="ingest",
            original_size=100 * 1024 * 1024,
            new_size=100 * 1024 * 1024,
            classification="HIGH",
            reason="New surveillance footage"
        ),
        AuditEntry(
            event_type=AuditEventType.DATA_REDUCED,
            actor="semantic_reducer",
            data_id="video_001",
            data_type="video",
            action="downsample",
            original_size=100 * 1024 * 1024,
            new_size=10 * 1024 * 1024,
            classification="LOW",
            policy_id="policy_001",
            reason="Low motion, no objects detected"
        ),
        AuditEntry(
            event_type=AuditEventType.POLICY_CREATED,
            actor="admin",
            data_id="policy_001",
            data_type="policy",
            action="create",
            reason="Created default surveillance policy"
        ),
    ]

    # Append entries
    print("\nAppending entries...")
    for entry in entries:
        entry_id = store.append(entry)
        print(f"  Appended: {entry.entry_id[:8]}... -> {entry.event_type.value}")

    # Query entries
    print("\nQuery all entries:")
    all_entries = store.query(limit=10)
    for e in all_entries:
        print(f"  [{e.timestamp}] {e.event_type.value}: {e.action} ({e.data_id})")

    # Verify integrity
    print("\nVerifying integrity...")
    result = store.verify_integrity()
    print(f"  Valid: {result['valid']}")
    print(f"  Total entries: {result['total_entries']}")
    if result['errors']:
        print(f"  Errors: {result['errors']}")

    # Get stats
    print("\nStatistics:")
    stats = store.get_stats()
    print(f"  Total entries: {stats['total_entries']}")
    print(f"  Original bytes: {stats['total_original_bytes'] / 1024 / 1024:.2f} MB")
    print(f"  New bytes: {stats['total_new_bytes'] / 1024 / 1024:.2f} MB")

    # Cleanup
    shutil.rmtree(temp_dir)
    print("\n[Cleaned up temp storage]")
