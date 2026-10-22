"""Fair infrastructure wakeups; each task receives only one node identity."""
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import signal
import threading

from hosted_runtime import HostedRuntime
from hosted_storage import PgStoreFactory


def main():
    stopped=threading.Event()
    for signum in (signal.SIGTERM,signal.SIGINT):
        signal.signal(signum,lambda *_: stopped.set())
    stores=PgStoreFactory(os.environ['DATABASE_URL'],max_connections=4)
    runtime=HostedRuntime(stores,os.environ.get('PUBLIC_ORIGIN','https://app.ledgerloops.com'))
    pending={}
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            while not stopped.wait(.5):
                for key,future in list(pending.items()):
                    if future.done():
                        if future.exception():
                            # Never log envelopes, credentials or balances.
                            logging.error('A local node wakeup failed; durable work will retry (%s)',type(future.exception()).__name__)
                        del pending[key]
                for node_id in runtime.scheduled_nodes():
                    if node_id not in pending:
                        pending[node_id]=executor.submit(runtime.tick,node_id)
    finally:
        stores.close()


if __name__=='__main__':
    main()
