"""
Kafka Integration for Distributed Deduplication

Provides Kafka producer and consumer for:
- Distributing fingerprint lookup requests
- Broadcasting dedup results
- Bloom filter synchronization
- Task coordination
"""

import asyncio
import json
import hashlib
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Callable, Dict, List, Optional, Any, Awaitable
from abc import ABC, abstractmethod


# Try to import aiokafka, provide mock if not available
try:
    from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
    from aiokafka.errors import KafkaError
    HAS_KAFKA = True
except ImportError:
    HAS_KAFKA = False
    KafkaError = Exception


class MessageType(Enum):
    """Kafka message types"""
    FINGERPRINT_LOOKUP = "fp_lookup"
    FINGERPRINT_RESULT = "fp_result"
    BLOOM_SYNC = "bloom_sync"
    TASK_ASSIGNMENT = "task"
    TASK_RESULT = "task_result"
    NODE_HEARTBEAT = "heartbeat"


@dataclass
class DedupMessage:
    """Base deduplication message"""
    type: MessageType
    node_id: str
    timestamp: float = field(default_factory=time.time)
    correlation_id: str = ""
    payload: Dict = field(default_factory=dict)

    def to_bytes(self) -> bytes:
        d = {
            "type": self.type.value,
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "payload": self.payload
        }
        return json.dumps(d).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> "DedupMessage":
        d = json.loads(data)
        return cls(
            type=MessageType(d["type"]),
            node_id=d["node_id"],
            timestamp=d.get("timestamp", 0),
            correlation_id=d.get("correlation_id", ""),
            payload=d.get("payload", {})
        )


@dataclass
class FingerprintLookupPayload:
    """Payload for fingerprint lookup request"""
    fingerprints: List[str]  # SHA-256 fingerprints to lookup
    request_id: str
    priority: int = 0  # Higher = more important


@dataclass
class FingerprintResultPayload:
    """Payload for fingerprint lookup result"""
    request_id: str
    results: List[Dict]  # List of {"fp": "...", "found": bool, "refcount": int}
    latency_ms: float


class KafkaDedupProducer:
    """
    Kafka producer for deduplication events.

    Publishes:
    - Fingerprint lookup requests
    - Bloom filter sync events
    - Task results
    """

    def __init__(self, bootstrap_servers: List[str], node_id: str):
        self.bootstrap_servers = bootstrap_servers
        self.node_id = node_id
        self._producer = None
        self._connected = False

    async def connect(self) -> None:
        """Connect to Kafka broker."""
        if not HAS_KAFKA:
            print("Warning: aiokafka not installed, running in mock mode")
            self._connected = True
            return

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            acks="all",  # Wait for all replicas
            enable_idempotence=True,  # Exactly-once semantics
            compression_type="lz4"  # Fast compression for messages
        )
        await self._producer.start()
        self._connected = True

    async def close(self) -> None:
        """Close the producer."""
        if self._producer:
            await self._producer.stop()
        self._connected = False

    async def send_lookup(self, topic: str, fingerprints: List[str],
                         request_id: str, priority: int = 0) -> None:
        """
        Send fingerprint lookup request.

        Args:
            topic: Kafka topic
            fingerprints: List of SHA-256 fingerprints
            request_id: Unique request ID for correlation
            priority: Request priority
        """
        payload = FingerprintLookupPayload(
            fingerprints=fingerprints,
            request_id=request_id,
            priority=priority
        )

        msg = DedupMessage(
            type=MessageType.FINGERPRINT_LOOKUP,
            node_id=self.node_id,
            correlation_id=request_id,
            payload=asdict(payload)
        )

        partition = self._get_partition(fingerprints[0] if fingerprints else "")

        await self._producer.send_and_wait(
            topic,
            msg.to_bytes(),
            partition=partition,
            headers=[("priority", str(priority).encode())]
        )

    async def send_result(self, topic: str, request_id: str,
                         results: List[Dict], latency_ms: float) -> None:
        """
        Send fingerprint lookup result.

        Args:
            topic: Kafka topic
            request_id: Original request ID
            results: List of fingerprint results
            latency_ms: Processing latency
        """
        payload = FingerprintResultPayload(
            request_id=request_id,
            results=results,
            latency_ms=latency_ms
        )

        msg = DedupMessage(
            type=MessageType.FINGERPRINT_RESULT,
            node_id=self.node_id,
            correlation_id=request_id,
            payload=asdict(payload)
        )

        await self._producer.send_and_wait(topic, msg.to_bytes())

    async def send_bloom_sync(self, topic: str, fingerprints: List[str]) -> None:
        """
        Send bloom filter sync event.

        Args:
            topic: Kafka topic
            fingerprints: Fingerprints to add to bloom filter
        """
        msg = DedupMessage(
            type=MessageType.BLOOM_SYNC,
            node_id=self.node_id,
            payload={"fingerprints": fingerprints}
        )

        await self._producer.send_and_wait(topic, msg.to_bytes())

    async def send_task_result(self, topic: str, task_id: str,
                              success: bool, result: Dict,
                              error: Optional[str] = None) -> None:
        """
        Send task completion result.

        Args:
            topic: Kafka topic
            task_id: Task ID
            success: Whether task succeeded
            result: Task result data
            error: Error message if failed
        """
        msg = DedupMessage(
            type=MessageType.TASK_RESULT,
            node_id=self.node_id,
            correlation_id=task_id,
            payload={
                "task_id": task_id,
                "success": success,
                "result": result,
                "error": error
            }
        )

        await self._producer.send_and_wait(topic, msg.to_bytes())

    def _get_partition(self, item: str) -> int:
        """Get partition for an item using consistent hashing."""
        if not item:
            return 0
        return abs(hash(item)) % 100


class KafkaDedupConsumer:
    """
    Kafka consumer for deduplication events.

    Features:
    - Consumer groups for parallel processing
    - Message batching
    - Handler registration
    """

    def __init__(self, bootstrap_servers: List[str], group_id: str,
                 topics: List[str], node_id: str):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.topics = topics
        self.node_id = node_id
        self._consumer = None
        self._running = False
        self._handlers: Dict[MessageType, Callable] = {}
        self._batch_size = 100
        self._batch_timeout = 1.0  # seconds

    async def connect(self) -> None:
        """Connect to Kafka broker."""
        if not HAS_KAFKA:
            print("Warning: aiokafka not installed, running in mock mode")
            return

        self._consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            enable_auto_commit=True,
            auto_offset_reset="earliest",
            max_poll_records=self._batch_size,
            session_timeout_ms=30000,
            heartbeat_interval_ms=10000
        )
        await self._consumer.start()
        self._running = True

    async def close(self) -> None:
        """Close the consumer."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()

    def register_handler(self, msg_type: MessageType,
                        handler: Callable[[DedupMessage], Awaitable[None]]) -> None:
        """
        Register a message handler.

        Args:
            msg_type: Type of message to handle
            handler: Async function to handle the message
        """
        self._handlers[msg_type] = handler

    async def consume(self) -> None:
        """Start consuming messages."""
        if not self._consumer:
            return

        try:
            async for message in self._consumer:
                if not self._running:
                    break

                try:
                    msg = DedupMessage.from_bytes(message.value)
                    handler = self._handlers.get(msg.type)

                    if handler:
                        await handler(msg)
                    else:
                        print(f"No handler for message type: {msg.type}")

                except Exception as e:
                    print(f"Error processing message: {e}")

        except asyncio.CancelledError:
            pass


class DedupPipeline:
    """
    End-to-end deduplication pipeline using Kafka.

    Integrates:
    - Scanner (produces fingerprints)
    - Lookup worker (consumes, looks up in FPDB, produces results)
    - Bloom filter sync
    """

    def __init__(self, kafka_servers: List[str], node_id: str,
                 fpdb_client, bloom_manager, lmdb_cache):
        self.kafka_servers = kafka_servers
        self.node_id = node_id
        self.fpdb = fpdb_client
        self.bloom = bloom_manager
        self.cache = lmdb_cache

        self.producer = KafkaDedupProducer(kafka_servers, node_id)
        self.consumer = KafkaDedupConsumer(
            kafka_servers,
            group_id=f"dedup-worker-{node_id}",
            topics=["dedup-requests", "dedup-results", "bloom-sync"],
            node_id=node_id
        )

        self._running = False

    async def start(self) -> None:
        """Start the pipeline."""
        await self.producer.connect()
        await self.consumer.connect()

        # Register message handlers
        self.consumer.register_handler(
            MessageType.FINGERPRINT_LOOKUP,
            self._handle_lookup
        )
        self.consumer.register_handler(
            MessageType.BLOOM_SYNC,
            self._handle_bloom_sync
        )

        self._running = True
        await self.consumer.consume()

    async def stop(self) -> None:
        """Stop the pipeline."""
        self._running = False
        await self.consumer.close()
        await self.producer.close()

    async def _handle_lookup(self, msg: DedupMessage) -> None:
        """Handle fingerprint lookup request."""
        payload = FingerprintLookupPayload(**msg.payload)
        request_id = payload.request_id
        fps = payload.fingerprints

        start_time = time.time()
        results = []

        for fp in fps:
            # 1. Check bloom filter (fast negative)
            if not self.bloom.may_contain(fp):
                results.append({"fp": fp, "found": False, "may_exist": False})
                continue

            # 2. Check local LMDB cache
            cached = self.cache.get(fp)
            if cached:
                results.append({
                    "fp": fp,
                    "found": True,
                    "refcount": cached.refcount,
                    "source": "cache"
                })
                continue

            # 3. Query global FPDB (would be async in production)
            result = await self.fpdb.lookup(fp)
            results.append({
                "fp": fp,
                "found": result.found,
                "refcount": result.record.refcount if result.record else 0
            })

        latency_ms = (time.time() - start_time) * 1000

        # Send result
        await self.producer.send_result(
            "dedup-results",
            request_id,
            results,
            latency_ms
        )

    async def _handle_bloom_sync(self, msg: DedupMessage) -> None:
        """Handle bloom filter sync message."""
        fps = msg.payload.get("fingerprints", [])
        for fp in fps:
            self.bloom.add(fp)

    async def process_file_chunks(self, file_path: str, chunks: List[str]) -> Dict:
        """
        Process a file's chunks through the dedup pipeline.

        Args:
            file_path: Path to the file
            chunks: List of chunk fingerprints

        Returns:
            Dedup results for the file
        """
        # 1. Batch lookup via Kafka
        request_id = f"{file_path}_{time.time()}"
        await self.producer.send_lookup("dedup-requests", chunks, request_id)

        # In production, would wait for result message with matching correlation_id
        # For now, process inline
        results = []
        for fp in chunks:
            # Check bloom first
            if not self.bloom.may_contain(fp):
                results.append({"fp": fp, "found": False, "is_unique": True})
                continue

            # Check cache
            cached = self.cache.get(fp)
            if cached:
                results.append({
                    "fp": fp,
                    "found": True,
                    "refcount": cached.refcount,
                    "is_unique": False
                })
                continue

            # Not found anywhere - it's unique
            self.bloom.add(fp)
            results.append({"fp": fp, "found": False, "is_unique": True})

        return {
            "file_path": file_path,
            "chunks": results,
            "unique_count": sum(1 for r in results if r.get("is_unique")),
            "duplicate_count": sum(1 for r in results if not r.get("is_unique"))
        }


# Example usage
if __name__ == "__main__":
    async def test_pipeline():
        # This would require actual Kafka and FPDB to run
        print("Kafka dedup pipeline module")
        print(f"Kafka available: {HAS_KAFKA}")

        # Test message serialization
        msg = DedupMessage(
            type=MessageType.FINGERPRINT_LOOKUP,
            node_id="test-node",
            payload={"fingerprints": ["abc123"] * 10}
        )
        data = msg.to_bytes()
        parsed = DedupMessage.from_bytes(data)
        print(f"Message type: {parsed.type.value}")
        print(f"Payload: {parsed.payload}")

    asyncio.run(test_pipeline())
