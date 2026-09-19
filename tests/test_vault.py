import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vault import Vault
from cdc.chunker import rabin_chunks


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'
        self.source.mkdir()
        self.expected = {'a/same.txt': b'enterprise A\n' * 5000,
                         'b/same.txt': b'enterprise B\n' * 5000,
                         'empty': b'', 'small': b'123'}
        for name, content in self.expected.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.vault = Vault(self.base / 'vault')
        self.destination = self.base / 'delivery'
        self.destination.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_independent_checkout_release_and_restart(self):
        record = self.vault.fold(self.source)
        self.source.rename(self.base / 'offline')
        delivered = self.vault.checkout(record['id'], self.destination)
        for name, content in self.expected.items():
            self.assertEqual((Path(delivered['delivery']) / name).read_bytes(), content)
        with self.assertRaises(ValueError):
            self.vault.release(record['id'])
        restarted = Vault(self.vault.root)
        result = restarted.release(record['id'], True)
        self.assertEqual(result['status'], 'released')
        self.assertEqual(list(restarted.directory(record['id']).iterdir()),
                         [restarted.directory(record['id']) / 'state.json'])
        self.assertNotIn('delivery', result)
        self.assertNotIn('receipt', result)
        self.assertEqual(restarted.release(record['id'], True), result)
        self.assertTrue((self.base / 'offline' / 'small').exists())

    def test_changed_delivery_blocks_cleanup(self):
        record = self.vault.fold(self.source)
        delivered = self.vault.checkout(record['id'], self.destination)
        (Path(delivered['delivery']) / 'small').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            self.vault.release(record['id'], True)
        self.assertTrue(list(self.vault.root.rglob('dataset*')))

    def test_interrupted_cleanup_can_resume(self):
        record = self.vault.fold(self.source)
        self.vault.checkout(record['id'], self.destination)
        original = Path.unlink
        def interrupted(path, *args, **kwargs):
            if path.name == 'receipt.json':
                raise OSError('simulated interruption')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'unlink', interrupted):
            with self.assertRaises(OSError):
                self.vault.release(record['id'], True)
        self.assertEqual(self.vault.read(record['id'])['status'], 'releasing')
        self.assertEqual(Vault(self.vault.root).release(record['id'], True)['status'], 'released')

    def test_no_duplicate_checkout_or_early_release(self):
        record = self.vault.fold(self.source)
        with self.assertRaises(ValueError):
            self.vault.release(record['id'], True)
        with self.assertRaises(ValueError):
            self.vault.checkout(record['id'], self.vault.root)
        self.vault.checkout(record['id'], self.destination)
        with self.assertRaises(ValueError):
            self.vault.checkout(record['id'], self.destination)

    def test_short_cdc_content_preserved(self):
        for size in range(1, 65):
            data = bytes(range(size))
            self.assertEqual(b''.join(c.data for c in rabin_chunks(data)), data)

    def test_corrupt_archive_cannot_checkout(self):
        record = self.vault.fold(self.source)
        next(self.vault.root.rglob('dataset*')).write_bytes(b'broken')
        with self.assertRaises(Exception):
            self.vault.checkout(record['id'], self.destination)
        self.assertEqual(self.vault.read(record['id'])['status'], 'folded')
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_selective_restore_mtime_and_state(self):
        stamp = 1700000000123456700
        os.utime(self.source / 'small', ns=(stamp, stamp))
        record = self.vault.fold(self.source)
        self.source.rename(self.base / 'offline')
        catalog = self.vault.catalog(record['id'])
        self.assertTrue(catalog['baseline_verified'])
        self.assertEqual(len(catalog['files']), 4)
        result = self.vault.retrieve(record['id'], self.destination, ['small', 'b/same.txt'])
        target = Path(result['folder'])
        self.assertEqual({p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}, {'small', 'b/same.txt'})
        self.assertEqual((target / 'small').stat().st_mtime_ns, stamp)
        self.assertTrue(result['mtime_preserved'])
        self.assertEqual(self.vault.read(record['id'])['status'], 'folded')
        with self.assertRaises(ValueError):
            self.vault.release(record['id'], True)

    def test_health_detects_corruption_and_survives_restart(self):
        record = self.vault.fold(self.source)
        self.assertEqual(self.vault.health(record['id'])['status'], 'healthy')
        archive = next(self.vault.root.rglob('dataset*'))
        archive.write_bytes(b'corrupted')
        self.assertEqual(self.vault.health(record['id'])['status'], 'failed')
        self.assertEqual(Vault(self.vault.root).read(record['id'])['health']['status'], 'failed')
        self.assertTrue(archive.exists())
        with self.assertRaises(ValueError):
            self.vault.retrieve(record['id'], self.destination, ['small'])

    def test_invalid_selection_does_not_write(self):
        record = self.vault.fold(self.source)
        for selection in (None, [], ['../escape'], ['small', 'small'], [123]):
            with self.assertRaises(ValueError):
                self.vault.retrieve(record['id'], self.destination, selection)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_excluded_files_reject_incomplete_custody(self):
        excluded = self.source / '.git'
        excluded.mkdir()
        (excluded / 'important').write_bytes(b'do not silently omit')
        with self.assertRaisesRegex(ValueError, '排除'):
            self.vault.fold(self.source)
        self.assertEqual(self.vault.list(), [])

    def test_changed_mtime_blocks_release(self):
        record = self.vault.fold(self.source)
        delivery = Path(self.vault.checkout(record['id'], self.destination)['delivery'])
        os.utime(delivery / 'small', ns=(0, 0))
        with self.assertRaisesRegex(ValueError, '修改时间'):
            self.vault.release(record['id'], True)

    def test_valid_but_replaced_archive_rejected(self):
        first = self.vault.fold(self.source)
        (self.source / 'small').write_bytes(b'new content')
        second = self.vault.fold(self.source)
        self.vault.archive_path(first).write_bytes(self.vault.archive_path(second).read_bytes())
        with self.assertRaisesRegex(ValueError, '指纹'):
            self.vault.catalog(first['id'])


if __name__ == '__main__':
    unittest.main()
