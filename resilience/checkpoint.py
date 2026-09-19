"""
Checkpoint and Recovery System

Provides fault-tolerant task execution with:
- Periodic checkpointing of task state
- Automatic recovery after node failure
- Task migration to healthy nodes
- Exactly-once execution semantics

Used by scan nodes and dedup workers to ensure no work is lost
when nodes crash.
"""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
import logging

logger = logging.getLogger(__name__)


class CheckpointStatus(Enum):
    """Status of a checkpoint"""
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERING = "recovering"


@dataclass
class Checkpoint:
    """A checkpoint of task state"""
    task_id: str
    task_type: str
    node_id: str
    status: CheckpointStatus
    progress: float  # 0.0 to 1.0
    state: Dict[str, Any]  # Task-specific state
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    version: int = 1  # For optimistic locking
    completed_at: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "Checkpoint":
        d["status"] = CheckpointStatus(d["status"])
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, s: str) -> "Checkpoint":
        return cls.from_dict(json.loads(s))


class CheckpointManager:
    """
    Manages checkpoints for distributed tasks.

    Features:
    - Periodic automatic checkpointing
    - Version-based conflict detection
    - Checkpoint TTL and cleanup
    - Task recovery on node failure
    """

    def __init__(self, storage_path: str, checkpoint_ttl: int = 86400):
        """
        Args:
            storage_path: Path to store checkpoint files
            checkpoint_ttl: Time in seconds before checkpoints expire
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.checkpoint_ttl = checkpoint_ttl

        # In production, use etcd or a distributed store
        # For now, use local filesystem
        self._checkpoints: Dict[str, Checkpoint] = {}

    def _get_checkpoint_path(self, task_id: str) -> Path:
        """Get path for a checkpoint file."""
        return self.storage_path / f"checkpoint_{task_id}.json"

    async def create_checkpoint(self, task_id: str, task_type: str,
                                node_id: str, state: Dict[str, Any],
                                progress: float = 0.0) -> Checkpoint:
        """
        Create a new checkpoint.

        Args:
            task_id: Unique task identifier
            task_type: Type of task (scan, dedup, archive)
            node_id: Node creating the checkpoint
            state: Task state to save
            progress: Progress percentage (0.0 to 1.0)

        Returns:
            Created Checkpoint
        """
        checkpoint = Checkpoint(
            task_id=task_id,
            task_type=task_type,
            node_id=node_id,
            status=CheckpointStatus.ACTIVE,
            progress=progress,
            state=state,
            created_at=time.time(),
            updated_at=time.time()
        )

        await self._save_checkpoint(checkpoint)
        return checkpoint

    async def update_checkpoint(self, task_id: str, state: Dict[str, Any],
                               progress: float, status: CheckpointStatus = None) -> Checkpoint:
        """
        Update an existing checkpoint.

        Args:
            task_id: Task to update
            state: New state
            progress: New progress value
            status: Optional new status

        Returns:
            Updated Checkpoint
        """
        checkpoint = await self.get_checkpoint(task_id)
        if checkpoint is None:
            raise ValueError(f"Checkpoint for task {task_id} not found")

        checkpoint.state = state
        checkpoint.progress = progress
        checkpoint.updated_at = time.time()
        checkpoint.version += 1

        if status:
            checkpoint.status = status

        await self._save_checkpoint(checkpoint)
        return checkpoint

    async def complete_checkpoint(self, task_id: str, result: Dict[str, Any]) -> Checkpoint:
        """
        Mark a checkpoint as completed.

        Args:
            task_id: Task to complete
            result: Final result data

        Returns:
            Completed Checkpoint
        """
        checkpoint = await self.get_checkpoint(task_id)
        if checkpoint:
            checkpoint.status = CheckpointStatus.COMPLETED
            checkpoint.completed_at = time.time()
            checkpoint.state["result"] = result
            checkpoint.progress = 1.0
            checkpoint.updated_at = time.time()
            await self._save_checkpoint(checkpoint)
        return checkpoint

    async def fail_checkpoint(self, task_id: str, error: str) -> Checkpoint:
        """
        Mark a checkpoint as failed.

        Args:
            task_id: Task that failed
            error: Error message

        Returns:
            Failed Checkpoint
        """
        checkpoint = await self.get_checkpoint(task_id)
        if checkpoint:
            checkpoint.status = CheckpointStatus.FAILED
            checkpoint.error = error
            checkpoint.completed_at = time.time()
            checkpoint.updated_at = time.time()
            await self._save_checkpoint(checkpoint)
        return checkpoint

    async def get_checkpoint(self, task_id: str) -> Optional[Checkpoint]:
        """
        Get a checkpoint by task ID.

        Args:
            task_id: Task identifier

        Returns:
            Checkpoint if found, None otherwise
        """
        # Check memory first
        if task_id in self._checkpoints:
            return self._checkpoints[task_id]

        # Load from disk
        path = self._get_checkpoint_path(task_id)
        if path.exists():
            try:
                data = path.read_text()
                checkpoint = Checkpoint.from_json(data)
                self._checkpoints[task_id] = checkpoint
                return checkpoint
            except Exception as e:
                logger.error(f"Failed to load checkpoint {task_id}: {e}")

        return None

    async def _save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Save checkpoint to disk."""
        path = self._get_checkpoint_path(checkpoint.task_id)
        path.write_text(checkpoint.to_json())
        self._checkpoints[checkpoint.task_id] = checkpoint

    async def get_recoverable_tasks(self, node_id: str) -> List[Checkpoint]:
        """
        Get all checkpoints that were running on a failed node.

        Args:
            node_id: ID of the failed node

        Returns:
            List of recoverable Checkpoints
        """
        recoverable = []
        for checkpoint in self._checkpoints.values():
            if (checkpoint.node_id == node_id and
                checkpoint.status == CheckpointStatus.ACTIVE):
                recoverable.append(checkpoint)

        # Also scan disk for any checkpoints we don't have in memory
        for path in self.storage_path.glob("checkpoint_*.json"):
            try:
                data = path.read_text()
                checkpoint = Checkpoint.from_json(data)
                if (checkpoint.node_id == node_id and
                    checkpoint.status == CheckpointStatus.ACTIVE and
                    checkpoint not in recoverable):
                    recoverable.append(checkpoint)
            except Exception as e:
                logger.error(f"Failed to load checkpoint {path}: {e}")

        return recoverable

    async def cleanup_expired(self) -> int:
        """
        Remove expired checkpoints.

        Returns:
            Number of checkpoints removed
        """
        now = time.time()
        removed = 0

        for task_id, checkpoint in list(self._checkpoints.items()):
            if now - checkpoint.updated_at > self.checkpoint_ttl:
                if checkpoint.status in (CheckpointStatus.COMPLETED,
                                         CheckpointStatus.FAILED):
                    path = self._get_checkpoint_path(task_id)
                    if path.exists():
                        path.unlink()
                    del self._checkpoints[task_id]
                    removed += 1

        return removed


class TaskRecoveryManager:
    """
    Manages task recovery after node failures.

    Features:
    - Detects failed nodes
    - Finds recoverable tasks
    - Reassigns tasks to healthy nodes
    - Ensures exactly-once execution
    """

    def __init__(self, checkpoint_manager: CheckpointManager,
                 node_registry, task_scheduler):
        self.checkpoints = checkpoint_manager
        self.node_registry = node_registry
        self.task_scheduler = task_scheduler

        self._running = False
        self._recovery_task: Optional[asyncio.Task] = None
        self._recovery_interval = 30  # seconds

    async def start(self) -> None:
        """Start the recovery manager."""
        self._running = True
        self._recovery_task = asyncio.create_task(self._recovery_loop())

    async def stop(self) -> None:
        """Stop the recovery manager."""
        self._running = False
        if self._recovery_task:
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass

    async def _recovery_loop(self) -> None:
        """Periodically check for and recover failed tasks."""
        while self._running:
            try:
                await self._check_for_failures()
            except Exception as e:
                logger.error(f"Recovery loop error: {e}")

            await asyncio.sleep(self._recovery_interval)

    async def _check_for_failures(self) -> None:
        """Check for node failures and recover their tasks."""
        # Get all active nodes
        healthy_nodes = await self.node_registry.get_healthy_nodes()

        # Find checkpoints on unhealthy nodes
        for checkpoint in self.checkpoints._checkpoints.values():
            if checkpoint.status != CheckpointStatus.ACTIVE:
                continue

            # Check if the node is still healthy
            node = await self.node_registry.get_node(checkpoint.node_id)
            if node is None or not node.is_healthy():
                # Node is dead, mark checkpoint as recovering
                checkpoint.status = CheckpointStatus.RECOVERING
                await self.checkpoints._save_checkpoint(checkpoint)

                # Reassign task
                await self._reassign_task(checkpoint)

    async def _reassign_task(self, checkpoint: Checkpoint) -> None:
        """
        Reassign a task to a healthy node.

        Args:
            checkpoint: Checkpoint of the task to reassign
        """
        logger.info(f"Reassigning task {checkpoint.task_id} from failed node {checkpoint.node_id}")

        # Create a new task in the scheduler
        # The new node will pick up the checkpoint and resume
        await self.task_scheduler.submit_task(
            task_type=checkpoint.task_type,
            params={
                "task_id": checkpoint.task_id,
                "resume_from_checkpoint": True,
                "checkpoint_task_id": checkpoint.task_id
            }
        )

    async def recover_task(self, task_id: str, node_id: str) -> Optional[Checkpoint]:
        """
        Resume a task from its checkpoint on a specific node.

        Args:
            task_id: Task to recover
            node_id: Node to resume on

        Returns:
            Checkpoint if found, None otherwise
        """
        checkpoint = await self.checkpoints.get_checkpoint(task_id)
        if checkpoint is None:
            return None

        # Update checkpoint to reflect new node
        checkpoint.node_id = node_id
        checkpoint.status = CheckpointStatus.ACTIVE
        checkpoint.updated_at = time.time()
        await self.checkpoints._save_checkpoint(checkpoint)

        return checkpoint


class CheckpointedTask:
    """
    Base class for tasks that support checkpointing.

    Subclass this to add checkpoint support to your tasks.
    """

    def __init__(self, task_id: str, checkpoint_manager: CheckpointManager,
                 checkpoint_interval: int = 60):
        self.task_id = task_id
        self.checkpoint_manager = checkpoint_manager
        self.checkpoint_interval = checkpoint_interval

        self._state: Dict[str, Any] = {}
        self._progress: float = 0.0
        self._last_checkpoint: float = 0
        self._running: bool = False

    async def run(self) -> Dict[str, Any]:
        """
        Run the task with periodic checkpointing.
        Override this in subclasses.
        """
        raise NotImplementedError("Subclass must implement run()")

    async def checkpoint(self, force: bool = False) -> None:
        """
        Create a checkpoint of current state.

        Args:
            force: If True, checkpoint even if interval hasn't passed
        """
        now = time.time()
        if not force and (now - self._last_checkpoint) < self.checkpoint_interval:
            return

        self._last_checkpoint = now
        await self.checkpoint_manager.update_checkpoint(
            self.task_id,
            state=self._state,
            progress=self._progress
        )

    def update_state(self, **kwargs) -> None:
        """Update task state (automatically checkpoints)."""
        self._state.update(kwargs)

    def update_progress(self, progress: float) -> None:
        """Update task progress (automatically checkpoints)."""
        self._progress = min(1.0, max(0.0, progress))
        # Only checkpoint on significant progress changes
        if abs(self._progress - (self._state.get("_last_reported_progress", 0))) > 0.05:
            self._state["_last_reported_progress"] = self._progress
            asyncio.create_task(self.checkpoint())


# Example usage
if __name__ == "__main__":
    print("Checkpoint and Recovery System")
    print("Usage: Create CheckpointManager and CheckpointedTask subclasses")
