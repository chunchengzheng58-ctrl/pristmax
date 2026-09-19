"""
Storage Tier Monitoring and Statistics

Provides real-time monitoring of storage tier usage,
including:
- Capacity and usage per tier
- Cost tracking
- Access patterns
- Migration progress
- Alerting on threshold violations
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
import threading

from tiering.storage_backend import StorageTier


@dataclass
class TierStats:
    """Statistics for a single tier"""
    tier: StorageTier
    total_bytes: int = 0
    used_bytes: int = 0
    available_bytes: int = 0
    blob_count: int = 0
    avg_blob_size: int = 0
    compression_ratio: float = 1.0
    total_access_count: int = 0
    last_access_time: Optional[float] = None
    migration_in_progress: int = 0

    @property
    def usage_percent(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return (self.used_bytes / self.total_bytes) * 100


@dataclass
class GlobalTierStats:
    """Global tier statistics across all tiers"""
    hot: TierStats = field(default_factory=lambda: TierStats(tier=StorageTier.HOT))
    warm: TierStats = field(default_factory=lambda: TierStats(tier=StorageTier.WARM))
    cold: TierStats = field(default_factory=lambda: TierStats(tier=StorageTier.COLD))

    @property
    def total_bytes(self) -> int:
        return self.hot.used_bytes + self.warm.used_bytes + self.cold.used_bytes

    @property
    def total_blob_count(self) -> int:
        return self.hot.blob_count + self.warm.blob_count + self.cold.blob_count

    def get_tier_stats(self, tier: StorageTier) -> TierStats:
        if tier == StorageTier.HOT:
            return self.hot
        elif tier == StorageTier.WARM:
            return self.warm
        elif tier == StorageTier.COLD:
            return self.cold
        raise ValueError(f"Unknown tier: {tier}")


@dataclass
class CostStats:
    """Cost tracking statistics"""
    monthly_cost_hot: float = 0.0
    monthly_cost_warm: float = 0.0
    monthly_cost_cold: float = 0.0
    monthly_cost_total: float = 0.0

    # Cost per GB per month (approximate)
    COST_PER_GB = {
        StorageTier.HOT: 0.03,
        StorageTier.WARM: 0.01,
        StorageTier.COLD: 0.001,
    }

    def calculate_from_stats(self, stats: GlobalTierStats) -> None:
        """Calculate costs from storage stats."""
        self.monthly_cost_hot = (
            stats.hot.used_bytes / (1024**3) * self.COST_PER_GB[StorageTier.HOT]
        )
        self.monthly_cost_warm = (
            stats.warm.used_bytes / (1024**3) * self.COST_PER_GB[StorageTier.WARM]
        )
        self.monthly_cost_cold = (
            stats.cold.used_bytes / (1024**3) * self.COST_PER_GB[StorageTier.COLD]
        )
        self.monthly_cost_total = (
            self.monthly_cost_hot + self.monthly_cost_warm + self.monthly_cost_cold
        )


@dataclass
class Alert:
    """Monitoring alert"""
    severity: str  # "info", "warning", "critical"
    message: str
    tier: Optional[StorageTier] = None
    timestamp: float = field(default_factory=time.time)
    resolved: bool = False


class TierMonitor:
    """
    Real-time monitoring for storage tiers.

    Features:
    - Periodic stats collection
    - Threshold-based alerting
    - Cost tracking
    - Access pattern analysis
    """

    def __init__(self, tier_manager, fpdb_client,
                 stats_interval: int = 60,  # seconds
                 alert_callback: Optional[Callable[[Alert], None]] = None):
        self.tier_manager = tier_manager
        self.fpdb = fpdb_client
        self.stats_interval = stats_interval
        self.alert_callback = alert_callback

        self._stats = GlobalTierStats()
        self._cost_stats = CostStats()
        self._alerts: List[Alert] = []
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

        # Thresholds for alerts
        self._thresholds = {
            "usage_percent_warning": 80.0,
            "usage_percent_critical": 95.0,
            "cost_increase_percent": 20.0,
        }

    async def start(self) -> None:
        """Start the monitoring loop."""
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the monitoring loop."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._collect_stats()
                await self._check_thresholds()
                await self._check_alerts()
            except Exception as e:
                print(f"Monitor error: {e}")

            await asyncio.sleep(self.stats_interval)

    async def _collect_stats(self) -> None:
        """Collect statistics from all tiers."""
        # In production, query FPDB for actual stats
        # For now, use placeholder logic

        for tier in StorageTier:
            stats = self._stats.get_tier_stats(tier)

            # Get blob count and total size from FPDB
            # records = await self.fpdb.get_by_tier(tier.value, limit=100000)
            # for record in records:
            #     stats.blob_count += 1
            #     stats.total_bytes += record.size
            #     stats.used_bytes += record.compressed_size

            # Calculate averages
            if stats.blob_count > 0:
                stats.avg_blob_size = stats.used_bytes // stats.blob_count

        # Update cost stats
        self._cost_stats.calculate_from_stats(self._stats)

    async def _check_thresholds(self) -> None:
        """Check if any thresholds are violated."""
        for tier in StorageTier:
            stats = self._stats.get_tier_stats(tier)

            # Check usage percent
            if stats.usage_percent >= self._thresholds["usage_percent_critical"]:
                self._create_alert(
                    "critical",
                    f"Tier {tier.value} usage at {stats.usage_percent:.1f}%",
                    tier
                )
            elif stats.usage_percent >= self._thresholds["usage_percent_warning"]:
                self._create_alert(
                    "warning",
                    f"Tier {tier.value} usage at {stats.usage_percent:.1f}%",
                    tier
                )

    def _create_alert(self, severity: str, message: str,
                     tier: Optional[StorageTier] = None) -> None:
        """Create and potentially emit an alert."""
        alert = Alert(severity=severity, message=message, tier=tier)
        self._alerts.append(alert)

        if self.alert_callback:
            self.alert_callback(alert)

    async def _check_alerts(self) -> None:
        """Check and auto-resolve alerts."""
        # Auto-resolve alerts that are no longer valid
        for alert in self._alerts:
            if alert.resolved:
                continue

            if alert.tier:
                stats = self._stats.get_tier_stats(alert.tier)
                if alert.severity == "critical":
                    if stats.usage_percent < self._thresholds["usage_percent_critical"]:
                        alert.resolved = True
                elif alert.severity == "warning":
                    if stats.usage_percent < self._thresholds["usage_percent_warning"]:
                        alert.resolved = True

    def get_stats(self) -> GlobalTierStats:
        """Get current statistics."""
        return self._stats

    def get_cost_stats(self) -> CostStats:
        """Get cost statistics."""
        return self._cost_stats

    def get_active_alerts(self) -> List[Alert]:
        """Get all unresolved alerts."""
        return [a for a in self._alerts if not a.resolved]

    def get_alert_summary(self) -> Dict[str, int]:
        """Get summary of alerts by severity."""
        active = self.get_active_alerts()
        return {
            "info": sum(1 for a in active if a.severity == "info"),
            "warning": sum(1 for a in active if a.severity == "warning"),
            "critical": sum(1 for a in active if a.severity == "critical"),
        }


class TierDashboard:
    """
    Dashboard data provider for tier statistics.

    Provides formatted data for web UI or API responses.
    """

    def __init__(self, monitor: TierMonitor):
        self.monitor = monitor

    def get_summary(self) -> Dict[str, Any]:
        """Get summary data for dashboard."""
        stats = self.monitor.get_stats()
        costs = self.monitor.get_cost_stats()
        alerts = self.monitor.get_alert_summary()

        return {
            "timestamp": time.time(),
            "storage": {
                "total_bytes": stats.total_bytes,
                "total_blob_count": stats.total_blob_count,
                "tiers": {
                    "hot": self._format_tier_stats(stats.hot),
                    "warm": self._format_tier_stats(stats.warm),
                    "cold": self._format_tier_stats(stats.cold),
                }
            },
            "costs": {
                "monthly_total": costs.monthly_cost_total,
                "by_tier": {
                    "hot": costs.monthly_cost_hot,
                    "warm": costs.monthly_cost_warm,
                    "cold": costs.monthly_cost_cold,
                },
                "annual_projection": costs.monthly_cost_total * 12,
            },
            "alerts": alerts,
        }

    def _format_tier_stats(self, stats: TierStats) -> Dict[str, Any]:
        """Format tier stats for dashboard."""
        return {
            "used_bytes": stats.used_bytes,
            "total_bytes": stats.total_bytes,
            "usage_percent": stats.usage_percent,
            "blob_count": stats.blob_count,
            "avg_blob_size": stats.avg_blob_size,
            "compression_ratio": stats.compression_ratio,
            "migration_in_progress": stats.migration_in_progress,
        }

    def get_migration_recommendations(self) -> Dict[str, Any]:
        """Get migration recommendations for cost optimization."""
        stats = self.monitor.get_stats()
        costs = self.monitor.get_cost_stats()

        recommendations = []

        # Analyze if moving data to colder tier would save money
        for tier in [StorageTier.HOT, StorageTier.WARM]:
            tier_stats = stats.get_tier_stats(tier)
            if tier_stats.blob_count == 0:
                continue

            next_tier = self._get_next_cold_tier(tier)
            if next_tier is None:
                continue

            # Estimate savings
            current_cost = (
                tier_stats.used_bytes / (1024**3) *
                costs.COST_PER_GB[tier]
            )
            new_cost = (
                tier_stats.used_bytes / (1024**3) *
                costs.COST_PER_GB[next_tier]
            )
            savings = current_cost - new_cost

            if savings > 0:
                recommendations.append({
                    "from_tier": tier.value,
                    "to_tier": next_tier.value,
                    "blob_count": tier_stats.blob_count,
                    "bytes": tier_stats.used_bytes,
                    "estimated_monthly_savings": savings,
                })

        return {
            "recommendations": recommendations,
            "total_potential_savings": sum(r["estimated_monthly_savings"] for r in recommendations),
        }

    def _get_next_cold_tier(self, tier: StorageTier) -> Optional[StorageTier]:
        """Get the next colder tier."""
        tier_order = [StorageTier.HOT, StorageTier.WARM, StorageTier.COLD]
        try:
            idx = tier_order.index(tier)
            if idx + 1 < len(tier_order):
                return tier_order[idx + 1]
        except ValueError:
            pass
        return None


# Example usage
if __name__ == "__main__":
    print("Tier monitoring module")
    print("Usage: Create TierMonitor with TierManager and FPDB client")
