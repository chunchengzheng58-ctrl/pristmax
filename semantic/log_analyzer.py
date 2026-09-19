"""
Log Analyzer for Semantic Log Reduction

Provides semantic analysis of server logs:
- Log level analysis (ERROR/WARN/INFO/DEBUG)
- Anomaly detection (error bursts, circuit breakers)
- Keyword extraction (order IDs, user IDs, transaction IDs)
- Sampling strategies for INFO logs

Target: Reduce log storage by 50-80% while preserving diagnostic capability.
"""

import hashlib
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Tuple
from collections import Counter, defaultdict
import random


class LogLevel(Enum):
    """Log level classification"""
    ERROR = "error"     # Errors - must preserve
    WARN = "warn"       # Warnings - must preserve
    INFO = "info"       # Info - sample/compress
    DEBUG = "debug"     # Debug - discard by default
    TRACE = "trace"     # Trace - discard
    UNKNOWN = "unknown"


class LogType(Enum):
    """Application log type"""
    APPLICATION = "application"
    ACCESS = "access"          # Nginx/Apache access log
    ERROR = "error"            # System error log
    AUDIT = "audit"            # Security audit log
    METRICS = "metrics"        # Performance metrics
    BUSINESS = "business"      # Business event log
    UNKNOWN = "unknown"


@dataclass
class LogLine:
    """Analysis result for a single log line"""
    timestamp: datetime
    level: LogLevel
    raw_message: str

    # Parsed fields
    logger_name: str = ""
    thread_name: str = ""
    class_name: str = ""
    method_name: str = ""

    # Semantic markers
    has_exception: bool = False
    exception_type: str = ""
    exception_message: str = ""

    # Keywords found
    user_id: Optional[str] = None
    order_id: Optional[str] = None
    session_id: Optional[str] = None
    transaction_id: Optional[str] = None
    ip_address: Optional[str] = None

    # Request info
    request_path: str = ""
    http_method: str = ""
    response_code: int = 0
    response_time_ms: int = 0

    # Business context
    business_action: str = ""
    business_entity: str = ""

    # Quality metrics
    is_sampled: bool = False
    sample_rate: float = 1.0

    # Original position in file
    line_number: int = 0
    raw_line: str = ""


@dataclass
class LogBlock:
    """Analysis result for a block of log lines (e.g., one file, one hour)"""
    block_id: str
    start_time: datetime
    end_time: datetime

    # Counts
    total_lines: int = 0
    error_count: int = 0
    warn_count: int = 0
    info_count: int = 0
    debug_count: int = 0

    # Unique identifiers
    unique_users: int = 0
    unique_orders: int = 0
    unique_sessions: int = 0

    # Anomalies detected
    error_burst: bool = False          # Multiple errors in short time
    error_burst_count: int = 0
    circuit_breaker_open: bool = False
    memory_warning: bool = False
    timeout_pattern: bool = False

    # Patterns
    most_common_error: str = ""
    error_trend: str = "stable"        # increasing, decreasing, stable

    # Preservation recommendation
    preserve_recommendation: float = 0.0
    recommended_action: str = "compress"  # preserve, sample, compress, discard
    preserve_reason: str = ""

    # Sample strategy
    sample_rate: float = 1.0           # 1.0 = keep all, 0.1 = keep 10%
    sample_strategy: str = ""          # "head", "tail", "distributed", "error_focused"

    # Quality
    format_valid: float = 0.0          # Percentage of lines that parsed correctly


class KeywordExtractor:
    """Extracts semantic keywords from log messages"""

    # Common patterns for identifier extraction
    PATTERNS = {
        'user_id': [
            r'user[_\s]?id[:\s=]+["\']?([a-zA-Z0-9_\-]{8,32})',
            r'uid[:\s=]+["\']?([a-zA-Z0-9_\-]{8,32})',
            r'["\']userId["\'][,\s:]+["\']([a-zA-Z0-9_\-]{8,32})',
            r'X-User-ID[:\s]+(\S+)',
        ],
        'order_id': [
            r'order[_\s]?id[:\s=]+["\']?([a-zA-Z0-9_\-]{10,40})',
            r'orderNo[:\s=]+["\']?([a-zA-Z0-9_\-]{10,40})',
            r'transaction[_\s]?id[:\s=]+["\']?([a-zA-Z0-9_\-]{10,40})',
        ],
        'session_id': [
            r'session[_\s]?id[:\s=]+["\']?([a-zA-Z0-9_\-]{16,64})',
            r'sid[:\s=]+["\']?([a-zA-Z0-9_\-]{16,64})',
            r'["\']sessionId["\'][,\s:]+["\']([a-zA-Z0-9_\-]{16,64})',
        ],
        'transaction_id': [
            r'transaction[_\s]?id[:\s=]+["\']?([a-zA-Z0-9_\-]{20,64})',
            r'txn[_\s]?id[:\s=]+["\']?([a-zA-Z0-9_\-]{20,64})',
            r'request[_\s]?id[:\s=]+["\']?([a-zA-Z0-9_\-]{20,64})',
        ],
        'ip_address': [
            r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b',
            r'X-Forwarded-For[:\s]+(\S+)',
            r'client_ip[:\s=]+(\S+)',
        ],
    }

    # HTTP status code pattern
    HTTP_STATUS_PATTERN = re.compile(r'\s(\d{3})\s')
    HTTP_METHOD_PATTERN = re.compile(r'(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s')

    def __init__(self):
        self.compiled_patterns = {
            key: [re.compile(p, re.IGNORECASE) for p in patterns]
            for key, patterns in self.PATTERNS.items()
        }

    def extract(self, message: str) -> Dict[str, Optional[str]]:
        """Extract keywords from log message"""
        result = {}

        for field_name, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                match = pattern.search(message)
                if match:
                    result[field_name] = match.group(1)
                    break

        return result

    def extract_http_info(self, message: str) -> Tuple[Optional[str], Optional[int]]:
        """Extract HTTP method and status code"""
        method_match = self.HTTP_METHOD_PATTERN.search(message)
        status_match = self.HTTP_STATUS_PATTERN.search(message)

        method = method_match.group(1) if method_match else None
        status = int(status_match.group(1)) if status_match else None

        return method, status


class LogParser:
    """
    Parses various log formats into structured LogLine objects.
    """

    # Common timestamp patterns
    TIMESTAMP_PATTERNS = [
        # ISO format: 2024-01-15T10:30:45.123Z
        (r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?', '%Y-%m-%dT%H:%M:%S'),
        # Common format: 2024-01-15 10:30:45
        (r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', '%Y-%m-%d %H:%M:%S'),
        # Syslog format: Jan 15 10:30:45
        (r'[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}', '%b %d %H:%M:%S'),
        # Unix timestamp
        (r'^\d{10,13}$', 'unix'),
    ]

    # Log level patterns
    LEVEL_PATTERNS = {
        LogLevel.ERROR: re.compile(r'\b(ERROR|FATAL|CRITICAL|SEVERE)\b', re.IGNORECASE),
        LogLevel.WARN: re.compile(r'\b(WARN|WARNING)\b', re.IGNORECASE),
        LogLevel.INFO: re.compile(r'\b(INFO|INFORMATION|NOTICE)\b', re.IGNORECASE),
        LogLevel.DEBUG: re.compile(r'\b(DEBUG|DBG)\b', re.IGNORECASE),
        LogLevel.TRACE: re.compile(r'\b(TRACE|VERBOSE)\b', re.IGNORECASE),
    }

    # Exception patterns
    EXCEPTION_PATTERNS = [
        re.compile(r'([a-zA-Z_]\w*Exception)\s*:\s*(.+)', re.IGNORECASE),
        re.compile(r'at\s+([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)+)\s*\(([^)]+)\)', re.IGNORECASE),
    ]

    def __init__(self):
        self.timestamp_patterns = [
            (re.compile(pattern), fmt) for pattern, fmt in self.TIMESTAMP_PATTERNS
        ]
        self.keyword_extractor = KeywordExtractor()

    def parse_line(self, line: str, line_number: int = 0) -> LogLine:
        """
        Parse a single log line into structured format.

        Args:
            line: Raw log line
            line_number: Line number in source file

        Returns:
            LogLine object
        """
        line = line.strip()
        if not line:
            return LogLine(
                timestamp=datetime.now(),
                level=LogLevel.UNKNOWN,
                raw_message="",
                line_number=line_number,
                raw_line=line
            )

        # Parse timestamp
        timestamp = self._parse_timestamp(line)

        # Parse level
        level = self._parse_level(line)

        # Extract keywords
        keywords = self.keyword_extractor.extract(line)
        method, status = self.keyword_extractor.extract_http_info(line)

        # Check for exception
        has_exception, exc_type, exc_msg = self._parse_exception(line)

        return LogLine(
            timestamp=timestamp,
            level=level,
            raw_message=line,
            line_number=line_number,
            raw_line=line,
            user_id=keywords.get('user_id'),
            order_id=keywords.get('order_id'),
            session_id=keywords.get('session_id'),
            transaction_id=keywords.get('transaction_id'),
            ip_address=keywords.get('ip_address'),
            http_method=method or "",
            response_code=status or 0,
            has_exception=has_exception,
            exception_type=exc_type or "",
            exception_message=exc_msg or ""
        )

    def _parse_timestamp(self, line: str) -> datetime:
        """Extract timestamp from log line"""
        for pattern, fmt in self.timestamp_patterns:
            match = pattern.search(line)
            if match:
                ts_str = match.group(0)
                if fmt == 'unix':
                    try:
                        ts = int(ts_str)
                        if ts > 1e12:  # milliseconds
                            ts = ts / 1000
                        return datetime.fromtimestamp(ts)
                    except:
                        pass
                else:
                    try:
                        # Handle timezone
                        ts_str = ts_str.replace('Z', '+0000')
                        if '+' in ts_str or ts_str.endswith(timestamp := ''):
                            pass
                        return datetime.strptime(ts_str[:19], fmt)  # Simplified
                    except:
                        pass
        return datetime.now()

    def _parse_level(self, line: str) -> LogLevel:
        """Determine log level"""
        for level, pattern in self.LEVEL_PATTERNS.items():
            if pattern.search(line):
                return level
        return LogLevel.UNKNOWN

    def _parse_exception(self, line: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Check for exception in line"""
        for pattern in self.EXCEPTION_PATTERNS:
            match = pattern.search(line)
            if match:
                if 'Exception' in match.group(0):
                    return True, match.group(1), match.group(2) if len(match.groups()) > 1 else None
        return False, None, None


class AnomalyDetector:
    """
    Detects anomalous patterns in logs:
    - Error bursts
    - Circuit breaker patterns
    - Timeout patterns
    - Memory/resource warnings
    """

    def __init__(self, burst_threshold: int = 5, burst_window_seconds: int = 60):
        """
        Args:
            burst_threshold: Number of errors in window to trigger burst detection
            burst_window_seconds: Time window for burst detection
        """
        self.burst_threshold = burst_threshold
        self.burst_window_seconds = burst_window_seconds
        self._error_timestamps: List[datetime] = []
        self._error_messages: Counter = Counter()

    def add_error(self, timestamp: datetime, message: str):
        """Add an error occurrence"""
        self._error_timestamps.append(timestamp)

        # Extract error type
        exc_match = re.search(r'([A-Z]\w*Exception)', message)
        if exc_match:
            self._error_messages[exc_match.group(1)] += 1

        # Clean old timestamps
        cutoff = timestamp - timedelta(seconds=self.burst_window_seconds)
        self._error_timestamps = [t for t in self._error_timestamps if t > cutoff]

    def detect_burst(self) -> Tuple[bool, int]:
        """Detect if there's currently an error burst"""
        return len(self._error_timestamps) >= self.burst_threshold, len(self._error_timestamps)

    def get_most_common_error(self) -> str:
        """Get the most common error type"""
        if self._error_messages:
            return self._error_messages.most_common(1)[0][0]
        return ""

    def detect_patterns(self, lines: List[LogLine]) -> Dict[str, bool]:
        """Detect various anomaly patterns in log lines"""
        result = {
            'error_burst': False,
            'circuit_breaker_open': False,
            'memory_warning': False,
            'timeout_pattern': False,
        }

        # Reset for this block
        self._error_timestamps = []
        self._error_messages = Counter()

        recent_errors: List[LogLine] = []
        timeout_count = 0
        memory_keywords = ['outofmemory', 'oom', 'heap', 'memory', 'gc', 'garbage collection']

        for line in lines:
            if line.level == LogLevel.ERROR:
                self.add_error(line.timestamp, line.raw_message)
                recent_errors.append(line)

                if 'timeout' in line.raw_message.lower():
                    timeout_count += 1

                if any(kw in line.raw_message.lower() for kw in memory_keywords):
                    result['memory_warning'] = True

            # Check for circuit breaker patterns
            if 'circuit breaker' in line.raw_message.lower():
                result['circuit_breaker_open'] = True

        # Check for error burst
        result['error_burst'], burst_count = self.detect_burst()

        # Check for timeout pattern (multiple timeouts in short period)
        result['timeout_pattern'] = timeout_count >= 3

        return result


class LogAnalyzer:
    """
    Main log analysis engine.

    Combines parsing, anomaly detection, and sampling strategies
    to provide semantic log reduction.
    """

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.parser = LogParser()
        self.anomaly_detector = AnomalyDetector(
            burst_threshold=self.config.get('burst_threshold', 5),
            burst_window_seconds=self.config.get('burst_window_seconds', 60)
        )
        self._log_blocks: List[LogBlock] = []
        self._block_id_counter = 0

    def analyze_line(self, line: str, line_number: int = 0) -> LogLine:
        """
        Analyze a single log line.

        Args:
            line: Raw log line
            line_number: Line number in source

        Returns:
            LogLine with analysis
        """
        return self.parser.parse_line(line, line_number)

    def analyze_block(self, lines: List[str], block_id: str = "") -> LogBlock:
        """
        Analyze a block of log lines (e.g., file, hour).

        Args:
            lines: List of raw log lines
            block_id: Optional identifier for this block

        Returns:
            LogBlock with aggregated analysis
        """
        self._block_id_counter += 1
        if not block_id:
            block_id = f"block_{self._block_id_counter:06d}"

        if not lines:
            return LogBlock(
                block_id=block_id,
                start_time=datetime.now(),
                end_time=datetime.now(),
                recommended_action="discard",
                preserve_reason="Empty block"
            )

        # Parse all lines
        parsed_lines: List[LogLine] = []
        for i, line in enumerate(lines):
            parsed = self.parser.parse_line(line, i)
            parsed_lines.append(parsed)

        # Count by level
        level_counts = Counter(l.level for l in parsed_lines)

        # Extract unique identifiers
        unique_users = len(set(l.user_id for l in parsed_lines if l.user_id))
        unique_orders = len(set(l.order_id for l in parsed_lines if l.order_id))
        unique_sessions = len(set(l.session_id for l in parsed_lines if l.session_id))

        # Time range
        timestamps = [l.timestamp for l in parsed_lines]
        start_time = min(timestamps) if timestamps else datetime.now()
        end_time = max(timestamps) if timestamps else datetime.now()

        # Detect anomalies
        anomaly_result = self.anomaly_detector.detect_patterns(parsed_lines)

        # Determine preservation recommendation
        preserve_score = self._calculate_preserve_score(
            level_counts, anomaly_result, unique_orders, unique_users
        )

        # Determine action
        action, sample_rate = self._determine_action(
            preserve_score, level_counts, anomaly_result
        )

        # Calculate format validity
        valid_lines = sum(1 for l in parsed_lines if l.level != LogLevel.UNKNOWN)
        format_valid = valid_lines / len(parsed_lines) if parsed_lines else 0.0

        block = LogBlock(
            block_id=block_id,
            start_time=start_time,
            end_time=end_time,
            total_lines=len(parsed_lines),
            error_count=level_counts.get(LogLevel.ERROR, 0),
            warn_count=level_counts.get(LogLevel.WARN, 0),
            info_count=level_counts.get(LogLevel.INFO, 0),
            debug_count=level_counts.get(LogLevel.DEBUG, 0) + level_counts.get(LogLevel.TRACE, 0),
            unique_users=unique_users,
            unique_orders=unique_orders,
            unique_sessions=unique_sessions,
            error_burst=anomaly_result['error_burst'],
            error_burst_count=len([l for l in parsed_lines if l.level == LogLevel.ERROR][-5:]),
            circuit_breaker_open=anomaly_result['circuit_breaker_open'],
            memory_warning=anomaly_result['memory_warning'],
            timeout_pattern=anomaly_result['timeout_pattern'],
            most_common_error=self.anomaly_detector.get_most_common_error(),
            preserve_recommendation=preserve_score,
            recommended_action=action,
            sample_rate=sample_rate,
            sample_strategy="error_focused" if level_counts.get(LogLevel.ERROR, 0) > 0 else "head_tail",
            format_valid=format_valid
        )

        self._log_blocks.append(block)
        return block

    def _calculate_preserve_score(
        self,
        level_counts: Counter,
        anomaly_result: Dict[str, bool],
        unique_orders: int,
        unique_users: int
    ) -> float:
        """Calculate preservation score for a log block"""
        score = 0.0

        # Errors are critical
        error_count = level_counts.get(LogLevel.ERROR, 0)
        if error_count > 0:
            score += min(0.5, error_count * 0.1)  # Up to 0.5 for errors

        # Warnings add value
        warn_count = level_counts.get(LogLevel.WARN, 0)
        if warn_count > 0:
            score += min(0.2, warn_count * 0.02)  # Up to 0.2 for warnings

        # Anomalies increase importance
        if anomaly_result['error_burst']:
            score += 0.2
        if anomaly_result['circuit_breaker_open']:
            score += 0.15
        if anomaly_result['timeout_pattern']:
            score += 0.1
        if anomaly_result['memory_warning']:
            score += 0.15

        # Business transactions are valuable
        if unique_orders > 0:
            score += min(0.1, unique_orders * 0.01)

        # Users add context value
        if unique_users > 10:
            score += 0.05

        return min(1.0, score)

    def _determine_action(
        self,
        preserve_score: float,
        level_counts: Counter,
        anomaly_result: Dict[str, bool]
    ) -> Tuple[str, float]:
        """Determine recommended action and sample rate"""
        error_count = level_counts.get(LogLevel.ERROR, 0)
        warn_count = level_counts.get(LogLevel.WARN, 0)

        # Critical: preserve everything
        if error_count > 0 and anomaly_result['error_burst']:
            return "preserve", 1.0

        # High value: preserve with sampling
        if preserve_score >= 0.6:
            return "sample", 1.0

        # Medium value: compress
        if preserve_score >= 0.3 or warn_count > 5:
            return "compress", 0.5

        # Low value: aggressive sampling
        if preserve_score >= 0.1:
            return "sample", 0.1

        # Waste: discard
        return "discard", 0.0

    def apply_sampling(self, lines: List[LogLine], strategy: str, rate: float) -> List[LogLine]:
        """
        Apply sampling strategy to log lines.

        Args:
            lines: Parsed log lines
            strategy: Sampling strategy (head, tail, distributed, error_focused)
            rate: Sampling rate (0.0-1.0)

        Returns:
            Sampled log lines
        """
        if rate >= 1.0:
            return lines

        if rate <= 0.0:
            # Keep only errors
            return [l for l in lines if l.level == LogLevel.ERROR]

        # Always keep errors and warnings
        priority_lines = [l for l in lines if l.level in (LogLevel.ERROR, LogLevel.WARN)]

        # Sample remaining
        remaining = [l for l in lines if l.level not in (LogLevel.ERROR, LogLevel.WARN)]

        if strategy == "head":
            # Keep first portion
            sample_count = int(len(remaining) * rate)
            sampled = remaining[:sample_count]
        elif strategy == "tail":
            # Keep last portion
            sample_count = int(len(remaining) * rate)
            sampled = remaining[-sample_count:]
        elif strategy == "distributed":
            # Evenly distributed sampling
            step = int(1 / rate)
            sampled = remaining[::step]
        elif strategy == "error_focused":
            # More samples near errors
            sampled = self._error_focused_sample(remaining, rate)
        else:
            # Random sampling
            random.seed(42)  # Reproducible
            sampled = random.sample(remaining, int(len(remaining) * rate))

        # Combine and mark as sampled
        result = priority_lines + sampled
        for line in result:
            line.is_sampled = line.level not in (LogLevel.ERROR, LogLevel.WARN)
            line.sample_rate = rate

        # Sort by timestamp
        result.sort(key=lambda l: l.timestamp)

        return result

    def _error_focused_sample(self, lines: List[LogLine], rate: float) -> List[LogLine]:
        """Sample with more density near errors"""
        if not lines:
            return []

        # Find error positions
        error_indices = [i for i, l in enumerate(lines) if l.has_exception]

        if not error_indices:
            # No errors, use distributed sampling
            return lines[::int(1/rate)]

        # Sample more densely near errors
        sampled = []
        window = max(10, int(len(lines) * rate * 2))

        for err_idx in error_indices:
            start = max(0, err_idx - window // 2)
            end = min(len(lines), err_idx + window // 2)
            sampled.extend(lines[start:end])

        # Deduplicate while preserving order
        seen = set()
        result = []
        for line in sampled:
            line_hash = hash(line.raw_line)
            if line_hash not in seen:
                seen.add(line_hash)
                result.append(line)

        return result

    def get_stats(self) -> Dict[str, Any]:
        """Get analysis statistics"""
        if not self._log_blocks:
            return {}

        total_lines = sum(b.total_lines for b in self._log_blocks)
        total_errors = sum(b.error_count for b in self._log_blocks)

        return {
            'total_blocks': len(self._log_blocks),
            'total_lines': total_lines,
            'total_errors': total_errors,
            'avg_lines_per_block': total_lines / len(self._log_blocks) if self._log_blocks else 0,
            'error_rate': total_errors / total_lines if total_lines else 0,
        }


# Integration example
if __name__ == '__main__':
    print("Log Analyzer Module")
    print("="*50)

    analyzer = LogAnalyzer({'burst_threshold': 3})

    # Sample log lines
    sample_logs = [
        "2024-01-15 10:30:45 INFO [main] Application started successfully",
        "2024-01-15 10:30:46 DEBUG [pool-1] Connection acquired from pool",
        "2024-01-15 10:30:47 INFO [http-nio-8080] GET /api/users 200 15ms",
        "2024-01-15 10:30:48 WARN [service] Slow query detected: 2500ms",
        "2024-01-15 10:30:49 ERROR [service] DatabaseConnectionException: Connection refused",
        "2024-01-15 10:30:50 ERROR [service] DatabaseConnectionException: Connection refused",
        "2024-01-15 10:30:51 ERROR [service] DatabaseConnectionException: Connection refused",
        "2024-01-15 10:30:52 INFO [scheduler] Task completed successfully",
        '2024-01-15 10:30:53 INFO [main] User login: userId="abc123" sessionId="sess_xyz"',
        "2024-01-15 10:30:54 DEBUG [pool-1] Releasing connection back to pool",
    ]

    print(f"\nAnalyzing {len(sample_logs)} log lines...")

    # Analyze lines
    parsed_lines = [analyzer.analyze_line(line, i) for i, line in enumerate(sample_logs)]

    for line in parsed_lines:
        print(f"  [{line.level.value.upper():5}] {line.raw_message[:60]}...")
        if line.user_id:
            print(f"       -> user_id: {line.user_id}, session: {line.session_id}")
        if line.has_exception:
            print(f"       -> EXCEPTION: {line.exception_type}")

    # Analyze block
    block = analyzer.analyze_block(sample_logs, "test_block")

    print(f"\nBlock Analysis:")
    print(f"  Block ID: {block.block_id}")
    print(f"  Time Range: {block.start_time} - {block.end_time}")
    print(f"  Total Lines: {block.total_lines}")
    print(f"  Errors: {block.error_count}, Warnings: {block.warn_count}")
    print(f"  Error Burst: {block.error_burst}")
    print(f"  Preserve Score: {block.preserve_recommendation:.2f}")
    print(f"  Recommended Action: {block.recommended_action}")
    print(f"  Sample Rate: {block.sample_rate:.1%}")

    # Apply sampling
    sampled = analyzer.apply_sampling(parsed_lines, block.sample_strategy, block.sample_rate)
    print(f"\nAfter Sampling: {len(sampled)} / {len(parsed_lines)} lines retained")
