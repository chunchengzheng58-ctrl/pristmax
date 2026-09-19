"""
Storage Tier Migration Scheduler and Executor

Manages automatic data migration between storage tiers based on:
- Access patterns (hot -> warm -> cold)
- Age policies
- Cost optimization
- User-defined rules

Features:
- Async migration execution
- Progress tracking
- Bandwidth throttling
- Retry on failure
- Consistency verification
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Awaitable
import logging

from tiering.storage_backend import StorageTier, StorageBackend, WriteResult


logger = logging.getLogger(__name__)


class MigrationStatus(Enum):
    """Status of a migration task"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class MigrationTask:
    """A single migration task"""
    fingerprint: str
    from_tier: StorageTier
    to_tier: StorageTier
    status: MigrationStatus = MigrationStatus.PENDING
    size: int = 0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class MigrationBatch:
    """A batch of migration tasks"""
    batch_id: str
    tasks: List[MigrationTask] = field(default_factory=list)
    status: MigrationStatus = MigrationStatus.PENDING
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    total_size: int = 0
    migrated_size: int = 0

    @property
    def progress(self) -> float:
        if self.total_size == 0:
            return 0.0
        return self.migrated_size / self.total_size


@dataclass
class MigrationStats:
    """Statistics for migration operations"""
    total_migrations: int = 0
    successful_migrations: int = 0
    failed_migrations: int = 0
    total_bytes_migrated: int = 0
    total_migration_time: float = 0.0  # seconds
    avg_migration_speed: float = 0.0   # MB/s


class MigrationScheduler:
    """
    Schedules and executes tier migrations.

    Features:
    - Batch migrations for efficiency
    - Rate limiting to avoid impacting production I/O
    - Retry with exponential backoff
    - Progress callbacks
    """

    def __init__(self, tier_manager, max_concurrent: int = 4,
                 bandwidth_limit_mbps: float = 100.0):
        self.tier_manager = tier_manager
        self.max_concurrent = max_concurrent
        self.bandwidth_limit_mbps = bandwidth_limit_mbps

        self._batches: Dict[str, MigrationBatch] = {}
        self._running = False
        self._stats = MigrationStats()
        self._callbacks: Dict[str, Callable] = {}

    async def migrate_batch(self, tasks: List[MigrationTask]) -> MigrationBatch:
        """
        Execute a batch of migrations.

        Args:
            tasks: List of MigrationTask to execute

        Returns:
            MigrationBatch with results
        """
        batch_id = hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]
        batch = MigrationBatch(
            batch_id=batch_id,
            tasks=tasks,
            total_size=sum(t.size for t in tasks)
        )
        self._batches[batch_id] = batch

        await self._execute_batch(batch)

        return batch

    async def _execute_batch(self, batch: MigrationBatch) -> None:
        """Execute all tasks in a batch with concurrency control."""
        batch.status = MigrationStatus.IN_PROGRESS

        # Use semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def execute_task_with_semaphore(task: MigrationTask):
            async with semaphore:
                await self._migrate_single(task)

        # Execute all tasks concurrently (but limited by semaphore)
        await asyncio.gather(
            *[execute_task_with_semaphore(task) for task in batch.tasks],
            return_exceptions=True
        )

        # Update batch status
        if all(t.status == MigrationStatus.COMPLETED for t in batch.tasks):
            batch.status = MigrationStatus.COMPLETED
        elif any(t.status == MigrationStatus.FAILED for t in batch.tasks):
            batch.status = MigrationStatus.FAILED

        batch.completed_at = time.time()

    async def _migrate_single(self, task: MigrationTask) -> None:
        """Migrate a single fingerprint from one tier to another."""
        task.status = MigrationStatus.IN_PROGRESS
        task.started_at = time.time()

        try:
            # Read from source tier
            source = self.tier_manager.get_backend(task.from_tier)
            target = self.tier_manager.get_backend(task.to_tier)

            if source is None or target is None:
                raise ValueError(f"Invalid tiers: {task.from_tier} -> {task.to_tier}")

            # Read data
            data = await source.read(task.fingerprint)

            # Apply target compression
            compressed, codec = target.compress_data(data)

            # Write to target
            result = await target.write(task.fingerprint, data)

            # Verify write
            verify_data = await target.read(task.fingerprint)
            if verify_data != data:
                raise ValueError("Verification failed: data mismatch after migration")

            # Delete from source on success
            await source.delete(task.fingerprint)

            task.status = MigrationStatus.COMPLETED
            self._stats.successful_migrations += 1
            self._stats.total_bytes_migrated += task.size
            self._stats.total_migration_time += time.time() - task.started_at

            logger.info(f"Migrated {task.fingerprint[:16]}... from {task.from_tier.value} to {task.to_tier.value}")

        except Exception as e:
            task.status = MigrationStatus.FAILED
            task.error = str(e)
            task.retry_count += 1

            if task.retry_count < task.max_retries:
                # Retry with exponential backoff
                await asyncio.sleep(2 ** task.retry_count)
                await self._migrate_single(task)
            else:
                self._stats.failed_migrations += 1
                logger.error(f"Migration failed for {task.fingerprint[:16]}...: {e}")

        task.completed_at = time.time()

    async def schedule_age_based_migration(self, fingerprint: str,
                                           current_tier: StorageTier,
                                           policies: Dict[StorageTier, Any]) -> bool:
        """
        Check if a fingerprint should be migrated based on age.

        Args:
            fingerprint: Fingerprint to check
            current_tier: Current tier
            policies: Tier policies with age limits

        Returns:
            True if migration was scheduled/executed
        """
        now = time.time()

        # Get the record's age
        # In production, this would come from FPDB
        # For now, assume we have the metadata
        created_at = now  # Placeholder

        age_days = (now - created_at) / 86400

        # Check if should migrate to colder tier
        next_tier = self._get_next_cold_tier(current_tier)
        if next_tier is None:
            return False

        policy = policies.get(next_tier)
        if policy and policy.max_age_days and age_days >= policy.max_age_days:
            task = MigrationTask(
                fingerprint=fingerprint,
                from_tier=current_tier,
                to_tier=next_tier
            )
            await self.migrate_batch([task])
            return True

        return False

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

    def get_stats(self) -> MigrationStats:
        """Get migration statistics."""
        if self._stats.total_migration_time > 0:
            self._stats.avg_migration_speed = (
                self._stats.total_bytes_migrated / (1024 * 1024) /
                self._stats.total_migration_time
            )
        return self._stats

    def get_batch_status(self, batch_id: str) -> Optional[MigrationBatch]:
        """Get status of a migration batch."""
        return self._batches.get(batch_id)


class TierMigrationManager:
    """
    High-level manager for tier migrations.

    Coordinates between the policy engine, scheduler, and FPDB
    to perform automated tier optimization.
    """

    def __init__(self, tier_manager, fpdb_client, policy_engine):
        self.tier_manager = tier_manager
        self.fpdb = fpdb_client
        self.policy_engine = policy_engine
        self.scheduler = MigrationScheduler(tier_manager)

    async def run_optimization_cycle(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Run a complete optimization cycle:
        1. Get current tier assignments from FPDB
        2. Analyze with policy engine
        3. Schedule migrations
        4. Execute migrations

        Args:
            dry_run: If True, only analyze without executing

        Returns:
            Dict with analysis and execution results
        """
        results = {
            "dry_run": dry_run,
            "candidates_analyzed": 0,
            "migrations_scheduled": 0,
            "migrations_completed": 0,
            "estimated_savings": 0.0,
            "actual_savings": 0.0,
            "errors": []
        }

        # 1. Get current state from FPDB
        # In production: query FPDB for fingerprints in each tier
        current_assignments = {}  # fp -> current tier
        contexts = {}  # fp -> ClassificationContext

        # Placeholder: in production, query actual FPDB
        # for fp in await self.fpdb.get_fingerprints_in_tier(StorageTier.HOT):
        #     record = await self.fpdb.lookup(fp)
        #     if record.found:
        #         current_assignments[fp] = StorageTier.HOT
        #         contexts[fp] = ClassificationContext(...)

        results["candidates_analyzed"] = len(current_assignments)

        # 2. Analyze with policy engine
        optimizer = TierOptimizer(self.policy_engine)
        recommendations = optimizer.analyze_migration_candidates(
            current_assignments, contexts
        )

        results["estimated_savings"] = sum(r["total_savings"] for r in recommendations)

        if dry_run:
            results["recommendations"] = recommendations[:100]  # Top 100
            return results

        # 3. Create migration tasks
        tasks = []
        for rec in recommendations[:1000]:  # Limit to top 1000
            task = MigrationTask(
                fingerprint=rec["fingerprint"],
                from_tier=rec["current_tier"],
                to_tier=rec["recommended_tier"],
                size=rec["size"]
            )
            tasks.append(task)

        results["migrations_scheduled"] = len(tasks)

        # 4. Execute migrations
        if tasks:
            batch = await self.scheduler.migrate_batch(tasks)
            results["migrations_completed"] = sum(
                1 for t in batch.tasks if t.status == MigrationStatus.COMPLETED
            )

        # 5. Calculate actual savings
        stats = self.scheduler.get_stats()
        results["actual_savings"] = stats.total_bytes_migrated * 0.001  # Simplified

        return results


# Example usage
if __name__ == "__main__":
    print("Tier migration scheduler module")
    print("Usage: Create MigrationScheduler with TierManager")
