import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from temporal_episode_benchmark_v2 import main


class ResumeInputTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.csv = root / 'fixture.csv'
        self.csv.write_bytes(b'unchanged fixture bytes\n')
        self.output = root / 'results.json'
        self.output.write_text(json.dumps({'complete': False, 'rows': [],
            'fixture_metadata': {'source_sha256': hashlib.sha256(self.csv.read_bytes()).hexdigest()}}))
        self.argv = ['--suite', 'sarafu', '--csv', str(self.csv), '--output', str(self.output),
                     '--limit', '5000', '--arrival-ticks', '1000', '--event-budget', '2000000']

    def test_unchanged_resume_delegates_exact_configuration(self):
        received = []
        previous = sys.argv
        with patch('temporal_episode_benchmark_v2.original.main',
                   side_effect=lambda: received.append(sys.argv[1:])) as runner:
            main(self.argv)
        runner.assert_called_once_with()
        self.assertEqual(received, [self.argv])
        self.assertIs(sys.argv, previous)

    def test_changed_csv_at_same_path_is_rejected_without_writes(self):
        before = self.output.read_bytes()
        self.csv.write_bytes(b'different fixture bytes\n')
        with patch('temporal_episode_benchmark_v2.original.main') as runner:
            with self.assertRaisesRegex(RuntimeError, 'CSV content differs'):
                main(self.argv)
        runner.assert_not_called()
        self.assertEqual(self.output.read_bytes(), before)

    def test_missing_fixture_hash_requires_new_output(self):
        self.output.write_text(json.dumps({'complete': False, 'rows': []}))
        with patch('temporal_episode_benchmark_v2.original.main') as runner:
            with self.assertRaisesRegex(RuntimeError, 'lacks a usable fixture hash'):
                main(self.argv)
        runner.assert_not_called()

    def test_fresh_output_and_synthetic_runs_delegate(self):
        self.output.unlink()
        with patch('temporal_episode_benchmark_v2.original.main') as runner:
            main(self.argv)
            main(['--suite', 'synthetic', '--output', str(self.output)])
        self.assertEqual(runner.call_count, 2)

    def test_original_configuration_rejection_propagates(self):
        previous = sys.argv
        with patch('temporal_episode_benchmark_v2.original.main',
                   side_effect=RuntimeError('Refusing to mix source/configurations')):
            with self.assertRaisesRegex(RuntimeError, 'source/configurations'):
                main(self.argv)
        self.assertIs(sys.argv, previous)


if __name__ == '__main__':
    unittest.main()
