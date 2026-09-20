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
import time
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


class ProgressBar:
    """终端进度条"""
    def __init__(self, width: int = 40):
        self.width = width
        self.current = 0
        self.total = 0
        self.message = ""

    def update(self, current: int, total: int, message: str = ""):
        self.current = current
        self.total = total
        self.message = message
        if total > 0:
            pct = int(current / total * 100)
            filled = int(self.width * current / total)
            bar = '█' * filled + '░' * (self.width - filled)
            sys.stdout.write(f'\r[{bar}] {pct:3d}% {message[:30]}')
            sys.stdout.flush()

    def finish(self, message: str = "完成"):
        sys.stdout.write(f'\r{" " * (self.width + 50)}\r')
        sys.stdout.flush()
        print(f"✅ {message}")

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.pristmax.agent.storage_agent import StorageAgent, FileInfo, color, Colors


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

    result = agent.analyze_large_files(path, min_size_mb=min_mb, limit=limit)
    files = result.get('items', [])

    if not files:
        print("   未找到符合条件的文件")
        return 0

    print(f"\n✅ 找到 {result.get('total', 0)} 个大文件:")
    total_wasted = sum(f.size for f in files)
    for i, f in enumerate(files, 1):
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
    incremental = not args.full_scan

    print(f"\n\033[1m\033[94m📈 存储统计: {path}\033[0m")
    print("=" * 50)

    progress = None
    if sys.stdout.isatty():
        progress = ProgressBar()
        progress.update(0, 100, "开始扫描...")

    def progress_callback(current, total, message):
        if progress:
            progress.update(current, total, message)

    stats = agent.get_storage_stats(path, incremental=incremental, progress=progress_callback)

    if progress:
        progress.finish(f"扫描完成 {stats['total_files']:,} 文件")

    scan_type = "\033[33m全量扫描\033[0m" if not incremental else "\033[92m增量扫描\033[0m"
    print(f"\n📍 扫描模式: {scan_type}")
    if incremental:
        print(f"   缓存命中: \033[92m{stats.get('cached_files', 0):,}\033[0m 文件")
        print(f"   新增/变更: \033[93m{stats.get('new_files', 0):,}\033[0m 文件")

    print(f"\n\033[1m【概览】\033[0m")
    print(f"   总文件数: \033[1m\033[94m{stats['total_files']:,}\033[0m")
    print(f"   总大小:   \033[1m\033[94m{stats['total_size_display']}\033[0m")

    print(f"\n\033[1m【类型分布】\033[0m")
    if stats['by_category']:
        for cat, info in sorted(stats['by_category'].items(), key=lambda x: x[1]['size'], reverse=True):
            bar_len = int(info['size'] / stats['total_size'] * 40) if stats['total_size'] > 0 else 0
            bar = '\033[92m' + '█' * bar_len + '\033[90m' + '░' * (40 - bar_len) + '\033[0m'
            print(f"   {cat:12s} [{bar}] {info['size_display']}")

    print(f"\n\033[1m【最大目录】\033[0m")
    if stats['largest_dirs']:
        for d in stats['largest_dirs'][:5]:
            print(f"   \033[90m{d['size_display']:>10s}\033[0m  {d['path']}")

    return 0


def cmd_export(agent: StorageAgent, args):
    """导出报告命令"""
    path = args.path or os.getcwd()
    output = args.output or f"storage-report.{args.format}"

    print(f"\n📄 正在生成报告: {output}")
    print(f"   格式: {args.format.upper()}")
    print(f"   目录: {path}")

    try:
        result = agent.export_report(path, output, format=args.format)
        print(f"\n✅ 报告已生成: {result}")
        return 0
    except Exception as e:
        print(f"\n❌ 生成失败: {e}")
        return 1


def cmd_chat(agent: StorageAgent, args):
    """对话命令"""
    path = args.path or os.getcwd()

    print(f"\n🤖 Storage Agent 对话模式")
    print(f"   扫描目录: {path}")
    print(f"   输入 'quit' 或 'exit' 退出\n")

    while True:
        try:
            user_input = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 再见!")
            return 0

        if not user_input:
            continue

        if user_input.lower() in ['quit', 'exit', 'q', '退出']:
            print("👋 再见!")
            return 0

        response = agent.chat(path, user_input)
        print(f"\nAgent: {response}")


def cmd_suggest(agent: StorageAgent, args):
    """建议命令"""
    path = args.path or os.getcwd()

    print(f"\n\033[1m\033[93m💡 智能建议: {path}\033[0m")
    print("=" * 50)

    suggestions = agent.get_suggestions(path)

    if not suggestions:
        print("\n✅ 目前没有需要关注的建议")
        return 0

    for s in suggestions:
        icon = "\033[91m⚠️\033[0m" if s['type'] == 'warning' else "\033[96m💡\033[0m" if s['type'] == 'tip' else "\033[94mℹ️\033[0m"
        print(f"\n{icon} \033[1m{s['title']}\033[0m")
        print(f"   {s['description']}")
        print(f"   → \033[92m{s['action']}\033[0m")

    return 0


def cmd_cleanup_duplicates(agent: StorageAgent, args):
    """清理重复文件命令"""
    path = args.path or os.getcwd()
    dry_run = not args.execute

    if dry_run:
        print(f"\n\033[93m🔍 预览模式: {path}\033[0m")
        print("   将显示要删除的文件，但不实际删除\n")
    else:
        print(f"\n\033[91m⚠️ 执行模式: {path}\033[0m")
        print("   即将删除以下文件!\n")

    print("=" * 50)
    result = agent.cleanup_duplicates(path, dry_run=dry_run)

    if result['groups_found'] == 0:
        print("\n✅ 没有发现重复文件")
        return 0

    print(f"\n发现 \033[1m{result['groups_found']}\033[0m 组重复文件")
    print(f"将删除 \033[1m{len(result['files_to_delete'])}\033[0m 个文件")
    print(f"可节省空间: \033[92m{FileInfo.format_size(result['space_to_free'])}\033[0m\n")

    if result['files_to_delete']:
        print("\033[1m【待删除文件】\033[0m")
        for i, filepath in enumerate(result['files_to_delete'][:20], 1):
            print(f"  {i}. \033[90m{filepath}\033[0m")
        if len(result['files_to_delete']) > 20:
            print(f"  ... 还有 {len(result['files_to_delete']) - 20} 个文件")

    if not dry_run:
        print(f"\n\033[92m✅ 已删除 {len(result['deleted'])} 个文件\033[0m")
        if result['errors']:
            print(f"\n\033[91m❌ 删除失败 {len(result['errors'])} 个文件\033[0m")
            for e in result['errors'][:5]:
                print(f"   • {e['file']}: {e['error']}")
    else:
        print(f"\n\033[93m💡 运行 --cleanup-duplicates --execute 实际删除\033[0m")

    return 0


def cmd_cleanup_large(agent: StorageAgent, args):
    """清理大文件命令"""
    path = args.path or os.getcwd()
    dry_run = not args.execute
    min_mb = args.min

    if dry_run:
        print(f"\n\033[93m🔍 预览模式: {path}\033[0m")
        print(f"   查找大于 {min_mb}MB 的文件\n")
    else:
        print(f"\n\033[91m⚠️ 执行模式: {path}\033[0m")
        print("   即将删除以下文件!\n")

    print("=" * 50)
    result = agent.cleanup_large_files(path, min_size_mb=min_mb, dry_run=dry_run)

    if result['files_found'] == 0:
        print(f"\n✅ 没有发现大于 {min_mb}MB 的文件")
        return 0

    print(f"\n发现 \033[1m{result['files_found']}\033[0m 个大文件")
    print(f"将删除 \033[1m{len(result['files_to_delete'])}\033[0m 个文件")
    print(f"可节省空间: \033[92m{FileInfo.format_size(result['space_to_free'])}\033[0m\n")

    if result['files_to_delete']:
        print("\033[1m【待删除文件】\033[0m")
        for i, filepath in enumerate(result['files_to_delete'][:20], 1):
            print(f"  {i}. \033[90m{filepath}\033[0m")
        if len(result['files_to_delete']) > 20:
            print(f"  ... 还有 {len(result['files_to_delete']) - 20} 个文件")

    if not dry_run:
        print(f"\n\033[92m✅ 已删除 {len(result['deleted'])} 个文件\033[0m")
        if result['errors']:
            print(f"\n\033[91m❌ 删除失败 {len(result['errors'])} 个文件\033[0m")
    else:
        print(f"\n\033[93m💡 运行 --cleanup-large --execute 实际删除\033[0m")

    return 0


def cmd_monitor(agent: StorageAgent, args):
    """监控模式命令"""
    path = args.path or os.getcwd()
    interval = args.interval

    print(f"\n\033[1m\033[95m🔄 监控模式: {path}\033[0m")
    print(f"   检测间隔: {interval} 秒")
    print(f"   按 Ctrl+C 停止\n")

    last_stats = None
    last_check = None

    try:
        while True:
            print(f"\n\033[90m[{datetime.now().strftime('%H:%M:%S')}] 执行检测...\033[0m")
            stats = agent.get_storage_stats(path, incremental=True)
            suggestions = agent.get_suggestions(path)

            if last_stats:
                # 检测变化
                file_diff = stats['total_files'] - last_stats['total_files']
                size_diff = stats['total_size'] - last_stats['total_size']

                if file_diff != 0 or size_diff != 0:
                    size_change = FileInfo.format_size(abs(size_diff)) if size_diff != 0 else "无"
                    direction = "↑" if size_diff > 0 else "↓"
                    print(f"\n\033[92m📊 变化检测:\033[0m 文件 {direction}{abs(file_diff):+,}, 大小 {direction}{size_change}")

            # 显示关键指标
            print(f"   总文件: \033[94m{stats['total_files']:,}\033[0m")
            print(f"   总大小: \033[94m{stats['total_size_display']}\033[0m")
            print(f"   缓存命中: \033[92m{stats.get('cached_files', 0):,}\033[0m")

            # 显示建议
            if suggestions:
                print(f"\n\033[93m⚠️ 建议 ({len(suggestions)}):\033[0m")
                for s in suggestions[:2]:
                    print(f"   • {s['title']} - {s['description']}")

            last_stats = stats
            last_check = datetime.now()

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\n\033[92m👋 监控已停止\033[0m")
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
  %(prog)s --stats                    显示统计信息 (带进度条)
  %(prog)s --stats --full-scan        强制全量扫描
  %(prog)s --suggest                  显示智能建议
  %(prog)s --cleanup-duplicates        预览重复文件清理
  %(prog)s --cleanup-duplicates --execute  执行重复文件清理
  %(prog)s --cleanup-large --min 100  预览大文件清理
  %(prog)s --cleanup-large --min 100 --execute  执行大文件清理
  %(prog)s --export -o report.html    导出HTML报告
  %(prog)s --chat                     进入对话交互模式
  %(prog)s --monitor --interval 30    监控模式 (30秒检测一次)
  %(prog)s serve --port 5002          启动API服务
        """
    )

    parser.add_argument('--path', '-p', help='要扫描的目录路径')
    parser.add_argument('--analyze', '-a', action='store_true', help='综合分析目录')
    parser.add_argument('--large-files', '-l', action='store_true', help='查找大文件')
    parser.add_argument('--duplicates', '-d', action='store_true', help='查找重复文件')
    parser.add_argument('--stats', '-s', action='store_true', help='显示统计信息')
    parser.add_argument('--export', '-e', action='store_true', help='导出报告')
    parser.add_argument('--suggest', action='store_true', help='显示智能建议')
    parser.add_argument('--cleanup-duplicates', action='store_true', help='清理重复文件')
    parser.add_argument('--cleanup-large', action='store_true', help='清理大文件')
    parser.add_argument('--chat', action='store_true', help='对话交互模式')
    parser.add_argument('--monitor', action='store_true', help='监控模式')
    parser.add_argument('--serve', action='store_true', help='启动API服务')
    parser.add_argument('--min', type=int, default=100, help='最小大小(MB for files, KB for dupes)')
    parser.add_argument('--limit', type=int, default=20, help='返回结果数量限制')
    parser.add_argument('--port', type=int, default=5002, help='API服务端口')
    parser.add_argument('--db', help='数据库路径 (默认: 内存数据库)')
    parser.add_argument('--full-scan', action='store_true', help='禁用增量扫描，强制全量扫描')
    parser.add_argument('--format', choices=['html', 'json'], default='html', help='报告格式 (默认: html)')
    parser.add_argument('--output', '-o', help='报告输出路径')
    parser.add_argument('--interval', type=int, default=60, help='监控检测间隔秒数 (默认: 60)')
    parser.add_argument('--execute', action='store_true', help='执行清理操作（默认仅预览）')

    args = parser.parse_args()

    # 创建 Agent 实例
    db_path = args.db if args.db else ':memory:'
    agent = StorageAgent(db_path=db_path)

    # 如果没有指定命令，默认分析
    if not any([args.analyze, args.large_files, args.duplicates, args.stats, args.serve, args.export, args.suggest, args.chat, args.monitor, args.cleanup_duplicates, args.cleanup_large]):
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
        elif args.export:
            return cmd_export(agent, args)
        elif args.suggest:
            return cmd_suggest(agent, args)
        elif args.cleanup_duplicates:
            return cmd_cleanup_duplicates(agent, args)
        elif args.cleanup_large:
            return cmd_cleanup_large(agent, args)
        elif args.chat:
            return cmd_chat(agent, args)
        elif args.monitor:
            return cmd_monitor(agent, args)
        elif args.serve:
            return cmd_serve(agent, args)
    finally:
        agent.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
