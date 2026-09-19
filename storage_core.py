"""Read-only inventory and independently verified, reversible archive production."""
import csv
import gzip
import hashlib
import io
import json
import math
import os
import stat
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

CHUNK = 1024 * 1024
TEXT = {'.txt', '.log', '.csv', '.tsv', '.json', '.xml', '.html', '.md', '.sql', '.yaml', '.yml'}
IMAGES = {'.jpg', '.jpeg', '.png', '.heic', '.tif', '.tiff', '.bmp', '.webp'}
MEDIA = {'.mp4', '.mov', '.avi', '.mp3', '.wav', '.mkv'}
ARCHIVES = {'.zip', '.gz', '.7z', '.rar', '.xz', '.bz2'}


def now():
    return datetime.now(timezone.utc).isoformat()


def category(name):
    ext = Path(name).suffix.lower()
    if ext in TEXT:
        return '文本与日志'
    if ext in IMAGES:
        return '图片与扫描件'
    if ext in MEDIA:
        return '音视频'
    if ext in ARCHIVES:
        return '压缩归档'
    if ext in {'.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx'}:
        return '办公文档'
    return '其他'


def digest_stream(stream):
    digest = hashlib.sha256()
    size = 0
    for block in iter(lambda: stream.read(CHUNK), b''):
        digest.update(block)
        size += len(block)
    return digest.hexdigest(), size


def stable_file(path, root):
    """Reject symlinks/junction escapes and files changed since inventory."""
    path, root = Path(path), Path(root).resolve()
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError('文件已移出扫描目录')
    current = path
    while current != root:
        if current.is_symlink() or current.is_junction():
            raise ValueError('不处理符号链接或目录联接')
        current = current.parent
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('不是普通文件')
    return info


def summarize(report):
    groups = {}
    kinds = {}
    for item in report['files']:
        kinds[item['category']] = kinds.get(item['category'], 0) + item['size']
        if item.get('sha256') and item['size'] and not item.get('hardlink_of'):
            groups.setdefault((item['sha256'], item['size']), []).append(item)
    duplicates = []
    for (sha, size), items in groups.items():
        if len(items) > 1:
            duplicates.append({'sha256': sha, 'size': size, 'ids': [x['id'] for x in items],
                               'potential_bytes': size * (len(items) - 1)})
            for item in items[1:]:
                item['duplicate_of'] = items[0]['id']
    report['duplicates'] = duplicates
    report['summary'] = {'files': len(report['files']), 'bytes': sum(kinds.values()),
                         'categories': kinds, 'duplicate_bytes': sum(g['potential_bytes'] for g in duplicates),
                         'text_bytes': sum(x['size'] for x in report['files'] if x['category'] == '文本与日志'),
                         'actual_reclaimed_bytes': 0, 'errors': len(report['errors'])}
    return report


def scan_local(root, progress=lambda x: None, exclude=None):
    root = Path(root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError('请输入存在的目录')
    exclude = Path(exclude).resolve() if exclude else None
    if exclude and root.is_relative_to(exclude):
        raise ValueError('不能扫描应用生成的数据目录')
    report = {'id': uuid.uuid4().hex, 'source': 'local', 'root': str(root), 'created_at': now(),
              'files': [], 'errors': [], 'complete': True}
    inodes = {}
    def walk_error(err):
        report['errors'].append({'path': str(err.filename), 'error': str(err)})
    for directory, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        dirs[:] = [d for d in dirs if d not in {'.git', '.venv', '__pycache__'}
                   and not (Path(directory) / d).is_symlink()
                   and not (Path(directory) / d).is_junction()
                   and (not exclude or not (Path(directory) / d).resolve().is_relative_to(exclude))]
        for name in names:
            path = Path(directory) / name
            relative = str(path.relative_to(root))
            try:
                before = stable_file(path, root)
                with path.open('rb') as stream:
                    sha, size = digest_stream(stream)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino) or size != before.st_size:
                    raise ValueError('扫描时文件发生变化，已排除')
                identity = (before.st_dev, before.st_ino)
                hardlink_of = inodes.get(identity) if before.st_ino else None
                record_id = uuid.uuid4().hex
                report['files'].append({'id': record_id, 'name': name, 'path': relative,
                                        'size': size, 'mtime': before.st_mtime, 'mtime_ns': before.st_mtime_ns,
                                        'sha256': sha, 'category': category(name),
                                        'hardlink_of': hardlink_of,
                                        'link_count': before.st_nlink,
                                        'archive_eligible': Path(name).suffix.lower() in TEXT and size > 0 and before.st_nlink == 1})
                if before.st_ino:
                    inodes.setdefault(identity, record_id)
            except (OSError, ValueError) as exc:
                report['errors'].append({'path': relative, 'error': str(exc)})
            if len(report['files']) % 25 == 0:
                progress({'files': len(report['files']), 'current': relative})
            if len(report['files']) >= 100000:
                report['complete'] = False
                report['errors'].append({'path': '', 'error': '已到 100000 文件上限；结果为部分盘点'})
                return summarize(report)
    return summarize(report)


def scan_s3(config, progress=lambda x: None):
    try:
        import boto3
    except ImportError as exc:
        raise ValueError('请先执行 pip install -r requirements.txt 安装 S3 支持') from exc
    bucket = str(config.get('bucket', '')).strip()
    if not bucket:
        raise ValueError('必须填写 Bucket')
    endpoint = str(config.get('endpoint', '')).strip() or None
    if endpoint and not endpoint.startswith('https://'):
        raise ValueError('自定义 S3 endpoint 必须使用 HTTPS')
    session = boto3.Session(profile_name=config.get('profile') or None, region_name=config.get('region') or None)
    client = session.client('s3', endpoint_url=endpoint)
    report = {'id': uuid.uuid4().hex, 'source': 's3', 'root': f"s3://{bucket}/{config.get('prefix', '')}",
              'created_at': now(), 'files': [], 'errors': [], 'complete': True,
              'scope_note': '仅当前对象元数据；不含历史版本、删除标记、分段上传及副本。ETag 不用作内容去重依据。'}
    for page in client.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=config.get('prefix', '')):
        for obj in page.get('Contents', []):
            key = obj['Key']
            report['files'].append({'id': uuid.uuid4().hex, 'name': key.rsplit('/', 1)[-1], 'path': key,
                                   'size': obj['Size'], 'mtime': obj['LastModified'].timestamp(),
                                   'category': category(key), 'sha256': None, 'archive_eligible': False,
                                   'storage_class': obj.get('StorageClass', 'STANDARD')})
            if len(report['files']) >= 100000:
                report['complete'] = False
                report['errors'].append({'path': '', 'error': '已到 100000 对象上限；结果为部分盘点'})
                return summarize(report)
        progress({'files': len(report['files']), 'current': report['root']})
    return summarize(report)


def create_archives(report, ids, output_root, progress=lambda x: None):
    if report['source'] != 'local':
        raise ValueError('当前版本仅生成本地文件归档；云端连接为只读盘点')
    if not ids or len(ids) > 500:
        raise ValueError('一次请选择 1—500 个文本文件')
    selected = [x for x in report['files'] if x['id'] in set(ids)]
    if len(selected) != len(set(ids)):
        raise ValueError('选择包含不存在的文件')
    batch = Path(output_root) / uuid.uuid4().hex
    batch.mkdir(parents=True)
    manifest = {'id': batch.name, 'report_id': report['id'], 'created_at': now(), 'items': [], 'errors': [],
                'source_deleted': False, 'actual_reclaimed_bytes': 0}
    for item in selected:
        dest = None
        try:
            if not item['archive_eligible']:
                raise ValueError('仅支持文本、日志及结构化文本归档')
            path = Path(report['root']) / item['path']
            before = stable_file(path, report['root'])
            if before.st_size != item['size'] or before.st_mtime_ns != item['mtime_ns']:
                raise ValueError('源文件已变化，请重新扫描')
            dest = batch / (item['id'] + '.gz')
            with path.open('rb') as source, dest.open('wb') as raw:
                with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as encoded:
                    for block in iter(lambda: source.read(CHUNK), b''):
                        encoded.write(block)
            with gzip.open(dest, 'rb') as decoded:
                restored_sha, restored_size = digest_stream(decoded)
            after = stable_file(path, report['root'])
            if restored_sha != item['sha256'] or restored_size != item['size'] or before.st_mtime_ns != after.st_mtime_ns:
                dest.unlink(missing_ok=True)
                raise ValueError('源文件变化或恢复校验失败；已丢弃归档')
            packed = dest.stat().st_size
            if packed >= item['size']:
                dest.unlink()
                raise ValueError('压缩后没有收益，未保留归档')
            manifest['items'].append({'file_id': item['id'], 'source_path': item['path'], 'original_bytes': item['size'],
                                      'archive': dest.name, 'archive_bytes': packed, 'sha256': item['sha256'],
                                      'potential_bytes': item['size'] - packed, 'verified': True})
        except (OSError, ValueError) as exc:
            if dest is not None:
                dest.unlink(missing_ok=True)
            manifest['errors'].append({'path': item['path'], 'error': str(exc)})
        progress({'files': len(manifest['items']), 'current': item['path']})
    (batch / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest['manifest_bytes'] = (batch / 'manifest.json').stat().st_size
    manifest['net_potential_bytes'] = max(0, sum(x['potential_bytes'] for x in manifest['items']) - manifest['manifest_bytes'])
    return manifest


def restore_archive(manifest, output_root, restore_root):
    folder = Path(restore_root) / uuid.uuid4().hex
    folder.mkdir(parents=True)
    restored = []
    try:
        for item in manifest['items']:
            # Use generated IDs, never source-relative paths, to prevent overwrite or traversal.
            target = folder / (item['file_id'] + Path(item['source_path']).suffix)
            source = Path(output_root) / manifest['id'] / item['archive']
            with gzip.open(source, 'rb') as decoded, target.open('xb') as dest:
                count = 0
                for block in iter(lambda: decoded.read(CHUNK), b''):
                    count += len(block)
                    if count > item['original_bytes']:
                        raise ValueError('归档解压大小超出记录')
                    dest.write(block)
            with target.open('rb') as file:
                sha, size = digest_stream(file)
            if sha != item['sha256'] or size != item['original_bytes']:
                raise ValueError('恢复内容校验失败')
            restored.append({'path': str(target), 'source_path': item['source_path'], 'verified': True})
    except Exception:
        # Only remove files created inside this new, private recovery directory.
        for child in folder.iterdir():
            if child.is_file():
                child.unlink()
        folder.rmdir()
        raise
    return {'folder': str(folder), 'files': restored}


def economics(report, manifest, local_rate, cloud_rate, processing_cost):
    rates = [float(x) for x in (local_rate, cloud_rate, processing_cost)]
    if any(not math.isfinite(x) or x < 0 for x in rates):
        raise ValueError('费用必须为有限的非负数')
    duplicate_ids = {i for g in report['duplicates'] for i in g['ids'][1:]}
    compression = sum(x['potential_bytes'] for x in (manifest or {}).get('items', []) if x['file_id'] not in duplicate_ids)
    overhead = (manifest or {}).get('manifest_bytes', 0)
    potential = max(0, report['summary']['duplicate_bytes'] + compression - overhead)
    gb = potential / 1_000_000_000
    local, cloud, processing = rates
    return {'potential_bytes': potential, 'local_annual': gb * local * 12,
            'cloud_annual': gb * cloud * 12, 'local_first_year_net': gb * local * 12 - processing,
            'cloud_first_year_net': gb * cloud * 12 - processing, 'processing_cost': processing,
            'actual_reclaimed_bytes': 0,
            'note': '本地与云端为两种独立情景，不自动相加。单价为用户输入的可避免边际成本；不含迁移/请求/取回费用。原件仍保留，节省尚未实现。'}


def export_csv(report):
    out = io.StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow(['路径', '类型', '字节数', 'SHA256', '重复于', '可归档'])
    def safe(value):
        value = str(value)
        return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value
    for item in report['files']:
        writer.writerow([safe(item['path']), item['category'], item['size'], item.get('sha256') or '',
                         item.get('duplicate_of', ''), item['archive_eligible']])
    return '\ufeff' + out.getvalue()


def extract_images(report, ids, output_root, progress=lambda x: None):
    if os.name != 'nt':
        raise ValueError('本版本图片提取需要 Windows OCR 和系统语言包')
    if report['source'] != 'local' or not ids or len(ids) > 50:
        raise ValueError('请选择 1—50 张本地 PNG/JPEG/BMP 图片')
    selected = [x for x in report['files'] if x['id'] in set(ids)]
    if len(selected) != len(set(ids)):
        raise ValueError('无效文件选择')
    batch = Path(output_root) / uuid.uuid4().hex
    batch.mkdir(parents=True)
    result = {'id': batch.name, 'report_id': report['id'], 'created_at': now(), 'items': [], 'errors': [],
              'source_deleted': False, 'quality_status': 'needs_human_review', 'actual_reclaimed_bytes': 0}
    script = Path(__file__).parent / 'scripts' / 'windows_ocr.ps1'
    for item in selected:
        try:
            if Path(item['name']).suffix.lower() not in {'.png', '.jpg', '.jpeg', '.bmp'}:
                raise ValueError('当前仅处理 PNG/JPEG/BMP 图片')
            source = Path(report['root']) / item['path']
            stable_file(source, report['root'])
            # OCR uses a verified temporary copy, independent from concurrent source changes.
            snapshot = batch / (item['id'] + Path(item['name']).suffix)
            try:
                with source.open('rb') as inp, snapshot.open('xb') as out:
                    digest = hashlib.sha256()
                    for block in iter(lambda: inp.read(CHUNK), b''):
                        digest.update(block)
                        out.write(block)
                if digest.hexdigest() != item['sha256']:
                    raise ValueError('图片已变化，请重新扫描')
                completed = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                            '-File', str(script), '-InputPath', str(snapshot.resolve())],
                                           capture_output=True, encoding='utf-8', errors='replace', timeout=90,
                                           creationflags=subprocess.CREATE_NO_WINDOW)
                if completed.returncode:
                    raise ValueError('OCR 引擎失败：' + completed.stderr[:500])
                extracted = json.loads(completed.stdout.lstrip('\ufeff'))
            finally:
                snapshot.unlink(missing_ok=True)
            if not extracted.get('text', '').strip():
                raise ValueError('没有识别到文字，保留原图')
            text_path = batch / (item['id'] + '.txt')
            text_path.write_text('\n'.join(x['text'] for x in extracted['lines']), encoding='utf-8')
            structure_path = batch / (item['id'] + '.json')
            structure_path.write_text(json.dumps(extracted, ensure_ascii=False), encoding='utf-8')
            derived = text_path.stat().st_size + structure_path.stat().st_size
            result['items'].append({'file_id': item['id'], 'source_path': item['path'], 'source_sha256': item['sha256'],
                                    'original_bytes': item['size'], 'derived_bytes': derived,
                                    'text_path': str(text_path), 'structure_path': str(structure_path),
                                    'text': text_path.read_text(encoding='utf-8'), 'language': extracted['language'],
                                    'quality_status': 'needs_human_review'})
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            result['errors'].append({'path': item['path'], 'error': str(exc)})
        progress({'files': len(result['items']), 'current': item['path']})
    (batch / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result
