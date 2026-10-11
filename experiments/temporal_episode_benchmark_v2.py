"""Input-validated CLI wrapper around the frozen strict-episode benchmark.

Use this entry point for new runs and resumes. Before delegating a Sarafu resume,
verify the CSV's current bytes against the existing artifact's fixture digest.
The original runner retains its source/configuration checks and checkpoint format.
This wrapper changes no simulation, fixture interpretation, or scoring code.
Input files must remain immutable while a benchmark is running.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import temporal_episode_benchmark as original


def validate_resume_input(output, csv_path):
    """Refuse ambiguous or changed input before the original runner can write."""
    output = Path(output)
    if not output.exists():
        return
    saved = json.loads(output.read_bytes())
    expected = saved.get('fixture_metadata', {}).get('source_sha256')
    if not isinstance(expected, str) or len(expected) != 64:
        raise RuntimeError('Existing Sarafu result lacks a usable fixture hash; preserve it and use a new output')
    digest = hashlib.sha256()
    with Path(csv_path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise RuntimeError('CSV content differs from the existing result fixture hash; preserve it and use a new output')


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Parse only the input guard's options; the frozen runner validates all
    # remaining arguments and the complete saved configuration itself.
    guard = argparse.ArgumentParser(add_help=False)
    guard.add_argument('--suite', default='smoke')
    guard.add_argument('--csv')
    guard.add_argument('--output')
    options, _ = guard.parse_known_args(argv)
    if options.suite == 'sarafu' and options.output and options.csv:
        validate_resume_input(options.output, options.csv)
    previous = sys.argv
    try:
        sys.argv = [previous[0], *argv]
        return original.main()
    finally:
        sys.argv = previous


if __name__ == '__main__':
    main()
