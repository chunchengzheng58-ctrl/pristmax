import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from durability import atomic_json, exclusive_lock
from deep_archive import create_bundle, inspect_bundle, restore_bundle
from storage_core import scan_local
from vault import Vault


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'
        self.source.mkdir()
        (self.source / 'data.txt').write_bytes(b'Lossless enterprise data\n' * 5000)
        self.vault = Vault(self.base / 'vault')
        self.delivery = self.base / 'delivery'
        self.delivery.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_state_replace_failure_keeps_previous_record(self):
        path = self.base / 'state.json'
        atomic_json(path, {'status': 'folded'})
        with patch('durability.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                atomic_json(path, {'status': 'released'})
        self.assertEqual(json.loads(path.read_text()), {'status': 'folded'})
        self.assertEqual(list(self.base.glob('.state-*.tmp')), [])

    def test_exclusion_between_vault_instances(self):
        with exclusive_lock(self.vault.root / '.operation.lock'):
            with self.assertRaisesRegex(ValueError, '其他操作'):
                Vault(self.vault.root).fold(self.source)
        self.assertEqual(self.vault.fold(self.source)['status'], 'folded')

    def test_process_exit_releases_lock(self):
        code = ('from durability import exclusive_lock; import sys,time; '
                'ctx=exclusive_lock(sys.argv[1]); ctx.__enter__(); '
                'print("locked",flush=True); time.sleep(30)')
        process = subprocess.Popen([sys.executable, '-c', code, str(self.vault.root / '.operation.lock')],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'locked')
            with self.assertRaises(ValueError):
                self.vault.fold(self.source)
        finally:
            process.terminate()
            process.communicate(timeout=5)
        self.assertEqual(self.vault.fold(self.source)['status'], 'folded')

    def test_disk_full_refuses_restore_without_output(self):
        record = self.vault.fold(self.source)
        with patch('deep_archive.shutil.disk_usage', return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(ValueError, '空间不足'):
                self.vault.checkout(record['id'], self.delivery)
        self.assertEqual(list(self.delivery.iterdir()), [])
        self.assertEqual(self.vault.read(record['id'])['status'], 'folded')
        self.assertTrue(self.vault.archive_path(record).exists())

    def test_failed_sync_does_not_publish_partial_delivery(self):
        record = self.vault.fold(self.source)
        with patch('deep_archive.sync_file', side_effect=OSError('writeback failure')):
            with self.assertRaises(OSError):
                self.vault.checkout(record['id'], self.delivery)
        self.assertEqual(list(self.delivery.iterdir()), [])
        self.assertEqual(self.vault.read(record['id'])['status'], 'folded')

    def test_archive_swap_between_verification_and_restore_rejected(self):
        record = self.vault.fold(self.source)
        (self.source / 'data.txt').write_bytes(b'Other valid contents\n' * 5000)
        replacement = self.vault.fold(self.source)
        original = self.vault.verified_mapping
        def swap(record):
            mapping = original(record)
            self.vault.archive_path(record).write_bytes(self.vault.archive_path(replacement).read_bytes())
            return mapping
        with patch.object(self.vault, 'verified_mapping', side_effect=swap):
            with self.assertRaisesRegex(ValueError, '清单不一致'):
                self.vault.checkout(record['id'], self.delivery)
        self.assertEqual(list(self.delivery.iterdir()), [])

    def test_release_state_write_failure_keeps_archive(self):
        record = self.vault.fold(self.source)
        self.vault.checkout(record['id'], self.delivery)
        with patch('vault.atomic_json', side_effect=OSError('state write failure')):
            with self.assertRaises(OSError):
                self.vault.release(record['id'], True)
        self.assertTrue(self.vault.archive_path(record).exists())
        self.assertEqual(self.vault.read(record['id'])['status'], 'awaiting_receipt')

    def test_malformed_manifest_and_expansion_limits(self):
        sha = hashlib.sha256(b'').hexdigest()
        def item(path='file', size=0):
            return {'path': path, 'sha256': sha, 'size': size}
        cases = [[], *[{'format': 'storage-atlas-bundle-v1', 'files': files} for files in
                      ([], [None], [item(size=True)], [item(size=20 * 1000**3 + 1)],
                       [item('a'), item('a/b')], [item('CON.txt')],
                       [item(str(i)) for i in range(2001)])]]
        archive = self.base / 'invalid.tar.gz'
        for mapping in cases:
            encoded = json.dumps(mapping).encode()
            with tarfile.open(archive, 'w:gz') as out:
                header = tarfile.TarInfo('manifest.json')
                header.size = len(encoded)
                out.addfile(header, io.BytesIO(encoded))
            with self.subTest(mapping_type=type(mapping).__name__):
                with self.assertRaises(ValueError):
                    inspect_bundle(archive)

    def test_mixed_binary_roundtrip(self):
        # Incompressible fragments are mixed with compressible business files.
        random = os.urandom(256 * 1024)
        (self.source / 'random.bin').write_bytes(random)
        (self.source / 'data.txt').write_bytes(b'enterprise record\n' * 100000)
        record = self.vault.fold(self.source)
        self.source.rename(self.base / 'offline')
        result = self.vault.checkout(record['id'], self.delivery)
        self.assertEqual((Path(result['delivery']) / 'random.bin').read_bytes(), random)
