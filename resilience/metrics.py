"""
Prometheus Metrics for Storage Atlas

Provides metrics collection and export for Prometheus monitoring:
- Storage tier metrics (capacity, usage, I/O)
- Deduplication metrics (ratio, cache hit rate)
- Node health metrics
- Kafka consumer lag
- System resource metrics
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
import threading


class MetricType(Enum):
    """Type of metric"""
    COUNTER = "counter"      # Monotonically increasing
    GAUGE = "gauge"          # Can go up or down
    HISTOGRAM = "histogram"  # Distribution of values
    SUMMARY = "summary"      # Aggregated quantiles


@dataclass
class Metric:
    """Base metric definition"""
    name: str
    description: str
    metric_type: MetricType
    labels: Dict[str, str] = field(default_factory=dict)
    value: float = 0.0


@dataclass
class Counter(Metric):
    """Counter metric - monotonically increasing"""
    def __init__(self, name: str, description: str, labels: Dict[str, str] = None):
        super().__init__(name, description, MetricType.COUNTER, labels or {})

    def inc(self, amount: float = 1.0) -> None:
        self.value += amount


@dataclass
class Gauge(Metric):
    """Gauge metric - can go up or down"""
    def __init__(self, name: str, description: str, labels: Dict[str, str] = None):
        super().__init__(name, description, MetricType.GAUGE, labels or {})

    def set(self, value: float) -> None:
        self.value = value

    def inc(self, amount: float = 1.0) -> None:
        self.value += amount

    def dec(self, amount: float = 1.0) -> None:
        self.value -= amount


@dataclass
class Histogram(Metric):
    """Histogram metric - buckets of values"""
    buckets: List[float] = field(default_factory=lambda: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
    count: int = 0
    sum: float = 0.0

    def __init__(self, name: str, description: str, buckets: List[float] = None):
        super().__init__(name, description, MetricType.HISTOGRAM)
        if buckets:
            self.buckets = buckets

    def observe(self, value: float) -> None:
        self.value = value
        self.count += 1
        self.sum += value


class MetricsRegistry:
    """
    Central metrics registry.

    Collects and exports metrics for Prometheus scraping.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._metrics: Dict[str, Metric] = {}
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._initialized = True

    def register_counter(self, name: str, description: str,
                        labels: Dict[str, str] = None) -> Counter:
        """Register a new counter metric."""
        key = self._make_key(name, labels)
        if key not in self._counters:
            self._counters[key] = Counter(name, description, labels)
            self._metrics[key] = self._counters[key]
        return self._counters[key]

    def register_gauge(self, name: str, description: str,
                      labels: Dict[str, str] = None) -> Gauge:
        """Register a new gauge metric."""
        key = self._make_key(name, labels)
        if key not in self._gauges:
            self._gauges[key] = Gauge(name, description, labels)
            self._metrics[key] = self._gauges[key]
        return self._gauges[key]

    def register_histogram(self, name: str, description: str,
                          buckets: List[float] = None,
                          labels: Dict[str, str] = None) -> Histogram:
        """Register a new histogram metric."""
        key = self._make_key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = Histogram(name, description, buckets)
            self._histograms[key].labels = labels or {}
            self._metrics[key] = self._histograms[key]
        return self._histograms[key]

    def get_counter(self, name: str, labels: Dict[str, str] = None) -> Optional[Counter]:
        """Get a counter by name and labels."""
        key = self._make_key(name, labels)
        return self._counters.get(key)

    def get_gauge(self, name: str, labels: Dict[str, str] = None) -> Optional[Gauge]:
        """Get a gauge by name and labels."""
        key = self._make_key(name, labels)
        return self._gauges.get(key)

    def _make_key(self, name: str, labels: Dict[str, str] = None) -> str:
        """Create a unique key for a metric."""
        if not labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def export_prometheus(self) -> str:
        """
        Export all metrics in Prometheus text format.

        Returns:
            Prometheus-formatted metrics string
        """
        lines = []

        for metric in self._metrics.values():
            # Skip if no value
            if hasattr(metric, 'count') and metric.count == 0 and metric.value == 0:
                continue

            # Comment with description
            lines.append(f"# HELP {metric.name} {metric.description}")
            lines.append(f"# TYPE {metric.name} {metric.metric_type.value}")

            if metric.metric_type == MetricType.COUNTER:
                lines.append(f"{metric.name} {metric.value}")
            elif metric.metric_type == MetricType.GAUGE:
                lines.append(f"{metric.name} {metric.value}")
            elif metric.metric_type == MetricType.HISTOGRAM:
                lines.append(f"{metric.name}_count {metric.count}")
                lines.append(f"{metric.name}_sum {metric.sum}")
                for bucket in metric.buckets:
                    # Count samples in this bucket
                    lines.append(f"{metric.name}_bucket{{le=\"{bucket}\"}} 0")

        return "\n".join(lines) + "\n"


# Pre-defined metrics for Storage Atlas
class StorageAtlasMetrics:
    """Storage Atlas standard metrics."""

    def __init__(self, registry: MetricsRegistry = None):
        self.registry = registry or MetricsRegistry()

        # Storage tier metrics
        self.tier_capacity = self.registry.register_gauge(
            "storage_tier_capacity_bytes",
            "Total capacity of storage tier in bytes",
        )
        self.tier_usage = self.registry.register_gauge(
            "storage_tier_usage_bytes",
            "Used storage in tier in bytes",
        )
        self.tier_blob_count = self.registry.register_gauge(
            "storage_tier_blob_count",
            "Number of blobs in tier",
        )

        # Deduplication metrics
        self.dedup_total_chunks = self.registry.register_counter(
            "dedup_total_chunks_processed",
            "Total number of chunks processed",
        )
        self.dedup_unique_chunks = self.registry.register_counter(
            "dedup_unique_chunks",
            "Number of unique chunks found",
        )
        self.dedup_ratio = self.registry.register_gauge(
            "dedup_ratio_current",
            "Current deduplication ratio",
        )
        self.cache_hits = self.registry.register_counter(
            "dedup_cache_hits_total",
            "Total cache hits",
        )
        self.cache_misses = self.registry.register_counter(
            "dedup_cache_misses_total",
            "Total cache misses",
        )
        self.bloom_hits = self.registry.register_counter(
            "dedup_bloom_hits_total",
            "Total bloom filter hits",
        )
        self.bloom_misses = self.registry.register_counter(
            "dedup_bloom_misses_total",
            "Total bloom filter misses",
        )

        # Scan metrics
        self.scan_files_total = self.registry.register_counter(
            "scan_files_total",
            "Total files scanned",
        )
        self.scan_bytes_total = self.registry.register_counter(
            "scan_bytes_total",
            "Total bytes scanned",
        )
        self.scan_duration_seconds = self.registry.register_histogram(
            "scan_duration_seconds",
            "Time taken to scan",
        )

        # Migration metrics
        self.migrations_total = self.registry.register_counter(
            "tier_migrations_total",
            "Total tier migrations completed",
        )
        self.migrations_failed = self.registry.register_counter(
            "tier_migrations_failed_total",
            "Total tier migrations failed",
        )
        self.migration_bytes = self.registry.register_counter(
            "tier_migration_bytes_total",
            "Total bytes migrated",
        )

        # Node health metrics
        self.node_status = self.registry.register_gauge(
            "node_status",
            "Node status (1=healthy, 0=unhealthy)",
        )
        self.node_tasks_active = self.registry.register_gauge(
            "node_tasks_active",
            "Number of active tasks on node",
        )

        # Kafka metrics
        self.kafka_consumer_lag = self.registry.register_gauge(
            "kafka_consumer_lag",
            "Consumer lag in messages",
        )
        self.kafka_messages_processed = self.registry.register_counter(
            "kafka_messages_processed_total",
            "Total Kafka messages processed",
        )

        # Cost metrics
        self.cost_monthly_estimate = self.registry.register_gauge(
            "cost_monthly_estimate_dollars",
            "Estimated monthly storage cost in dollars",
        )


class MetricsCollector:
    """
    Background metrics collector.

    Periodically collects system metrics and updates gauges.
    """

    def __init__(self, interval: int = 15):
        self.interval = interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._callbacks: List[Callable[[], None]] = []

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to collect custom metrics."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Start the collector."""
        self._running = True
        self._task = asyncio.create_task(self._collect_loop())

    async def stop(self) -> None:
        """Stop the collector."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _collect_loop(self) -> None:
        """Main collection loop."""
        while self._running:
            try:
                # Collect system metrics
                self._collect_system_metrics()

                # Call custom callbacks
                for callback in self._callbacks:
                    try:
                        callback()
                    except Exception as e:
                        print(f"Metrics callback error: {e}")

            except Exception as e:
                print(f"Metrics collection error: {e}")

            await asyncio.sleep(self.interval)

    def _collect_system_metrics(self) -> None:
        """Collect basic system metrics."""
        try:
            import psutil

            # CPU and memory
            memory = psutil.virtual_memory()
            memory_used = self.registry.get_gauge("system_memory_used_bytes")
            if memory_used:
                memory_used.set(memory.used)

            cpu_percent = self.registry.get_gauge("system_cpu_percent")
            if cpu_percent:
                cpu_percent.set(psutil.cpu_percent())

        except ImportError:
            # psutil not installed, skip system metrics
            pass


# Global metrics instance
metrics = StorageAtlasMetrics()


# Example usage
if __name__ == "__main__":
    # Create some metrics
    registry = MetricsRegistry()
    storage_metrics = StorageAtlasMetrics(registry)

    # Update some values
    storage_metrics.scan_files_total.inc(100)
    storage_metrics.dedup_ratio.set(5.71)
    storage_metrics.tier_usage.set(1024 * 1024 * 1024)  # 1GB

    # Export for Prometheus
    output = registry.export_prometheus()
    print(output)
