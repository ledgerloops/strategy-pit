"""Durable, bounded benchmark subprocess queue; this does not restart an assistant.

Manifests are trusted local instructions containing argv arrays, never shell
strings. All jobs run in this repository. Checkpoints retain a human-readable
heartbeat and verify source/input/output hashes before reusing completed work.
Existing state requires explicit --resume. Timeouts terminate the process group.
A finite worker can outlive a browser, but cannot survive machine/session removal.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / 'experiments' / 'results'


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def resolve(path):
    path = Path(path)
    return (REPO / path).resolve() if not path.is_absolute() else path.resolve()


def writable(path):
    path = resolve(path)
    if not any(path.is_relative_to(root) for root in (Path('/tmp'), RESULTS)):
        raise ValueError('Campaign state/log/output paths must be in /tmp or experiments/results')
    return path


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def file_hashes(paths):
    return {str(resolve(p)): digest(resolve(p)) for p in paths}


def load_manifest(path):
    manifest = json.loads(Path(path).read_text())
    jobs = manifest.get('jobs')
    if manifest.get('version') != 1 or not isinstance(jobs, list) or not 1 <= len(jobs) <= 1000:
        raise ValueError('Expected version 1 manifest with 1..1000 jobs')
    seen = set()
    for job in jobs:
        ident, argv = job.get('id'), job.get('argv')
        if not isinstance(ident,str) or not ident or not all(c.isalnum() or c in '-_' for c in ident) or ident in seen:
            raise ValueError('Unique simple job ID required')
        seen.add(ident)
        if not isinstance(argv,list) or not argv or not all(isinstance(a,str) and '\0' not in a for a in argv):
            raise ValueError('argv must be a nonempty string array')
        timeout = job.get('timeout_seconds')
        if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not 0 < timeout <= 86400:
            raise ValueError('Each job needs a finite timeout of at most 86400 seconds')
        for field in ('sources','inputs','outputs'):
            if not isinstance(job.get(field),list) or not all(isinstance(p,str) for p in job[field]):
                raise ValueError(field + ' must be a list of paths')
        if not job['sources'] or not job['outputs']:
            raise ValueError('Explicit sources and outputs required')
        for output in job['outputs']:
            writable(output)
    fingerprint = hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
    return manifest, fingerprint


def stop_process(process):
    if process.poll() is not None:
        return
    os.killpg(process.pid,signal.SIGTERM)
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL)
        process.wait()


def run_campaign(manifest_path, state_path, *, resume=False, max_seconds=3600, heartbeat_seconds=5):
    if not 0 < max_seconds <= 604800 or not 0 < heartbeat_seconds <= 60:
        raise ValueError('Campaign duration must be positive and at most one week; heartbeat at most 60 seconds')
    manifest, fingerprint = load_manifest(manifest_path)
    state_path = writable(state_path)
    state_path.parent.mkdir(parents=True,exist_ok=True)
    with state_path.with_suffix(state_path.suffix+'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        if state_path.exists():
            if not resume:
                raise ValueError('Checkpoint exists; inspect it and explicitly use --resume')
            state = json.loads(state_path.read_text())
            if state.get('manifest_sha256') != fingerprint:
                raise ValueError('Manifest changed; use a new checkpoint')
        else:
            state = dict(version=1,manifest_sha256=fingerprint,created_at=now(),jobs={})
        for record in state['jobs'].values():
            if record.get('status') == 'running' and record.get('process_pid'):
                try:
                    os.kill(record['process_pid'],0)
                except ProcessLookupError:
                    pass
                else:
                    raise ValueError('Previous job process may still be alive; inspect it before resuming')
        for job in manifest['jobs']:
            state['jobs'].setdefault(job['id'],dict(status='pending',attempts=0))
        state.update(worker_pid=os.getpid(),status='running',started_at=now())
        deadline = time.monotonic() + max_seconds
        def checkpoint(progress=False):
            state['heartbeat_at'] = now()
            if progress:
                state['last_progress_at'] = state['heartbeat_at']
            atomic_json(state_path,state)
        checkpoint(True)
        failed = False
        for job in manifest['jobs']:
            ident = job['id']
            record = state['jobs'].setdefault(ident,dict(status='pending',attempts=0))
            source_paths = job['sources'] + job['inputs'] + [str(Path(__file__).resolve())]
            try:
                inputs = file_hashes(source_paths)
            except OSError as exc:
                record.update(status='failed',error=str(exc))
                failed = True
                checkpoint(True)
                continue
            if record['status'] == 'completed' and record.get('source_input_sha256') == inputs:
                try:
                    if record.get('output_sha256') == file_hashes(job['outputs']):
                        continue
                except OSError:
                    pass
            if time.monotonic() >= deadline:
                record.update(status='pending',reason='Campaign time budget exhausted before start')
                state['status'] = 'paused'
                checkpoint(True)
                return 2
            log_path = writable(state_path.parent / (state_path.stem+'-'+ident+'.log'))
            record.update(status='running',attempts=record['attempts']+1,started_at=now(),
                          source_input_sha256=inputs,log=str(log_path),argv=job['argv'])
            record.pop('error',None)
            checkpoint(True)
            process = None
            try:
                # Remove stale outputs before rerun so a command that produces
                # nothing cannot accidentally inherit a previous successful file.
                for output in job['outputs']:
                    path = writable(output)
                    path.parent.mkdir(parents=True,exist_ok=True)
                    if path.exists():
                        backup = path.with_name(path.name+f'.previous-{record["attempts"]}')
                        path.replace(backup)
                with log_path.open('ab') as log:
                    log.write(('\nCampaign attempt '+str(record['attempts'])+' '+now()+'\n').encode())
                    log.flush()
                    process = subprocess.Popen(job['argv'],cwd=REPO,stdout=log,stderr=subprocess.STDOUT,
                                               shell=False,start_new_session=True)
                    record['process_pid'] = process.pid
                    job_deadline = min(deadline,time.monotonic()+job['timeout_seconds'])
                    while process.poll() is None:
                        remaining = job_deadline-time.monotonic()
                        if remaining <= 0:
                            stop_process(process)
                            raise TimeoutError('Job or campaign time budget exhausted')
                        try:
                            process.wait(timeout=min(heartbeat_seconds,remaining))
                        except subprocess.TimeoutExpired:
                            checkpoint()
                record['returncode'] = process.returncode
                if process.returncode:
                    raise RuntimeError(f'Command exited {process.returncode}; inspect {log_path}')
                if file_hashes(source_paths) != inputs:
                    raise RuntimeError('Source/input changed during job; results not certified')
                if job.get('require_json_complete', False):
                    for output in job['outputs']:
                        result = json.loads(resolve(output).read_text())
                        if not isinstance(result,dict) or result.get('complete') is not True:
                            raise RuntimeError('Benchmark output is not marked complete: '+output)
                record['output_sha256'] = file_hashes(job['outputs'])
                record.update(status='completed',finished_at=now())
            except KeyboardInterrupt:
                if process is not None:
                    stop_process(process)
                record.update(status='failed',error='Worker interrupted',finished_at=now())
                state['status'] = 'paused'
                checkpoint(True)
                return 130
            except (OSError,RuntimeError,TimeoutError,ValueError) as exc:
                if process is not None:
                    stop_process(process)
                record.update(status='failed',error=str(exc),finished_at=now())
                failed = True
            checkpoint(True)
        state['status'] = 'failed' if failed else 'completed'
        state['finished_at'] = now()
        checkpoint(True)
        return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    parser.add_argument('--state',required=True)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--max-seconds',type=float,default=3600)
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(run_campaign(args.manifest,args.state,resume=args.resume,max_seconds=args.max_seconds))


if __name__ == '__main__':
    main()
