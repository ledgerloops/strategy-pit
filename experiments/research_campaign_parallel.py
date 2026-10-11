"""Finite parallel wrapper around the existing bounded, hashed campaign worker."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import threading
import time
from research_campaign import atomic_json, load_manifest, run_campaign, writable


def run_parallel(manifest_path,state_path,*,resume=False,max_workers=3,max_seconds=7200):
    if not 1<=max_workers<=3 or not 0<max_seconds<=7200:
        raise ValueError('At most3 workers and7200seconds')
    manifest,fingerprint=load_manifest(manifest_path)
    if len(manifest['jobs'])>12 or any(j['timeout_seconds']>1200 for j in manifest['jobs']):
        raise ValueError('At most12 jobs,1200seconds each')
    state_path=writable(state_path);state_path.parent.mkdir(parents=True,exist_ok=True)
    source=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with state_path.with_suffix(state_path.suffix+'.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if state_path.exists():
            old=json.loads(state_path.read_text())
            if not resume:raise ValueError('Existing parallel state requires explicit --resume')
            if old['manifest_sha256']!=fingerprint or old['driver_sha256']!=source:
                raise ValueError('Changed parallel manifest or driver')
        deadline=time.monotonic()+max_seconds
        stop=threading.Event()
        launch_ready=threading.Event()
        state=dict(complete=False,status='running',worker_pid=os.getpid(),manifest_sha256=fingerprint,
                   driver_sha256=source,max_workers=max_workers,max_seconds=max_seconds,
                   started_at=datetime.now(timezone.utc).isoformat(),jobs={})
        children={}
        for job in manifest['jobs']:
            prefix=state_path.parent/(state_path.stem+'-'+job['id'])
            child_manifest=prefix.with_name(prefix.name+'-manifest.json')
            child_state=prefix.with_name(prefix.name+'-state.json')
            atomic_json(child_manifest,dict(version=1,purpose=manifest.get('purpose',''),jobs=[job]))
            children[job['id']]=(child_manifest,child_state,job)
            state['jobs'][job['id']]=dict(status='pending',state=str(child_state))
        atomic_json(state_path,state)
        def work(ident):
            launch_ready.wait()
            path,child_state,_=children[ident]
            remaining=deadline-time.monotonic()
            if stop.is_set() or remaining<=0:return dict(status='pending',reason='Parallel deadline/interruption')
            code=run_campaign(path,child_state,resume=child_state.exists(),max_seconds=min(remaining,1200),heartbeat_seconds=.25)
            child=json.loads(child_state.read_text())
            return dict(status=child['status'],returncode=code,state=str(child_state))
        def terminate_active():
            signalled=[]
            # Each PID came from our own child worker state; verify its command
            # before signalling its session process group, never an unrelated PID.
            for _,child_state,job in children.values():
                if not child_state.exists():continue
                child=json.loads(child_state.read_text())
                record=child.get('jobs',{}).get(job['id'],{})
                pid=record.get('process_pid')
                if record.get('status')!='running' or not pid:continue
                try:
                    command=Path(f'/proc/{pid}/cmdline').read_bytes()
                    expected=b'\0'.join(arg.encode() for arg in job['argv'])+b'\0'
                    started=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
                    if command==expected and os.getpgid(pid)==pid:
                        os.killpg(pid,signal.SIGTERM)
                        signalled.append((pid,expected,started))
                except ProcessLookupError:pass
                except FileNotFoundError:pass
            if signalled:time.sleep(.2)
            for pid,expected,started in signalled:
                try:
                    current_start=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
                    if (expected==Path(f'/proc/{pid}/cmdline').read_bytes() and
                            started==current_start and os.getpgid(pid)==pid):
                        os.killpg(pid,signal.SIGKILL)
                except (FileNotFoundError,ProcessLookupError):pass
        pool=ThreadPoolExecutor(max_workers=max_workers)
        futures={}
        try:
            for ident in children:
                futures[pool.submit(work,ident)]=ident
            launch_ready.set()
            for future in as_completed(futures,timeout=max_seconds):
                ident=futures[future]
                try:state['jobs'][ident]=future.result()
                except Exception as error:state['jobs'][ident]=dict(status='failed',error=f'{type(error).__name__}: {error}')
                state['last_progress_at']=datetime.now(timezone.utc).isoformat()
                atomic_json(state_path,state)
        except (TimeoutError,KeyboardInterrupt) as error:
            stop.set();launch_ready.set()
            for future in futures:future.cancel()
            state.update(status='paused',reason=type(error).__name__)
            atomic_json(state_path,state)
            # Repeated scans close the race where a worker passed its stop
            # check but has not registered its subprocess at interruption.
            while any(not future.done() for future in futures):
                terminate_active()
                time.sleep(.05)
            for future,ident in futures.items():
                if future.done() and not future.cancelled():
                    try:state['jobs'][ident]=future.result()
                    except Exception as child_error:state['jobs'][ident]=dict(status='failed',error=str(child_error))
        finally:
            if not launch_ready.is_set():
                stop.set();launch_ready.set()
            pool.shutdown(wait=True,cancel_futures=True)
        if state['status']=='running':
            state['complete']=all(j['status']=='completed' for j in state['jobs'].values())
            state['status']='completed' if state['complete'] else 'failed'
        state['finished_at']=datetime.now(timezone.utc).isoformat();atomic_json(state_path,state)
        return 0 if state['complete'] else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest');p.add_argument('--state',required=True);p.add_argument('--resume',action='store_true')
    p.add_argument('--max-workers',type=int,default=3);p.add_argument('--max-seconds',type=float,default=7200)
    a=p.parse_args()
    def interrupted(signum,frame):
        signal.signal(signal.SIGTERM,signal.SIG_IGN)
        signal.signal(signal.SIGINT,signal.SIG_IGN)
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGINT,interrupted)
    raise SystemExit(run_parallel(a.manifest,a.state,resume=a.resume,max_workers=a.max_workers,max_seconds=a.max_seconds))


if __name__=='__main__':main()
