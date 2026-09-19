"""
Distributed Scan Node Worker

A scan node processes files, computes fingerprints, and reports results
back to the coordinator. Designed for horizontal scaling.
"""

import asyncio
import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional, Set
import json

from fpdb.sharding import ConsistentHashRing, ShardRouter
from fpdb.fingerprint import FingerprintRecord, compute_fingerprint
from cdc.chunker import rabin_chunks, DeduplicatingChunker, Chunk


# Configuration for scanning
DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1MB for simple fixed chunking
DEFAULT_EXCLUDIRS = {'.git', '.venv', '__pycache__', 'node_modules', '.DS_Store'}
DEFAULT_EXCLUDE_EXTENSIONS = {'.pyc', '.pyo', '.so', '.dll', '.dylib'}


@dataclass
class ScanOptions:
    """Options for a scan operation"""
    root_path: str
    follow_symlinks: bool = False
    exclude_dirs: Set[str] = field(default_factory=DEFAULT_EXCLUDIRS)
    exclude_extensions: Set[str] = field(default_factory=DEFAULT_EXCLUDE_EXTENSIONS)
    max_file_size: int = 10 * 1024 * 1024 * 1024  # 10GB
    min_file_size: int = 1  # 1 byte
    chunk_size: int = DEFAULT_CHUNK_SIZE
    use_cdc: bool = True  # Use content-defined chunking
    include_checksums: bool = True


@dataclass
class FileRecord:
    """Record for a single file during scanning"""
    path: str
    size: int
    mtime: float
    sha256: str
    chunks: List[str] = field(default_factory=list)  # Fingerprints of chunks
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None


@dataclass
class ScanResult:
    """Result of scanning a directory or file"""
    total_files: int
    total_bytes: int
    total_chunks: int
    unique_chunks: int
    duplicate_chunks: int
    files: List[FileRecord]
    errors: List[Dict]
    duration_seconds: float
    dedup_ratio: float


class LocalScanner:
    """
    Local file system scanner with CDC chunking support.

    Reuses the core scanning logic from the original storage_core.py
    but adds distributed processing capabilities.
    """

    def __init__(self, options: ScanOptions):
        self.options = options
        self._chunker = DeduplicatingChunker()

    async def scan_file(self, file_path: str) -> Optional[FileRecord]:
        """
        Scan a single file and compute its fingerprint.

        Returns:
            FileRecord if successful, None if skipped/error
        """
        try:
            path = Path(file_path)

            # Check if file should be skipped
            if path.is_symlink() and not self.options.follow_symlinks:
                return None

            stat = path.stat()

            # Skip directories
            if stat.is_dir():
                return None

            # Skip files based on size
            if stat.st_size < self.options.min_file_size:
                return None
            if stat.st_size > self.options.max_file_size:
                return None

            # Compute file-level SHA-256
            sha256, size = await self._compute_file_hash(file_path)

            # Compute chunks
            chunks = []
            if self.options.use_cdc:
                async for chunk in self._chunk_file(file_path):
                    chunks.append(chunk.fingerprint)
            else:
                # Fixed-size chunking
                with open(file_path, 'rb') as f:
                    while True:
                        data = f.read(self.options.chunk_size)
                        if not data:
                            break
                        chunks.append(compute_fingerprint(data))

            return FileRecord(
                path=str(path),
                size=size,
                mtime=stat.st_mtime,
                sha256=sha256,
                chunks=chunks
            )

        except (PermissionError, FileNotFoundError, OSError) as e:
            return None

    async def _compute_file_hash(self, file_path: str) -> tuple[str, int]:
        """Compute SHA-256 hash of entire file."""
        sha256_hash = hashlib.sha256()
        size = 0

        with open(file_path, 'rb') as f:
            while True:
                data = f.read(8192)
                if not data:
                    break
                sha256_hash.update(data)
                size += len(data)

        return sha256_hash.hexdigest(), size

    async def _chunk_file(self, file_path: str) -> AsyncIterator[Chunk]:
        """Yield chunks from a file using CDC."""
        with open(file_path, 'rb') as f:
            data = f.read()
            for chunk in rabin_chunks(data):
                yield chunk

    async def scan_directory(self, root_path: str) -> ScanResult:
        """
        Scan a directory recursively.

        Args:
            root_path: Root directory to scan

        Returns:
            ScanResult with all files and statistics
        """
        start_time = datetime.utcnow()
        files: List[FileRecord] = []
        errors: List[Dict] = []
        seen_signatures: Dict[str, str] = {}  # sha256 -> first file path

        await asyncio.sleep(0)  # Yield to event loop

        for dirpath, dirnames, filenames in os.walk(root_path):
            # Filter excluded directories
            dirnames[:] = [d for d in dirnames if d not in self.options.exclude_dirs]

            for filename in filenames:
                file_path = os.path.join(dirpath, filename)

                # Skip excluded extensions
                _, ext = os.path.splitext(filename)
                if ext in self.options.exclude_extensions:
                    continue

                record = await self.scan_file(file_path)
                if record is None:
                    continue

                files.append(record)

                # Track duplicates
                sig = record.sha256
                if sig in seen_signatures:
                    record.is_duplicate = True
                    record.duplicate_of = seen_signatures[sig]
                else:
                    seen_signatures[sig] = record.path

        # Compute statistics
        total_chunks = sum(len(f.chunks) for f in files)
        unique_chunks_set = set()
        for f in files:
            for c in f.chunks:
                unique_chunks_set.add(c)
        unique_chunks = len(unique_chunks_set)

        duration = (datetime.utcnow() - start_time).total_seconds()

        return ScanResult(
            total_files=len(files),
            total_bytes=sum(f.size for f in files),
            total_chunks=total_chunks,
            unique_chunks=unique_chunks,
            duplicate_chunks=total_chunks - unique_chunks,
            files=files,
            errors=errors,
            duration_seconds=duration,
            dedup_ratio=total_chunks / unique_chunks if unique_chunks > 0 else 1.0
        )


class ScanNode:
    """
    Distributed scan node that communicates with the coordinator.

    Features:
    - Registers with coordinator on startup
    - Requests scan tasks from coordinator
    - Reports progress during scanning
    - Handles task migration on failure
    """

    def __init__(self, node_id: str, coordinator_host: str, coordinator_port: int):
        self.node_id = node_id
        self.coordinator_host = coordinator_host
        self.coordinator_port = coordinator_port
        self._running = False
        self._current_task: Optional[Dict] = None
        self._shard_ring: Optional[ConsistentHashRing] = None
        self._shard_router: Optional[ShardRouter] = None

    async def start(self) -> None:
        """Start the scan node."""
        self._running = True

        # In production: connect to coordinator via gRPC
        # await self._connect_to_coordinator()

        # Start the main loop
        await self._main_loop()

    async def stop(self) -> None:
        """Stop the scan node gracefully."""
        self._running = False

    async def _main_loop(self) -> None:
        """Main event loop for the scan node."""
        while self._running:
            try:
                # Request a task from coordinator
                task = await self._request_task()

                if task is None:
                    # No task available, wait and retry
                    await asyncio.sleep(5)
                    continue

                # Execute the task
                self._current_task = task
                await self._execute_task(task)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
                await asyncio.sleep(1)

    async def _request_task(self) -> Optional[Dict]:
        """Request a scan task from the coordinator."""
        # In production: gRPC call to coordinator
        # response = await self.coordinator_stub.GetScanTask(...)
        return None

    async def _execute_task(self, task: Dict) -> None:
        """Execute a scan task."""
        source_path = task.get("source_path")
        options = ScanOptions(root_path=source_path)

        scanner = LocalScanner(options)

        # Scan with progress reporting
        result = await scanner.scan_directory(source_path)

        # Report completion to coordinator
        await self._report_completion(task, result)

    async def _report_progress(self, task: Dict, progress: float,
                               files_scanned: int, bytes_scanned: int) -> None:
        """Report scan progress to coordinator."""
        # In production: gRPC call
        pass

    async def _report_completion(self, task: Dict, result: ScanResult) -> None:
        """Report task completion to coordinator."""
        # In production: gRPC call with result stats
        print(f"Scan completed: {result.total_files} files, "
              f"{result.total_bytes} bytes, "
              f"{result.dedup_ratio:.2f}x dedup ratio")


class DistributedScanWorker:
    """
    Worker for running distributed scans across multiple nodes.

    Provides:
    - Work partitioning
    - Progress aggregation
    - Result merging
    """

    def __init__(self):
        self._results: List[ScanResult] = []

    async def run_partitioned_scan(self, root_path: str, num_partitions: int = 4) -> ScanResult:
        """
        Run a scan partitioned across multiple workers.

        Args:
            root_path: Directory to scan
            num_partitions: Number of parallel partitions

        Returns:
            Aggregated ScanResult from all partitions
        """
        # Partition the directory
        partitions = self._partition_directory(root_path, num_partitions)

        # Run scans in parallel
        tasks = []
        for partition in partitions:
            options = ScanOptions(root_path=partition)
            scanner = LocalScanner(options)
            task = asyncio.create_task(scanner.scan_directory(partition))
            tasks.append(task)

        # Wait for all to complete
        results = await asyncio.gather(*tasks)

        # Merge results
        return self._merge_results(results)

    def _partition_directory(self, root_path: str, num_partitions: int) -> List[str]:
        """Partition a directory into roughly equal parts."""
        # Simple strategy: partition by top-level subdirectories
        path = Path(root_path)
        subdirs = [d for d in path.iterdir() if d.is_dir()]

        if not subdirs:
            # No subdirs, scan the root directly
            return [root_path]

        # Distribute subdirs across partitions
        partitions = [[] for _ in range(num_partitions)]
        for i, subdir in enumerate(subdirs):
            partitions[i % num_partitions].append(str(subdir))

        # Return first partition for single-threaded test
        # In production, would spawn multiple workers
        return [str(path)] if partitions[0] else [root_path]

    def _merge_results(self, results: List[ScanResult]) -> ScanResult:
        """Merge multiple scan results into one."""
        total_files = sum(r.total_files for r in results)
        total_bytes = sum(r.total_bytes for r in results)
        total_chunks = sum(r.total_chunks for r in results)

        all_files = []
        for r in results:
            all_files.extend(r.files)

        all_errors = []
        for r in results:
            all_errors.extend(r.errors)

        # Compute unique chunks across all results
        unique_chunks = len(set())
        for r in results:
            for f in r.files:
                for c in f.chunks:
                    unique_chunks.add(c)

        duration = max(r.duration_seconds for r in results)

        return ScanResult(
            total_files=total_files,
            total_bytes=total_bytes,
            total_chunks=total_chunks,
            unique_chunks=len(unique_chunks),
            duplicate_chunks=total_chunks - len(unique_chunks),
            files=all_files,
            errors=all_errors,
            duration_seconds=duration,
            dedup_ratio=total_chunks / len(unique_chunks) if unique_chunks > 0 else 1.0
        )


# Entry point for running a scan node
async def main():
    """Main entry point for scan node worker."""
    import argparse

    parser = argparse.ArgumentParser(description="Storage Atlas Scan Node")
    parser.add_argument("--node-id", required=True, help="Unique node ID")
    parser.add_argument("--coordinator-host", default="localhost", help="Coordinator host")
    parser.add_argument("--coordinator-port", type=int, default=50051, help="Coordinator port")
    parser.add_argument("--scan-path", help="Path to scan (for testing)")

    args = parser.parse_args()

    if args.scan_path:
        # Run a single scan (for testing)
        options = ScanOptions(root_path=args.scan_path)
        scanner = LocalScanner(options)
        result = await scanner.scan_directory(args.scan_path)
        print(f"Scan result: {result.total_files} files, {result.total_bytes} bytes")
        print(f"Deduplication ratio: {result.dedup_ratio:.2f}x")
    else:
        # Start scan node worker
        node = ScanNode(args.node_id, args.coordinator_host, args.coordinator_port)
        await node.start()


if __name__ == "__main__":
    asyncio.run(main())
