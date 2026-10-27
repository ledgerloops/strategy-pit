"""Idempotent infrastructure migration; no demo resets or token rotation."""
import os
from hosted_storage import PgStoreFactory


def main():
    stores=PgStoreFactory(os.environ['DATABASE_URL'],max_connections=1)
    try:
        stores.initialize()
        stores.assert_ready()
        stores.create('accounts')
    finally:
        stores.close()


if __name__=='__main__':
    main()
