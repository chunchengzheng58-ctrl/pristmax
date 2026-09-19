import gzip
import hashlib
import io
import json
import math
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from storage_core import scan_local, create_archives, restore_archive, economics, export_csv, scan_s3, extract_images


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / 'input'
        self.root.mkdir()
        self.content = ('企业资料 123456789\n' * 3000).encode()
        (self.root / 'first.log').write_bytes(self.content)
        (self.root / 'copy.log').write_bytes(self.content)
        (self.root / 'unique.txt').write_bytes(b'other repeated data\n' * 2500)

    def tearDown(self):
        self.temp.cleanup()

    def archive(self):
        report = scan_local(self.root)
        ids = [f['id'] for f in report['files'] if not f.get('duplicate_of')]
        manifest = create_archives(report, ids, self.base / 'archives')
        return report, manifest

    def test_exact_duplicates_and_empty_files(self):
        (self.root / 'empty').touch()
        (self.root / 'empty2').touch()
        report = scan_local(self.root)
        self.assertEqual(len(report['duplicates']), 1)
        self.assertEqual(report['summary']['duplicate_bytes'], len(self.content))
        self.assertEqual(report['summary']['actual_reclaimed_bytes'], 0)

    def test_roundtrip_and_sources_untouched(self):
        report, manifest = self.archive()
        self.assertEqual(len(manifest['items']), 2)
        self.assertGreater(manifest['net_potential_bytes'], 0)
        result = restore_archive(manifest, self.base / 'archives', self.base / 'restored')
        self.assertEqual(len(result['files']), 2)
        for f in result['files']:
            self.assertEqual(Path(f['path']).read_bytes(), (self.root / f['source_path']).read_bytes())
        self.assertEqual((self.root / 'first.log').read_bytes(), self.content)

    def test_changed_source_rejected(self):
        report = scan_local(self.root)
        item = next(x for x in report['files'] if x['name'] == 'first.log')
        (self.root / 'first.log').write_bytes(b'changed')
        manifest = create_archives(report, [item['id']], self.base / 'archives')
        self.assertFalse(manifest['items'])
        self.assertIn('变化', manifest['errors'][0]['error'])

    def test_same_stat_changed_content_rejected(self):
        report = scan_local(self.root)
        item = next(x for x in report['files'] if x['name'] == 'first.log')
        path = self.root / 'first.log'
        path.write_bytes(b'X' * item['size'])
        os.utime(path, ns=(item['mtime_ns'], item['mtime_ns']))
        manifest = create_archives(report, [item['id']], self.base / 'archives')
        self.assertFalse(manifest['items'])

    def test_corrupt_archive_rejected(self):
        _, manifest = self.archive()
        first = manifest['items'][0]
        archive = self.base / 'archives' / manifest['id'] / first['archive']
        archive.write_bytes(gzip.compress(b'wrong'))
        with self.assertRaises(ValueError):
            restore_archive(manifest, self.base / 'archives', self.base / 'restored')
        self.assertEqual(list((self.base / 'restored').iterdir()), [])

    def test_economics_no_double_count(self):
        report = scan_local(self.root)
        manifest = create_archives(report, [f['id'] for f in report['files']], self.base / 'archives')
        result = economics(report, manifest, 0.1, 0.2, 10)
        copies = {i for g in report['duplicates'] for i in g['ids'][1:]}
        expected = report['summary']['duplicate_bytes'] + sum(x['potential_bytes'] for x in manifest['items'] if x['file_id'] not in copies) - manifest['manifest_bytes']
        self.assertEqual(result['potential_bytes'], expected)
        self.assertAlmostEqual(result['cloud_annual'], expected / 1e9 * .2 * 12)
        self.assertEqual(result['actual_reclaimed_bytes'], 0)

    def test_bad_costs_rejected(self):
        report = scan_local(self.root)
        for value in (-1, 'nan', 'inf'):
            with self.assertRaises(ValueError):
                economics(report, None, value, 0, 0)

    def test_csv_formula_escaped(self):
        (self.root / '=DANGEROUS.txt').write_text('a', encoding='utf-8')
        self.assertIn("'=DANGEROUS.txt", export_csv(scan_local(self.root)))

    def test_output_excluded(self):
        output = self.root / 'output'
        output.mkdir()
        (output / 'secret.txt').write_text('exclude me')
        report = scan_local(self.root, exclude=output)
        self.assertEqual(len(report['files']), 3)
        with self.assertRaises(ValueError):
            scan_local(output, exclude=output)

    def test_hardlink_not_counted_as_new_storage(self):
        try:
            os.link(self.root / 'unique.txt', self.root / 'linked.txt')
        except OSError:
            self.skipTest('hardlinks unsupported')
        report = scan_local(self.root)
        self.assertEqual(report['summary']['duplicate_bytes'], len(self.content))
        self.assertFalse(any(x['archive_eligible'] for x in report['files'] if x['name'] in {'unique.txt', 'linked.txt'}))

    def test_s3_pagination_and_etag_not_duplicate(self):
        stamp = datetime.now(timezone.utc)
        pages = [{'Contents': [{'Key': 'a.txt', 'Size': 100, 'ETag': 'same', 'LastModified': stamp}]},
                 {'Contents': [{'Key': 'b.txt', 'Size': 100, 'ETag': 'same', 'LastModified': stamp}]}]
        calls = []
        class Client:
            def get_paginator(self, name):
                calls.append(name)
                return self
            def paginate(self, **kwargs):
                calls.append(kwargs)
                return pages
        class Session:
            def __init__(self, **kwargs):
                pass
            def client(self, *args, **kwargs):
                return Client()
        with patch.dict(sys.modules, {'boto3': types.SimpleNamespace(Session=Session)}):
            report = scan_s3({'bucket': 'test', 'prefix': 'example/'})
        self.assertEqual(report['summary']['bytes'], 200)
        self.assertEqual(report['summary']['duplicate_bytes'], 0)
        self.assertFalse(any(x['archive_eligible'] for x in report['files']))
        self.assertEqual(calls[1], {'Bucket': 'test', 'Prefix': 'example/'})

    def test_invalid_selection(self):
        report = scan_local(self.root)
        with self.assertRaises(ValueError):
            create_archives(report, ['missing'], self.base / 'archives')

    @unittest.skipUnless(os.name == 'nt', 'Windows OCR integration wrapper')
    def test_ocr_keeps_source_and_marks_unreviewed(self):
        image = self.root / 'slide.png'
        image.write_bytes(b'fixture image bytes')
        report = scan_local(self.root)
        item = next(x for x in report['files'] if x['name'] == 'slide.png')
        payload = {'text': 'budget 1200', 'lines': [{'text': 'budget 1200', 'words': []}], 'language': 'en-US'}
        output = types.SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr='')
        with patch('storage_core.subprocess.run', return_value=output):
            result = extract_images(report, [item['id']], self.base / 'extracted')
        self.assertEqual(len(result['items']), 1)
        self.assertEqual(result['items'][0]['quality_status'], 'needs_human_review')
        self.assertEqual(result['items'][0]['text'], 'budget 1200')
        self.assertEqual(image.read_bytes(), b'fixture image bytes')
        self.assertFalse(list((self.base / 'extracted').rglob('*.png')))
        self.assertEqual(result['actual_reclaimed_bytes'], 0)


if __name__ == '__main__':
    unittest.main()
