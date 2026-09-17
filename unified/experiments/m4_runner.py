"""
M4 Runner: Distributed Storage and Deduplication

M4 主程序: 集成去重和分布式存储。

功能:
- 内容定义分块
- 去重索引
- 分布式协调
- 数据修复
"""
import os
import sys
import json
import argparse
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from .dedup import (
    FastCDC,
    DedupIndex,
    DistributedIndex,
    chunk_file_with_dedup
)

from .distributed import (
    DistributedCoordinator,
    StorageNode,
    NodeState
)


@dataclass
class DedupResult:
    """去重结果"""
    file_path: str
    total_chunks: int = 0
    unique_chunks: int = 0
    duplicate_chunks: int = 0

    original_size: int = 0
    stored_size: int = 0
    saved_size: int = 0

    dedup_ratio: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class M4Report:
    """M4 实验报告"""
    report_id: str
    experiment_name: str
    created_at: str

    # 去重统计
    total_files: int = 0
    total_chunks: int = 0
    unique_chunks: int = 0
    total_original_size: int = 0
    total_stored_size: int = 0
    total_saved_size: int = 0
    overall_dedup_ratio: float = 0.0

    # 分布式统计
    cluster_stats: Dict[str, Any] = None

    # 文件结果
    file_results: List[DedupResult] = None

    def __post_init__(self):
        if self.cluster_stats is None:
            self.cluster_stats = {}
        if self.file_results is None:
            self.file_results = []

    def to_dict(self) -> dict:
        return asdict(self)


class M4Runner:
    """
    M4 分布式去重运行器

    流程:
    1. 扫描文件
    2. 内容分块
    3. 去重索引查询
    4. 存储唯一块
    5. 分布式协调
    """

    def __init__(
        self,
        experiment_name: str,
        storage_path: str,
        output_dir: str = "./m4_results"
    ):
        self.experiment_name = experiment_name
        self.storage_path = storage_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 组件
        self.chunker = FastCDC()
        self.dedup_index = DedupIndex(str(self.output_dir / "dedup_index.db"))
        self.distributed_index = DistributedIndex(node_id="node-1")
        self.coordinator = DistributedCoordinator(replication_factor=2)

        # 添加默认节点
        self._setup_default_nodes()

        # 结果
        self.results: List[DedupResult] = []

    def _setup_default_nodes(self):
        """设置默认节点"""
        for i in range(3):
            node = StorageNode(
                node_id=f"node-{i}",
                host=f"192.168.1.{100+i}",
                port=8000,
                capacity_bytes=100 * 1024**3  # 100 GB
            )
            self.coordinator.add_node(node)

    def process_file(self, file_path: str) -> DedupResult:
        """
        处理单个文件

        Args:
            file_path: 文件路径

        Returns:
            DedupResult
        """
        result = DedupResult(file_path=file_path)
        result.original_size = os.path.getsize(file_path)

        print(f"[M4] Processing: {file_path}")

        # 分块
        chunks = self.chunker.chunk_file(file_path)
        result.total_chunks = len(chunks)

        # 去重查询
        unique_chunks = []
        for chunk in chunks:
            existing = self.dedup_index.get_by_hash(chunk.content_hash)

            if existing:
                # 重复块
                chunk.is_duplicate = True
                chunk.ref_chunk_id = existing.chunk_id
                result.duplicate_chunks += 1
            else:
                # 唯一块
                unique_chunks.append(chunk)
                result.unique_chunks += 1

                # 添加到索引
                self.dedup_index.add_chunk(
                    chunk_id=chunk.chunk_id,
                    content_hash=chunk.content_hash,
                    size=chunk.size,
                    storage_path=str(self.output_dir / "chunks"),
                    offset=chunk.offset
                )

                # 存储到分布式节点
                self.coordinator.store_chunk(
                    chunk_id=chunk.chunk_id,
                    content_hash=chunk.content_hash,
                    size=chunk.size,
                    data_path="/data/chunks"
                )

        # 计算存储大小
        result.stored_size = sum(c.size for c in unique_chunks)
        result.saved_size = result.original_size - result.stored_size
        result.dedup_ratio = result.saved_size / result.original_size if result.original_size > 0 else 0

        print(f"[M4] Result: {result.unique_chunks} unique, {result.duplicate_chunks} duplicate, {result.dedup_ratio:.1%} ratio")

        return result

    def scan_files(self, extensions: List[str] = None) -> List[str]:
        """扫描文件"""
        if extensions is None:
            extensions = ['.mp4', '.avi', '.mkv', '.mov', '.bin', '.dat']

        files = []
        for root, dirs, filenames in os.walk(self.storage_path):
            for filename in filenames:
                if any(filename.lower().endswith(ext) for ext in extensions):
                    files.append(os.path.join(root, filename))

        return files

    def run(self, file_paths: List[str] = None) -> M4Report:
        """
        运行去重

        Args:
            file_paths: 文件路径列表

        Returns:
            M4Report
        """
        # 扫描文件
        if file_paths is None:
            file_paths = self.scan_files()

        print(f"[M4] Found {len(file_paths)} files")

        # 处理每个文件
        for path in file_paths:
            if not os.path.exists(path):
                continue

            result = self.process_file(path)
            self.results.append(result)

        # 生成报告
        report = self.generate_report()

        return report

    def generate_report(self) -> M4Report:
        """生成报告"""
        report = M4Report(
            report_id=f"m4-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            experiment_name=self.experiment_name,
            created_at=datetime.now().isoformat()
        )

        # 汇总统计
        report.total_files = len(self.results)
        report.total_chunks = sum(r.total_chunks for r in self.results)
        report.unique_chunks = sum(r.unique_chunks for r in self.results)
        report.total_original_size = sum(r.original_size for r in self.results)
        report.total_stored_size = sum(r.stored_size for r in self.results)
        report.total_saved_size = sum(r.saved_size for r in self.results)

        if report.total_original_size > 0:
            report.overall_dedup_ratio = report.total_saved_size / report.total_original_size

        # 分布式统计
        report.cluster_stats = self.coordinator.get_cluster_stats()

        # 文件结果
        report.file_results = [r.to_dict() for r in self.results]

        # 保存报告
        report_path = self.output_dir / "reports" / f"{report.report_id}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

        self._print_summary(report)

        return report

    def _print_summary(self, report: M4Report):
        """打印摘要"""
        print("\n" + "=" * 70)
        print(f"M4 DEDUPLICATION REPORT: {report.experiment_name}")
        print("=" * 70)

        print(f"\nFiles: {report.total_files}")
        print(f"Chunks: {report.total_chunks} total, {report.unique_chunks} unique")

        print(f"\nStorage:")
        print(f"  Original: {report.total_original_size / 1024**2:.1f} MB")
        print(f"  Stored: {report.total_stored_size / 1024**2:.1f} MB")
        print(f"  Saved: {report.total_saved_size / 1024**2:.1f} MB ({report.overall_dedup_ratio:.1%})")

        print(f"\nDistributed Cluster:")
        stats = report.cluster_stats
        print(f"  Nodes: {stats.get('total_nodes', 0)}")
        print(f"  Active: {stats.get('active_nodes', 0)}")
        print(f"  Total Chunks: {stats.get('total_chunks', 0)}")
        print(f"  Capacity: {stats.get('total_capacity_gb', 0):.1f} GB")
        print(f"  Usage: {stats.get('usage_percent', 0):.1f}%")

        print("=" * 70)


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description='M4: Distributed Storage and Deduplication')

    parser.add_argument('--storage', default='./test_videos', help='存储路径')
    parser.add_argument('--output-dir', default='./m4_results', help='输出目录')
    parser.add_argument('--name', default='m4-dedup', help='实验名称')

    args = parser.parse_args()

    runner = M4Runner(
        experiment_name=args.name,
        storage_path=args.storage,
        output_dir=args.output_dir
    )

    # 运行
    report = runner.run()

    return 0


if __name__ == '__main__':
    sys.exit(main())
