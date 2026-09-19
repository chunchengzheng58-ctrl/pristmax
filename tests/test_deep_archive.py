import json
import os
from pathlib import Path
import tempfile
import unittest

from storage_core import scan_local
from deep_archive import create_bundle, restore_bundle, inspect_bundle, safe_relative


class DeepArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / 'input'
        self.root.mkdir()
        (self.root / 'nested').mkdir()
        for i in range(20):
            (self.root / 'nested' / f'item-{i}.txt').write_text(('business record month 2026 value ' + str(i) + '\n') * 200, encoding='utf-8')
        (self.root / 'copy.txt').write_bytes((self.root / 'nested' / 'item-0.txt').read_bytes())
        (self.root / 'empty.txt').touch()
        self.report = scan_local(self.root)
        self.ids = [f['id'] for f in self.report['files']]

    def tearDown(self):
        self.temp.cleanup()

    def create(self):
        return create_bundle(self.report, self.ids, self.base / 'bundles')

    def test_roundtrip_dedup_and_smallest_codec(self):
        result = self.create()
        self.assertEqual(result['unique_contents'], len(self.ids) - 1)
        self.assertEqual(result['archive_bytes'], min(t['bytes'] for t in result['trials']))
        self.assertGreater(result['net_potential_bytes'], 0)
        directory = self.base / 'bundles' / result['id']
        self.assertEqual(len(list(directory.iterdir())), 2)
        self.assertEqual(result['receipt_bytes'], (directory / 'receipt.json').stat().st_size)
        self.assertEqual(result['net_potential_bytes'], result['original_bytes'] - sum(p.stat().st_size for p in directory.iterdir()))
        restored = restore_bundle(result, self.base / 'bundles', self.base / 'restored')
        for item in self.report['files']:
            self.assertEqual((Path(restored['folder']) / item['path']).read_bytes(), (self.root / item['path']).read_bytes())
        self.assertEqual(result['actual_reclaimed_bytes'], 0)

    def test_repeated_run_reuses_same_archive(self):
        first = self.create()
        second = self.create()
        self.assertEqual(first['id'], second['id'])
        self.assertTrue(second['reused'])
        self.assertEqual(len(list((self.base / 'bundles').iterdir())), 1)

    def test_changed_duplicate_rejected(self):
        (self.root / 'copy.txt').write_text('changed')
        with self.assertRaises(ValueError):
            self.create()

    def test_corruption_rejected_before_restore(self):
        receipt = self.create()
        path = self.base / 'bundles' / receipt['id'] / receipt['archive']
        path.write_bytes(b'broken')
        with self.assertRaises(Exception):
            restore_bundle(receipt, self.base / 'bundles', self.base / 'restored')
        self.assertFalse((self.base / 'restored').exists())

    def test_incompressible_small_file_discarded(self):
        root = self.base / 'random'
        root.mkdir()
        (root / 'random.bin').write_bytes(os.urandom(1024))
        report = scan_local(root)
        with self.assertRaisesRegex(ValueError, '无净缩减'):
            create_bundle(report, [f['id'] for f in report['files']], self.base / 'bundles')
        self.assertEqual(list((self.base / 'bundles').iterdir()), [])

    def test_unsafe_paths_rejected(self):
        for path in ('../escape', '/absolute', 'C:/absolute', 'file:stream', 'a/../../b'):
            with self.assertRaises(ValueError):
                safe_relative(path)


if __name__ == '__main__':
    unittest.main()
