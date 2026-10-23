"""Fair infrastructure wakeups; each task receives only one node identity.

The registry supplies only snapshot versions to the scheduler. Routing and
clearing still run inside the selected node, with no registry/version input.
Unchanged idle snapshots need not be downloaded on every half-second poll.
"""
from concurrent.futures import ThreadPoolExecutor
import logging
import math
import os
import signal
import threading
import time

from hosted_runtime import HostedRuntime
from hosted_storage import PgStoreFactory

POLL_SECONDS = .5
IDLE_HEARTBEAT_SECONDS = 60
ERROR_RETRY_SECONDS = 1


class WakeupSchedule:
    """Coalesce work by durable version without acknowledging unseen changes.

    Remember the version observed BEFORE submitting a tick. A message arriving
    during the tick, or between its commit and completion, must trigger another
    wakeup. Reading a newer version after completion would lose that signal.
    The volatile schedule is rebuilt from durable nodes after every restart.
    """
    def __init__(self):
        self.pending = {}
        self.seen = {}
        self.due = {}
        self.failed_until = {}

    @staticmethod
    def _next_due(result, now, wall_time):
        if not isinstance(result, dict):
            # A missing hint must not suppress recovery from an older runtime.
            return now+ERROR_RETRY_SECONDS
        delays = [IDLE_HEARTBEAT_SECONDS]
        if result.get('retry_outbox'):
            delays.append(POLL_SECONDS)
        search_at = result.get('next_search_at')
        if type(search_at) in (int, float) and math.isfinite(search_at):
            delays.append(max(POLL_SECONDS, search_at-wall_time))
        return now+min(delays)

    def collect(self, *, now=None, wall_time=None):
        now = time.monotonic() if now is None else now
        wall_time = time.time() if wall_time is None else wall_time
        for node_id, (version, future) in list(self.pending.items()):
            if not future.done():
                continue
            del self.pending[node_id]
            try:
                result = future.result()
            except Exception as error:
                # Do not advance the observed version on an uncertain outcome.
                # Freshly loading the durable node resolves commit ambiguity.
                self.failed_until[node_id] = now+ERROR_RETRY_SECONDS
                self.due[node_id] = now+ERROR_RETRY_SECONDS
                logging.error('A local node wakeup failed; durable work will retry (%s)', type(error).__name__)
            else:
                self.seen[node_id] = version
                self.failed_until.pop(node_id, None)
                self.due[node_id] = self._next_due(result, now, wall_time)

    def dispatch(self, versions, executor, tick, *, now=None):
        now = time.monotonic() if now is None else now
        for node_id, version in versions.items():
            if node_id in self.pending or now < self.failed_until.get(node_id, 0):
                continue
            if self.seen.get(node_id) != version or now >= self.due.get(node_id, 0):
                self.pending[node_id] = (version, executor.submit(tick, node_id))
        # Registry deletion is infrastructure-only. Never cancel an active tick.
        for node_id in set(self.seen)-set(versions)-set(self.pending):
            self.seen.pop(node_id, None)
            self.due.pop(node_id, None)
            self.failed_until.pop(node_id, None)


def main():
    stopped=threading.Event()
    for signum in (signal.SIGTERM,signal.SIGINT):
        signal.signal(signum,lambda *_: stopped.set())
    stores=PgStoreFactory(os.environ['DATABASE_URL'],max_connections=3)
    runtime=HostedRuntime(stores,os.environ.get('PUBLIC_ORIGIN','https://app.ledgerloops.com'))
    schedule=WakeupSchedule()
    registry_error=None
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            while not stopped.wait(POLL_SECONDS):
                schedule.collect()
                try:
                    versions=runtime.scheduled_node_versions()
                except Exception as error:
                    # A registry outage cannot discard completed work or create
                    # a second tick. Retry the small query on the next poll.
                    if registry_error != type(error):
                        logging.error('Node scheduling metadata is unavailable; retrying (%s)',type(error).__name__)
                    registry_error=type(error)
                    continue
                registry_error=None
                schedule.dispatch(versions,executor,runtime.tick)
    finally:
        stores.close()


if __name__=='__main__':
    main()
