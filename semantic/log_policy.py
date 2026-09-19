"""
Log Processing Policy

Configurable policies for server log semantic reduction.
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

from semantic.log_analyzer import (
    LogLevel, LogType, LogBlock, LogAnalyzer
)
from semantic_reducer import (
    DataValue, ReductionAction, AuditRecord, AuditLogger
)


class PreservationPriority(Enum):
    """Priority levels for log preservation"""
    CRITICAL = "critical"     # Never reduce/discard (errors, anomalies)
    HIGH = "high"             # Prefer preserve (warnings, business events)
    MEDIUM = "medium"         # Can compress (INFO with business context)
    LOW = "low"               # Can sample (DEBUG, routine INFO)
    WASTE = "waste"           # Discard if no retention requirement (TRACE)


class LogSamplingStrategy(Enum):
    """Sampling strategies for logs"""
    HEAD = "head"             # Keep beginning of block
    TAIL = "tail"             # Keep end of block
    DISTRIBUTED = "distributed"  # Evenly distributed
    ERROR_FOCUSED = "error_focused"  # More samples near errors


@dataclass
class LevelRule:
    """Rule based on log level"""
    level: LogLevel
    preservation_priority: PreservationPriority
    action: ReductionAction = ReductionAction.PRESERVE_INTACT
    sampling_rate: float = 1.0  # 1.0 = keep all
    compress: bool = False
    reason: str = ""


@dataclass
class PatternRule:
    """Rule based on log message pattern"""
    pattern: str              # Regex pattern
    preservation_priority: PreservationPriority
    action: ReductionAction = ReductionAction.PRESERVE_INTACT
    reason: str = ""


@dataclass
class TimeWindowRule:
    """Rule based on time window"""
    start_hour: int           # 0-23
    end_hour: int             # 0-23
    preservation_priority: PreservationPriority
    sampling_rate: float = 1.0
    reason: str = ""


@dataclass
class LogPolicy:
    """
    Policy configuration for log processing.

    Defines rules for:
    - Log level preservation (ERROR always kept, TRACE discarded)
    - Pattern-based preservation (specific keywords, user IDs)
    - Time-based sampling (less sampling during business hours)
    - Business event preservation (order IDs, transactions)
    """

    policy_id: str = ""
    policy_name: str = ""
    created_at: str = ""

    # Log type this policy applies to
    log_type: LogType = LogType.APPLICATION

    # Level rules (evaluated in order)
    level_rules: List[LevelRule] = field(default_factory=list)

    # Pattern rules
    pattern_rules: List[PatternRule] = field(default_factory=list)

    # Time window rules
    time_rules: List[TimeWindowRule] = field(default_factory=list)

    # Global sampling settings
    default_sampling_rate: float = 0.1     # Default 10% for low-priority
    sampling_strategy: LogSamplingStrategy = LogSamplingStrategy.ERROR_FOCUSED

    # Compression settings
    compress_low_value: bool = True
    compression_level: int = 9             # 1-9, highest compression

    # Retention (days)
    retain_days_critical: int = 365
    retain_days_high: int = 90
    retain_days_medium: int = 30
    retain_days_low: int = 7

    # Business event preservation
    preserve_order_logs: bool = True       # Keep logs with order IDs
    preserve_transaction_logs: bool = True  # Keep logs with transaction IDs
    preserve_user_action_logs: bool = True  # Keep user action logs

    # Keyword preservation
    preserve_keywords: List[str] = field(default_factory=list)  # Additional keywords to preserve

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
            'log_type': self.log_type.value,
            'level_rules': [
                {
                    'level': r.level.value,
                    'preservation_priority': r.preservation_priority.value,
                    'action': r.action.value,
                    'sampling_rate': r.sampling_rate,
                    'reason': r.reason
                }
                for r in self.level_rules
            ],
            'pattern_rules': [
                {
                    'pattern': r.pattern,
                    'preservation_priority': r.preservation_priority.value,
                    'action': r.action.value,
                    'reason': r.reason
                }
                for r in self.pattern_rules
            ],
            'time_rules': [
                {
                    'start_hour': r.start_hour,
                    'end_hour': r.end_hour,
                    'preservation_priority': r.preservation_priority.value,
                    'sampling_rate': r.sampling_rate,
                    'reason': r.reason
                }
                for r in self.time_rules
            ],
            'default_sampling_rate': self.default_sampling_rate,
            'sampling_strategy': self.sampling_strategy.value,
            'compress_low_value': self.compress_low_value,
            'compression_level': self.compression_level,
            'retain_days_critical': self.retain_days_critical,
            'retain_days_high': self.retain_days_high,
            'retain_days_medium': self.retain_days_medium,
            'retain_days_low': self.retain_days_low,
            'preserve_order_logs': self.preserve_order_logs,
            'preserve_transaction_logs': self.preserve_transaction_logs,
            'preserve_user_action_logs': self.preserve_user_action_logs,
            'preserve_keywords': self.preserve_keywords,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'LogPolicy':
        policy = cls(
            policy_id=data.get('policy_id', ''),
            policy_name=data.get('policy_name', ''),
            created_at=data.get('created_at', ''),
            log_type=LogType(data.get('log_type', 'application')),
            default_sampling_rate=data.get('default_sampling_rate', 0.1),
            sampling_strategy=LogSamplingStrategy(data.get('sampling_strategy', 'error_focused')),
            compress_low_value=data.get('compress_low_value', True),
            compression_level=data.get('compression_level', 9),
            retain_days_critical=data.get('retain_days_critical', 365),
            retain_days_high=data.get('retain_days_high', 90),
            retain_days_medium=data.get('retain_days_medium', 30),
            retain_days_low=data.get('retain_days_low', 7),
            preserve_order_logs=data.get('preserve_order_logs', True),
            preserve_transaction_logs=data.get('preserve_transaction_logs', True),
            preserve_user_action_logs=data.get('preserve_user_action_logs', True),
            preserve_keywords=data.get('preserve_keywords', []),
        )

        for r in data.get('level_rules', []):
            policy.level_rules.append(LevelRule(
                level=LogLevel(r['level']),
                preservation_priority=PreservationPriority(r['preservation_priority']),
                action=ReductionAction(r['action']),
                sampling_rate=r.get('sampling_rate', 1.0),
                reason=r.get('reason', '')
            ))

        for r in data.get('pattern_rules', []):
            policy.pattern_rules.append(PatternRule(
                pattern=r['pattern'],
                preservation_priority=PreservationPriority(r['preservation_priority']),
                action=ReductionAction(r['action']),
                reason=r.get('reason', '')
            ))

        for r in data.get('time_rules', []):
            policy.time_rules.append(TimeWindowRule(
                start_hour=r['start_hour'],
                end_hour=r['end_hour'],
                preservation_priority=PreservationPriority(r['preservation_priority']),
                sampling_rate=r.get('sampling_rate', 1.0),
                reason=r.get('reason', '')
            ))

        return policy

    @classmethod
    def default_application(cls) -> 'LogPolicy':
        """Default policy for application logs."""
        policy = cls(
            policy_name="Default Application Log Policy",
            log_type=LogType.APPLICATION,
        )

        # Level rules: ERROR=critical, WARN=high, INFO=medium, DEBUG=low, TRACE=waste
        policy.level_rules = [
            LevelRule(LogLevel.ERROR, PreservationPriority.CRITICAL,
                     ReductionAction.PRESERVE_INTACT, 1.0, False, "Errors must be preserved"),
            LevelRule(LogLevel.WARN, PreservationPriority.HIGH,
                     ReductionAction.PRESERVE_INTACT, 1.0, False, "Warnings indicate issues"),
            LevelRule(LogLevel.INFO, PreservationPriority.MEDIUM,
                     ReductionAction.DOWNSAMPLE, 0.3, True, "INFO can be sampled"),
            LevelRule(LogLevel.DEBUG, PreservationPriority.LOW,
                     ReductionAction.ARCHIVE, 0.1, True, "Debug logs low value"),
            LevelRule(LogLevel.TRACE, PreservationPriority.WASTE,
                     ReductionAction.DELETE, 0.0, False, "Trace logs discarded"),
        ]

        # Business hours: less aggressive sampling
        policy.time_rules = [
            TimeWindowRule(9, 18, PreservationPriority.MEDIUM, 0.5, "Business hours - more context"),
            TimeWindowRule(0, 6, PreservationPriority.LOW, 0.1, "Night - typically routine"),
        ]

        return policy

    @classmethod
    def default_access(cls) -> 'LogPolicy':
        """Default policy for access logs (Nginx, Apache)."""
        policy = cls(
            policy_name="Default Access Log Policy",
            log_type=LogType.ACCESS,
            preserve_order_logs=False,
        )

        # Access logs: preserve errors, sample successes
        policy.level_rules = [
            LevelRule(LogLevel.ERROR, PreservationPriority.CRITICAL,
                     ReductionAction.PRESERVE_INTACT, 1.0, False, "HTTP 5xx errors"),
            LevelRule(LogLevel.WARN, PreservationPriority.HIGH,
                     ReductionAction.PRESERVE_INTACT, 1.0, False, "HTTP 4xx errors"),
            LevelRule(LogLevel.INFO, PreservationPriority.MEDIUM,
                     ReductionAction.ARCHIVE, 0.05, True, "HTTP 2xx success - sample only"),
            LevelRule(LogLevel.DEBUG, PreservationPriority.WASTE,
                     ReductionAction.DELETE, 0.0, False, "Debug info discarded"),
        ]

        # Sample more during peak hours
        policy.time_rules = [
            TimeWindowRule(9, 22, PreservationPriority.MEDIUM, 0.2, "Active hours"),
            TimeWindowRule(22, 9, PreservationPriority.LOW, 0.05, "Night - minimal sampling"),
        ]

        return policy


class LogPolicyEngine:
    """
    Engine for applying policies to log blocks.
    """

    def __init__(self, policy: LogPolicy, audit_logger: AuditLogger = None):
        self.policy = policy
        self.audit_logger = audit_logger
        self.log_analyzer = LogAnalyzer()

    def evaluate_block(self, log_block: LogBlock, block_path: str = "") -> Dict:
        """
        Evaluate a log block against the policy.

        Args:
            log_block: Analysis result from LogAnalyzer
            block_path: Path to the log file

        Returns:
            Dict with evaluation results and recommended actions
        """
        priority = PreservationPriority.MEDIUM
        reasons = []
        actions_taken = []

        # Check level rules
        if log_block.error_count > 0:
            priority = PreservationPriority.CRITICAL
            reasons.append("errors_detected")
            actions_taken.append("preserve_all")
        elif log_block.warn_count > 0:
            if priority.value > PreservationPriority.HIGH.value:
                priority = PreservationPriority.HIGH
            reasons.append("warnings_detected")
        elif log_block.info_count > 0:
            if priority.value > PreservationPriority.MEDIUM.value:
                priority = PreservationPriority.MEDIUM

        # Check anomalies
        if log_block.error_burst:
            priority = PreservationPriority.CRITICAL
            reasons.append("error_burst")
            actions_taken.append("flag_error_burst")

        if log_block.circuit_breaker_open:
            priority = PreservationPriority.CRITICAL
            reasons.append("circuit_breaker_open")
            actions_taken.append("flag_circuit_breaker")

        if log_block.memory_warning:
            if priority.value < PreservationPriority.HIGH.value:
                priority = PreservationPriority.HIGH
            reasons.append("memory_warning")

        if log_block.timeout_pattern:
            if priority.value < PreservationPriority.HIGH.value:
                priority = PreservationPriority.HIGH
            reasons.append("timeout_pattern")

        # Check time rules
        block_hour = log_block.start_time.hour
        for rule in self.policy.time_rules:
            if rule.start_hour <= block_hour < rule.end_hour:
                if rule.preservation_priority.value > priority.value:
                    priority = rule.preservation_priority
                    actions_taken.append(f"time_rule:{rule.reason}")
                break

        # Business events override
        if self.policy.preserve_order_logs and log_block.unique_orders > 0:
            if priority.value < PreservationPriority.HIGH.value:
                priority = PreservationPriority.HIGH
            reasons.append(f"orders_detected:{log_block.unique_orders}")
            actions_taken.append("preserve_for_orders")

        if self.policy.preserve_transaction_logs and log_block.unique_sessions > 0:
            if priority.value < PreservationPriority.MEDIUM.value:
                priority = PreservationPriority.MEDIUM
            reasons.append(f"sessions_detected:{log_block.unique_sessions}")

        # Determine action based on priority
        if priority == PreservationPriority.CRITICAL:
            action = ReductionAction.PRESERVE_INTACT
            retention_days = self.policy.retain_days_critical
            sampling_rate = 1.0
        elif priority == PreservationPriority.HIGH:
            action = ReductionAction.PRESERVE_INTACT
            retention_days = self.policy.retain_days_high
            sampling_rate = 1.0
        elif priority == PreservationPriority.MEDIUM:
            action = ReductionAction.DOWNSAMPLE
            retention_days = self.policy.retain_days_medium
            sampling_rate = 0.3
        elif priority == PreservationPriority.LOW:
            action = ReductionAction.ARCHIVE
            retention_days = self.policy.retain_days_low
            sampling_rate = 0.1
        else:
            action = ReductionAction.DELETE
            retention_days = 0
            sampling_rate = 0.0

        # Calculate size estimate
        # Assume avg 500 bytes per line
        original_size = log_block.total_lines * 500
        if action == ReductionAction.PRESERVE_INTACT:
            new_size = original_size
        elif action == ReductionAction.DOWNSAMPLE:
            new_size = int(original_size * sampling_rate)
            if self.policy.compress_low_value:
                new_size = int(new_size * 0.3)  # Additional compression
        elif action == ReductionAction.ARCHIVE:
            new_size = int(original_size * sampling_rate * 0.2)  # Heavy compression
        else:
            new_size = 0

        result = {
            'block_id': log_block.block_id,
            'priority': priority.value,
            'action': action.value,
            'retention_days': retention_days,
            'original_size': original_size,
            'estimated_size': new_size,
            'savings_percent': (1 - new_size/original_size)*100 if original_size > 0 else 0,
            'sampling_rate': sampling_rate,
            'sampling_strategy': self.policy.sampling_strategy.value,
            'reasons': reasons,
            'actions_taken': actions_taken,
            'error_count': log_block.error_count,
            'warn_count': log_block.warn_count,
            'unique_orders': log_block.unique_orders,
            'unique_sessions': log_block.unique_sessions,
        }

        # Log to audit if available
        if self.audit_logger:
            record = AuditRecord(
                record_id=uuid.uuid4().hex,
                timestamp=datetime.utcnow().isoformat() + 'Z',
                data_id=hashlib.md5(block_path.encode()).hexdigest()[:16] if block_path else log_block.block_id,
                data_type='log',
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

    def evaluate_batch(self, log_blocks: List[LogBlock]) -> List[Dict]:
        """Evaluate multiple log blocks."""
        return [self.evaluate_block(block) for block in log_blocks]


# Demo usage
if __name__ == '__main__':
    from semantic.log_analyzer import LogAnalyzer

    print("Log Policy Engine Demo")
    print("="*50)

    # Create policy
    policy = LogPolicy.default_application()
    print(f"\nPolicy: {policy.policy_name}")
    print(f"  ID: {policy.policy_id}")
    print(f"  Level Rules: {len(policy.level_rules)}")
    print(f"  Time Rules: {len(policy.time_rules)}")

    # Create engine
    engine = LogPolicyEngine(policy)

    # Sample log data
    sample_logs = [
        "2024-01-15 10:30:45 INFO [main] Application started on port 8080",
        "2024-01-15 10:30:46 DEBUG [pool-1] Connection pool initialized: size=10",
        "2024-01-15 10:30:47 INFO [http-nio-8080] GET /api/health 200 5ms",
        "2024-01-15 10:30:48 WARN [service] Database slow query: 2500ms",
        "2024-01-15 10:30:49 ERROR [service] NullPointerException: Cannot invoke method on null",
        "2024-01-15 10:30:50 ERROR [service] NullPointerException: Cannot invoke method on null",
        "2024-01-15 10:30:51 ERROR [service] NullPointerException: Cannot invoke method on null",
        "2024-01-15 10:30:52 INFO [scheduler] Task BatchProcess completed in 5000ms",
        '2024-01-15 10:30:53 INFO [main] Order placed: orderId="ORD20240115001" userId="user_123"',
        "2024-01-15 10:30:54 DEBUG [pool-1] Releasing connection back to pool",
        "2024-01-15 10:30:55 TRACE [sql] SELECT * FROM users WHERE id = 123",
        "2024-01-15 10:30:56 INFO [http-nio-8080] POST /api/orders 201 150ms",
    ]

    # Analyze block
    analyzer = LogAnalyzer()
    block = analyzer.analyze_block(sample_logs, "demo_block")

    print(f"\nBlock Analysis:")
    print(f"  Total Lines: {block.total_lines}")
    print(f"  Errors: {block.error_count}, Warnings: {block.warn_count}")
    print(f"  Unique Orders: {block.unique_orders}")
    print(f"  Error Burst: {block.error_burst}")
    print(f"  Preserve Score: {block.preserve_recommendation:.2f}")

    # Evaluate against policy
    result = engine.evaluate_block(block, "/var/log/app.log")

    print(f"\nPolicy Evaluation:")
    print(f"  Priority: {result['priority']}")
    print(f"  Action: {result['action']}")
    print(f"  Retention: {result['retention_days']} days")
    print(f"  Sampling Rate: {result['sampling_rate']:.0%}")
    print(f"  Original Size: {result['original_size']:,} bytes")
    print(f"  Estimated Size: {result['estimated_size']:,} bytes")
    print(f"  Savings: {result['savings_percent']:.1f}%")
    print(f"  Reasons: {result['reasons']}")
