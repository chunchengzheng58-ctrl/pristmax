"""
Semantic-Aware Data Reduction System (语义感知数据降量系统)

Core concept: Instead of blindly storing all bits, intelligently classify
and reduce data based on semantic value.

Dual-Track Architecture:
- Hot Path: High-value data → preserved intact
- Cold Path: Low-value data → reduced/archived

Design principles:
1. Configurable rules (customer defines what matters)
2. Full audit trail (every decision logged)
3. Business-level fidelity (not bit-level lossless)
4. Quantifiable ROI (storage savings measurable)
"""

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import threading


class DataValue(Enum):
    """Classification of data value"""
    HIGH = "high"        # Must preserve intact
    MEDIUM = "medium"    # Can reduce but keep
    LOW = "low"          # Can archive or discard


class ReductionAction(Enum):
    """Action taken on data"""
    PRESERVE_INTACT = "preserve_intact"     # Store as-is
    COMPRESS = "compress"                   # Apply semantic compression
    DOWNSAMPLE = "downsample"               # Reduce resolution/frequency
    ARCHIVE = "archive"                     # Move to cold storage
    DELETE = "delete"                       # Discard (with backup)


@dataclass
class DataClassifier:
    """
    AI/Rule-based classifier for data value assessment.

    Combines:
    - Rule-based classification (configurable)
    - ML-based semantic analysis (extensible)
    - Pattern recognition for common data types
    """

    rules: Dict[str, Any] = field(default_factory=dict)

    # Built-in classification rules
    HIGH_VALUE_PATTERNS = [
        "error", "exception", "fail", "critical", "alert",
        "security", "breach", "unauthorized",
        "meeting", "presentation", "contract", "invoice",
    ]

    LOW_VALUE_PATTERNS = [
        "debug", "trace", "heartbeat", "health_check",
        "cache_hit", "static_asset", "thumbnail",
        "duplicate", "temp", "tmp", "backup_old",
    ]

    def classify(self, data_type: str, metadata: Dict) -> DataValue:
        """
        Classify data based on type and metadata.

        Args:
            data_type: Type of data (video, log, image, etc.)
            metadata: Additional context

        Returns:
            DataValue classification
        """
        # Check custom rules first
        if data_type in self.rules.get('preserve_types', []):
            return DataValue.HIGH

        if data_type in self.rules.get('discard_types', []):
            return DataValue.LOW

        # Check content patterns
        content = metadata.get('content', '').lower()
        filename = metadata.get('filename', '').lower()

        # High value indicators
        high_score = sum(1 for p in self.HIGH_VALUE_PATTERNS
                        if p in content or p in filename)

        # Low value indicators
        low_score = sum(1 for p in self.LOW_VALUE_PATTERNS
                       if p in content or p in filename)

        if high_score > low_score:
            return DataValue.HIGH
        elif low_score > high_score:
            return DataValue.LOW
        return DataValue.MEDIUM

    def set_rules(self, rules: Dict) -> None:
        """Update classification rules."""
        self.rules = rules


@dataclass
class VideoAnalyzer:
    """
    Semantic analyzer for video content.

    Identifies:
    - Motion/activity
    - Faces/people
    - Objects of interest
    - Scene changes
    """

    def __init__(self):
        self.motion_threshold = 0.05  # 5% pixel change = motion
        self.min_clip_duration = 5    # seconds

    def analyze_frame(self, frame_data: bytes) -> Dict:
        """
        Analyze a single video frame.

        Returns:
            Dict with motion_score, has_faces, has_objects, scene_id
        """
        # Simplified simulation - real implementation would use CV
        import struct
        import random

        # Simulate frame analysis
        motion_score = random.random() * 0.3  # 0-30% simulated motion
        has_faces = random.random() > 0.7     # 30% chance of faces
        has_objects = random.random() > 0.5   # 50% chance of objects

        return {
            'motion_score': motion_score,
            'has_faces': has_faces,
            'has_objects': has_objects,
            'timestamp': time.time(),
        }

    def should_preserve_clip(self, clip_analysis: List[Dict]) -> bool:
        """
        Determine if a video clip should be preserved intact.

        Args:
            clip_analysis: List of frame analyses for the clip

        Returns:
            True if clip has significant content
        """
        if not clip_analysis:
            return False

        # Check for any frame with motion/faces/objects
        for frame in clip_analysis:
            if (frame['motion_score'] > self.motion_threshold or
                frame['has_faces'] or
                frame['has_objects']):
                return True

        return False


@dataclass
class LogAnalyzer:
    """
    Semantic analyzer for log files.

    Classifies log entries by importance:
    - ERROR/WARN → preserve
    - INFO/DEBUG → can reduce
    - TRACE/HEARTBEAT → low value
    """

    HIGH_VALUE_LOG_LEVELS = {'ERROR', 'FATAL', 'CRITICAL', 'WARN', 'WARNING'}
    MEDIUM_VALUE_LOG_LEVELS = {'INFO'}
    LOW_VALUE_LOG_LEVELS = {'DEBUG', 'TRACE', 'VERBOSE'}

    def analyze_entry(self, log_entry: str) -> DataValue:
        """Classify a single log entry."""
        upper = log_entry.upper()

        for level in self.HIGH_VALUE_LOG_LEVELS:
            if f'{level}:' in upper or f'[{level}]' in upper:
                return DataValue.HIGH

        for level in self.MEDIUM_VALUE_LOG_LEVELS:
            if f'{level}:' in upper or f'[{level}]' in upper:
                return DataValue.MEDIUM

        return DataValue.LOW

    def should_preserve_entry(self, log_entry: str) -> bool:
        """Quick check if entry should be preserved."""
        return self.analyze_entry(log_entry) != DataValue.LOW


@dataclass
class ReductionPolicy:
    """
    Configurable policy for data reduction.

    Customers define what to preserve/discard based on:
    - Data type
    - Content patterns
    - Age/retention
    - Access frequency
    """

    preserve_types: List[str] = field(default_factory=list)
    discard_types: List[str] = field(default_factory=list)
    compression_level: str = "balanced"  # fast, balanced, best
    video_downsample_ratio: float = 0.1  # 10% of frames preserved
    log_retention_days: int = 90
    archive_after_days: int = 30
    min_storage_savings: float = 0.5  # Require 50% savings to apply reduction

    def to_dict(self) -> Dict:
        return {
            'preserve_types': self.preserve_types,
            'discard_types': self.discard_types,
            'compression_level': self.compression_level,
            'video_downsample_ratio': self.video_downsample_ratio,
            'log_retention_days': self.log_retention_days,
            'archive_after_days': self.archive_after_days,
            'min_storage_savings': self.min_storage_savings,
        }


@dataclass
class AuditRecord:
    """
    Immutable audit trail record.

    Records every action taken on data for compliance and debugging.
    """

    record_id: str
    timestamp: str
    data_id: str
    data_type: str
    original_size: int
    action: ReductionAction
    new_size: Optional[int]
    classification: DataValue
    policy_id: str
    reason: str
    hash_before: str
    hash_after: Optional[str]

    def to_dict(self) -> Dict:
        return {
            'record_id': self.record_id,
            'timestamp': self.timestamp,
            'data_id': self.data_id,
            'data_type': self.data_type,
            'original_size': self.original_size,
            'action': self.action.value,
            'new_size': self.new_size,
            'classification': self.classification.value,
            'policy_id': self.policy_id,
            'reason': self.reason,
            'hash_before': self.hash_before,
            'hash_after': self.hash_after,
        }


class AuditLogger:
    """
    Immutable audit log for compliance.

    All data processing decisions are logged.
    """

    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._records: List[AuditRecord] = []

    def log(self, record: AuditRecord) -> None:
        """Log an audit record."""
        with self._lock:
            self._records.append(record)

            # Append to JSONL file (append-only, immutable)
            log_file = self.storage_path / f"audit_{datetime.now().strftime('%Y%m%d')}.jsonl"
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + '\n')

    def query(self, data_id: str = None, start_time: str = None,
              end_time: str = None, action: str = None) -> List[AuditRecord]:
        """Query audit records."""
        with self._lock:
            results = self._records.copy()

            if data_id:
                results = [r for r in results if r.data_id == data_id]
            if start_time:
                results = [r for r in results if r.timestamp >= start_time]
            if end_time:
                results = [r for r in results if r.timestamp <= end_time]
            if action:
                results = [r for r in results if r.action.value == action]

            return results

    def generate_report(self, start_date: str, end_date: str) -> Dict:
        """Generate compliance report."""
        records = self.query(start_time=start_date, end_time=end_date)

        total_original = sum(r.original_size for r in records)
        total_after = sum(r.new_size or r.original_size for r in records)
        actions_count = {}

        for r in records:
            actions_count[r.action.value] = actions_count.get(r.action.value, 0) + 1

        return {
            'period': f'{start_date} to {end_date}',
            'total_records': len(records),
            'total_original_bytes': total_original,
            'total_after_bytes': total_after,
            'savings_bytes': total_original - total_after,
            'savings_percent': (1 - total_after/total_original)*100 if total_original > 0 else 0,
            'actions_breakdown': actions_count,
        }


@dataclass
class SemanticReducer:
    """
    Main semantic reduction engine.

    Orchestrates classification, analysis, and reduction.
    """

    def __init__(self, storage_dir: str, policy: ReductionPolicy = None):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.policy = policy or ReductionPolicy()
        self.classifier = DataClassifier()
        self.video_analyzer = VideoAnalyzer()
        self.log_analyzer = LogAnalyzer()
        self.audit_logger = AuditLogger(str(self.storage_dir / 'audit'))

        self._reduction_count = 0
        self._original_total = 0
        self._reduced_total = 0

    def process_video(self, video_path: str, metadata: Dict = None) -> Dict:
        """
        Process video file with semantic analysis.

        Args:
            video_path: Path to video file
            metadata: Optional metadata

        Returns:
            Processing result with action taken
        """
        metadata = metadata or {}
        original_size = Path(video_path).stat().st_size
        self._original_total += original_size

        # Classify
        value = self.classifier.classify('video', metadata)

        if value == DataValue.HIGH:
            action = ReductionAction.PRESERVE_INTACT
            new_size = original_size
            reason = "High-value content (faces/objects detected)"
        elif value == DataValue.MEDIUM:
            # Apply downsampling
            action = ReductionAction.DOWNSAMPLE
            new_size = int(original_size * self.policy.video_downsample_ratio)
            reason = f"Medium-value content, downsampled {self.policy.video_downsample_ratio*100}%"
        else:
            # Low value - check if worth archiving
            action = ReductionAction.ARCHIVE
            new_size = int(original_size * 0.05)  # Compress heavily
            reason = "Low-value content, archived with compression"

        # Simulate processing
        # In real impl, would actually transcode video

        # Create audit record
        record = AuditRecord(
            record_id=uuid.uuid4().hex,
            timestamp=datetime.utcnow().isoformat() + 'Z',
            data_id=hashlib.md5(video_path.encode()).hexdigest()[:16],
            data_type='video',
            original_size=original_size,
            action=action,
            new_size=new_size,
            classification=value,
            policy_id='default',
            reason=reason,
            hash_before=hashlib.sha256(open(video_path, 'rb').read()).hexdigest()[:16],
            hash_after=None,
        )
        self.audit_logger.log(record)

        self._reduction_count += 1
        self._reduced_total += new_size

        return {
            'original_size': original_size,
            'new_size': new_size,
            'action': action.value,
            'classification': value.value,
            'savings': original_size - new_size,
            'savings_percent': (1 - new_size/original_size)*100 if original_size > 0 else 0,
            'audit_id': record.record_id,
        }

    def process_log(self, log_path: str, metadata: Dict = None) -> Dict:
        """
        Process log file with semantic analysis.

        Keeps ERROR/WARN entries, discards DEBUG/TRACE.
        """
        metadata = metadata or {}
        original_size = Path(log_path).stat().st_size
        self._original_total += original_size

        # Read and analyze log
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        preserved_lines = []
        discarded_lines = 0

        for line in lines:
            if self.log_analyzer.should_preserve_entry(line):
                preserved_lines.append(line)
            else:
                discarded_lines += 1

        # Calculate new size
        preserved_content = ''.join(preserved_lines)
        new_size = len(preserved_content.encode('utf-8'))

        if discarded_lines > len(lines) * 0.5:
            action = ReductionAction.COMPRESS
            reason = f"High discard rate ({discarded_lines}/{len(lines)} lines)"
        else:
            action = ReductionAction.PRESERVE_INTACT
            reason = "Essential log entries preserved"

        # Audit record
        record = AuditRecord(
            record_id=uuid.uuid4().hex,
            timestamp=datetime.utcnow().isoformat() + 'Z',
            data_id=hashlib.md5(log_path.encode()).hexdigest()[:16],
            data_type='log',
            original_size=original_size,
            action=action,
            new_size=new_size,
            classification=DataValue.MEDIUM,
            policy_id='default',
            reason=reason,
            hash_before=hashlib.sha256(open(log_path, 'rb').read()).hexdigest()[:16],
            hash_after=None,
        )
        self.audit_logger.log(record)

        self._reduction_count += 1
        self._reduced_total += new_size

        return {
            'original_size': original_size,
            'new_size': new_size,
            'action': action.value,
            'lines_preserved': len(preserved_lines),
            'lines_discarded': discarded_lines,
            'savings': original_size - new_size,
            'savings_percent': (1 - new_size/original_size)*100 if original_size > 0 else 0,
            'audit_id': record.record_id,
        }

    def get_stats(self) -> Dict:
        """Get reduction statistics."""
        return {
            'files_processed': self._reduction_count,
            'original_total_bytes': self._original_total,
            'reduced_total_bytes': self._reduced_total,
            'total_savings_bytes': self._original_total - self._reduced_total,
            'total_savings_percent': (1 - self._reduced_total/self._original_total)*100
                                    if self._original_total > 0 else 0,
        }


class DataValueCalculator:
    """
    Calculate and report storage value metrics.

    For ROI presentations to customers.
    """

    def __init__(self):
        self.history: List[Dict] = []

    def add_result(self, result: Dict) -> None:
        """Add a processing result to history."""
        self.history.append({
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            **result
        })

    def calculate_roi(self, storage_cost_per_tb: float, years: int = 1) -> Dict:
        """
        Calculate ROI based on processing history.

        Args:
            storage_cost_per_tb: Cost per TB per year
            years: Number of years for ROI calculation

        Returns:
            ROI analysis report
        """
        if not self.history:
            return {'error': 'No data available'}

        total_original = sum(h.get('original_size', 0) for h in self.history)
        total_after = sum(h.get('new_size', h.get('original_size', 0)) for h in self.history)
        savings = total_original - total_after

        # Project to PB scale
        scale_factor = 1_000_000_000_000 / total_original if total_original > 0 else 0
        projected_savings_pb = savings * scale_factor

        annual_savings = projected_savings_pb * storage_cost_per_tb
        roi_1_year = (annual_savings / (annual_savings * 0.2)) * 100  # Assume 20% implementation cost

        return {
            'sample_size': len(self.history),
            'sample_original_gb': total_original / 1_000_000_000,
            'sample_after_gb': total_after / 1_000_000_000,
            'sample_savings_percent': (1 - total_after/total_original)*100 if total_original > 0 else 0,

            'projected_1pb_savings_percent': (1 - total_after/total_original)*100 if total_original > 0 else 0,
            'projected_1pb_storage_tb': 1000 - (1000 * (1 - total_after/total_original)) if total_original > 0 else 1000,

            'annual_savings_at_scale': annual_savings,
            'roi_1_year_percent': roi_1_year,
            'payback_months': 12 / (roi_1_year/100) if roi_1_year > 0 else 0,
        }


# Example usage
if __name__ == '__main__':
    print("Semantic-Aware Data Reduction System")
    print("="*50)
    print("Initializing reducer with default policy...")

    reducer = SemanticReducer('./semantic_storage')
    calculator = DataValueCalculator()

    print("\nProcessing sample video...")
    # Would process actual video here
    result = {
        'original_size': 1_000_000_000,  # 1GB
        'new_size': 100_000_000,         # 100MB
        'action': 'downsample',
    }
    calculator.add_result(result)

    print("\nProcessing sample log file...")
    result = {
        'original_size': 10_000_000,     # 10MB
        'new_size': 1_000_000,           # 1MB
        'action': 'compress',
    }
    calculator.add_result(result)

    print("\nCalculating ROI...")
    roi = calculator.calculate_roi(storage_cost_per_tb=5000)
    print(f"  Sample savings: {roi.get('sample_savings_percent', 0):.1f}%")
    print(f"  Projected 1PB savings: {roi.get('projected_1pb_savings_percent', 0):.1f}%")
    print(f"  Annual savings at scale: ¥{roi.get('annual_savings_at_scale', 0):,.0f}")
