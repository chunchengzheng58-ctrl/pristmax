"""Content-addressed, deduplicated solid archives with verified restoration."""
import bz2
import gzip
import hashlib
import io
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import time
import uuid

from storage_core import CHUNK, digest_stream, stable_file, now
from durability import sync_file, sync_directory

CODECS = {'gzip': (gzip.open, '.tar.gz'), 'bzip2': (bz2.open, '.tar.bz2'), 'xz': (lzma.open, '.tar.xz')}


def safe_relative(name):
    if not isinstance(name, str) or not name or '\x00' in name:
        raise ValueError('不安全的归档路径')
    path = PurePosixPath(name.replace('\\', '/'))
    if path.is_absolute() or not path.parts or any(p in {'..', '.'} or ':' in p for p in path.parts):
        raise ValueError('不安全的归档路径')
    reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{p}{i}' for p in ('COM', 'LPT') for i in range(1, 10)}
    if any(p.endswith((' ', '.')) or p.split('.')[0].upper() in reserved for p in path.parts):
        raise ValueError('归档路径包含 Windows 保留名称')
    return path


def check_sources(report, files):
    for item in files:
        path = Path(report['root']) / item['path']
        info = stable_file(path, report['root'])
        if info.st_nlink != 1:
            raise ValueError('文件存在硬链接，需单独评估：' + item['path'])
        with path.open('rb') as stream:
            sha, size = digest_stream(stream)
        if sha != item['sha256'] or size != item['size']:
            raise ValueError('源文件已变化，请重新扫描：' + item['path'])


def inspect_bundle(path, expected=None):
    """Stream and validate all contents, reject unknown/duplicate members and links."""
    with tarfile.open(path, 'r|*') as archive:
        first = archive.next()
        if first is None or first.name != 'manifest.json' or not first.isfile() or first.size > 8 * CHUNK:
            raise ValueError('归档清单无效')
        mapping = json.load(archive.extractfile(first))
        if not isinstance(mapping, dict) or mapping.get('format') != 'storage-atlas-bundle-v1':
            raise ValueError('未知归档格式')
        if not isinstance(mapping.get('files'), list) or not 1 <= len(mapping['files']) <= 2000:
            raise ValueError('归档文件数量超出限制')
        if expected is not None and mapping != expected:
            raise ValueError('归档清单不一致')
        blobs, paths = {}, set()
        for item in mapping['files']:
            if not isinstance(item, dict) or not {'path', 'sha256', 'size'}.issubset(item):
                raise ValueError('文件清单字段缺失')
            normalized = str(safe_relative(item['path'])).casefold()
            if normalized in paths:
                raise ValueError('归档路径冲突')
            paths.add(normalized)
            if 'mtime_ns' in item and (type(item['mtime_ns']) is not int or not 0 <= item['mtime_ns'] < 2**63):
                raise ValueError('文件修改时间无效')
            sha, size = item['sha256'], item['size']
            if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha) or type(size) is not int or size < 0:
                raise ValueError('内容记录无效')
            if sha in blobs and blobs[sha] != size:
                raise ValueError('内容大小冲突')
            blobs[sha] = size
        if sum(item['size'] for item in mapping['files']) > 20 * 1000**3:
            raise ValueError('归档恢复体积超出单批限制')
        for name in paths:
            if any(str(parent) in paths for parent in PurePosixPath(name).parents if str(parent) != '.'):
                raise ValueError('文件与目录路径冲突')
        seen = set()
        for member in archive:
            if member.name == 'manifest.json' and not seen:
                # TarFile iteration may revisit the first member returned by next().
                if member is first:
                    continue
            sha = member.name.removeprefix('blobs/')
            if not member.isfile() or member.name != 'blobs/' + sha or sha not in blobs or sha in seen or member.size != blobs[sha]:
                raise ValueError('归档内容结构无效')
            actual_sha, actual_size = digest_stream(archive.extractfile(member))
            if actual_sha != sha or actual_size != blobs[sha]:
                raise ValueError('归档内容校验失败')
            seen.add(sha)
        if seen != set(blobs):
            raise ValueError('归档缺少文件内容')
        return mapping


def create_bundle(report, ids, output_root, progress=lambda value: None, preserve_mtime=False):
    if report['source'] != 'local':
        raise ValueError('深度归档需要本地或已挂载 NAS 数据')
    ids = set(ids)
    files = [x for x in report['files'] if x['id'] in ids]
    if not files or len(files) != len(ids) or len(files) > 2000:
        raise ValueError('一次请选择 1—2000 个文件')
    if sum(x['size'] for x in files) > 20 * 1000**3:
        raise ValueError('本次试点单批上限为 20GB，请缩小范围')
    files.sort(key=lambda x: (Path(x['path']).suffix.lower(), x['path']))
    mapping = {'format': 'storage-atlas-bundle-v1', 'files': [
        {'path': str(safe_relative(x['path'])), 'sha256': x['sha256'], 'size': x['size']} for x in files]}
    if preserve_mtime:
        for item in mapping['files']:
            item['mtime_ns'] = stable_file(Path(report['root']) / item['path'], report['root']).st_mtime_ns
    metadata = json.dumps(mapping, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    check_sources(report, files)
    identifier = hashlib.sha256(metadata).hexdigest()[:32]
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / identifier
    if (target / 'receipt.json').exists():
        result = json.loads((target / 'receipt.json').read_text(encoding='utf-8'))
        inspect_bundle(target / result['archive'], mapping)
        return {**result, 'report_id': report['id'], 'reused': True}
    work = output_root / ('pending-' + uuid.uuid4().hex)
    work.mkdir()
    try:
        unique = {}
        for item in files:
            unique.setdefault(item['sha256'], item)
        trials, best = [], None
        for codec, (opener, suffix) in CODECS.items():
            started = time.monotonic()
            candidate = work / ('dataset' + suffix)
            with opener(candidate, 'wb', **({'preset': 6} if codec == 'xz' else {'compresslevel': 9})) as compressed:
                with tarfile.open(fileobj=compressed, mode='w|', format=tarfile.USTAR_FORMAT) as archive:
                    header = tarfile.TarInfo('manifest.json')
                    header.size = len(metadata)
                    archive.addfile(header, io.BytesIO(metadata))
                    for index, item in enumerate(unique.values()):
                        source = Path(report['root']) / item['path']
                        stable_file(source, report['root'])
                        header = tarfile.TarInfo('blobs/' + item['sha256'])
                        header.size = item['size']
                        with source.open('rb') as data:
                            archive.addfile(header, data)
                        progress({'files': index + 1, 'current': f'{codec.upper()} · {item["path"]}'})
            inspect_bundle(candidate, mapping)
            size = candidate.stat().st_size
            trials.append({'codec': codec, 'bytes': size, 'seconds': round(time.monotonic() - started, 3)})
            if best is None or size < best.stat().st_size:
                if best is not None:
                    best.unlink()
                best = candidate
            else:
                candidate.unlink()
        check_sources(report, files)
        if preserve_mtime:
            for item in mapping['files']:
                if stable_file(Path(report['root']) / item['path'], report['root']).st_mtime_ns != item['mtime_ns']:
                    raise ValueError('源文件修改时间发生变化，请重新折叠')
        original = sum(x['size'] for x in files)
        result = {'id': identifier, 'report_id': report['id'], 'created_at': now(), 'archive': best.name,
                  'codec': min(trials, key=lambda x: x['bytes'])['codec'], 'archive_bytes': best.stat().st_size,
                  'original_bytes': original, 'file_count': len(files), 'unique_contents': len(unique),
                  'dedup_bytes': original - sum(x['size'] for x in unique.values()), 'trials': trials,
                  'verified': True, 'reused': False, 'source_deleted': False, 'actual_reclaimed_bytes': 0,
                  'net_potential_bytes': 0, 'receipt_bytes': 0}
        receipt = work / 'receipt.json'
        # Include the receipt in the measured footprint; converge its self-size fields.
        for _ in range(12):
            encoded = json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8')
            result['net_potential_bytes'] = max(0, original - result['archive_bytes'] - len(encoded))
            if result['receipt_bytes'] == len(encoded):
                break
            result['receipt_bytes'] = len(encoded)
        receipt.write_bytes(json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8'))
        if result['net_potential_bytes'] <= 0:
            raise ValueError('计入清单后无净缩减收益，已丢弃所有候选，原件未修改')
        sync_file(best)
        sync_file(receipt)
        sync_directory(work)
        work.rename(target)
        sync_directory(output_root)
        return result
    finally:
        # All paths here are generated children of the application's bundle directory.
        if work.exists() and work.parent == output_root and work.name.startswith('pending-'):
            for child in work.iterdir():
                if child.is_file():
                    child.unlink()
            work.rmdir()


def restore_bundle(receipt, output_root, restore_root, selected_paths=None, expected_mapping=None):
    identifier = receipt['id']
    if len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier):
        raise ValueError('无效归档 ID')
    filename = receipt['archive']
    if filename not in {'dataset' + x[1] for x in CODECS.values()}:
        raise ValueError('无效归档文件名')
    source = Path(output_root) / identifier / filename
    mapping = inspect_bundle(source, expected_mapping)
    full_mapping = mapping
    if selected_paths is not None:
        if not isinstance(selected_paths, list) or not selected_paths or not all(isinstance(p, str) for p in selected_paths):
            raise ValueError('请提供非空文件路径列表')
        selected = set(selected_paths)
        if len(selected) != len(selected_paths) or not selected.issubset({x['path'] for x in mapping['files']}):
            raise ValueError('所选文件不存在或重复')
        mapping = {**mapping, 'files': [x for x in mapping['files'] if x['path'] in selected]}
    restore_root = Path(restore_root).resolve()
    disk_path = restore_root
    while not disk_path.exists():
        disk_path = disk_path.parent
    if shutil.disk_usage(disk_path).free < sum(x['size'] for x in mapping['files']) + CHUNK:
        raise ValueError('交付目录磁盘空间不足，未开始恢复')
    identifier = uuid.uuid4().hex
    target = restore_root / ('.pending-' + identifier)
    target.mkdir(parents=True)
    try:
        by_sha = {}
        for item in mapping['files']:
            destination = target.joinpath(*safe_relative(item['path']).parts)
            if not destination.resolve().is_relative_to(target):
                raise ValueError('恢复路径越界')
            by_sha.setdefault(item['sha256'], []).append(destination)
        with tarfile.open(source, 'r|*') as archive:
            seen = set()
            expected_blobs = {x['sha256']: x['size'] for x in full_mapping['files']}
            first = archive.next()
            if first is None or first.name != 'manifest.json' or not first.isfile() or first.size > 8 * CHUNK:
                raise ValueError('恢复时归档清单发生变化')
            if json.load(archive.extractfile(first)) != full_mapping:
                raise ValueError('恢复时归档清单发生变化')
            for member in archive:
                if member is first:
                    continue
                sha = member.name.removeprefix('blobs/')
                if member.name != 'blobs/' + sha or not member.isfile() or sha not in expected_blobs or sha in seen or member.size != expected_blobs[sha]:
                    raise ValueError('恢复时归档内容结构发生变化')
                seen.add(sha)
                if sha not in by_sha:
                    continue
                destinations = by_sha[sha]
                first = destinations[0]
                first.parent.mkdir(parents=True, exist_ok=True)
                with first.open('xb') as out:
                    shutil.copyfileobj(archive.extractfile(member), out, CHUNK)
                for other in destinations[1:]:
                    other.parent.mkdir(parents=True, exist_ok=True)
                    with first.open('rb') as inp, other.open('xb') as out:
                        shutil.copyfileobj(inp, out, CHUNK)
            if seen != set(expected_blobs):
                raise ValueError('恢复时归档缺少文件内容')
        for item in mapping['files']:
            restored = target.joinpath(*safe_relative(item['path']).parts)
            with restored.open('rb') as data:
                sha, size = digest_stream(data)
            if sha != item['sha256'] or size != item['size']:
                raise ValueError('恢复校验失败')
            if 'mtime_ns' in item:
                os.utime(restored, ns=(restored.stat().st_atime_ns, item['mtime_ns']))
                if restored.stat().st_mtime_ns != item['mtime_ns']:
                    raise ValueError('目标文件系统无法精确保留修改时间')
            sync_file(restored)
        sync_directory(target)
        final = restore_root / identifier
        target.rename(final)
        target = final
        sync_directory(restore_root)
        return {'folder': str(target), 'file_count': len(mapping['files']), 'verified': True,
                'partial': selected_paths is not None,
                'mtime_preserved': all('mtime_ns' in x for x in mapping['files'])}
    except Exception:
        # Delete only this newly created recovery directory, after checking its boundary.
        if target.parent == restore_root and target.resolve().parent == restore_root:
            shutil.rmtree(target)
        raise
