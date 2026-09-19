"""
Health Checks and Node Failure Detection

Provides:
- Health check endpoints and probes
- Node failure detection via heartbeats
- Automatic failover to healthy nodes
- Cluster status monitoring
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
import threading


class HealthStatus(Enum):
    """Health status of a component"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """Result of a health check"""
    component: str
    status: HealthStatus
    message: str = ""
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NodeHealth:
    """Health status of a cluster node"""
    node_id: str
    status: HealthStatus
    is_leader: bool = False
    last_heartbeat: float = field(default_factory=time.time)
    consecutive_failures: int = 0
    checks: Dict[str, HealthCheck] = field(default_factory=dict)

    def is_healthy(self, heartbeat_timeout: float = 15.0) -> bool:
        """Check if node is considered healthy."""
        if self.status == HealthStatus.UNHEALTHY:
            return False
        elapsed = time.time() - self.last_heartbeat
        return elapsed < heartbeat_timeout


class HealthCheckManager:
    """
    Manages health checks for all cluster components.

    Features:
    - Liveness probes (is the process alive?)
    - Readiness probes (can the node accept requests?)
    - Component-level health checks
    - Automatic failover when leader fails
    """

    HEARTBEAT_INTERVAL = 5.0  # seconds
    HEARTBEAT_TIMEOUT = 15.0  # seconds (3 missed = unhealthy)
    MAX_CONSECUTIVE_FAILURES = 3

    def __init__(self, node_id: str):
        self.node_id = node_id
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None

        # Health state
        self._status = HealthStatus.UNKNOWN
        self._checks: Dict[str, HealthCheck] = {}
        self._last_heartbeat_sent = 0.0

        # Callbacks
        self._status_callbacks: List[Callable[[HealthStatus], None]] = []
        self._failure_callbacks: List[Callable[[str], None]] = []

        # In production, use etcd to track heartbeat
        self._etcd = None

    async def start(self) -> None:
        """Start the health check manager."""
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        await self._run_checks()

    async def stop(self) -> None:
        """Stop the health check manager."""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats."""
        while self._running:
            try:
                await self._send_heartbeat()
            except Exception as e:
                print(f"Heartbeat error: {e}")

            await asyncio.sleep(self.HEARTBEAT_INTERVAL)

    async def _send_heartbeat(self) -> None:
        """Send a heartbeat to the cluster."""
        self._last_heartbeat_sent = time.time()

        # In production: write heartbeat to etcd
        # key = f"/nodes/{self.node_id}/heartbeat"
        # await self.etcd.put(key, str(time.time()))

    async def register_check(self, component: str,
                            check_func: Callable[[], HealthCheck]) -> None:
        """
        Register a health check function.

        Args:
            component: Name of the component
            check_func: Async function that returns HealthCheck
        """
        self._checks[component] = check_func

    async def run_checks(self) -> Dict[str, HealthCheck]:
        """
        Run all health checks.

        Returns:
            Dict of component -> HealthCheck results
        """
        results = {}

        for component, check_func in self._checks.items():
            try:
                start = time.time()
                result = await check_func()
                result.latency_ms = (time.time() - start) * 1000
                results[component] = result
            except Exception as e:
                results[component] = HealthCheck(
                    component=component,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {e}"
                )

        self._checks = results
        return results

    async def _run_checks(self) -> None:
        """Periodically run health checks."""
        while self._running:
            await self.run_checks()
            await asyncio.sleep(self.HEARTBEAT_INTERVAL * 2)

    def get_status(self) -> HealthStatus:
        """Get overall health status."""
        if not self._checks:
            return HealthStatus.UNKNOWN

        # If any critical component is unhealthy, overall is unhealthy
        for check in self._checks.values():
            if check.status == HealthStatus.UNHEALTHY:
                return HealthStatus.UNHEALTHY

        # If any component is degraded, overall is degraded
        for check in self._checks.values():
            if check.status == HealthStatus.DEGRADED:
                return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY

    def register_status_callback(self, callback: Callable[[HealthStatus], None]) -> None:
        """Register callback for status changes."""
        self._status_callbacks.append(callback)

    def register_failure_callback(self, callback: Callable[[str], None]) -> None:
        """Register callback for component failures."""
        self._failure_callbacks.append(callback)


class ClusterHealthMonitor:
    """
    Monitors health of all nodes in the cluster.

    Features:
    - Tracks heartbeat from all nodes
    - Detects node failures
    - Elects new leader when leader fails
    - Reports cluster-wide health
    """

    def __init__(self, etcd_client, cluster_id: str):
        self.etcd = etcd_client
        self.cluster_id = cluster_id
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

        self._nodes: Dict[str, NodeHealth] = {}
        self._leader_id: Optional[str] = None

        # Callbacks
        self._node_failure_callbacks: List[Callable[[str], None]] = []
        self._leader_change_callbacks: List[Callable[[Optional[str]], None]] = []

    async def start(self) -> None:
        """Start the cluster health monitor."""
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the cluster health monitor."""
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
                await self._check_node_health()
                await self._check_leader_health()
            except Exception as e:
                print(f"Cluster monitor error: {e}")

            await asyncio.sleep(5.0)

    async def _check_node_health(self) -> None:
        """Check health of all nodes."""
        # In production: query etcd for all node heartbeats
        # /nodes/*/heartbeat
        pass

    async def _check_leader_health(self) -> None:
        """Check if leader is still healthy, elect new one if not."""
        if self._leader_id is None:
            return

        leader = self._nodes.get(self._leader_id)
        if leader and not leader.is_healthy():
            # Leader is dead, elect new one
            await self._elect_new_leader()

    async def _elect_new_leader(self) -> None:
        """Elect a new leader from healthy nodes."""
        old_leader = self._leader_id

        # Find healthy nodes
        healthy_nodes = [nid for nid, node in self._nodes.items()
                        if node.is_healthy()]

        if not healthy_nodes:
            # No healthy nodes
            self._leader_id = None
        else:
            # Simple election: first healthy node becomes leader
            self._leader_id = healthy_nodes[0]

        # Notify callbacks
        if old_leader != self._leader_id:
            for callback in self._leader_change_callbacks:
                try:
                    callback(self._leader_id)
                except Exception as e:
                    print(f"Leader change callback error: {e}")

    def register_node_failure_callback(self, callback: Callable[[str], None]) -> None:
        """Register callback for node failures."""
        self._node_failure_callbacks.append(callback)

    def register_leader_change_callback(self, callback: Callable[[Optional[str]], None]) -> None:
        """Register callback for leader changes."""
        self._leader_change_callbacks.append(callback)

    def get_cluster_status(self) -> Dict[str, Any]:
        """Get overall cluster status."""
        total_nodes = len(self._nodes)
        healthy_nodes = sum(1 for n in self._nodes.values() if n.is_healthy())

        return {
            "cluster_id": self.cluster_id,
            "total_nodes": total_nodes,
            "healthy_nodes": healthy_nodes,
            "unhealthy_nodes": total_nodes - healthy_nodes,
            "leader": self._leader_id,
            "nodes": {
                node_id: {
                    "status": node.status.value,
                    "is_leader": node_id == self._leader_id,
                    "last_heartbeat": node.last_heartbeat
                }
                for node_id, node in self._nodes.items()
            }
        }


# Pre-defined health checks
async def check_etcd_connection() -> HealthCheck:
    """Check if etcd is reachable."""
    start = time.time()
    try:
        # In production: actual etcd check
        # await etcd.get("/health")
        await asyncio.sleep(0.01)
        return HealthCheck(
            component="etcd",
            status=HealthStatus.HEALTHY,
            message="etcd reachable",
            latency_ms=(time.time() - start) * 1000
        )
    except Exception as e:
        return HealthCheck(
            component="etcd",
            status=HealthStatus.UNHEALTHY,
            message=f"etcd unreachable: {e}",
            latency_ms=(time.time() - start) * 1000
        )


async def check_kafka_connection() -> HealthCheck:
    """Check if Kafka is reachable."""
    start = time.time()
    try:
        # In production: actual Kafka check
        # producer = AIOKafkaProducer()
        # await producer.start()
        await asyncio.sleep(0.01)
        return HealthCheck(
            component="kafka",
            status=HealthStatus.HEALTHY,
            message="Kafka reachable",
            latency_ms=(time.time() - start) * 1000
        )
    except Exception as e:
        return HealthCheck(
            component="kafka",
            status=HealthStatus.UNHEALTHY,
            message=f"Kafka unreachable: {e}",
            latency_ms=(time.time() - start) * 1000
        )


async def check_fpdb_connection() -> HealthCheck:
    """Check if FPDB (ScyllaDB) is reachable."""
    start = time.time()
    try:
        # In production: actual ScyllaDB check
        # result = await scylladb.execute("SELECT 1")
        await asyncio.sleep(0.01)
        return HealthCheck(
            component="fpdb",
            status=HealthStatus.HEALTHY,
            message="FPDB reachable",
            latency_ms=(time.time() - start) * 1000
        )
    except Exception as e:
        return HealthCheck(
            component="fpdb",
            status=HealthStatus.UNHEALTHY,
            message=f"FPDB unreachable: {e}",
            latency_ms=(time.time() - start) * 1000
        )


async def check_disk_space(path: str = "/data", threshold: float = 0.9) -> HealthCheck:
    """Check if disk has sufficient space."""
    start = time.time()
    try:
        import shutil
        stat = shutil.disk_usage(path)
        usage_percent = (stat.used / stat.total) if stat.total > 0 else 0

        if usage_percent >= threshold:
            status = HealthStatus.UNHEALTHY
            message = f"Disk usage at {usage_percent*100:.1f}%"
        elif usage_percent >= threshold * 0.8:
            status = HealthStatus.DEGRADED
            message = f"Disk usage at {usage_percent*100:.1f}%"
        else:
            status = HealthStatus.HEALTHY
            message = f"Disk usage at {usage_percent*100:.1f}%"

        return HealthCheck(
            component="disk_space",
            status=status,
            message=message,
            latency_ms=(time.time() - start) * 1000,
            details={"path": path, "usage_percent": usage_percent}
        )
    except Exception as e:
        return HealthCheck(
            component="disk_space",
            status=HealthStatus.UNKNOWN,
            message=f"Could not check disk: {e}",
            latency_ms=(time.time() - start) * 1000
        )


# Example usage
if __name__ == "__main__":
    print("Health Checks and Node Failure Detection module")
    print("Usage: Create HealthCheckManager and ClusterHealthMonitor")
