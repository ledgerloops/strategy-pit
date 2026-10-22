"""Run the HTTP server and background wakeups together on one Heroku dyno."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def supervise(commands, *, shutdown_timeout=20, poll_interval=.1):
    """Fail the dyno when either service exits; stop and reap both process groups."""
    stopping = None
    children = []
    previous_handlers = {}

    def stop(signum, _frame):
        nonlocal stopping
        stopping = signum

    def send(signum):
        for _name, child in children:
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass

    for signum in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[signum] = signal.signal(signum, stop)
    try:
        for name, command in commands:
            if stopping:
                break
            children.append((name, subprocess.Popen(command, start_new_session=True)))
        while not stopping:
            for name, child in children:
                if child.poll() is not None:
                    print(f'{name} exited; restarting the dyno is required', file=sys.stderr, flush=True)
                    return 1
            time.sleep(poll_interval)
        return 128 + stopping
    except OSError:
        print('Unable to start a hosted service', file=sys.stderr, flush=True)
        return 1
    finally:
        send(signal.SIGTERM)
        deadline = time.monotonic() + shutdown_timeout
        while any(child.poll() is None for _name, child in children) and time.monotonic() < deadline:
            time.sleep(poll_interval)
        # Also remove orphan descendants if a service exited before its children.
        send(signal.SIGKILL)
        for _name, child in children:
            child.wait()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def main():
    app = Path(__file__).resolve().parent
    return supervise([
        ('web', [sys.executable, '-m', 'gunicorn', '--chdir', str(app),
                 '--workers', '2', '--threads', '4', '--bind', '0.0.0.0:' + os.environ['PORT'],
                 '--timeout', '45', '--graceful-timeout', '15', 'hosted_server:create_app()']),
        ('worker', [sys.executable, str(app / 'hosted_worker.py')]),
    ])


if __name__ == '__main__':
    raise SystemExit(main())
