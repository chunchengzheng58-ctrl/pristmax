"""
Distributed Locking

Provides distributed mutex locks and leader election using etcd.
Used for:
- Critical section protection
- Leader election
- Resource allocation
- Preventing split-brain in clusters
"""

import asyncio
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Callable
import hashlib


class LockStatus(Enum):
    """Status of a lock acquisition attempt"""
    ACQUIRED = "acquired"
    NOT_ACQUIRED = "not_acquired"
    TIMEOUT = "timeout"
    RELEASED = "released"


@dataclass
class Lock:
    """Represents a distributed lock"""
    name: str
    token: str  # Unique token identifying the lock holder
    holder: str  # Node ID that holds the lock
    acquired_at: float
    expires_at: float  # TTL for the lock
    ttl: int  # Time to live in seconds


class DistributedLock:
    """
    Distributed mutex lock implementation.

    Uses etcd compare-and-swap for atomic lock acquisition.
    Locks have TTL to prevent deadlocks if holder crashes.
    """

    def __init__(self, etcd_client, lock_name: str, ttl: int = 30):
        """
        Args:
            etcd_client: etcd client instance
            lock_name: Name of the lock
            ttl: Lock TTL in seconds (auto-release if not renewed)
        """
        self.etcd = etcd_client
        self.lock_name = lock_name
        self.ttl = ttl
        self.token = str(uuid.uuid4())
        self._acquired = False
        self._renewal_task: Optional[asyncio.Task] = None

    async def acquire(self, timeout: float = 10.0) -> LockStatus:
        """
        Attempt to acquire the lock.

        Args:
            timeout: Maximum time to wait for lock

        Returns:
            LockStatus indicating result
        """
        start_time = time.time()
        lock_key = f"/locks/{self.lock_name}"

        while time.time() - start_time < timeout:
            # Try to acquire using compare-and-swap
            # In production: etcd.compare_and_swap(lock_key, self.token, ttl=self.ttl)
            # For now, mock implementation
            acquired = await self._try_acquire(lock_key)

            if acquired:
                self._acquired = True
                # Start renewal task to keep lock alive
                self._renewal_task = asyncio.create_task(self._renew_loop())
                return LockStatus.ACQUIRED

            # Wait before retry
            await asyncio.sleep(0.5)

        return LockStatus.TIMEOUT

    async def _try_acquire(self, lock_key: str) -> bool:
        """Try to acquire the lock once."""
        # In production, use etcd's atomic compare-and-swap:
        # current = await self.etcd.get(lock_key)
        # if current is None or current.token == self.token:
        #     await self.etcd.put(lock_key, self.token, lease=self.ttl * 1000)
        #     return True
        return True  # Mock

    async def _renew_loop(self) -> None:
        """Periodically renew the lock TTL."""
        while self._acquired:
            try:
                await asyncio.sleep(self.ttl // 2)
                if self._acquired:
                    # Renew the lock
                    # In production: etcd.renew_lease(lock_key, self.token)
                    pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Lock renewal error: {e}")
                break

    async def release(self) -> LockStatus:
        """
        Release the lock.

        Returns:
            LockStatus indicating result
        """
        if not self._acquired:
            return LockStatus.RELEASED

        self._acquired = False

        if self._renewal_task:
            self._renewal_task.cancel()
            try:
                await self._renewal_task
            except asyncio.CancelledError:
                pass

        # In production, release via etcd delete with token verification
        # lock_key = f"/locks/{self.lock_name}"
        # await self.etcd.delete(lock_key, token=self.token)

        return LockStatus.RELEASED

    async def __aenter__(self) -> "DistributedLock":
        status = await self.acquire()
        if status != LockStatus.ACQUIRED:
            raise TimeoutError(f"Failed to acquire lock: {status}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.release()


class ReadWriteLock:
    """
    Distributed read-write lock.

    Allows multiple readers or a single writer.
    Useful for protecting shared resources like FPDB connections.
    """

    def __init__(self, etcd_client, lock_name: str, ttl: int = 30):
        self.etcd = etcd_client
        self.read_lock = DistributedLock(etcd_client, f"{lock_name}_read", ttl)
        self.write_lock = DistributedLock(etcd_client, f"{lock_name}_write", ttl)
        self._readers: int = 0
        self._readers_lock = asyncio.Lock()

    async def acquire_read(self) -> LockStatus:
        """Acquire a read lock."""
        async with self._readers_lock:
            if self._readers == 0:
                # First reader needs write lock to ensure no writer
                status = await self.write_lock.acquire(timeout=5.0)
                if status != LockStatus.ACQUIRED:
                    return status
            self._readers += 1
        return LockStatus.ACQUIRED

    async def release_read(self) -> None:
        """Release a read lock."""
        async with self._readers_lock:
            self._readers -= 1
            if self._readers == 0:
                await self.write_lock.release()

    async def acquire_write(self) -> LockStatus:
        """Acquire a write lock."""
        return await self.write_lock.acquire()

    async def release_write(self) -> None:
        """Release a write lock."""
        await self.write_lock.release()


class LeaderElection:
    """
    Leader election using distributed locks.

    Uses the "let one leader lead" pattern where multiple nodes
    compete for a leader lock, and the winner performs cluster duties.
    """

    def __init__(self, etcd_client, cluster_id: str, node_id: str,
                 lease_ttl: int = 30):
        """
        Args:
            etcd_client: etcd client instance
            cluster_id: Unique cluster identifier
            node_id: This node's identifier
            lease_ttl: Leader lease TTL in seconds
        """
        self.etcd = etcd_client
        self.cluster_id = cluster_id
        self.node_id = node_id
        self.lease_ttl = lease_ttl

        self.leader_lock = DistributedLock(
            etcd_client,
            f"leader_{cluster_id}",
            ttl=lease_ttl
        )

        self._is_leader = False
        self._leadership_task: Optional[asyncio.Task] = None
        self._callbacks: List[Callable[[bool], None]] = []

    async def try_become_leader(self) -> bool:
        """
        Attempt to become the leader.

        Returns:
            True if this node became leader, False otherwise
        """
        status = await self.leader_lock.acquire(timeout=1.0)
        if status == LockStatus.ACQUIRED:
            self._is_leader = True
            # Notify callbacks
            for callback in self._callbacks:
                try:
                    callback(True)
                except Exception as e:
                    print(f"Leadership callback error: {e}")
            return True

        return False

    async def resign_leadership(self) -> None:
        """Resign from leadership."""
        if self._is_leader:
            await self.leader_lock.release()
            self._is_leader = False
            for callback in self._callbacks:
                try:
                    callback(False)
                except Exception as e:
                    print(f"Leadership callback error: {e}")

    async def start(self) -> None:
        """Start the leader election process."""
        if self._leadership_task is None:
            self._leadership_task = asyncio.create_task(self._election_loop())

    async def stop(self) -> None:
        """Stop the leader election process."""
        if self._leadership_task:
            self._leadership_task.cancel()
            try:
                await self._leadership_task
            except asyncio.CancelledError:
                pass

        await self.resign_leadership()

    async def _election_loop(self) -> None:
        """Main election loop - try to become or remain leader."""
        while True:
            try:
                if not self._is_leader:
                    # Try to become leader
                    await self.try_become_leader()
                else:
                    # We are leader, wait and re-confirm
                    await asyncio.sleep(self.lease_ttl // 2)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Election loop error: {e}")
                await asyncio.sleep(1)

    def register_callback(self, callback: Callable[[bool], None]) -> None:
        """Register a callback for leadership changes."""
        self._callbacks.append(callback)

    @property
    def is_leader(self) -> bool:
        """Check if this node is the leader."""
        return self._is_leader


class ResourceAllocator:
    """
    Allocates scarce resources across the cluster.

    Uses distributed locks to ensure atomic allocation.
    """

    def __init__(self, etcd_client):
        self.etcd = etcd_client
        self._allocations: Dict[str, str] = {}  # resource -> node_id

    async def allocate(self, resource: str, node_id: str,
                       ttl: int = 300) -> bool:
        """
        Attempt to allocate a resource to a node.

        Args:
            resource: Resource identifier
            node_id: Node to allocate to
            ttl: Allocation TTL

        Returns:
            True if allocated successfully
        """
        lock = DistributedLock(self.etcd, f"resource_{resource}", ttl=ttl)
        status = await lock.acquire(timeout=5.0)

        if status == LockStatus.ACQUIRED:
            self._allocations[resource] = node_id
            await lock.release()
            return True

        return False

    async def release(self, resource: str, node_id: str) -> bool:
        """
        Release an allocation.

        Args:
            resource: Resource to release
            node_id: Node that holds the allocation

        Returns:
            True if released successfully
        """
        if self._allocations.get(resource) == node_id:
            del self._allocations[resource]
            return True
        return False

    async def get_allocation(self, resource: str) -> Optional[str]:
        """Get the node that holds a resource allocation."""
        return self._allocations.get(resource)


# Example usage
if __name__ == "__main__":
    print("Distributed Locking module")
    print("Usage: Create DistributedLock or LeaderElection with etcd client")
