import argparse
import hashlib
import importlib.util
import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from storage_core import scan_local, scan_s3, create_archives, restore_archive, economics, export_csv, extract_images, stable_file, now
from deep_archive import create_bundle, restore_bundle, CODECS
from vault import Vault

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('STORAGE_ATLAS_DATA', str(BASE / 'data'))).resolve()
STATE = DATA / 'state'
for directory in (STATE, DATA / 'archives', DATA / 'restored'):
    directory.mkdir(parents=True, exist_ok=True)
JOBS = {}
LOCK = threading.RLock()
WORK = threading.Lock()
VAULT = Vault(DATA / 'vault')


def save(kind, value):
    with LOCK:
        target = STATE / f"{kind}-{value['id']}.json"
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        temp.replace(target)


def read(kind, identifier):
    if len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier):
        raise ValueError('无效记录 ID')
    with LOCK:
        return json.loads((STATE / f'{kind}-{identifier}.json').read_text(encoding='utf-8'))


def audit(action, details):
    with LOCK:
        with (DATA / 'audit.jsonl').open('a', encoding='utf-8') as file:
            file.write(json.dumps({'at': now(), 'action': action, 'details': details}, ensure_ascii=False) + '\n')


def start_job(action, operation):
    if not WORK.acquire(blocking=False):
        raise ValueError('已有任务正在运行，请完成后再提交')
    identifier = uuid.uuid4().hex
    JOBS[identifier] = {'id': identifier, 'action': action, 'status': 'running', 'progress': {'files': 0}, 'created_at': now()}
    def progress(value):
        with LOCK:
            JOBS[identifier]['progress'] = value
    def run():
        try:
            result = operation(progress)
            with LOCK:
                JOBS[identifier].update(status='done', result=result)
            audit(action, {'status': 'done', 'job': identifier, 'record_id': result.get('id')})
        except Exception as exc:
            with LOCK:
                JOBS[identifier].update(status='error', error=str(exc))
            audit(action, {'status': 'error', 'error': '操作未完成' if action in {'企业无损折叠', '独立还原交付', '核验交付并清理保管区', '归档目录校验', '归档完整性巡检', '选择性取出'} else str(exc)})
        finally:
            WORK.release()
    threading.Thread(target=run, daemon=True).start()
    return {'job_id': identifier}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def reply(self, value, code=200, content_type='application/json; charset=utf-8', download=None):
        body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if download:
            self.send_header('Content-Disposition', f'attachment; filename="{download}"')
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

    def do_GET(self):
        if not self.valid_host():
            return self.reply({'error': 'Host rejected'}, 403)
        path = urlparse(self.path).path
        try:
            if path == '/favicon.ico':
                return self.reply(b'', code=204, content_type='image/x-icon')
            if path in ('/', '/app.js', '/style.css'):
                filename = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[path]
                mime = {'/': 'text/html', '/app.js': 'text/javascript', '/style.css': 'text/css'}[path]
                return self.reply((BASE / 'web' / filename).read_bytes(), content_type=mime + '; charset=utf-8')
            if path == '/api/status':
                reports = [json.loads(f.read_text(encoding='utf-8')) for f in STATE.glob('report-*.json')]
                reports.sort(key=lambda x: x['created_at'], reverse=True)
                return self.reply({'s3_available': importlib.util.find_spec('boto3') is not None,
                                   'reports': [{k: r[k] for k in ('id', 'root', 'source', 'created_at', 'summary')} for r in reports],
                                   'data_directory': str(DATA), 'mode': 'local-single-operator'})
            if path == '/api/vault':
                return self.reply(VAULT.list())
            if path.startswith('/api/job/'):
                with LOCK:
                    return self.reply(JOBS[path.rsplit('/', 1)[1]])
            if path.startswith('/api/report/'):
                return self.reply(read('report', path.rsplit('/', 1)[1]))
            if path.startswith('/api/bundle-download/'):
                receipt = read('bundle', path.rsplit('/', 1)[1])
                if receipt['archive'] not in {'dataset' + x[1] for x in CODECS.values()}:
                    raise ValueError('无效归档名称')
                archive = DATA / 'bundles' / receipt['id'] / receipt['archive']
                with archive.open('rb') as stream:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Length', str(archive.stat().st_size))
                    self.send_header('Content-Disposition', f'attachment; filename="{receipt["archive"]}"')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.end_headers()
                    while block := stream.read(1024 * 1024):
                        self.wfile.write(block)
                return
            if path.startswith('/api/source/'):
                parts = path.split('/')
                if len(parts) != 5:
                    raise ValueError('无效图片地址')
                report = read('report', parts[3])
                item = next((f for f in report['files'] if f['id'] == parts[4]), None)
                if report['source'] != 'local' or not item:
                    raise ValueError('找不到本地来源')
                mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.bmp': 'image/bmp'}.get(Path(item['name']).suffix.lower())
                if not mime or item['size'] > 30 * 1024 * 1024:
                    raise ValueError('仅预览 30MB 以内的 PNG/JPEG/BMP 图片')
                original = Path(report['root']) / item['path']
                info = stable_file(original, report['root'])
                if info.st_size != item['size']:
                    raise ValueError('原图发生变化')
                with original.open('rb') as file:
                    content = file.read(30 * 1024 * 1024 + 1)
                if hashlib.sha256(content).hexdigest() != item['sha256']:
                    raise ValueError('原图发生变化')
                return self.reply(content, content_type=mime)
            if path.startswith('/api/export/'):
                report = read('report', path.rsplit('/', 1)[1])
                return self.reply(export_csv(report).encode('utf-8'), content_type='text/csv; charset=utf-8', download='inventory.csv')
            if path == '/api/audit':
                file = DATA / 'audit.jsonl'
                lines = file.read_text(encoding='utf-8').splitlines()[-100:] if file.exists() else []
                return self.reply([json.loads(line) for line in reversed(lines)])
            return self.reply({'error': 'Not found'}, 404)
        except (ValueError, FileNotFoundError, KeyError) as exc:
            return self.reply({'error': str(exc)}, 404)

    def do_POST(self):
        origin = self.headers.get('Origin')
        allowed = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}
        if not self.valid_host() or self.headers.get('X-Storage-App') != '1' or (origin and origin not in allowed):
            return self.reply({'error': '请求来源不被允许'}, 403)
        try:
            size = int(self.headers.get('Content-Length', 0))
            if size < 0 or size > 1024 * 1024:
                raise ValueError('请求过大')
            body = json.loads(self.rfile.read(size) or b'{}')
            path = urlparse(self.path).path
            if path == '/api/vault/fold':
                return self.reply(start_job('企业无损折叠', lambda progress: VAULT.fold(body['root'], progress)))
            if path == '/api/vault/catalog':
                return self.reply(start_job('归档目录校验', lambda _: VAULT.catalog(body['id'])))
            if path == '/api/vault/health':
                return self.reply(start_job('归档完整性巡检', lambda _: VAULT.health(body['id'])))
            if path == '/api/vault/retrieve':
                return self.reply(start_job('选择性取出', lambda _: VAULT.retrieve(body['id'], body['destination'], body['paths'])))
            if path == '/api/vault/checkout':
                return self.reply(start_job('独立还原交付', lambda _: VAULT.checkout(body['id'], body['destination'])))
            if path == '/api/vault/release':
                return self.reply(start_job('核验交付并清理保管区', lambda _: VAULT.release(body['id'], body.get('acknowledged'))))
            if path == '/api/scan':
                def operation(progress):
                    source = body.get('source', 'local')
                    if source not in {'local', 's3'}:
                        raise ValueError('未知存储源')
                    report = scan_local(body.get('root', ''), progress, exclude=DATA) if source == 'local' else scan_s3(body, progress)
                    save('report', report)
                    return report
                if body.get('source', 'local') == 'local' and not body.get('root', '').strip():
                    raise ValueError('请输入扫描目录')
                return self.reply(start_job('扫描资料库', operation))
            if path == '/api/demo':
                def operation(progress):
                    demo = DATA / 'demo' / uuid.uuid4().hex
                    demo.mkdir(parents=True)
                    text = ('timestamp,department,event,status\n2026-09-14,operations,archive_check,ok\n' * 5000)
                    (demo / 'operations.csv').write_text(text, encoding='utf-8')
                    (demo / 'operations-copy.csv').write_text(text, encoding='utf-8')
                    (demo / 'training-notes.txt').write_text('培训资料：请保留业务事实、公式与图表。\n' * 4000, encoding='utf-8')
                    (demo / 'policy.json').write_text(json.dumps({'retention': '由资料所有者设定', 'department': '培训中心'}, ensure_ascii=False), encoding='utf-8')
                    report = scan_local(demo, progress)
                    report['demo'] = True
                    save('report', report)
                    return report
                return self.reply(start_job('生成演示资料并扫描', operation))
            if path == '/api/archive':
                report = read('report', body['report_id'])
                def operation(progress):
                    manifest = create_archives(report, body['ids'], DATA / 'archives', progress)
                    save('manifest', manifest)
                    return manifest
                return self.reply(start_job('生成并验证归档', operation))
            if path == '/api/bundle':
                report = read('report', body['report_id'])
                def operation(progress):
                    result = create_bundle(report, body['ids'], DATA / 'bundles', progress)
                    save('bundle', result)
                    return result
                return self.reply(start_job('整批深度归档', operation))
            if path == '/api/restore-bundle':
                receipt = read('bundle', body['bundle_id'])
                return self.reply(start_job('恢复整批目录', lambda _: restore_bundle(receipt, DATA / 'bundles', DATA / 'restored')))
            if path == '/api/extract':
                report = read('report', body['report_id'])
                def operation(progress):
                    result = extract_images(report, body['ids'], DATA / 'extracted', progress)
                    save('extraction', result)
                    return result
                return self.reply(start_job('提取图片文字', operation))
            if path == '/api/restore':
                manifest = read('manifest', body['manifest_id'])
                return self.reply(start_job('恢复验证', lambda _: restore_archive(manifest, DATA / 'archives', DATA / 'restored')))
            if path == '/api/economics':
                report = read('report', body['report_id'])
                if body.get('bundle_id'):
                    bundle = read('bundle', body['bundle_id'])
                    if bundle['report_id'] != report['id']:
                        raise ValueError('归档与报告不匹配')
                    result = economics({'duplicates': [], 'summary': {'duplicate_bytes': bundle['net_potential_bytes']}},
                                       None, body.get('local_rate', 0), body.get('cloud_rate', 0), body.get('processing_cost', 0))
                    result['note'] += ' 使用当前深度归档实测净缩减（已含内部去重），不叠加其他归档或去重收益。'
                    return self.reply(result)
                manifest = read('manifest', body['manifest_id']) if body.get('manifest_id') else None
                if manifest and manifest['report_id'] != report['id']:
                    raise ValueError('归档与扫描报告不匹配')
                return self.reply(economics(report, manifest, body.get('local_rate', 0), body.get('cloud_rate', 0), body.get('processing_cost', 0)))
            return self.reply({'error': 'Not found'}, 404)
        except (ValueError, KeyError, TypeError, FileNotFoundError) as exc:
            return self.reply({'error': str(exc)}, 400)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Storage Atlas: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
