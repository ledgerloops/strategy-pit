"""Package completed measurements and their exact reproduction sources."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/mdg2-comfort-curves-2026-10-20'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    for name in ('results.json', 'decrease-first-results.json'):
        assert json.loads((OUT / name).read_text())['complete']
    for name, result in (('independent-audit.json', 'results.json'),
                         ('decrease-first-independent-audit.json', 'decrease-first-results.json')):
        audit = json.loads((OUT / name).read_text())
        assert audit['independent_audit_passed']
        assert audit['results_sha256'] == sha(OUT / result)
    names = [
        'comfort_headroom.py', 'comfort_curve_benchmark.py', 'comfort_curve_audit.py',
        'make_comfort_curve_workloads.py', 'comfort-curve-plan.json',
        'comfort-curve-workloads.json', 'comfort-curve-freeze.json',
        'comfort_decrease_first.py', 'decrease_first_benchmark.py',
        'make_decrease_first_workloads.py', 'decrease-first-plan.json',
        'decrease-first-workloads.json', 'decrease-first-freeze.json',
        'test_comfort_headroom.py', 'test_comfort_decrease_first.py',
        'test_decrease_first_benchmark.py', 'build_comfort_curve_report.py',
        'package_comfort_curves.py',
    ]
    sources = [ROOT / 'experiments/mdg2' / name for name in names]
    sources += [ROOT / 'app/comfort.py']
    sources += sorted((ROOT / 'experiments').glob('test_comfort_simulation*.py'))
    # Existing comfort tests import this research model.
    sources += [ROOT / 'experiments/comfort_simulation.py',
                ROOT / 'experiments/comfort_simulation_expanded.py']
    manifest = dict(
        base_commit=subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        version='comfort-headroom-v1 and local-decrease-first-v1',
        python='3.12.14', networkx='3.5', matplotlib='3.10.8',
        sources={str(p.relative_to(ROOT)): sha(p) for p in sources},
        note='Uncommitted research sources are pinned individually; base commit alone does not identify this experiment.',
    )
    (OUT / 'SOURCE-MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    artifacts = sorted(p for p in OUT.iterdir()
                       if p.is_file() and p.name != 'SHA256SUMS.txt')
    files = sorted(set(sources + artifacts))
    sums = OUT / 'SHA256SUMS.txt'
    sums.write_text(''.join(f'{sha(p)}  {p.relative_to(ROOT)}\n' for p in files))
    destination = OUT.with_suffix('.zip')
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in files + [sums]:
            archive.write(path, str(path.relative_to(ROOT)))
    print(destination)
    print(f'{len(files) + 1} files; {destination.stat().st_size:,} bytes')


if __name__ == '__main__':
    main()
