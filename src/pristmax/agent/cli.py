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


def get_desktop_path() -> str:
    """获取桌面路径"""
    if sys.platform == 'win32':
        return os.path.join(os.path.expanduser('~'), 'Desktop')
    elif sys.platform == 'darwin':
        return os.path.join(os.path.expanduser('~'), 'Desktop')
    else:
        return os.path.join(os.path.expanduser('~'), 'desktop')

def cmd_desktop_undo(agent: StorageAgent, args):
    """撤销桌面整理命令"""
    desktop = get_desktop_path()
    undo_file = os.path.join(desktop, '.desktop_org_undo.json')

    print(f"\n↩️ 撤销桌面整理: {desktop}")
    print("=" * 50)

    if not os.path.exists(undo_file):
        print("❌ 没有找到撤销记录")
        return 1

    try:
        import json
        with open(undo_file, 'r', encoding='utf-8') as f:
            operations = json.load(f)
    except Exception as e:
        print(f"❌ 读取撤销记录失败: {e}")
        return 1

    print(f"\n📋 找到 {len(operations)} 条操作记录")
    print("=" * 50)

    if args.execute:
        print("🛠️  执行撤销...")
    else:
        print("🔍 预览模式 (添加 --execute 执行撤销)")

    undone = 0
    for op in operations:
        if args.execute:
            try:
                if os.path.exists(op['to']):
                    os.rename(op['to'], op['from'])
                    print(f"   ✓ 撤销: {os.path.basename(op['to'])} → {os.path.dirname(op['from'])}/")
                    undone += 1
            except Exception as e:
                print(f"   ✗ 失败: {os.path.basename(op['to'])} - {e}")
        else:
            print(f"   → {os.path.basename(op['to'])} → {os.path.dirname(op['from'])}/")

    if args.execute:
        os.remove(undo_file)
        print(f"\n✅ 撤销完成! 已恢复 {undone} 个文件")
    else:
        print(f"\n💡 添加 --execute 执行此次撤销")

    return 0

def cmd_desktop(agent: StorageAgent, args):
    """桌面整理命令"""
    desktop = get_desktop_path()
    mode = args.desktop_mode or 'type'  # type | time | project

    print(f"\n🗂️ 桌面整理: {desktop}")
    print("=" * 50)

    # 扫描桌面
    files = []
    folders = []
    shortcuts = []

    try:
        items = os.listdir(desktop)
    except Exception as e:
        print(f"❌ 无法访问桌面: {e}")
        return 1

    for item in items:
        full_path = os.path.join(desktop, item)
        if os.path.isfile(full_path):
            ext = os.path.splitext(item)[1].lower()
            mtime = os.path.getmtime(full_path)
            mod_time = datetime.fromtimestamp(mtime)
            if ext in ['.lnk', '.url', '.exe']:
                shortcuts.append({'name': item, 'path': full_path, 'ext': ext, 'time': mod_time})
            else:
                files.append({'name': item, 'path': full_path, 'ext': ext, 'time': mod_time})
        elif os.path.isdir(full_path):
            folders.append({'name': item, 'path': full_path})

    print(f"\n📊 桌面概览:")
    print(f"   文件: {len(files)} 个")
    print(f"   快捷方式: {len(shortcuts)} 个")
    print(f"   文件夹: {len(folders)} 个")

    # 扩展名映射
    ext_categories = {
        '图片': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico'],
        '文档': ['.doc', '.docx', '.pdf', '.txt', '.xls', '.xlsx', '.ppt', '.pptx', '.md'],
        '视频': ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'],
        '音频': ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a'],
        '代码': ['.py', '.js', '.java', '.c', '.cpp', '.h', '.html', '.css', '.json', '.xml'],
        '压缩包': ['.zip', '.rar', '.7z', '.tar', '.gz'],
    }

    icon_map = {'图片': '🖼️', '文档': '📄', '视频': '🎬', '音频': '🎵', '代码': '💻', '压缩包': '📦', '其他': '📁'}

    # 根据模式分类
    categories = {}
    operations = []

    if mode == 'type':
        # 按类型分类
        categories = {cat: [] for cat in ext_categories}
        categories['其他'] = []

        for f in files:
            categorized = False
            for cat, extensions in ext_categories.items():
                if f['ext'] in extensions:
                    categories[cat].append(f)
                    categorized = True
                    break
            if not categorized:
                categories['其他'].append(f)

        print(f"\n📋 分类预览 (按类型):")
        for cat, items in categories.items():
            if items:
                icon = icon_map.get(cat, '📁')
                print(f"\n   {icon} {cat} ({len(items)} 个):")
                for item in items[:5]:
                    print(f"      - {item['name']}")
                if len(items) > 5:
                    print(f"      ... 还有 {len(items) - 5} 个")

    elif mode == 'time':
        # 按时间分类
        categories = {}

        for f in files:
            year = f['time'].strftime('%Y')
            month = f['time'].strftime('%Y-%m')
            if year not in categories:
                categories[year] = {}
            if month not in categories[year]:
                categories[year][month] = []
            categories[year][month].append(f)

        print(f"\n📋 分类预览 (按时间):")
        for year in sorted(categories.keys(), reverse=True):
            months = categories[year]
            total = sum(len(items) for items in months.values())
            print(f"\n   📅 {year}年 ({total} 个):")
            for month in sorted(months.keys(), reverse=True):
                items = months[month]
                print(f"      📆 {month} ({len(items)} 个)")
                for item in items[:3]:
                    print(f"         - {item['name']}")
                if len(items) > 3:
                    print(f"         ... 还有 {len(items) - 3} 个")

    elif mode == 'project':
        # 按项目分类
        project_keywords = {
            '项目': ['project', '项目', 'pro', 'app', '应用', '小程序', 'app'],
            '工作': ['work', '工作', 'job', 'office', '商务'],
            '学习': ['learn', '学习', 'study', '课程', '笔记', 'note'],
            '个人': ['personal', '个人', 'private', '生活', '照片'],
            '资料': ['doc', '文档', '资料', 'file', '文件', 'pdf'],
        }

        categories = {cat: [] for cat in project_keywords}
        categories['未分类'] = []

        for f in files:
            name_lower = f['name'].lower()
            categorized = False
            for cat, keywords in project_keywords.items():
                if any(kw in name_lower for kw in keywords):
                    categories[cat].append(f)
                    categorized = True
                    break
            if not categorized:
                categories['未分类'].append(f)

        print(f"\n📋 分类预览 (按项目):")
        for cat, items in categories.items():
            if items:
                icon = icon_map.get(cat, '📁')
                print(f"\n   {icon} {cat} ({len(items)} 个):")
                for item in items[:5]:
                    print(f"      - {item['name']}")
                if len(items) > 5:
                    print(f"      ... 还有 {len(items) - 5} 个")

    # 快捷方式单独处理
    if shortcuts:
        print(f"\n   📁 快捷方式 ({len(shortcuts)} 个):")
        for s in shortcuts[:5]:
            print(f"      - {s['name']}")
        if len(shortcuts) > 5:
            print(f"      ... 还有 {len(shortcuts) - 5} 个")

    # 确认执行
    print(f"\n" + "=" * 50)
    print(f"整理模式: {mode}")
    if args.execute:
        print("🛠️  执行整理...")
    else:
        print("🔍 预览模式 (添加 --execute 执行整理)")

    # 执行整理
    created_folders = []

    if mode == 'type':
        for cat, items in categories.items():
            if items:
                folder_path = os.path.join(desktop, cat)
                if not os.path.exists(folder_path):
                    if args.execute:
                        os.makedirs(folder_path)
                    created_folders.append(cat)
                    print(f"\n📂 {'创建文件夹' if args.execute else '将创建'}: {cat}/")
                for item in items:
                    new_path = os.path.join(folder_path, item['name'])
                    operations.append({'from': item['path'], 'to': new_path})
                    if args.execute:
                        try:
                            os.rename(item['path'], new_path)
                            print(f"   ✓ 移动: {item['name']} → {cat}/")
                        except Exception as e:
                            print(f"   ✗ 失败: {item['name']} - {e}")

    elif mode == 'time':
        for year, months in sorted(categories.items(), reverse=True):
            for month, items in sorted(months.items(), reverse=True):
                folder_path = os.path.join(desktop, month)
                if not os.path.exists(folder_path):
                    if args.execute:
                        os.makedirs(folder_path)
                    created_folders.append(month)
                    print(f"\n📂 {'创建文件夹' if args.execute else '将创建'}: {month}/")
                for item in items:
                    new_path = os.path.join(folder_path, item['name'])
                    operations.append({'from': item['path'], 'to': new_path})
                    if args.execute:
                        try:
                            os.rename(item['path'], new_path)
                            print(f"   ✓ 移动: {item['name']} → {month}/")
                        except Exception as e:
                            print(f"   ✗ 失败: {item['name']} - {e}")

    elif mode == 'project':
        for cat, items in categories.items():
            if items:
                folder_path = os.path.join(desktop, cat)
                if not os.path.exists(folder_path):
                    if args.execute:
                        os.makedirs(folder_path)
                    created_folders.append(cat)
                    print(f"\n📂 {'创建文件夹' if args.execute else '将创建'}: {cat}/")
                for item in items:
                    new_path = os.path.join(folder_path, item['name'])
                    operations.append({'from': item['path'], 'to': new_path})
                    if args.execute:
                        try:
                            os.rename(item['path'], new_path)
                            print(f"   ✓ 移动: {item['name']} → {cat}/")
                        except Exception as e:
                            print(f"   ✗ 失败: {item['name']} - {e}")

    # 移动快捷方式
    if shortcuts:
        shortcut_folder = os.path.join(desktop, '快捷方式')
        if not os.path.exists(shortcut_folder):
            if args.execute:
                os.makedirs(shortcut_folder)
            created_folders.append('快捷方式')
            print(f"\n📂 {'创建文件夹' if args.execute else '将创建'}: 快捷方式/")
        for s in shortcuts:
            new_path = os.path.join(shortcut_folder, s['name'])
            operations.append({'from': s['path'], 'to': new_path})
            if args.execute:
                try:
                    os.rename(s['path'], new_path)
                    print(f"   ✓ 移动: {s['name']} → 快捷方式/")
                except Exception as e:
                    print(f"   ✗ 失败: {s['name']} - {e}")

    # 保存操作记录（用于撤销）
    if args.execute and operations:
        import json
        undo_file = os.path.join(desktop, '.desktop_org_undo.json')
        with open(undo_file, 'w', encoding='utf-8') as f:
            json.dump(operations, f, ensure_ascii=False, indent=2)
        print(f"\n💡 整理记录已保存，如需撤销请使用 --undo")

    if args.execute:
        print(f"\n✅ 整理完成!")
        print(f"   已创建 {len(created_folders)} 个文件夹")
        print(f"   已整理 {len(operations)} 个项目")
    else:
        print(f"\n💡 添加 --execute 执行此次整理")

    return 0


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
  %(prog)s --desktop                 整理桌面文件
  %(prog)s --desktop --execute        执行桌面整理
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
    parser.add_argument('--desktop', action='store_true', help='整理桌面文件')
    parser.add_argument('--desktop-mode', choices=['type', 'time', 'project'], default='type', help='桌面整理模式: type=按类型, time=按时间, project=按项目')
    parser.add_argument('--undo', action='store_true', help='撤销上次桌面整理')
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
    if not any([args.analyze, args.large_files, args.duplicates, args.stats, args.serve, args.export, args.suggest, args.chat, args.monitor, args.cleanup_duplicates, args.cleanup_large, args.desktop]):
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
        elif args.undo:
            return cmd_desktop_undo(agent, args)
        elif args.desktop:
            return cmd_desktop(agent, args)
    finally:
        agent.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
