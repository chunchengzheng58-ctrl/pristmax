"""
Storage Agent CLI

Usage:
    storage-agent --path /data --analyze
    storage-agent --large-files --min 100MB
    storage-agent --duplicates
    storage-agent --stats
"""
import argparse
import sys
import os
import io
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.pristmax.agent.storage_agent import StorageAgent, FileInfo


def format_bytes(size: int) -> str:
    """格式化字节大小"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def cmd_analyze(agent: StorageAgent, args):
    """分析命令"""
    path = args.path or os.getcwd()
    print(f"\n📊 正在分析: {path}")
    print("-" * 50)

    stats = agent.get_storage_stats(path)

    print(f"\n✅ 扫描完成!")
    print(f"   总文件: {stats['total_files']:,}")
    print(f"   总大小: {stats['total_size_display']}")

    if stats['by_category']:
        print(f"\n📁 按类型分布:")
        for cat, info in sorted(stats['by_category'].items(), key=lambda x: x[1]['size'], reverse=True)[:5]:
            print(f"   {cat:12s}: {info['size_display']:>10s} ({info['count']:,} 个文件)")

    return 0


def cmd_large_files(agent: StorageAgent, args):
    """大文件命令"""
    path = args.path or os.getcwd()
    min_mb = args.min or 100
    limit = args.limit or 20

    print(f"\n📦 查找大于 {min_mb}MB 的文件...")
    print("-" * 50)

    files = agent.analyze_large_files(path, min_size_mb=min_mb, limit=limit)

    if not files:
        print("   未找到符合条件的文件")
        return 0

    print(f"\n✅ 找到 {len(files)} 个大文件:")
    total_wasted = sum(f.size for f in files)
    for i, f in enumerate(files[:limit], 1):
        print(f"   #{i:2d}  {f.size_display:>8s}  {f.path}")

    print(f"\n   大文件总占用: {format_bytes(total_wasted)}")
    return 0


def cmd_duplicates(agent: StorageAgent, args):
    """重复文件命令"""
    path = args.path or os.getcwd()
    min_kb = args.min or 1

    print(f"\n🔄 搜索重复文件 (最小 {min_kb}KB)...")
    print("-" * 50)

    duplicates = agent.find_duplicates(path, min_size_kb=min_kb)

    if not duplicates:
        print("   未找到重复文件")
        return 0

    print(f"\n✅ 找到 {len(duplicates)} 组重复文件:")
    total_wasted = 0
    for i, group in enumerate(duplicates[:10], 1):
        wasted = group.wasted_space
        total_wasted += wasted
        print(f"\n   组 {i}: {group.count} 个文件, 每文件 {group.size_display}")
        for f in group.files[:3]:
            print(f"      - {f}")
        if len(group.files) > 3:
            print(f"      ... 还有 {len(group.files) - 3} 个")

    print(f"\n💰 可节省空间: {format_bytes(total_wasted)}")
    return 0


def cmd_stats(agent: StorageAgent, args):
    """统计命令"""
    path = args.path or os.getcwd()

    print(f"\n📈 存储统计: {path}")
    print("=" * 50)

    stats = agent.get_storage_stats(path)

    print(f"\n【概览】")
    print(f"   总文件数: {stats['total_files']:,}")
    print(f"   总大小:   {stats['total_size_display']}")

    print(f"\n【类型分布】")
    if stats['by_category']:
        for cat, info in sorted(stats['by_category'].items(), key=lambda x: x[1]['size'], reverse=True):
            bar_len = int(info['size'] / stats['total_size'] * 40) if stats['total_size'] > 0 else 0
            bar = '█' * bar_len + '░' * (40 - bar_len)
            print(f"   {cat:12s} [{bar}] {info['size_display']}")

    print(f"\n【最大目录】")
    if stats['largest_dirs']:
        for d in stats['largest_dirs'][:5]:
            print(f"   {d['size_display']:>10s}  {d['path']}")

    return 0


def cmd_serve(agent: StorageAgent, args):
    """启动API服务"""
    from src.pristmax.agent.api import app
    print(f"\n🚀 启动 Storage Agent API 服务...")
    print(f"   端口: {args.port}")
    print(f"   访问: http://localhost:{args.port}/api/agent/stats?path=/data")
    app.run(host='0.0.0.0', port=args.port, debug=False)
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Storage Agent - 智能存储管家',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --path /data --analyze      分析目录
  %(prog)s --large-files --min 100    查找大于100MB的文件
  %(prog)s --duplicates               查找重复文件
  %(prog)s --stats                    显示统计信息
  %(prog)s serve --port 5002          启动API服务
        """
    )

    parser.add_argument('--path', '-p', help='要扫描的目录路径')
    parser.add_argument('--analyze', '-a', action='store_true', help='综合分析目录')
    parser.add_argument('--large-files', '-l', action='store_true', help='查找大文件')
    parser.add_argument('--duplicates', '-d', action='store_true', help='查找重复文件')
    parser.add_argument('--stats', '-s', action='store_true', help='显示统计信息')
    parser.add_argument('--serve', action='store_true', help='启动API服务')
    parser.add_argument('--min', type=int, default=100, help='最小大小(MB for files, KB for dupes)')
    parser.add_argument('--limit', type=int, default=20, help='返回结果数量限制')
    parser.add_argument('--port', type=int, default=5002, help='API服务端口')
    parser.add_argument('--db', help='数据库路径 (默认: 内存数据库)')

    args = parser.parse_args()

    # 创建 Agent 实例
    db_path = args.db if args.db else ':memory:'
    agent = StorageAgent(db_path=db_path)

    # 如果没有指定命令，默认分析
    if not any([args.analyze, args.large_files, args.duplicates, args.stats, args.serve]):
        args.analyze = True

    try:
        if args.analyze:
            return cmd_analyze(agent, args)
        elif args.large_files:
            return cmd_large_files(agent, args)
        elif args.duplicates:
            return cmd_duplicates(agent, args)
        elif args.stats:
            return cmd_stats(agent, args)
        elif args.serve:
            return cmd_serve(agent, args)
    finally:
        agent.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
