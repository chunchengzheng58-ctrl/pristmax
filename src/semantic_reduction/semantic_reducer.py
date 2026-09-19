# -*- coding: utf-8 -*-
"""
Semantic Reducer - Core Engine

Main processing engine that combines semantic analysis with data reduction.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import json

from semantic_reduction.utils.config import Config, get_config
from semantic_reduction.utils.logger import get_logger, AuditLogger


class DataValue(Enum):
    """Data value classification"""
    HIGH = "high"       # Must preserve intact
    MEDIUM = "medium"   # Can reduce
    LOW = "low"         # Can archive/discard


class ReductionAction(Enum):
    """Action to take on data"""
    PRESERVE_INTACT = "preserve_intact"  # Keep as-is
    DOWNSAMPLE = "downsample"            # Reduce quality
    COMPRESS = "compress"                # Compress heavily
    ARCHIVE = "archive"                  # Move to cold storage
    DELETE = "delete"                    # Discard


@dataclass
class ReductionResult:
    """Result of a reduction operation"""
    data_id: str
    action: ReductionAction
    original_size: int
    new_size: int
    classification: DataValue
    reasons: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + 'Z'

    @property
    def savings_percent(self) -> float:
        """Calculate savings percentage"""
        if self.original_size == 0:
            return 0.0
        return (1 - self.new_size / self.original_size) * 100

    def to_dict(self) -> Dict:
        return {
            'data_id': self.data_id,
            'action': self.action.value,
            'original_size': self.original_size,
            'new_size': self.new_size,
            'classification': self.classification.value,
            'savings_percent': self.savings_percent,
            'reasons': self.reasons,
            'metadata': self.metadata,
            'timestamp': self.timestamp
        }


@dataclass
class AuditRecord:
    """Immutable audit record"""
    record_id: str
    timestamp: str
    data_id: str
    data_type: str
    action: str
    original_size: int
    new_size: int
    classification: str
    policy_id: str
    reason: str
    hash_before: str
    hash_after: str


class SemanticReducer:
    """
    Main semantic reduction engine.

    Analyzes data semantically and applies appropriate reduction strategies:
    - HIGH value data: preserved intact
    - MEDIUM value data: downsampled/compressed
    - LOW value data: archived or discarded
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        audit_path: Optional[str] = None
    ):
        """
        Initialize SemanticReducer.

        Args:
            config: Configuration instance
            audit_path: Path to audit log directory
        """
        self.config = config or get_config()
        self.logger = get_logger()

        # Setup audit logger
        audit_dir = audit_path or self.config.get('audit.path', './data/audit')
        self.audit_logger = AuditLogger(f"{audit_dir}/reduction_{datetime.now().strftime('%Y%m%d')}.log")

        # Statistics
        self._stats = {
            'total_processed': 0,
            'total_original_bytes': 0,
            'total_new_bytes': 0,
            'by_action': {},
            'by_classification': {}
        }

    def process_video(
        self,
        video_path: str,
        analysis_result: Dict,
        policy: Dict
    ) -> ReductionResult:
        """
        Process a video file based on analysis and policy.

        Args:
            video_path: Path to video file
            analysis_result: Video analysis (motion, faces, etc.)
            policy: Policy configuration

        Returns:
            ReductionResult
        """
        self.logger.info(f"Processing video: {video_path}")

        # Get original size
        original_size = Path(video_path).stat().st_size if Path(video_path).exists() else 0

        # Determine classification and action
        classification, action, reasons = self._classify_video(analysis_result, policy)

        # Calculate new size
        new_size = self._calculate_new_size(original_size, action, policy)

        result = ReductionResult(
            data_id=video_path,
            action=action,
            original_size=original_size,
            new_size=new_size,
            classification=classification,
            reasons=reasons,
            metadata={
                'motion_score': analysis_result.get('motion_score', 0),
                'has_faces': analysis_result.get('has_faces', False),
                'has_people': analysis_result.get('has_people', False),
                'scene_type': analysis_result.get('scene_type', 'unknown')
            }
        )

        # Log audit
        self._log_audit(result, 'video')

        # Update stats
        self._update_stats(result)

        self.logger.info(
            f"Video processed: {action.value}, "
            f"saved {result.savings_percent:.1f}%"
        )

        return result

    def process_log(
        self,
        log_content: str,
        analysis_result: Dict,
        policy: Dict
    ) -> ReductionResult:
        """
        Process log content based on analysis and policy.

        Args:
            log_content: Raw log content
            analysis_result: Log analysis (levels, keywords, etc.)
            policy: Policy configuration

        Returns:
            ReductionResult
        """
        self.logger.info("Processing log content")

        original_size = len(log_content.encode('utf-8'))

        # Determine classification and action
        classification, action, reasons = self._classify_log(analysis_result, policy)

        # Calculate new size
        new_size = self._calculate_log_new_size(log_content, action, analysis_result, policy)

        result = ReductionResult(
            data_id=analysis_result.get('log_id', 'unknown'),
            action=action,
            original_size=original_size,
            new_size=new_size,
            classification=classification,
            reasons=reasons,
            metadata={
                'error_count': analysis_result.get('error_count', 0),
                'warn_count': analysis_result.get('warn_count', 0),
                'line_count': analysis_result.get('line_count', 0),
                'sampled_lines': analysis_result.get('sampled_lines', 0)
            }
        )

        # Log audit
        self._log_audit(result, 'log')

        # Update stats
        self._update_stats(result)

        self.logger.info(
            f"Log processed: {action.value}, "
            f"saved {result.savings_percent:.1f}%"
        )

        return result

    def _classify_video(
        self,
        analysis: Dict,
        policy: Dict
    ) -> tuple:
        """
        Classify video and determine action.

        Returns:
            (classification, action, reasons)
        """
        reasons = []
        classification = DataValue.MEDIUM
        action = ReductionAction.DOWNSAMPLE

        # Check face detection override
        if policy.get('preserve_with_faces') and analysis.get('has_faces'):
            classification = DataValue.HIGH
            action = ReductionAction.PRESERVE_INTACT
            reasons.append('faces_detected')

        # Check people detection override
        elif policy.get('preserve_with_people') and analysis.get('has_people'):
            classification = DataValue.HIGH
            action = ReductionAction.PRESERVE_INTACT
            reasons.append('people_detected')

        # Check vehicle detection override
        elif policy.get('preserve_with_vehicles') and analysis.get('has_vehicles'):
            classification = DataValue.HIGH
            action = ReductionAction.PRESERVE_INTACT
            reasons.append('vehicles_detected')

        # Check motion level
        elif analysis.get('motion_score', 0) > 0.3:
            classification = DataValue.MEDIUM
            action = ReductionAction.COMPRESS
            reasons.append('significant_motion')

        # Low motion - likely static scene
        else:
            classification = DataValue.LOW
            action = ReductionAction.ARCHIVE
            reasons.append('low_motion_static_scene')

        return classification, action, reasons

    def _classify_log(
        self,
        analysis: Dict,
        policy: Dict
    ) -> tuple:
        """
        Classify log and determine action.

        Returns:
            (classification, action, reasons)
        """
        reasons = []
        classification = DataValue.MEDIUM
        action = ReductionAction.COMPRESS

        error_count = analysis.get('error_count', 0)
        warn_count = analysis.get('warn_count', 0)

        # Errors are always high priority
        if error_count > 0:
            classification = DataValue.HIGH
            action = ReductionAction.PRESERVE_INTACT
            reasons.append(f'errors_detected:{error_count}')

        # Warnings are high priority
        elif warn_count > 0:
            classification = DataValue.HIGH
            action = ReductionAction.PRESERVE_INTACT
            reasons.append(f'warnings_detected:{warn_count}')

        # Business events (orders, transactions)
        elif analysis.get('has_business_events'):
            classification = DataValue.MEDIUM
            action = ReductionAction.COMPRESS
            reasons.append('business_events')

        # Low value - debug/trace logs
        else:
            classification = DataValue.LOW
            action = ReductionAction.ARCHIVE
            reasons.append('routine_logs')

        return classification, action, reasons

    def _calculate_new_size(
        self,
        original_size: int,
        action: ReductionAction,
        policy: Dict
    ) -> int:
        """Calculate new size based on action"""
        if action == ReductionAction.PRESERVE_INTACT:
            return original_size
        elif action == ReductionAction.DOWNSAMPLE:
            ratio = policy.get('low_value_downsample_ratio', 0.1)
            return int(original_size * ratio)
        elif action == ReductionAction.COMPRESS:
            return int(original_size * 0.3)
        elif action == ReductionAction.ARCHIVE:
            return int(original_size * 0.05)
        else:
            return 0

    def _calculate_log_new_size(
        self,
        content: str,
        action: ReductionAction,
        analysis: Dict,
        policy: Dict
    ) -> int:
        """Calculate new log size based on action and sampling"""
        if action == ReductionAction.PRESERVE_INTACT:
            return len(content.encode('utf-8'))

        # For sampling, calculate based on sample rate
        sample_rate = policy.get('default_sampling_rate', 0.1)
        original_lines = analysis.get('line_count', 1)
        sampled_lines = int(original_lines * sample_rate)

        # Estimate bytes per line
        avg_line_size = len(content.encode('utf-8')) / max(original_lines, 1)

        return int(sampled_lines * avg_line_size)

    def _log_audit(self, result: ReductionResult, data_type: str) -> None:
        """Log audit record"""
        self.audit_logger.log(
            action=result.action.value,
            data_id=result.data_id,
            data_type=data_type,
            original_size=result.original_size,
            new_size=result.new_size,
            reason='; '.join(result.reasons)
        )

    def _update_stats(self, result: ReductionResult) -> None:
        """Update processing statistics"""
        self._stats['total_processed'] += 1
        self._stats['total_original_bytes'] += result.original_size
        self._stats['total_new_bytes'] += result.new_size

        # By action
        action_key = result.action.value
        if action_key not in self._stats['by_action']:
            self._stats['by_action'][action_key] = 0
        self._stats['by_action'][action_key] += 1

        # By classification
        class_key = result.classification.value
        if class_key not in self._stats['by_classification']:
            self._stats['by_classification'][class_key] = 0
        self._stats['by_classification'][class_key] += 1

    def get_stats(self) -> Dict:
        """Get processing statistics"""
        stats = self._stats.copy()
        stats['savings_percent'] = (
            (stats['total_original_bytes'] - stats['total_new_bytes']) /
            stats['total_original_bytes'] * 100
            if stats['total_original_bytes'] > 0 else 0
        )
        return stats

    def reset_stats(self) -> None:
        """Reset statistics"""
        self._stats = {
            'total_processed': 0,
            'total_original_bytes': 0,
            'total_new_bytes': 0,
            'by_action': {},
            'by_classification': {}
        }

    def calculate_roi(
        self,
        scale_factor: float = 1.0,
        years: int = 1,
        storage_cost_per_tb: Optional[float] = None
    ) -> Dict:
        """
        Calculate ROI based on current statistics.

        Args:
            scale_factor: Multiplier for projection (e.g., 10 = 10x scale)
            years: Number of years for projection
            storage_cost_per_tb: Storage cost per TB in currency units

        Returns:
            ROI calculation results
        """
        if storage_cost_per_tb is None:
            storage_cost_per_tb = self.config.get('roi.storage_cost_per_tb', 5000)

        original_tb = self._stats['total_original_bytes'] / 1024 / 1024 / 1024 / 1024
        reduced_tb = self._stats['total_new_bytes'] / 1024 / 1024 / 1024 / 1024
        saved_tb = original_tb - reduced_tb

        # Scale up
        scaled_original = original_tb * scale_factor * 365 * years
        scaled_reduced = reduced_tb * scale_factor * 365 * years
        scaled_saved = scaled_original - scaled_reduced

        # Costs
        original_cost = scaled_original * storage_cost_per_tb
        reduced_cost = scaled_reduced * storage_cost_per_tb
        annual_savings = (scaled_original - scaled_reduced) * storage_cost_per_tb / years

        # ROI calculation (assuming implementation cost = 20% of annual savings)
        implementation_cost = annual_savings * 0.2
        roi = (annual_savings - implementation_cost) / implementation_cost * 100 if implementation_cost > 0 else 0
        payback_months = 12 / (roi / 100 + 1) if roi > 0 else 12

        return {
            'sample_original_tb': round(original_tb, 4),
            'sample_reduced_tb': round(reduced_tb, 4),
            'sample_savings_percent': round(
                (1 - reduced_tb / original_tb) * 100 if original_tb > 0 else 0, 1
            ),
            'projected_annual_original_tb': round(scaled_original / years, 2),
            'projected_annual_reduced_tb': round(scaled_reduced / years, 2),
            'annual_savings': round(annual_savings, 2),
            'implementation_cost': round(implementation_cost, 2),
            'roi_percent': round(roi, 0),
            'payback_months': round(payback_months, 1),
            'storage_cost_per_tb': storage_cost_per_tb,
            'currency': self.config.get('roi.currency', 'CNY')
        }
