"""
Distributed Node Coordination

Provides:
- Node registration and heartbeat
- Leader election
- Distributed locking
- Task assignment and migration

Uses etcd as the coordination backend.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
import asyncio
import json
import uuid
import hashlib


class NodeState(Enum):
    """Node lifecycle states"""
    REGISTERING = "registering"
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    UNHEALTHY = "unhealthy"
    DEAD = "dead"


class NodeRole(Enum):
    """Node roles in the cluster"""
    SCAN_NODE = "scan_node"
    COORDINATOR = "coordinator"
    STORAGE_NODE = "storage_node"


@dataclass
class NodeInfo:
    """Information about a cluster node"""
    node_id: str
    role: str
    host: str
    port: int
    state: str = NodeState.REGISTERING.value
    capacity: Dict[str, int] = field(default_factory=dict)  # e.g., {"files_per_sec": 1000}
    current_load: int = 0
    registered_at: str = ""
    last_heartbeat: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.registered_at:
            self.registered_at = datetime.utcnow().isoformat() + "Z"
        if not self.last_heartbeat:
            self.last_heartbeat = self.registered_at

    def to_dict(self) -> Dict:
        return {
            "node_id": self.node_id,
            "role": self.role,
            "host": self.host,
            "port": self.port,
            "state": self.state,
            "capacity": self.capacity,
            "current_load": self.current_load,
            "registered_at": self.registered_at,
            "last_heartbeat": self.last_heartbeat,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "NodeInfo":
        return cls(**d)

    def touch(self) -> None:
        """Update heartbeat timestamp."""
        self.last_heartbeat = datetime.utcnow().isoformat() + "Z"

    def is_healthy(self, heartbeat_timeout: float = 15.0) -> bool:
        """Check if node is healthy based on last heartbeat."""
        last = datetime.fromisoformat(self.last_heartbeat.rstrip('Z'))
        now = datetime.utcnow()
        elapsed = (now - last).total_seconds()
        return elapsed < heartbeat_timeout


@dataclass
class TaskInfo:
    """Information about a distributed task"""
    task_id: str
    task_type: str  # "scan", "dedup", "archive", "restore"
    status: str     # "pending", "running", "completed", "failed", "cancelled"
    assigned_to: Optional[str] = None  # node_id
    progress: float = 0.0  # 0.0 to 1.0
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    checkpoint: Optional[Dict] = None  # Last checkpoint state
    error: Optional[str] = None
    result: Optional[Dict] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status,
            "assigned_to": self.assigned_to,
            "progress": self.progress,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "checkpoint": self.checkpoint,
            "error": self.error,
            "result": self.result
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "TaskInfo":
        return cls(**d)


class EtcdClient:
    """
    Simplified etcd client for coordination.

    In production, use etcd3 library with proper connection pooling.
    This is a mock implementation showing the interface.
    """

    def __init__(self, hosts: List[str], port: int = 2379):
        self.hosts = hosts
        self.port = port
        self._connected = False
        # In production: self._client = etcd3.client(hosts=hosts, port=port)

    async def connect(self) -> None:
        """Establish connection to etcd cluster."""
        # In production: await self._client.connect()
        self._connected = True

    async def close(self) -> None:
        """Close connection."""
        # In production: await self._client.close()
        self._connected = False

    async def put(self, key: str, value: str, lease: Optional[str] = None) -> None:
        """Put a key-value pair."""
        # In production: await self._client.put(key, value, lease=lease)
        pass

    async def get(self, key: str) -> Optional[str]:
        """Get a value by key."""
        # In production: return await self._client.get(key)
        return None

    async def delete(self, key: str) -> None:
        """Delete a key."""
        # In production: await self._client.delete(key)
        pass

    async def watch(self, key: str, callback: Callable) -> None:
        """Watch a key for changes."""
        # In production: await self._client.watch(key, callback)
        pass

    async def compare_and_swap(self, key: str, old_value: str, new_value: str) -> bool:
        """Atomic compare-and-swap."""
        # In production: return await self._client.compare_and_swap(key, old_value, new_value)
        return True

    async def acquire_lock(self, lock_name: str, timeout: float = 10.0) -> Optional[str]:
        """Acquire a distributed lock. Returns lock token if successful."""
        lock_key = f"/locks/{lock_name}"
        token = str(uuid.uuid4())
        # In production: return await self._client.acquire_lock(lock_key, token, timeout=timeout)
        return token

    async def release_lock(self, lock_name: str, token: str) -> None:
        """Release a distributed lock."""
        lock_key = f"/locks/{lock_name}"
        # In production: await self._client.release_lock(lock_key, token)
        pass


class NodeRegistry:
    """
    Manages node registration, heartbeat, and discovery.

    Uses etcd for distributed state with the following key structure:
    - /nodes/{node_id} - Node info JSON
    - /tasks/{task_id} - Task info JSON
    - /locks/{lock_name} - Distributed locks
    - /leader - Leader election
    """

    HEARTBEAT_INTERVAL = 5.0  # seconds
    HEARTBEAT_TIMEOUT = 15.0  # seconds (3 missed heartbeats = dead)
    CHECKPOINT_INTERVAL = 60.0  # seconds

    def __init__(self, etcd: EtcdClient):
        self.etcd = etcd
        self.local_node: Optional[NodeInfo] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

    async def register_node(self, node_id: str, role: str, host: str, port: int,
                           capacity: Optional[Dict] = None) -> NodeInfo:
        """
        Register this node with the cluster.

        Args:
            node_id: Unique identifier for this node
            role: Node role (scan_node, coordinator, storage_node)
            host: Host address
            port: Port number
            capacity: Optional capacity dict (e.g., {"files_per_sec": 1000})

        Returns:
            NodeInfo for the registered node
        """
        self.local_node = NodeInfo(
            node_id=node_id,
            role=role,
            host=host,
            port=port,
            state=NodeState.ACTIVE.value,
            capacity=capacity or {}
        )

        # Store in etcd
        key = f"/nodes/{node_id}"
        value = json.dumps(self.local_node.to_dict())
        await self.etcd.put(key, value)

        # Start heartbeat
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        return self.local_node

    async def unregister_node(self) -> None:
        """Unregister this node from the cluster."""
        self._running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self.local_node:
            key = f"/nodes/{self.local_node.node_id}"
            await self.etcd.delete(key)

    async def _heartbeat_loop(self) -> None:
        """Background task to send periodic heartbeats."""
        while self._running:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                if self.local_node and self._running:
                    self.local_node.touch()
                    key = f"/nodes/{self.local_node.node_id}"
                    value = json.dumps(self.local_node.to_dict())
                    await self.etcd.put(key, value)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Heartbeat error: {e}")

    async def get_node(self, node_id: str) -> Optional[NodeInfo]:
        """Get info about a specific node."""
        key = f"/nodes/{node_id}"
        value = await self.etcd.get(key)
        if value:
            return NodeInfo.from_dict(json.loads(value))
        return None

    async def list_nodes(self, role: Optional[str] = None) -> List[NodeInfo]:
        """
        List all nodes in the cluster.

        Args:
            role: Optional filter by role

        Returns:
            List of NodeInfo objects
        """
        # In production, use etcd prefix listing
        # For now, return empty list (would iterate /nodes/* keys)
        return []

    async def get_healthy_nodes(self, role: Optional[str] = None) -> List[NodeInfo]:
        """Get all healthy nodes, optionally filtered by role."""
        nodes = await self.list_nodes(role)
        return [n for n in nodes if n.is_healthy(self.HEARTBEAT_TIMEOUT)]

    async def update_node_state(self, state: NodeState) -> None:
        """Update the state of the local node."""
        if self.local_node:
            self.local_node.state = state.value
            key = f"/nodes/{self.local_node.node_id}"
            value = json.dumps(self.local_node.to_dict())
            await self.etcd.put(key, value)

    async def update_load(self, load: int) -> None:
        """Update the current load of the local node."""
        if self.local_node:
            self.local_node.current_load = load
            key = f"/nodes/{self.local_node.node_id}"
            value = json.dumps(self.local_node.to_dict())
            await self.etcd.put(key, value)


class TaskScheduler:
    """
    Distributed task scheduling with fault tolerance.

    Features:
    - Task assignment to nodes
    - Automatic reassignment on node failure
    - Checkpoint-based recovery
    - Task priority and cancellation
    """

    def __init__(self, etcd: EtcdClient, registry: NodeRegistry):
        self.etcd = etcd
        self.registry = registry
        self._task_callbacks: Dict[str, Callable] = {}

    async def submit_task(self, task_type: str, params: Dict,
                          priority: int = 0) -> TaskInfo:
        """
        Submit a new task for execution.

        Args:
            task_type: Type of task (scan, dedup, archive, restore)
            params: Task-specific parameters
            priority: Higher = more important (0-100)

        Returns:
            TaskInfo with task_id and initial status
        """
        task_id = str(uuid.uuid4())
        task = TaskInfo(
            task_id=task_id,
            task_type=task_type,
            status="pending"
        )

        # Store in etcd
        key = f"/tasks/{task_id}"
        value = json.dumps(task.to_dict())
        await self.etcd.put(key, value)

        # Try to assign immediately
        await self._assign_task(task)

        return task

    async def _assign_task(self, task: TaskInfo) -> bool:
        """Attempt to assign a task to an available node."""
        # Find a suitable node
        nodes = await self.registry.get_healthy_nodes(role="scan_node")
        if not nodes:
            return False

        # Pick node with lowest load
        nodes.sort(key=lambda n: n.current_load)
        selected = nodes[0]

        task.assigned_to = selected.node_id
        task.status = "running"
        task.started_at = datetime.utcnow().isoformat() + "Z"

        # Update in etcd
        key = f"/tasks/{task.task_id}"
        value = json.dumps(task.to_dict())
        await self.etcd.put(key, value)

        # Notify the node (in production, use gRPC or message queue)
        return True

    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """Get task info."""
        key = f"/tasks/{task_id}"
        value = await self.etcd.get(key)
        if value:
            return TaskInfo.from_dict(json.loads(value))
        return None

    async def update_task_progress(self, task_id: str, progress: float,
                                   checkpoint: Optional[Dict] = None) -> None:
        """Update task progress and checkpoint."""
        task = await self.get_task(task_id)
        if task:
            task.progress = progress
            if checkpoint:
                task.checkpoint = checkpoint
            key = f"/tasks/{task_id}"
            value = json.dumps(task.to_dict())
            await self.etcd.put(key, value)

    async def complete_task(self, task_id: str, result: Dict) -> None:
        """Mark a task as completed."""
        task = await self.get_task(task_id)
        if task:
            task.status = "completed"
            task.progress = 1.0
            task.completed_at = datetime.utcnow().isoformat() + "Z"
            task.result = result
            key = f"/tasks/{task_id}"
            value = json.dumps(task.to_dict())
            await self.etcd.put(key, value)

    async def fail_task(self, task_id: str, error: str) -> None:
        """Mark a task as failed."""
        task = await self.get_task(task_id)
        if task:
            task.status = "failed"
            task.error = error
            task.completed_at = datetime.utcnow().isoformat() + "Z"
            key = f"/tasks/{task_id}"
            value = json.dumps(task.to_dict())
            await self.etcd.put(key, value)

    async def cancel_task(self, task_id: str) -> None:
        """Cancel a task."""
        task = await self.get_task(task_id)
        if task and task.status in ("pending", "running"):
            task.status = "cancelled"
            task.completed_at = datetime.utcnow().isoformat() + "Z"
            key = f"/tasks/{task_id}"
            value = json.dumps(task.to_dict())
            await self.etcd.put(key, value)

    async def reassign_dead_node_tasks(self, dead_node_id: str) -> List[str]:
        """
        Reassign all tasks from a dead node.

        Returns:
            List of reassigned task IDs
        """
        # In production: query all tasks where assigned_to = dead_node_id
        # and status = running, then reassign
        return []

    def register_callback(self, task_type: str, callback: Callable) -> None:
        """Register a callback for task completion."""
        self._task_callbacks[task_type] = callback


class LeaderElection:
    """
    Leader election using etcd compare-and-swap.

    Uses the "let one leader lead" pattern with TTL-based leases.
    """

    LEADER_TTL = 30.0  # seconds

    def __init__(self, etcd: EtcdClient, cluster_id: str):
        self.etcd = etcd
        self.cluster_id = cluster_id
        self.leader_key = f"/leader/{cluster_id}"
        self._is_leader = False
        self._leader_task: Optional[asyncio.Task] = None

    async def campaign(self, node_id: str) -> bool:
        """
        Attempt to become leader.

        Args:
            node_id: ID of the node campaigning

        Returns:
            True if this node became leader
        """
        # Try to acquire leader lock
        token = await self.etcd.acquire_lock(self.leader_key, timeout=5.0)
        if token:
            self._is_leader = True
            self._leader_task = asyncio.create_task(self._keep_alive(node_id))
            return True
        return False

    async def _keep_alive(self, node_id: str) -> None:
        """Background task to renew leader lease."""
        while self._is_leader:
            try:
                await asyncio.sleep(self.LEADER_TTL / 2)
                if self._is_leader:
                    # Renew lease
                    pass
            except asyncio.CancelledError:
                break

    async def resign(self) -> None:
        """Resign from leadership."""
        self._is_leader = False
        if self._leader_task:
            self._leader_task.cancel()
            try:
                await self._leader_task
            except asyncio.CancelledError:
                pass

    async def get_leader(self) -> Optional[str]:
        """Get the current leader's node ID."""
        value = await self.etcd.get(self.leader_key)
        if value:
            data = json.loads(value)
            return data.get("node_id")
        return None

    @property
    def is_leader(self) -> bool:
        """Check if this node is the leader."""
        return self._is_leader
