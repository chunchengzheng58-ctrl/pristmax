import json
import os
import socket
import subprocess
import tempfile
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            cls.port = sock.getsockname()[1]
        cls.base = f'http://127.0.0.1:{cls.port}'
        cls.data_temp = tempfile.TemporaryDirectory()
        cls.process = subprocess.Popen([sys.executable, 'app.py', '--port', str(cls.port)],
                                       cwd=Path(__file__).resolve().parents[1], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       env={**os.environ, 'STORAGE_ATLAS_DATA': cls.data_temp.name})
        for _ in range(80):
            try:
                urllib.request.urlopen(cls.base + '/api/status', timeout=1).close()
                return
            except OSError:
                time.sleep(.1)
        raise RuntimeError('server did not start')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)
        cls.data_temp.cleanup()

    def request(self, path, data=None, headers=None):
        headers = headers or {'X-Storage-App': '1', 'Content-Type': 'application/json'}
        req = urllib.request.Request(self.base + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.load(response)

    def job(self, path, body):
        identifier = self.request(path, body)['job_id']
        for _ in range(200):
            state = self.request('/api/job/' + identifier)
            if state['status'] == 'done':
                return state['result']
            if state['status'] == 'error':
                self.fail(state['error'])
            time.sleep(.05)
        self.fail('job timed out')

    def test_full_api_roundtrip(self):
        report = self.job('/api/demo', {})
        self.assertTrue(report['demo'])
        ids = [x['id'] for x in report['files'] if x['archive_eligible'] and not x.get('duplicate_of')]
        manifest = self.job('/api/archive', {'report_id': report['id'], 'ids': ids})
        self.assertGreater(len(manifest['items']), 0)
        restored = self.job('/api/restore', {'manifest_id': manifest['id']})
        self.assertTrue(all(x['verified'] for x in restored['files']))
        costs = self.request('/api/economics', {'report_id': report['id'], 'manifest_id': manifest['id'], 'cloud_rate': .2})
        self.assertGreater(costs['potential_bytes'], 0)
        self.assertEqual(costs['actual_reclaimed_bytes'], 0)
        self.assertEqual(self.request('/api/report/' + report['id'])['id'], report['id'])
        bundle = self.job('/api/bundle', {'report_id': report['id'], 'ids': [x['id'] for x in report['files']]})
        recovered = self.job('/api/restore-bundle', {'bundle_id': bundle['id']})
        self.assertEqual(recovered['file_count'], len(report['files']))
        costs = self.request('/api/economics', {'report_id': report['id'], 'bundle_id': bundle['id'], 'cloud_rate': .2})
        self.assertEqual(costs['potential_bytes'], bundle['net_potential_bytes'])
        with urllib.request.urlopen(self.base + '/api/bundle-download/' + bundle['id'], timeout=5) as response:
            self.assertEqual(len(response.read()), bundle['archive_bytes'])

    def test_vault_api_handover(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'input'
            source.mkdir()
            content = b'customer private data\n' * 10000
            (source / 'record.txt').write_bytes(content)
            destination = Path(folder) / 'delivery'
            destination.mkdir()
            record = self.job('/api/vault/fold', {'root': str(source)})
            source.rename(Path(folder) / 'offline')
            catalog = self.job('/api/vault/catalog', {'id': record['id']})
            self.assertEqual(catalog['files'][0]['path'], 'record.txt')
            health = self.job('/api/vault/health', {'id': record['id']})
            self.assertEqual(health['status'], 'healthy')
            selected = self.job('/api/vault/retrieve', {'id': record['id'], 'destination': str(destination), 'paths': ['record.txt']})
            self.assertTrue(selected['partial'])
            self.assertTrue(selected['archive_retained'])
            self.assertEqual((Path(selected['folder']) / 'record.txt').read_bytes(), content)
            delivered = self.job('/api/vault/checkout', {'id': record['id'], 'destination': str(destination)})
            self.assertEqual((Path(delivered['delivery']) / 'record.txt').read_bytes(), content)
            result = self.job('/api/vault/release', {'id': record['id'], 'acknowledged': True})
            self.assertEqual(result['status'], 'released')
            self.assertIn(result, self.request('/api/vault'))

    def test_cross_origin_mutation_denied(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request('/api/demo', {}, {'X-Storage-App': '1', 'Origin': 'https://untrusted.example'})
        self.assertEqual(ctx.exception.code, 403)

    def test_missing_header_denied(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request('/api/demo', {}, {'Content-Type': 'application/json'})
        self.assertEqual(ctx.exception.code, 403)

    def test_invalid_root_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request('/api/scan', {'source': 'local', 'root': ''})
        self.assertEqual(ctx.exception.code, 400)

    def test_image_preview_rejects_changed_source(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / 'test.png'
            image.write_bytes(b'preview fixture')
            report = self.job('/api/scan', {'source': 'local', 'root': folder})
            item = report['files'][0]
            url = self.base + '/api/source/' + report['id'] + '/' + item['id']
            with urllib.request.urlopen(url, timeout=5) as response:
                self.assertEqual(response.read(), b'preview fixture')
                self.assertEqual(response.headers['Content-Type'], 'image/png')
            image.write_bytes(b'changed fixture')
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(url, timeout=5)
            self.assertEqual(ctx.exception.code, 404)
