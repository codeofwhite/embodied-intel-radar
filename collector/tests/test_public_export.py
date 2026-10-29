import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/export-public-snapshot.py'
SPEC = importlib.util.spec_from_file_location('public_export', SCRIPT)
export = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(export)


class PublicExportTests(unittest.TestCase):
    def setUp(self):
        self.jobs = {'meta': {'generatedAt': '2026-01-01T00:00:00Z', 'profile': 'PRIVATE'},
                     'jobs': [{'id': '1', 'company': 'Example', 'title': 'Robotics',
                               'url': 'https://example.com/job', 'match': 99,
                               'matchBasis': ['PRIVATE'], 'note': 'PRIVATE',
                               'salary': {'note': 'PRIVATE'}, 'skills': ['Python', {'note': 'PRIVATE'}]}],
                     'companies': [], 'savedSocial': [{'note': 'PRIVATE'}]}

    def test_personal_and_nested_fields_are_excluded(self):
        result = export.build_snapshot(self.jobs)
        encoded = json.dumps(result)
        self.assertNotIn('PRIVATE', encoded)
        self.assertNotIn('match', result['jobs'][0])
        self.assertEqual(result['jobs'][0]['skills'], ['Python'])

    def test_empty_and_malformed_jobs_rejected(self):
        for value in [[], None, 'bad', [{'url': 'javascript:alert(1)'}]]:
            jobs = copy.deepcopy(self.jobs)
            jobs['jobs'] = value
            with self.assertRaises(ValueError):
                export.build_snapshot(jobs)

    def test_urls_cannot_contain_credentials_or_private_hosts(self):
        for url in ['http://example.com', 'https://localhost/a', 'https://127.0.0.1/a',
                    'https://user:pass@example.com', 'https://example.com?token=secret',
                    'javascript:alert(1)', 'https://[::1]/']:
            self.assertEqual(export.public_url(url), '')
        self.assertEqual(export.public_url('https://example.com/job?id=1'), 'https://example.com/job?id=1')

    def test_source_date_is_preserved_not_relabelled_now(self):
        result = export.build_snapshot(self.jobs)
        self.assertEqual(result['generatedAt'], '2026-01-01T00:00:00+00:00')
        self.jobs['meta']['generatedAt'] = '2099-01-01T00:00:00Z'
        with self.assertRaises(ValueError):
            export.build_snapshot(self.jobs)

    def test_optional_failed_section_keeps_its_original_date(self):
        previous = {'events': [{'id': 'old', 'url': 'https://example.com/release'}], 'sectionUpdatedAt': {'events': '2025-12-01T00:00:00Z'}}
        result = export.build_snapshot(self.jobs, previous=previous)
        self.assertEqual(result['events'], previous['events'])
        self.assertEqual(result['sectionUpdatedAt']['events'], previous['sectionUpdatedAt']['events'])

    def test_previous_sections_also_pass_the_allowlist(self):
        previous = {'events': [{'id': 'old', 'url': 'https://example.com/release', 'note': 'PRIVATE'}]}
        result = export.build_snapshot(self.jobs, previous=previous)
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_valid_url_alone_is_not_a_job(self):
        self.jobs['jobs'] = [{'url': 'https://example.com/job'}]
        with self.assertRaises(ValueError):
            export.build_snapshot(self.jobs)

    def test_social_search_is_never_reported_as_verified_jobs(self):
        social = {'meta': {'generatedAt': '2026-01-01T00:00:00Z'},
                  'items': [{'url': 'https://x.com/example/status/1', 'verification': 'verified', 'note': 'PRIVATE'}]}
        result = export.build_snapshot(self.jobs, social=social)
        self.assertEqual(len(result['jobs']), 1)
        self.assertEqual(result['social'][0]['verification'], '搜索索引线索·待核实')
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_failed_cli_preserves_existing_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'snapshot.json'
            output.write_text('{"previous":true}\n')
            (root / 'jobs.json').write_text('{broken')
            result = subprocess.run([sys.executable, str(SCRIPT), '--data-dir', str(root), '--output', str(output)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_text(), '{"previous":true}\n')


if __name__ == '__main__':
    unittest.main()
