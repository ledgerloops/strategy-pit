//! Run against a disposable database, using a non-superuser/non-BYPASSRLS role:
//! LEDGERLOOPS_TEST_POSTGRES_DSN=... cargo test --test postgres_store -- --ignored
use atomic_lib::db::kv_store::{KvPair, KvStore};
use atomic_lib::db::trees::{Method, Operation, Tree};
use ledgerloops_atomic::postgres_store::PostgresStore;
use postgres::{Client, NoTls};
use sha2::{Digest, Sha256};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

static SERIAL: AtomicU64 = AtomicU64::new(0);

fn unique() -> String {
    format!(
        "kv_{}_{}_{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        SERIAL.fetch_add(1, Ordering::Relaxed)
    )
}

struct Fixture {
    dsn: String,
    namespace: String,
    store: Option<PostgresStore>,
}

impl Fixture {
    fn new() -> Self {
        let dsn = std::env::var("LEDGERLOOPS_TEST_POSTGRES_DSN")
            .expect("Set LEDGERLOOPS_TEST_POSTGRES_DSN to a disposable database");
        let namespace = unique();
        let store = PostgresStore::connect_no_tls(&dsn, &namespace).unwrap();
        Self {
            dsn,
            namespace,
            store: Some(store),
        }
    }

    fn store(&self) -> &PostgresStore {
        self.store.as_ref().unwrap()
    }

    fn reopen(&mut self) {
        drop(self.store.take());
        let deadline = Instant::now() + Duration::from_secs(3);
        loop {
            match PostgresStore::connect_no_tls(&self.dsn, &self.namespace) {
                Ok(store) => {
                    self.store = Some(store);
                    return;
                }
                Err(error)
                    if error.to_string().contains("active writer") && Instant::now() < deadline =>
                {
                    std::thread::sleep(Duration::from_millis(20));
                }
                Err(error) => panic!("Could not reopen isolated test namespace: {error}"),
            }
        }
    }

    fn stored(&self, tree: Tree, key: &[u8]) -> Option<Vec<u8>> {
        let mut client = Client::connect(&self.dsn, NoTls).unwrap();
        let mut tx = client.transaction().unwrap();
        tx.query_one(
            "SELECT set_config('ledgerloops.atomic_namespace',$1,true)",
            &[&self.namespace],
        )
        .unwrap();
        tx.query_opt(
            "SELECT value FROM public.atomic_kv WHERE namespace=$1 AND tree_name=$2 AND key=$3",
            &[&self.namespace, &tree.name(), &key],
        )
        .unwrap()
        .map(|row| row.get(0))
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        if let Some(store) = &self.store {
            for tree in Tree::ALL {
                let _ = store.clear_tree(tree);
            }
        }
    }
}

fn insert(tree: Tree, key: &[u8], value: &[u8]) -> Operation {
    Operation {
        tree,
        method: Method::Insert,
        key: key.to_vec(),
        val: Some(value.to_vec()),
    }
}

fn entries(store: &PostgresStore, tree: Tree) -> Vec<KvPair> {
    store
        .iter_tree(tree)
        .collect::<Result<Vec<_>, _>>()
        .unwrap()
}

struct FailureTrigger {
    client: Client,
    name: String,
}

impl FailureTrigger {
    fn new(fixture: &Fixture) -> Self {
        let mut client = Client::connect(&fixture.dsn, NoTls).unwrap();
        let name = unique();
        // Both identifiers and namespace originate in unique(), never a user.
        client
            .batch_execute(&format!(
                "CREATE FUNCTION public.{name}() RETURNS trigger LANGUAGE plpgsql AS $$
             BEGIN RAISE EXCEPTION 'injected failure'; END $$;
             CREATE TRIGGER {name} BEFORE INSERT OR UPDATE ON public.atomic_kv
             FOR EACH ROW WHEN (NEW.namespace='{}' AND NEW.key=decode('72656a656374','hex'))
             EXECUTE FUNCTION public.{name}();",
                fixture.namespace
            ))
            .unwrap();
        Self { client, name }
    }
}

impl Drop for FailureTrigger {
    fn drop(&mut self) {
        let _ =
            self.client.batch_execute(&format!(
            "DROP TRIGGER IF EXISTS {} ON public.atomic_kv; DROP FUNCTION IF EXISTS public.{}();",
            self.name, self.name));
    }
}

#[test]
#[ignore = "requires disposable PostgreSQL via LEDGERLOOPS_TEST_POSTGRES_DSN"]
fn namespace_and_tree_isolation_with_reopen() {
    let mut first = Fixture::new();
    let second = Fixture::new();
    first
        .store()
        .insert(Tree::Resources, b"same", b"first")
        .unwrap();
    first
        .store()
        .insert(Tree::LoroSnapshots, b"same", b"snapshot")
        .unwrap();
    second
        .store()
        .insert(Tree::Resources, b"same", b"second")
        .unwrap();
    first.store().flush().unwrap();
    first.reopen();
    assert_eq!(
        first.store().get(Tree::Resources, b"same").unwrap(),
        Some(b"first".to_vec())
    );
    assert_eq!(
        first.store().get(Tree::LoroSnapshots, b"same").unwrap(),
        Some(b"snapshot".to_vec())
    );
    assert_eq!(
        second.store().get(Tree::Resources, b"same").unwrap(),
        Some(b"second".to_vec())
    );
    first.store().remove(Tree::Resources, b"same").unwrap();
    assert!(!first
        .store()
        .contains_key(Tree::Resources, b"same")
        .unwrap());
    assert!(second
        .store()
        .contains_key(Tree::Resources, b"same")
        .unwrap());
}

#[test]
#[ignore = "requires disposable PostgreSQL via LEDGERLOOPS_TEST_POSTGRES_DSN"]
fn writer_lease_is_held_until_store_drop() {
    let mut fixture = Fixture::new();
    assert!(PostgresStore::connect_no_tls(&fixture.dsn, &fixture.namespace).is_err());
    let independent = Fixture::new();
    independent
        .store()
        .insert(Tree::Resources, b"independent", b"yes")
        .unwrap();
    fixture
        .store()
        .insert(Tree::Resources, b"persist", b"yes")
        .unwrap();
    fixture.reopen();
    assert_eq!(
        fixture.store().get(Tree::Resources, b"persist").unwrap(),
        Some(b"yes".to_vec())
    );
}

#[test]
#[ignore = "requires disposable PostgreSQL via LEDGERLOOPS_TEST_POSTGRES_DSN"]
fn binary_prefixes_ranges_and_pages_are_ordered() {
    let fixture = Fixture::new();
    let keys = vec![
        vec![],
        vec![0],
        vec![0, 255],
        vec![1],
        vec![1, 0],
        vec![1, 255],
        vec![2],
        vec![255],
        vec![255, 0],
        vec![255, 255],
        vec![255, 255, 0],
    ];
    let operations: Vec<_> = keys
        .iter()
        .enumerate()
        .map(|(index, key)| insert(Tree::Blobs, key, &vec![7; index + 1]))
        .collect();
    fixture.store().apply_batch(&operations).unwrap();
    for prefix in [
        vec![],
        vec![0],
        vec![1],
        vec![1, 255],
        vec![255],
        vec![255, 255],
        vec![255, 255, 255],
    ] {
        let actual: Vec<_> = fixture
            .store()
            .scan_prefix(Tree::Blobs, &prefix)
            .map(|row| row.unwrap().0)
            .collect();
        let expected: Vec<_> = keys
            .iter()
            .filter(|key| key.starts_with(&prefix))
            .cloned()
            .collect();
        assert_eq!(actual, expected);
    }
    let expected: Vec<_> = keys
        .iter()
        .filter(|key| key.as_slice() >= &[1][..] && key.as_slice() < &[255][..])
        .cloned()
        .collect();
    let forward: Vec<_> = fixture
        .store()
        .range(Tree::Blobs, vec![1], vec![255], false)
        .map(|row| row.unwrap().0)
        .collect();
    assert_eq!(forward, expected);
    let reverse: Vec<_> = fixture
        .store()
        .range(Tree::Blobs, vec![1], vec![255], true)
        .map(|row| row.unwrap().0)
        .collect();
    assert_eq!(reverse, expected.into_iter().rev().collect::<Vec<_>>());
    let page = fixture
        .store()
        .range_page(Tree::Blobs, vec![1], vec![255], 2)
        .unwrap();
    assert_eq!(page.len(), 2);
    assert_eq!(
        fixture
            .store()
            .range_value_sizes(Tree::Blobs, vec![1], vec![255], 2)
            .unwrap(),
        page.iter()
            .map(|(key, value)| (key.clone(), value.len() as u64))
            .collect::<Vec<_>>()
    );
    assert!(fixture
        .store()
        .range_page(Tree::Blobs, vec![2], vec![1], 2)
        .unwrap()
        .is_empty());
    assert!(fixture
        .store()
        .range_page(Tree::Blobs, vec![], vec![255], 0)
        .unwrap()
        .is_empty());
    assert_eq!(
        fixture.store().first_entry(Tree::Blobs).unwrap().unwrap().0,
        Vec::<u8>::new()
    );
    assert_eq!(fixture.store().len(Tree::Blobs).unwrap(), keys.len());
}

#[test]
#[ignore = "requires disposable PostgreSQL via LEDGERLOOPS_TEST_POSTGRES_DSN"]
fn apply_batch_failure_rolls_back_every_tree() {
    let fixture = Fixture::new();
    fixture
        .store()
        .insert(Tree::Resources, b"old", b"before")
        .unwrap();
    let _trigger = FailureTrigger::new(&fixture);
    let failure = fixture
        .store()
        .apply_batch(&[
            insert(Tree::Resources, b"old", b"after"),
            insert(Tree::LoroSnapshots, b"new", b"snapshot"),
            insert(Tree::Envelopes, b"reject", b"fabricated-private-value"),
        ])
        .unwrap_err();
    assert!(!failure.to_string().contains("fabricated-private-value"));
    assert_eq!(
        fixture.store().get(Tree::Resources, b"old").unwrap(),
        Some(b"before".to_vec())
    );
    assert_eq!(
        fixture.store().get(Tree::LoroSnapshots, b"new").unwrap(),
        None
    );
    assert_eq!(
        fixture.store().get(Tree::Envelopes, b"reject").unwrap(),
        None
    );
    assert!(fixture
        .store()
        .apply_batch(&[
            insert(Tree::Resources, b"must-not-land", b"x"),
            Operation {
                tree: Tree::Resources,
                method: Method::Insert,
                key: b"invalid".to_vec(),
                val: None
            },
        ])
        .is_err());
    assert!(!fixture
        .store()
        .contains_key(Tree::Resources, b"must-not-land")
        .unwrap());
}

#[test]
#[ignore = "requires disposable PostgreSQL via LEDGERLOOPS_TEST_POSTGRES_DSN"]
fn buffered_batches_have_read_your_writes_and_durable_commit() {
    let fixture = Fixture::new();
    fixture
        .store()
        .insert(Tree::Resources, b"old", b"before")
        .unwrap();
    fixture.store().begin_batch();
    fixture.store().remove(Tree::Resources, b"old").unwrap();
    fixture
        .store()
        .insert(Tree::Resources, b"new", b"pending")
        .unwrap();
    assert_eq!(fixture.store().get(Tree::Resources, b"old").unwrap(), None);
    assert_eq!(
        fixture.store().get(Tree::Resources, b"new").unwrap(),
        Some(b"pending".to_vec())
    );
    assert_eq!(
        entries(fixture.store(), Tree::Resources),
        vec![(b"new".to_vec(), b"pending".to_vec())]
    );
    assert_eq!(
        fixture.stored(Tree::Resources, b"old"),
        Some(b"before".to_vec())
    );
    assert_eq!(fixture.stored(Tree::Resources, b"new"), None);
    assert!(fixture.store().flush().is_err());
    fixture.store().clear_tree(Tree::Resources).unwrap();
    fixture
        .store()
        .insert(Tree::Resources, b"last", b"after-clear")
        .unwrap();
    assert_eq!(fixture.store().len(Tree::Resources).unwrap(), 1);
    fixture.store().commit_batch().unwrap();
    fixture.store().flush().unwrap();
    assert_eq!(
        fixture.stored(Tree::Resources, b"last"),
        Some(b"after-clear".to_vec())
    );
    assert_eq!(fixture.stored(Tree::Resources, b"old"), None);
}

#[test]
#[ignore = "requires disposable PostgreSQL via LEDGERLOOPS_TEST_POSTGRES_DSN"]
fn failed_buffer_commit_can_retry_without_partial_database_changes() {
    let fixture = Fixture::new();
    let trigger = FailureTrigger::new(&fixture);
    fixture.store().begin_batch();
    fixture
        .store()
        .insert(Tree::Resources, b"first", b"one")
        .unwrap();
    fixture
        .store()
        .insert(Tree::Outbox, b"reject", b"two")
        .unwrap();
    assert!(fixture.store().commit_batch().is_err());
    assert_eq!(fixture.stored(Tree::Resources, b"first"), None);
    assert_eq!(fixture.stored(Tree::Outbox, b"reject"), None);
    assert_eq!(
        fixture.store().get(Tree::Resources, b"first").unwrap(),
        Some(b"one".to_vec())
    );
    drop(trigger);
    fixture.store().commit_batch().unwrap();
    assert_eq!(
        fixture.stored(Tree::Resources, b"first"),
        Some(b"one".to_vec())
    );
    assert_eq!(
        fixture.stored(Tree::Outbox, b"reject"),
        Some(b"two".to_vec())
    );
}

#[test]
#[ignore = "requires disposable PostgreSQL via LEDGERLOOPS_TEST_POSTGRES_DSN"]
fn forced_rls_denies_missing_scope_and_scopes_unfiltered_reads() {
    let first = Fixture::new();
    let second = Fixture::new();
    first
        .store()
        .insert(Tree::Resources, b"only-first", b"one")
        .unwrap();
    second
        .store()
        .insert(Tree::Resources, b"only-second", b"two")
        .unwrap();
    let mut raw = Client::connect(&first.dsn, NoTls).unwrap();
    assert_eq!(
        raw.query_one("SELECT count(*) FROM public.atomic_kv", &[])
            .unwrap()
            .get::<_, i64>(0),
        0
    );
    let digest = Sha256::digest(b"unscoped").to_vec();
    let failure = raw
        .execute(
            "INSERT INTO public.atomic_kv(namespace,tree_name,key_digest,key,value) VALUES($1,$2,$3,$4,$5)",
            &[
                &first.namespace,
                &Tree::Resources.name(),
                &digest,
                &&b"unscoped"[..],
                &&b"x"[..]
            ]
        )
        .unwrap_err();
    assert_eq!(
        failure.code(),
        Some(&postgres::error::SqlState::INSUFFICIENT_PRIVILEGE)
    );
    {
        let mut tx = raw.transaction().unwrap();
        tx.query_one(
            "SELECT set_config('ledgerloops.atomic_namespace',$1,true)",
            &[&first.namespace],
        )
        .unwrap();
        let rows = tx.query("SELECT key FROM public.atomic_kv", &[]).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].get::<_, Vec<u8>>(0), b"only-first".to_vec());
        tx.commit().unwrap();
    }
    assert_eq!(
        raw.query_one("SELECT count(*) FROM public.atomic_kv", &[])
            .unwrap()
            .get::<_, i64>(0),
        0
    );
}

#[test]
#[ignore = "requires disposable PostgreSQL via LEDGERLOOPS_TEST_POSTGRES_DSN"]
fn long_keys_are_not_limited_by_postgresql_btree_entry_size() {
    let fixture = Fixture::new();
    let mut seed = 17u32;
    let key: Vec<u8> = (0..32768)
        .map(|_| {
            seed = seed.wrapping_mul(1664525).wrapping_add(1013904223);
            (seed >> 24) as u8
        })
        .collect();
    fixture
        .store()
        .insert(Tree::PropValSub, &key, b"long-indexed-value")
        .unwrap();
    assert_eq!(
        fixture.store().get(Tree::PropValSub, &key).unwrap(),
        Some(b"long-indexed-value".to_vec())
    );
    let prefix: Vec<_> = fixture
        .store()
        .scan_prefix(Tree::PropValSub, &key[..8192])
        .collect::<Result<Vec<_>, _>>()
        .unwrap();
    assert_eq!(prefix, vec![(key.clone(), b"long-indexed-value".to_vec())]);
    let mut end = key.clone();
    end.push(0);
    assert_eq!(
        fixture
            .store()
            .range_page(Tree::PropValSub, key.clone(), end, 1)
            .unwrap(),
        prefix
    );
    fixture.store().remove(Tree::PropValSub, &key).unwrap();
    assert!(!fixture
        .store()
        .contains_key(Tree::PropValSub, &key)
        .unwrap());
}

#[test]
#[ignore = "requires disposable PostgreSQL via LEDGERLOOPS_TEST_POSTGRES_DSN"]
fn fingerprint_collision_rejects_the_entire_batch_without_overwriting() {
    let fixture = Fixture::new();
    let mut raw = Client::connect(&fixture.dsn, NoTls).unwrap();
    let digest = Sha256::digest(b"target-key").to_vec();
    {
        let mut tx = raw.transaction().unwrap();
        tx.query_one(
            "SELECT set_config('ledgerloops.atomic_namespace',$1,true)",
            &[&fixture.namespace],
        )
        .unwrap();
        // Artificial collision fixture: a different full key occupies the
        // desired digest. This does not require finding a real SHA256 collision.
        tx.execute(
            "INSERT INTO public.atomic_kv(namespace,tree_name,key_digest,key,value)
                    VALUES($1,$2,$3,$4,$5)",
            &[
                &fixture.namespace,
                &Tree::Resources.name(),
                &digest,
                &&b"other-key"[..],
                &&b"preserved"[..],
            ],
        )
        .unwrap();
        tx.commit().unwrap();
    }
    let result = fixture.store().apply_batch(&[
        insert(Tree::LoroSnapshots, b"must-rollback", b"new"),
        insert(Tree::Resources, b"target-key", b"must-not-overwrite"),
    ]);
    assert!(result.unwrap_err().to_string().contains("digest collision"));
    assert_eq!(
        fixture.stored(Tree::Resources, b"other-key"),
        Some(b"preserved".to_vec())
    );
    assert_eq!(fixture.stored(Tree::LoroSnapshots, b"must-rollback"), None);
    fixture
        .store()
        .remove(Tree::Resources, b"target-key")
        .unwrap();
    assert_eq!(
        fixture.stored(Tree::Resources, b"other-key"),
        Some(b"preserved".to_vec())
    );
}

async fn exercise_inside_tokio() {
    // Construct, query, iterate, commit and destroy the PostgreSQL client while
    // the calling thread is entered into Tokio. A synchronous postgres::Client
    // on this thread panics during runtime nesting, even if connected elsewhere.
    let mut fixture = Fixture::new();
    fixture
        .store()
        .insert(Tree::Resources, b"async", b"initial")
        .unwrap();
    fixture.store().begin_batch();
    fixture
        .store()
        .insert(Tree::Resources, b"async", b"committed")
        .unwrap();
    assert_eq!(
        fixture.store().get(Tree::Resources, b"async").unwrap(),
        Some(b"committed".to_vec())
    );
    fixture.store().commit_batch().unwrap();
    assert_eq!(
        entries(fixture.store(), Tree::Resources),
        vec![(b"async".to_vec(), b"committed".to_vec())]
    );
    fixture.store().flush().unwrap();
    fixture.reopen();
    assert_eq!(
        fixture.store().get(Tree::Resources, b"async").unwrap(),
        Some(b"committed".to_vec())
    );
    // Drop is deliberately inside the runtime, including fixture cleanup.
    drop(fixture);
}

#[tokio::test(flavor = "current_thread")]
#[ignore = "requires disposable PostgreSQL via LEDGERLOOPS_TEST_POSTGRES_DSN"]
async fn postgres_client_lifecycle_is_safe_in_current_thread_tokio() {
    exercise_inside_tokio().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
#[ignore = "requires disposable PostgreSQL via LEDGERLOOPS_TEST_POSTGRES_DSN"]
async fn postgres_client_lifecycle_is_safe_in_multithread_tokio() {
    exercise_inside_tokio().await;
}
