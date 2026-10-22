"""Real subprocess lifecycle checks for the one-dyno supervisor; no database."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


CHILD = """
import os, signal, sys, time
from pathlib import Path
root, name, behavior = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
def stop(*_):
    (root / (name + '.stopped')).write_text('terminated')
    sys.exit(0)
signal.signal(signal.SIGTERM, signal.SIG_IGN if behavior == 'ignore' else stop)
(root / (name + '.ready')).write_text(str(os.getpid()))
while True:
    if behavior == 'fail' and (root / 'fail').exists():
        sys.exit(7)
    time.sleep(.01)
"""


class SingleDynoTests(unittest.TestCase):
    def start_services(self, root, behaviors, shutdown_timeout=1):
        commands = [(name, [sys.executable, '-c', CHILD, str(root), name, behavior])
                    for name, behavior in behaviors]
        program = ('import sys; from hosted_single import supervise; '
                   'sys.exit(supervise(' + repr(commands) + ', shutdown_timeout=' +
                   repr(shutdown_timeout) + ', poll_interval=.01))')
        process = subprocess.Popen([sys.executable, '-c', program],
                                   cwd=Path(__file__).resolve().parent,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.cleanup_process, process)
        deadline = time.monotonic() + 5
        while not all((root / (name + '.ready')).exists() for name, _ in behaviors):
            if process.poll() is not None or time.monotonic() >= deadline:
                self.fail('Services did not become ready')
            time.sleep(.01)
        return process

    @staticmethod
    def cleanup_process(process):
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        process.stderr.close()

    def assert_children_reaped(self, root):
        for path in root.glob('*.ready'):
            with self.assertRaises(ProcessLookupError):
                os.kill(int(path.read_text()), 0)

    def test_either_service_exit_stops_sibling_and_fails_dyno(self):
        for failing, sibling in [('worker', 'web'), ('web', 'worker')]:
            with self.subTest(failing=failing), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                process = self.start_services(root, [(failing, 'fail'), (sibling, 'wait')])
                (root / 'fail').touch()
                self.assertEqual(process.wait(timeout=5), 1)
                self.assertTrue((root / (sibling + '.stopped')).exists())
                self.assertIn(failing + ' exited', process.stderr.read())
                self.assert_children_reaped(root)

    def test_sigterm_reaches_both_services_and_reaps_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            process = self.start_services(root, [('web', 'wait'), ('worker', 'wait')])
            process.send_signal(signal.SIGTERM)
            self.assertEqual(process.wait(timeout=5), 128 + signal.SIGTERM)
            for name in ('web', 'worker'):
                self.assertTrue((root / (name + '.stopped')).exists())
            self.assert_children_reaped(root)

    def test_stuck_service_is_killed_after_bounded_shutdown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            process = self.start_services(root, [('web', 'wait'), ('worker', 'ignore')], .15)
            started = time.monotonic()
            process.terminate()
            self.assertEqual(process.wait(timeout=5), 128 + signal.SIGTERM)
            self.assertLess(time.monotonic() - started, 2)
            self.assertTrue((root / 'web.stopped').exists())
            self.assert_children_reaped(root)


if __name__ == '__main__':
    unittest.main()
