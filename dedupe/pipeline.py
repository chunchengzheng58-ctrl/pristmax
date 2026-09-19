"""
Deduplication Pipeline

End-to-end deduplication pipeline that combines:
- Content-Defined Chunking (CDC)
- Bloom filter for fast negative lookups
- Local LMDB cache
- Global FPDB lookup via Kafka

This is the core deduplication engine for PB-scale storage optimization.
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, AsyncIterator, Callable
from enum import Enum

from cdc.chunker import rabin_chunks, Chunk, DedupChunk, DeduplicatingChunker
from fpdb.fingerprint import FingerprintRecord, compute_fingerprint, DedupResult
from dedupe.lmdb_cache import LMDBFingerprintCache, CacheEntry
from dedupe.bloom_sync import BloomFilterManager


class DedupStrategy(Enum):
    """Deduplication strategy"""
    FULL_FILE = "full_file"      # Entire file as single chunk
    FIXED_BLOCK = "fixed_block"  # Fixed-size blocks
    CDC = "cdc"                  # Content-defined chunking


@dataclass
class ChunkRef:
    """Reference to a chunk with deduplication info"""
    fingerprint: str
    offset: int
    size: int
    is_unique: bool
    refcount: int = 0
    compressed_size: Optional[int] = None


@dataclass
class FileDedupResult:
    """Result of deduplicating a single file"""
    file_path: str
    file_size: int
    chunks: List[ChunkRef]
    unique_chunks: int
    duplicate_chunks: int
    original_bytes: int  # Sum of all chunk sizes
    deduplicated_bytes: int  # Unique chunk sizes only
    dedup_ratio: float
    duration_ms: float


@dataclass
class DedupStats:
    """Overall deduplication statistics"""
    total_files: int = 0
    total_chunks: int = 0
    unique_chunks: int = 0
    duplicate_chunks: int = 0
    total_bytes: int = 0
    deduplicated_bytes: int = 0
    dedup_ratio: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    bloom_hits: int = 0
    bloom_misses: int = 0
    fpdb_queries: int = 0
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "total_files": self.total_files,
            "total_chunks": self.total_chunks,
            "unique_chunks": self.unique_chunks,
            "duplicate_chunks": self.duplicate_chunks,
            "total_bytes": self.total_bytes,
            "deduplicated_bytes": self.deduplicated_bytes,
            "dedup_ratio": self.dedup_ratio,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "bloom_hits": self.bloom_hits,
            "bloom_misses": self.bloom_misses,
            "fpdb_queries": self.fpdb_queries,
            "duration_seconds": self.duration_seconds
        }


class DedupPipeline:
    """
    End-to-end deduplication pipeline.

    Workflow:
    1. Read file data
    2. Apply CDC to generate chunks
    3. For each chunk:
       a. Check bloom filter (fast negative)
       b. Check local LMDB cache
       c. Query global FPDB if needed
    4. Return deduplication results
    """

    def __init__(self, lmdb_path: str, node_id: str,
                 fpdb_client: Optional[Any] = None):
        """
        Initialize the deduplication pipeline.

        Args:
            lmdb_path: Path to LMDB cache directory
            node_id: Unique identifier for this node
            fpdb_client: Optional FPDB client for distributed lookups
        """
        self.node_id = node_id
        self.fpdb = fpdb_client
        self.cache = LMDBFingerprintCache(lmdb_path)
        self.bloom = BloomFilterManager(node_id)
        self._stats = DedupStats()
        self._running = False

    def close(self):
        """Close all resources."""
        self.cache.close()

    def chunk_file(self, data: bytes) -> List[Chunk]:
        """
        Chunk file data using CDC.

        Args:
            data: Raw file bytes

        Returns:
            List of Chunk objects
        """
        return list(rabin_chunks(data))

    def check_chunk(self, fingerprint: str) -> tuple[bool, int]:
        """
        Check if a chunk is unique or duplicate.

        Args:
            fingerprint: SHA-256 fingerprint of chunk

        Returns:
            (is_unique, refcount) tuple
        """
        # 1. Check bloom filter (fast negative)
        if not self.bloom.may_contain(fingerprint):
            self._stats.bloom_misses += 1
            # Bloom says definitely not in DB - it's unique
            self.bloom.add(fingerprint)
            return True, 0

        self._stats.bloom_hits += 1

        # 2. Check local LMDB cache
        cached = self.cache.get(fingerprint)
        if cached:
            self._stats.cache_hits += 1
            # Update refcount in cache
            new_refcount = self.cache.update_refcount(fingerprint, 1)
            return False, new_refcount or cached.refcount

        self._stats.cache_misses += 1

        # 3. Query global FPDB if available
        if self.fpdb:
            self._stats.fpdb_queries += 1
            result = asyncio.run(self.fpdb.lookup(fingerprint))
            if result.found and result.record:
                # Store in local cache for future lookups
                self.cache.put(fingerprint, CacheEntry(
                    fp=fingerprint,
                    size=result.record.size,
                    refcount=result.record.refcount,
                    compressed_size=result.record.compressed_size,
                    compression=result.record.compression,
                    tier=result.record.tier,
                    created_at=time.time(),
                    last_accessed=time.time(),
                    access_count=1
                ))
                return False, result.record.refcount

        # Not found anywhere - it's unique, store in local cache
        self.bloom.add(fingerprint)
        self.cache.put(fingerprint, CacheEntry(
            fp=fingerprint,
            size=0,  # Unknown at this point
            refcount=1,
            compressed_size=0,
            compression="none",
            tier="warm",
            created_at=time.time(),
            last_accessed=time.time(),
            access_count=1
        ))
        return True, 1

    def deduplicate_file(self, file_path: str, data: bytes) -> FileDedupResult:
        """
        Deduplicate a single file.

        Args:
            file_path: Path to the file
            data: Raw file bytes

        Returns:
            FileDedupResult with deduplication details
        """
        start_time = time.time()
        chunks = self.chunk_file(data)

        chunk_refs = []
        unique_count = 0
        duplicate_count = 0
        original_bytes = 0
        deduplicated_bytes = 0

        for chunk in chunks:
            original_bytes += chunk.size
            is_unique, refcount = self.check_chunk(chunk.fingerprint)

            if is_unique:
                unique_count += 1
                deduplicated_bytes += chunk.size
            else:
                duplicate_count += 1

            chunk_refs.append(ChunkRef(
                fingerprint=chunk.fingerprint,
                offset=chunk.offset,
                size=chunk.size,
                is_unique=is_unique,
                refcount=refcount
            ))

        duration_ms = (time.time() - start_time) * 1000

        # Update stats
        self._stats.total_files += 1
        self._stats.total_chunks += len(chunks)
        self._stats.unique_chunks += unique_count
        self._stats.duplicate_chunks += duplicate_count
        self._stats.total_bytes += original_bytes
        self._stats.deduplicated_bytes += deduplicated_bytes

        dedup_ratio = len(chunks) / unique_count if unique_count > 0 else 1.0

        return FileDedupResult(
            file_path=file_path,
            file_size=len(data),
            chunks=chunk_refs,
            unique_chunks=unique_count,
            duplicate_chunks=duplicate_count,
            original_bytes=original_bytes,
            deduplicated_bytes=deduplicated_bytes,
            dedup_ratio=dedup_ratio,
            duration_ms=duration_ms
        )

    def get_stats(self) -> DedupStats:
        """Get current deduplication statistics."""
        if self._stats.total_chunks > 0 and self._stats.unique_chunks > 0:
            self._stats.dedup_ratio = (
                self._stats.total_chunks / self._stats.unique_chunks
            )
        return self._stats

    def reset_stats(self) -> None:
        """Reset statistics."""
        self._stats = DedupStats()


class StreamingDedupPipeline(DedupPipeline):
    """
    Streaming version of the deduplication pipeline.

    Processes files in a streaming fashion for memory efficiency
    with very large files.
    """

    def __init__(self, lmdb_path: str, node_id: str,
                 chunk_size: int = 1024 * 1024,  # 1MB chunks
                 fpdb_client: Optional[Any] = None):
        super().__init__(lmdb_path, node_id, fpdb_client)
        self.chunk_size = chunk_size

    async def deduplicate_file_streaming(
        self,
        file_path: str,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> FileDedupResult:
        """
        Deduplicate a file using streaming (memory efficient).

        Args:
            file_path: Path to file
            progress_callback: Optional callback for progress updates

        Returns:
            FileDedupResult
        """
        start_time = time.time()
        chunk_refs = []
        unique_count = 0
        duplicate_count = 0
        original_bytes = 0
        deduplicated_bytes = 0
        file_size = Path(file_path).stat().st_size

        with open(file_path, 'rb') as f:
            offset = 0
            buffer = b""

            while True:
                # Read next chunk
                new_data = f.read(self.chunk_size)
                if not new_data:
                    break

                buffer += new_data

                # Generate chunks from buffer
                chunks = self.chunk_file(buffer)

                for chunk in chunks:
                    original_bytes += chunk.size
                    is_unique, refcount = self.check_chunk(chunk.fingerprint)

                    if is_unique:
                        unique_count += 1
                        deduplicated_bytes += chunk.size
                    else:
                        duplicate_count += 1

                    chunk_refs.append(ChunkRef(
                        fingerprint=chunk.fingerprint,
                        offset=offset,
                        size=chunk.size,
                        is_unique=is_unique,
                        refcount=refcount
                    ))

                    offset += chunk.size

                # Update progress
                if progress_callback:
                    progress_callback(offset / file_size if file_size > 0 else 0)

                # Keep remainder in buffer for next iteration
                if offset < len(buffer):
                    buffer = buffer[offset:]
                else:
                    buffer = b""
                offset = 0

        duration_ms = (time.time() - start_time) * 1000

        return FileDedupResult(
            file_path=file_path,
            file_size=file_size,
            chunks=chunk_refs,
            unique_chunks=unique_count,
            duplicate_chunks=duplicate_count,
            original_bytes=original_bytes,
            deduplicated_bytes=deduplicated_bytes,
            dedup_ratio=len(chunk_refs) / unique_count if unique_count > 0 else 1.0,
            duration_ms=duration_ms
        )


class DistributedDedupCoordinator:
    """
    Coordinator for distributed deduplication across multiple nodes.

    Manages:
    - Work distribution
    - Result aggregation
    - Global statistics
    """

    def __init__(self, num_workers: int = 4):
        self.num_workers = num_workers
        self._pipelines: List[DedupPipeline] = []
        self._running = False

    def create_pipeline(self, lmdb_path: str, node_id: str,
                       fpdb_client: Any = None) -> DedupPipeline:
        """Create a new dedup pipeline worker."""
        pipeline = DedupPipeline(lmdb_path, node_id, fpdb_client)
        self._pipelines.append(pipeline)
        return pipeline

    async def process_directory(self, root_path: str,
                               progress_callback: Optional[Callable] = None) -> DedupStats:
        """
        Process a directory of files using multiple workers.

        Args:
            root_path: Root directory to process
            progress_callback: Optional progress callback

        Returns:
            Aggregated DedupStats
        """
        import os
        files = []
        for dirpath, _, filenames in os.walk(root_path):
            for f in filenames:
                files.append(os.path.join(dirpath, f))

        total_files = len(files)
        completed = 0

        # Process files in parallel
        tasks = []
        for file_path in files:
            # Simple round-robin assignment to pipelines
            pipeline = self._pipelines[completed % len(self._pipelines)]
            task = asyncio.create_task(
                self._process_file_async(pipeline, file_path)
            )
            tasks.append((pipeline, task))
            completed += 1

        # Wait for all to complete
        aggregate_stats = DedupStats()
        for pipeline, task in tasks:
            result = await task
            # Aggregate results
            aggregate_stats.total_files += 1
            aggregate_stats.total_chunks += len(result.chunks)
            aggregate_stats.unique_chunks += result.unique_chunks
            aggregate_stats.duplicate_chunks += result.duplicate_chunks
            aggregate_stats.total_bytes += result.original_bytes
            aggregate_stats.deduplicated_bytes += result.deduplicated_bytes

            if progress_callback:
                progress_callback(completed / total_files)

        # Compute final ratio
        if aggregate_stats.unique_chunks > 0:
            aggregate_stats.dedup_ratio = (
                aggregate_stats.total_chunks / aggregate_stats.unique_chunks
            )

        return aggregate_stats

    async def _process_file_async(self, pipeline: DedupPipeline,
                                   file_path: str) -> FileDedupResult:
        """Process a single file asynchronously."""
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, Path(file_path).read_bytes)
        return pipeline.deduplicate_file(file_path, data)


# Example usage
if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test data with repeating patterns
        test_data = b"Hello, World! " * 10000  # 130KB of repeating data

        # Test single-file deduplication
        pipeline = DedupPipeline(tmpdir, "test-node")

        # First pass - all unique
        result1 = pipeline.deduplicate_file("/test/file1.txt", test_data)
        print(f"Pass 1: {result1.unique_chunks} unique, {result1.duplicate_chunks} duplicates")
        print(f"  Dedup ratio: {result1.dedup_ratio:.2f}x")

        # Second pass - all duplicates
        result2 = pipeline.deduplicate_file("/test/file2.txt", test_data)
        print(f"Pass 2: {result2.unique_chunks} unique, {result2.duplicate_chunks} duplicates")
        print(f"  Dedup ratio: {result2.dedup_ratio:.2f}x")

        # Stats
        stats = pipeline.get_stats()
        print(f"\nOverall stats:")
        print(f"  Total chunks: {stats.total_chunks}")
        print(f"  Unique chunks: {stats.unique_chunks}")
        print(f"  Duplicate chunks: {stats.duplicate_chunks}")
        print(f"  Dedup ratio: {stats.dedup_ratio:.2f}x")
        print(f"  Cache hits: {stats.cache_hits}, misses: {stats.cache_misses}")
        print(f"  Bloom hits: {stats.bloom_hits}, misses: {stats.bloom_misses}")

        pipeline.close()
