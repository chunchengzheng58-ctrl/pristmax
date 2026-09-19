"""Local customer-controlled custody. No source deletion or remote transport."""
import json
import os
import time
import uuid
from functools import wraps
from pathlib import Path
from durability import atomic_json, exclusive_lock, sync_file

from deep_archive import create_bundle, restore_bundle, inspect_bundle, safe_relative, CODECS
from storage_core import scan_local, stable_file, digest_stream, now


def serialized(operation):
    @wraps(operation)
    def guarded(self, *args, **kwargs):
        with exclusive_lock(self.root / '.operation.lock'):
            return operation(self, *args, **kwargs)
    return guarded


class Vault:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def directory(self, identifier):
        if len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier):
            raise ValueError('无效保管编号')
        path = self.root / identifier
        if path.is_symlink() or path.resolve().parent != self.root:
            raise ValueError('保管路径异常')
        return path

    def save(self, record):
        path = self.directory(record['id']) / 'state.json'
        atomic_json(path, record)

    def read(self, identifier):
        return json.loads((self.directory(identifier) / 'state.json').read_text(encoding='utf-8'))

    def list(self):
        return [self.read(p.name) for p in self.root.iterdir() if p.is_dir() and (p / 'state.json').exists()]

    def archive_path(self, record):
        receipt = record['receipt']
        identifier = receipt['id']
        if len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier):
            raise ValueError('无效归档编号')
        if receipt['archive'] not in {'dataset' + x[1] for x in CODECS.values()}:
            raise ValueError('无效归档文件名')
        path = self.directory(record['id']) / 'bundles' / identifier / receipt['archive']
        stable_file(path, self.directory(record['id']))
        return path

    def verified_mapping(self, record):
        path = self.archive_path(record)
        with path.open('rb') as stream:
            digest, _ = digest_stream(stream)
        if record.get('archive_sha256') and digest != record['archive_sha256']:
            raise ValueError('归档与存入时指纹不一致，拒绝交付或清理')
        return inspect_bundle(path)

    @serialized
    def catalog(self, identifier):
        record = self.read(identifier)
        if record['status'] not in {'folded', 'awaiting_receipt'}:
            raise ValueError('当前状态不能读取归档目录')
        mapping = self.verified_mapping(record)
        return {'id': identifier, 'files': mapping['files'], 'verified': True,
                'baseline_verified': bool(record.get('archive_sha256'))}

    @serialized
    def health(self, identifier):
        record = self.read(identifier)
        if record['status'] not in {'folded', 'awaiting_receipt'}:
            raise ValueError('当前状态不能巡检')
        started = time.monotonic()
        try:
            mapping = self.verified_mapping(record)
            result = {'at': now(), 'status': 'healthy', 'verified_files': len(mapping['files']),
                      'baseline_verified': bool(record.get('archive_sha256'))}
        except Exception:
            result = {'at': now(), 'status': 'failed', 'verified_files': 0,
                      'note': '归档缺失、损坏或无法读取；原件和保管内容未清理。'}
        result['seconds'] = round(time.monotonic() - started, 3)
        record['health'] = result
        self.save(record)
        return {'id': identifier, **result}

    @serialized
    def retrieve(self, identifier, destination, paths):
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
            raise ValueError('请选择要取出的文件')
        record = self.read(identifier)
        if record['status'] != 'folded':
            raise ValueError('只允许从尚未交接的归档按需取出')
        mapping = self.verified_mapping(record)
        root = self.delivery_root(destination)
        result = restore_bundle(record['receipt'], self.directory(identifier) / 'bundles', root, paths, expected_mapping=mapping)
        return {'id': identifier, **result, 'archive_retained': True}

    def delivery_root(self, destination):
        root = Path(destination).resolve(strict=True)
        if not root.is_dir() or root.is_relative_to(self.root) or self.root.is_relative_to(root):
            raise ValueError('请选择保管区之外的独立、已存在交付目录')
        return root

    @serialized
    def fold(self, source, progress=lambda _: None):
        source = Path(source).resolve(strict=True)
        if source.is_relative_to(self.root) or self.root.is_relative_to(source):
            raise ValueError('源目录与保管区不能互相包含')
        report = scan_local(source, progress)
        if not report['complete'] or report['errors']:
            raise ValueError('扫描不完整或有异常，不能作为完整保管任务')
        # Do not silently accept scanner exclusions as a complete custody inventory.
        discovered = set()
        def fail_walk(error):
            raise error
        for parent, dirs, names in os.walk(source, onerror=fail_walk):
            for name in dirs:
                path = Path(parent) / name
                if path.is_symlink() or path.is_junction():
                    raise ValueError('保管目录包含不支持的链接目录')
            for name in names:
                path = Path(parent) / name
                stable_file(path, source)
                discovered.add(path.relative_to(source).as_posix())
        if discovered != {f['path'].replace('\\', '/') for f in report['files']}:
            raise ValueError('目录含有扫描排除文件，请拆分资料后重试；未创建归档')
        identifier = uuid.uuid4().hex
        folder = self.directory(identifier)
        folder.mkdir()
        try:
            receipt = create_bundle(report, [f['id'] for f in report['files']], folder / 'bundles', progress, preserve_mtime=True)
            record = {'id': identifier, 'status': 'folded', 'receipt': receipt,
                      'file_count': receipt['file_count'], 'original_bytes': receipt['original_bytes'],
                      'source_deleted': False, 'actual_reclaimed_bytes': 0}
            with self.archive_path(record).open('rb') as stream:
                record['archive_sha256'], _ = digest_stream(stream)
            record['metadata_profile'] = 'content-path-mtime-v1'
            self.save(record)
            return record
        except Exception:
            # Retain any completed artifact on state-write failure for recovery.
            if not list(folder.iterdir()):
                folder.rmdir()
            raise

    @serialized
    def checkout(self, identifier, destination):
        record = self.read(identifier)
        if record['status'] != 'folded':
            raise ValueError('当前状态不允许重复取出，请先完成已有交接')
        root = self.delivery_root(destination)
        mapping = self.verified_mapping(record)
        result = restore_bundle(record['receipt'], self.directory(identifier) / 'bundles', root, expected_mapping=mapping)
        record.update(status='awaiting_receipt', delivery=result['folder'])
        self.save(record)
        return record

    @serialized
    def release(self, identifier, acknowledged=False):
        record = self.read(identifier)
        if record['status'] == 'released':
            return record
        if acknowledged is not True or record['status'] not in {'awaiting_receipt', 'releasing'}:
            raise ValueError('必须先恢复并确认收妥文件')
        folder = self.directory(identifier)
        receipt = record['receipt']
        bundle_id = receipt['id']
        if len(bundle_id) != 32 or any(c not in '0123456789abcdef' for c in bundle_id):
            raise ValueError('无效归档编号')
        bundle = folder / 'bundles' / bundle_id
        if receipt['archive'] not in {'dataset' + x[1] for x in CODECS.values()}:
            raise ValueError('无效归档文件名')
        archive = bundle / receipt['archive']
        if bundle.resolve() != bundle or archive.is_symlink():
            raise ValueError('保管目录被替换，停止清理')
        mapping = self.verified_mapping(record) if archive.exists() else record.get('release_mapping')
        if not mapping:
            raise ValueError('缺少可验证的归档，停止清理')
        delivery = Path(record['delivery'])
        if delivery.is_symlink() or delivery.resolve() != delivery or delivery.is_relative_to(self.root):
            raise ValueError('交付目录异常')
        for item in mapping['files']:
            path = delivery.joinpath(*safe_relative(item['path']).parts)
            stable_file(path, delivery)
            with path.open('rb') as stream:
                sha, size = digest_stream(stream)
            if (sha, size) != (item['sha256'], item['size']):
                raise ValueError('交付文件已变化或不完整，保管内容继续保留')
            if 'mtime_ns' in item and path.stat().st_mtime_ns != item['mtime_ns']:
                raise ValueError('交付文件修改时间已变化，保管内容继续保留')
            sync_file(path)
        allowed = {receipt['archive'], 'receipt.json'}
        if bundle.exists() and any(p.name not in allowed or not p.is_file() or p.is_symlink() for p in bundle.iterdir()):
            raise ValueError('保管区出现未知文件，停止清理')
        record.update(status='releasing', release_mapping=mapping)
        self.save(record)
        # Unlink only explicitly owned files; no recursive deletion or source access.
        for name in allowed:
            (bundle / name).unlink(missing_ok=True)
        if bundle.exists():
            bundle.rmdir()
        parent = folder / 'bundles'
        if parent.exists():
            parent.rmdir()
        result = {'id': identifier, 'status': 'released', 'file_count': record['file_count'],
                  'managed_archive_removed': True, 'source_deleted': False,
                  'note': '已清理本任务保管归档；不包含系统快照、外部备份或介质物理擦除保证。'}
        self.save(result)
        return result
