"""
Surveillance Video Processing Policy

Configurable policies for surveillance video semantic reduction.
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

from semantic.video_analyzer import (
    SceneType, MotionLevel, ClipAnalysis, VideoAnalyzer
)
from semantic_reducer import (
    DataValue, ReductionAction, AuditRecord, AuditLogger
)


class PreservationPriority(Enum):
    """Priority levels for preservation decisions"""
    CRITICAL = "critical"     # Never reduce/discard (faces, incidents)
    HIGH = "high"             # Prefer preserve
    MEDIUM = "medium"         # Can reduce
    LOW = "low"               # Can archive
    WASTE = "waste"           # Discard if no retention requirement


@dataclass
class TimeWindowRule:
    """Rule based on time window"""
    start_hour: int           # 0-23
    end_hour: int             # 0-23
    preservation_priority: PreservationPriority
    reason: str = ""


@dataclass
class MotionRule:
    """Rule based on motion level"""
    min_motion: float         # 0.0-1.0
    max_motion: float         # 0.0-1.0
    preservation_priority: PreservationPriority
    require_objects: bool = False  # Require people/vehicles detected
    reason: str = ""


@dataclass
class SceneRule:
    """Rule based on scene type"""
    scene_type: SceneType
    preservation_priority: PreservationPriority
    reason: str = ""


@dataclass
class SurveillancePolicy:
    """
    Policy configuration for surveillance video processing.

    Defines rules for:
    - Time-based preservation (e.g., keep business hours fully)
    - Motion-based preservation (e.g., preserve high-motion clips)
    - Scene-based preservation (e.g., preserve entrance cameras)
    - Object detection preservation (e.g., always preserve when people detected)
    """

    policy_id: str = ""
    policy_name: str = ""
    created_at: str = ""

    # Time window rules (evaluated in order)
    time_rules: List[TimeWindowRule] = field(default_factory=list)

    # Motion rules
    motion_rules: List[MotionRule] = field(default_factory=list)

    # Scene rules
    scene_rules: List[SceneRule] = field(default_factory=list)

    # Global settings
    preserve_with_faces: bool = True          # Always preserve if faces detected
    preserve_with_people: bool = True         # Always preserve if people detected
    preserve_with_vehicles: bool = True       # Always preserve if vehicles detected

    # Reduction settings
    low_value_downsample_ratio: float = 0.1   # Keep 10% of frames for low-value content
    low_value_compression: str = "high"       # Compression level for low-value

    # Retention
    retain_days_critical: int = 365           # Keep critical data 1 year
    retain_days_high: int = 90                # Keep high priority 90 days
    retain_days_medium: int = 30              # Keep medium priority 30 days
    retain_days_low: int = 7                  # Keep low priority 7 days

    # Quality thresholds
    min_brightness: float = 0.1               # Below this = likely unusable
    min_sharpness: float = 0.3                # Below this = too blurry

    def __post_init__(self):
        if not self.policy_id:
            self.policy_id = uuid.uuid4().hex[:16]
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + 'Z'

    def to_dict(self) -> Dict:
        return {
            'policy_id': self.policy_id,
            'policy_name': self.policy_name,
            'created_at': self.created_at,
            'time_rules': [
                {
                    'start_hour': r.start_hour,
                    'end_hour': r.end_hour,
                    'preservation_priority': r.preservation_priority.value,
                    'reason': r.reason
                }
                for r in self.time_rules
            ],
            'motion_rules': [
                {
                    'min_motion': r.min_motion,
                    'max_motion': r.max_motion,
                    'preservation_priority': r.preservation_priority.value,
                    'require_objects': r.require_objects,
                    'reason': r.reason
                }
                for r in self.motion_rules
            ],
            'scene_rules': [
                {
                    'scene_type': r.scene_type.value,
                    'preservation_priority': r.preservation_priority.value,
                    'reason': r.reason
                }
                for r in self.scene_rules
            ],
            'preserve_with_faces': self.preserve_with_faces,
            'preserve_with_people': self.preserve_with_people,
            'preserve_with_vehicles': self.preserve_with_vehicles,
            'low_value_downsample_ratio': self.low_value_downsample_ratio,
            'retain_days_critical': self.retain_days_critical,
            'retain_days_high': self.retain_days_high,
            'retain_days_medium': self.retain_days_medium,
            'retain_days_low': self.retain_days_low,
            'min_brightness': self.min_brightness,
            'min_sharpness': self.min_sharpness,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'SurveillancePolicy':
        policy = cls(
            policy_id=data.get('policy_id', ''),
            policy_name=data.get('policy_name', ''),
            created_at=data.get('created_at', ''),
            preserve_with_faces=data.get('preserve_with_faces', True),
            preserve_with_people=data.get('preserve_with_people', True),
            preserve_with_vehicles=data.get('preserve_with_vehicles', True),
            low_value_downsample_ratio=data.get('low_value_downsample_ratio', 0.1),
            retain_days_critical=data.get('retain_days_critical', 365),
            retain_days_high=data.get('retain_days_high', 90),
            retain_days_medium=data.get('retain_days_medium', 30),
            retain_days_low=data.get('retain_days_low', 7),
            min_brightness=data.get('min_brightness', 0.1),
            min_sharpness=data.get('min_sharpness', 0.3),
        )

        for r in data.get('time_rules', []):
            policy.time_rules.append(TimeWindowRule(
                start_hour=r['start_hour'],
                end_hour=r['end_hour'],
                preservation_priority=PreservationPriority(r['preservation_priority']),
                reason=r.get('reason', '')
            ))

        for r in data.get('motion_rules', []):
            policy.motion_rules.append(MotionRule(
                min_motion=r['min_motion'],
                max_motion=r['max_motion'],
                preservation_priority=PreservationPriority(r['preservation_priority']),
                require_objects=r.get('require_objects', False),
                reason=r.get('reason', '')
            ))

        for r in data.get('scene_rules', []):
            policy.scene_rules.append(SceneRule(
                scene_type=SceneType(r['scene_type']),
                preservation_priority=PreservationPriority(r['preservation_priority']),
                reason=r.get('reason', '')
            ))

        return policy

    @classmethod
    def default_indoor(cls) -> 'SurveillancePolicy':
        """Default policy for indoor cameras."""
        policy = cls(
            policy_name="Default Indoor Camera Policy",
        )

        # Business hours - higher priority
        policy.time_rules = [
            TimeWindowRule(8, 18, PreservationPriority.HIGH, "Business hours"),
            TimeWindowRule(0, 6, PreservationPriority.LOW, "Night - typically empty"),
        ]

        # High motion with people = critical
        policy.motion_rules = [
            MotionRule(0.3, 1.0, PreservationPriority.CRITICAL, True, "High motion with people"),
            MotionRule(0.2, 1.0, PreservationPriority.HIGH, False, "Significant motion"),
            MotionRule(0.05, 0.2, PreservationPriority.MEDIUM, False, "Some motion"),
        ]

        # Entrance = higher priority
        policy.scene_rules = [
            SceneRule(SceneType.ENTRANCE, PreservationPriority.HIGH, "Entrance monitoring"),
            SceneRule(SceneType.CORRIDOR, PreservationPriority.MEDIUM, "Corridor"),
        ]

        return policy

    @classmethod
    def default_parking(cls) -> 'SurveillancePolicy':
        """Default policy for parking lot cameras."""
        policy = cls(
            policy_name="Default Parking Lot Policy",
        )

        # Evening hours - higher activity
        policy.time_rules = [
            TimeWindowRule(18, 23, PreservationPriority.HIGH, "Evening - high activity"),
            TimeWindowRule(6, 10, PreservationPriority.MEDIUM, "Morning transition"),
        ]

        # Vehicles detected = critical
        policy.motion_rules = [
            MotionRule(0.2, 1.0, PreservationPriority.CRITICAL, True, "Motion with vehicles"),
            MotionRule(0.1, 1.0, PreservationPriority.HIGH, False, "Significant motion"),
        ]

        policy.scene_rules = [
            SceneRule(SceneType.PARKING, PreservationPriority.HIGH, "Parking lot monitoring"),
        ]

        policy.preserve_with_vehicles = True

        return policy


class SurveillancePolicyEngine:
    """
    Engine for applying surveillance policies to video clips.
    """

    def __init__(self, policy: SurveillancePolicy, audit_logger: AuditLogger = None):
        self.policy = policy
        self.audit_logger = audit_logger
        self.video_analyzer = VideoAnalyzer()

    def evaluate_clip(self, clip_analysis: ClipAnalysis, clip_path: str = "") -> Dict:
        """
        Evaluate a video clip against the policy.

        Args:
            clip_analysis: Analysis result from VideoAnalyzer
            clip_path: Path to the clip file

        Returns:
            Dict with evaluation results and recommended actions
        """
        # Start with base score from analyzer
        priority = PreservationPriority.MEDIUM
        reasons = []
        actions_taken = []

        # Check time rules
        clip_hour = int(clip_analysis.start_time // 3600) % 24
        for rule in self.policy.time_rules:
            if rule.start_hour <= clip_hour < rule.end_hour:
                if rule.preservation_priority.value > priority.value:
                    priority = rule.preservation_priority
                reasons.append(f"time:{rule.reason}")
                break

        # Check motion rules
        for rule in self.policy.motion_rules:
            if rule.min_motion <= clip_analysis.max_motion_score <= rule.max_motion:
                if rule.preservation_priority.value > priority.value:
                    priority = rule.preservation_priority
                reasons.append(f"motion:{rule.reason}")

                if rule.require_objects and not (clip_analysis.has_people or clip_analysis.has_vehicles):
                    # Downgrade if objects required but not found
                    priority = PreservationPriority(
                        max(priority.value, PreservationPriority.LOW.value)
                    )
                break

        # Check scene rules
        for rule in self.policy.scene_rules:
            if rule.scene_type == clip_analysis.dominant_scene:
                if rule.preservation_priority.value > priority.value:
                    priority = rule.preservation_priority
                reasons.append(f"scene:{rule.reason}")
                break

        # Override rules for specific detections
        if self.policy.preserve_with_faces and clip_analysis.has_faces:
            priority = PreservationPriority.CRITICAL
            reasons.append("faces_detected_override")
            actions_taken.append("preserve_for_faces")

        if self.policy.preserve_with_people and clip_analysis.has_people:
            if priority.value < PreservationPriority.HIGH.value:
                priority = PreservationPriority.HIGH
            reasons.append("people_detected_override")
            actions_taken.append("preserve_for_people")

        if self.policy.preserve_with_vehicles and clip_analysis.has_vehicles:
            if priority.value < PreservationPriority.HIGH.value:
                priority = PreservationPriority.HIGH
            reasons.append("vehicles_detected_override")
            actions_taken.append("preserve_for_vehicles")

        # Quality checks
        if clip_analysis.avg_brightness < self.policy.min_brightness:
            reasons.append(f"low_brightness:{clip_analysis.avg_brightness:.2f}")
            actions_taken.append("flag_low_quality")

        if clip_analysis.avg_sharpness < self.policy.min_sharpness:
            reasons.append(f"low_sharpness:{clip_analysis.avg_sharpness:.2f}")
            actions_taken.append("flag_blurry")

        # Determine final action
        if priority == PreservationPriority.CRITICAL:
            action = ReductionAction.PRESERVE_INTACT
            retention_days = self.policy.retain_days_critical
        elif priority == PreservationPriority.HIGH:
            action = ReductionAction.PRESERVE_INTACT
            retention_days = self.policy.retain_days_high
        elif priority == PreservationPriority.MEDIUM:
            action = ReductionAction.DOWNSAMPLE
            retention_days = self.policy.retain_days_medium
        elif priority == PreservationPriority.LOW:
            action = ReductionAction.ARCHIVE
            retention_days = self.policy.retain_days_low
        else:
            action = ReductionAction.DELETE
            retention_days = 0

        # Calculate size reduction estimate
        original_size = clip_analysis.frame_count * 1024 * 100  # Simulated
        if action == ReductionAction.PRESERVE_INTACT:
            new_size = original_size
        elif action == ReductionAction.DOWNSAMPLE:
            new_size = int(original_size * self.policy.low_value_downsample_ratio)
        elif action == ReductionAction.ARCHIVE:
            new_size = int(original_size * 0.05)
        else:
            new_size = 0

        result = {
            'clip_id': clip_analysis.clip_id,
            'priority': priority.value,
            'action': action.value,
            'retention_days': retention_days,
            'original_size': original_size,
            'estimated_size': new_size,
            'savings_percent': (1 - new_size/original_size)*100 if original_size > 0 else 0,
            'reasons': reasons,
            'actions_taken': actions_taken,
            'quality_flags': [a for a in actions_taken if a.startswith('flag_')],
        }

        # Log to audit if available
        if self.audit_logger:
            record = AuditRecord(
                record_id=uuid.uuid4().hex,
                timestamp=datetime.utcnow().isoformat() + 'Z',
                data_id=hashlib.md5(clip_path.encode()).hexdigest()[:16] if clip_path else clip_analysis.clip_id,
                data_type='video',
                original_size=original_size,
                action=action,
                new_size=new_size,
                classification=DataValue.HIGH if priority in (PreservationPriority.CRITICAL, PreservationPriority.HIGH)
                              else DataValue.MEDIUM if priority == PreservationPriority.MEDIUM
                              else DataValue.LOW,
                policy_id=self.policy.policy_id,
                reason='; '.join(reasons),
                hash_before='',
                hash_after='',
            )
            self.audit_logger.log(record)

        return result

    def evaluate_batch(self, clip_analyses: List[ClipAnalysis]) -> List[Dict]:
        """Evaluate multiple clips."""
        return [self.evaluate_clip(clip) for clip in clip_analyses]


# Demo usage
if __name__ == '__main__':
    from semantic.video_analyzer import VideoAnalyzer

    print("Surveillance Policy Engine Demo")
    print("="*50)

    # Create policy
    policy = SurveillancePolicy.default_indoor()
    print(f"\nPolicy: {policy.policy_name}")
    print(f"  ID: {policy.policy_id}")

    # Create engine
    engine = SurveillancePolicyEngine(policy)

    # Simulate clip analysis
    analyzer = VideoAnalyzer()

    print("\nSimulating 60-second clip (60 frames at 1fps)...")

    for i in range(60):
        frame_data = b'fake'
        timestamp = float(i)
        analyzer.analyze_frame(frame_data, timestamp, i)

    # Get clip analysis
    clip = analyzer.analyze_clip(0.0, 59.0)

    print(f"\nClip Analysis:")
    print(f"  Duration: 60s")
    print(f"  Motion: {clip.motion_level.value} (max: {clip.max_motion_score:.3f})")
    print(f"  People: {clip.has_people}, Vehicles: {clip.has_vehicles}, Faces: {clip.has_faces}")
    print(f"  Scene: {clip.dominant_scene.value}")
    print(f"  Preserve Score: {clip.preserve_recommendation:.2f}")

    # Evaluate against policy
    result = engine.evaluate_clip(clip, "/path/to/clip.mp4")

    print(f"\nPolicy Evaluation:")
    print(f"  Priority: {result['priority']}")
    print(f"  Action: {result['action']}")
    print(f"  Retention: {result['retention_days']} days")
    print(f"  Original Size: {result['original_size']:,} bytes")
    print(f"  Estimated Size: {result['estimated_size']:,} bytes")
    print(f"  Savings: {result['savings_percent']:.1f}%")
    print(f"  Reasons: {result['reasons']}")
