"""
M4 Dedup: Super-Fast Content-Defined Chunking

极速内容定义分块:
- SIMD 风格字节表查找
- 滚动哈希优化 (Rabin指纹)
- 内存映射文件 (mmap)
- 并行分块
- 智能边界检测
"""
import hashlib
import mmap
import struct
from dataclasses import dataclass
from typing import List, Optional, Callable, Tuple
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import os


@dataclass
class Chunk:
    """数据块"""
    chunk_id: str
    content_hash: str  # SHA-256 of content
    size: int
    offset: int  # offset in original file

    # 压缩信息
    is_compressible: bool = True
    compressed_size: Optional[int] = None

    # 去重信息
    is_duplicate: bool = False
    ref_chunk_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'chunk_id': self.chunk_id,
            'content_hash': self.content_hash,
            'size': self.size,
            'offset': self.offset,
            'is_compressible': self.is_compressible,
            'compressed_size': self.compressed_size,
            'is_duplicate': self.is_duplicate,
            'ref_chunk_id': self.ref_chunk_id
        }


class FastCDC:
    """
    极速内容定义分块

    优化点:
    1. 预计算滑动窗口哈希表 (256字节表)
    2. 位操作优化边界检测
    3. mmap 大文件处理
    4. 批量哈希计算
    """

    # 最小/最大块大小
    MIN_CHUNK_SIZE = 2048   # 2 KB
    MAX_CHUNK_SIZE = 16384  # 16 KB
    WINDOW_SIZE = 48

    # 边界检测 mask (低13位为0表示边界，约 1/8192 概率)
    BOUNDARY_MASK = 0x1FFF

    def __init__(
        self,
        min_chunk: int = 2048,
        max_chunk: int = 16384,
        polynomial: int = 0x3DA3358B4D022C91
    ):
        self.min_chunk = min_chunk
        self.max_chunk = max_chunk
        self.polynomial = polynomial

        # 预计算哈希表
        self._hash_table = self._compute_hash_table()

        # Rabin fingerprint 状态
        self._fp_table = self._compute_fp_table()

    def _compute_hash_table(self) -> bytes:
        """预计算 256 字节的哈希表用于快速字节到 uint8 映射"""
        table = bytearray(256)
        for i in range(256):
            # 简化的字节混淆
            table[i] = (i ^ 0x5A) & 0xFF
        return bytes(table)

    def _compute_fp_table(self) -> bytes:
        """预计算 Rabin fingerprint 表"""
        table = bytearray(256)
        for i in range(256):
            val = i
            for _ in range(self.WINDOW_SIZE):
                val = ((val << 1) ^ (val >> 63) ^ self.polynomial) & 0xFFFFFFFFFFFFFFFF
            table[i] = val & 0xFF
        return bytes(table)

    def _rolling_hash(self, data: bytes, init_val: int = 0) -> int:
        """
        滚动哈希

        使用预计算的表格加速
        """
        hash_val = init_val
        for byte in data:
            # 使用查表代替数学运算
            hash_val = ((hash_val << 1) ^ self._fp_table[byte]) & 0xFFFFFFFFFFFFFFFF
        return hash_val

    def chunk_file(
        self,
        file_path: str,
        read_chunk_size: int = 65536  # 64KB 读取块
    ) -> List[Chunk]:
        """
        对文件进行分块 (内存映射优化)

        Args:
            file_path: 文件路径
            read_chunk_size: 内部读取块大小

        Returns:
            List[Chunk]: 块列表
        """
        chunks = []
        chunk_index = 0
        offset = 0

        with open(file_path, 'rb') as f:
            # 使用 mmap 如果文件大于阈值
            file_size = os.fstat(f.fileno()).st_size

            if file_size > 100 * 1024 * 1024:  # > 100MB
                return self._chunk_file_mmap(f, file_size, chunk_index)

            # 小文件直接读取
            buffer = b''
            while True:
                data = f.read(read_chunk_size)
                if not data:
                    break
                buffer += data

                # 分块处理
                while len(buffer) >= self.min_chunk:
                    boundary = self._find_boundary(buffer)

                    if boundary:
                        chunk_data = buffer[:boundary]
                        buffer = buffer[boundary:]
                        chunk = self._create_chunk(chunk_data, offset, chunk_index)
                        chunks.append(chunk)
                        offset += boundary
                        chunk_index += 1
                    elif len(buffer) >= self.max_chunk:
                        # 强制分块
                        chunk_data = buffer[:self.max_chunk]
                        buffer = buffer[self.max_chunk:]
                        chunk = self._create_chunk(chunk_data, offset, chunk_index)
                        chunks.append(chunk)
                        offset += self.max_chunk
                        chunk_index += 1
                    else:
                        break

            # 处理剩余数据
            if buffer:
                chunk = self._create_chunk(buffer, offset, chunk_index)
                chunks.append(chunk)

        return chunks

    def _chunk_file_mmap(
        self,
        f,
        file_size: int,
        start_index: int
    ) -> List[Chunk]:
        """使用 mmap 进行大文件分块"""
        chunks = []
        chunk_index = start_index
        offset = 0

        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            pos = 0

            while pos < file_size:
                # 计算到下一个边界的距离
                chunk_end = min(pos + self.max_chunk, file_size)
                boundary = self._find_boundary_in_range(mm, pos, chunk_end)

                if boundary is None or boundary - pos < self.min_chunk:
                    # 没有找到自然边界，使用最大块大小
                    boundary = min(pos + self.max_chunk, file_size)

                # 创建块
                chunk_data = mm[pos:boundary]
                chunk = self._create_chunk(chunk_data, offset, chunk_index)
                chunks.append(chunk)

                offset += len(chunk_data)
                pos = boundary
                chunk_index += 1

        return chunks

    def _find_boundary(self, data: bytes) -> Optional[int]:
        """
        在数据中查找自然块边界

        Returns:
            边界位置，如果没有找到则返回 None
        """
        if len(data) < self.min_chunk:
            return None

        # 检查从 min_chunk 开始的位置
        for i in range(self.min_chunk, min(len(data), self.max_chunk + 1)):
            # 使用简化哈希检测边界
            # 检查累积 XOR 的低 13 位
            if i >= self.WINDOW_SIZE:
                window = data[i - self.WINDOW_SIZE:i]
                fp = self._rolling_hash_fast(window)
                if (fp & self.BOUNDARY_MASK) == 0:
                    return i

        return None

    def _find_boundary_in_range(
        self,
        mm: mmap.mmap,
        start: int,
        end: int
    ) -> Optional[int]:
        """在 mmap 范围内查找边界"""
        chunk_size = end - start
        if chunk_size < self.min_chunk:
            return None

        for i in range(start + self.min_chunk, end):
            if i - start >= self.WINDOW_SIZE:
                window = mm[i - self.WINDOW_SIZE:i]
                fp = self._rolling_hash_fast(window)
                if (fp & self.BOUNDARY_MASK) == 0:
                    return i

        return None

    def _rolling_hash_fast(self, data: bytes) -> int:
        """快速滚动哈希"""
        hash_val = 0
        for byte in data:
            hash_val = ((hash_val << 1) ^ byte ^ self.polynomial) & 0xFFFFFFFFFFFFFFFF
        return hash_val

    def _create_chunk(
        self,
        data: bytes,
        offset: int,
        index: int
    ) -> Chunk:
        """创建块"""
        content_hash = hashlib.sha256(data).hexdigest()
        chunk_id = f"c-{index:08d}-{content_hash[:16]}"

        return Chunk(
            chunk_id=chunk_id,
            content_hash=content_hash,
            size=len(data),
            offset=offset
        )


class ParallelChunker:
    """
    并行分块器

    使用多进程对大文件进行并行分块
    """

    def __init__(
        self,
        chunker: Optional[FastCDC] = None,
        max_workers: int = 4
    ):
        self.chunker = chunker or FastCDC()
        self.max_workers = max_workers

    def chunk_file(self, file_path: str) -> List[Chunk]:
        """
        并行分块

        策略: 将文件分段，每个 worker 处理一段，然后合并
        """
        file_size = os.path.getsize(file_path)

        # 小文件不需要并行
        if file_size < 50 * 1024 * 1024:  # < 50MB
            return self.chunker.chunk_file(file_path)

        # 计算分段
        chunk_size = max(10 * 1024 * 1024, file_size // self.max_workers)  # 至少 10MB
        segments = []
        offset = 0

        with open(file_path, 'rb') as f:
            while offset < file_size:
                end = min(offset + chunk_size, file_size)
                segments.append((offset, end))
                offset = end

        # 并行处理
        chunks = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for i, (start, end) in enumerate(segments):
                future = executor.submit(
                    self._chunk_segment,
                    file_path, start, end, i
                )
                futures.append(future)

            for future in futures:
                segment_chunks = future.result()
                chunks.extend(segment_chunks)

        # 按偏移量排序
        chunks.sort(key=lambda c: c.offset)
        return chunks

    def _chunk_segment(
        self,
        file_path: str,
        start: int,
        end: int,
        segment_index: int
    ) -> List[Chunk]:
        """处理文件段"""
        chunks = []

        with open(file_path, 'rb') as f:
            f.seek(start)
            data = f.read(end - start)

        # 在段内进行分块，但第一个块需要特殊处理
        segment_chunks = self.chunker.chunk_file_bytes(data)

        # 调整偏移量
        for chunk in segment_chunks:
            chunk.offset += start
            chunk.chunk_id = f"s{segment_index}-{chunk.chunk_id}"

        return segment_chunks


def chunk_file_with_dedup(
    file_path: str,
    chunker: Callable = None
) -> List[Chunk]:
    """
    对文件进行分块并准备去重

    Args:
        file_path: 文件路径
        chunker: 分块器，默认使用 FastCDC

    Returns:
        List[Chunk]: 块列表
    """
    if chunker is None:
        chunker = FastCDC()

    return chunker.chunk_file(file_path)


def main():
    """演示"""
    import tempfile
    import time

    # 创建测试文件
    test_size = 100 * 1024 * 1024  # 100MB
    with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f:
        # 写入重复模式
        pattern = b'A' * 1000 + b'B' * 1000
        for _ in range(test_size // len(pattern)):
            f.write(pattern)
        test_file = f.name

    try:
        # 测试 FastCDC
        chunker = FastCDC()

        start = time.time()
        chunks = chunker.chunk_file(test_file)
        elapsed = time.time() - start

        print(f"[Dedup] Created {len(chunks)} chunks in {elapsed:.2f}s")
        print(f"[Dedup] Throughput: {test_size / 1024 / 1024 / elapsed:.1f} MB/s")

        # 统计
        hashes = [c.content_hash for c in chunks]
        unique_hashes = set(hashes)
        print(f"[Dedup] Unique: {len(unique_hashes)} / {len(chunks)}")
        print(f"[Dedup] Dedup ratio: {1 - len(unique_hashes)/len(chunks):.1%}")

        # 显示前5个块
        print(f"\n[Dedup] First 5 chunks:")
        for chunk in chunks[:5]:
            print(f"  - {chunk.chunk_id}: size={chunk.size}, offset={chunk.offset}")

    finally:
        os.unlink(test_file)


if __name__ == '__main__':
    main()
