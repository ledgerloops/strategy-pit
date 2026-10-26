//! PostgreSQL storage for Atomic's actual KV trees, one row per key.
//!
//! The trusted host selects a namespace. Explicit predicates and forced RLS
//! protect omitted scope filters; this is not a SQL sandbox against the host.
//! A dedicated database thread owns the synchronous PostgreSQL client, so calls
//! and destruction are safe inside Tokio runtimes. The KV interface still blocks
//! its caller waiting for PostgreSQL; hosts should budget blocking work. A single actor
//! must serialize its writes; buffering is not a general transaction API and
//! does not prevent two independent actors from making conflicting decisions.

use atomic_lib::db::kv_store::{KvIter, KvPair, KvStore};
use atomic_lib::db::trees::{Method, Operation, Tree};
use atomic_lib::errors::{AtomicError, AtomicResult};
use postgres::{Client, Config, NoTls, Transaction};
use postgres_native_tls::MakeTlsConnector;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::sync::{mpsc, Mutex, MutexGuard};
use std::thread::JoinHandle;

pub const TABLE: &str = "public.atomic_kv";

#[derive(Clone)]
enum Command {
    Write(Operation),
    Clear(Tree),
}

struct State {
    client: Client,
    pending: Option<Vec<Command>>,
}

struct WorkerStore {
    namespace: String,
    state: Mutex<State>,
}

// postgres::Client owns a private Tokio runtime. Its construction, every call,
// and its destructor must stay outside the application's Tokio runtime. Even
// constructing it on a blocking thread and later moving it is insufficient.
type Job = Box<dyn FnOnce(&WorkerStore) + Send + 'static>;

pub struct PostgresStore {
    namespace: String,
    sender: Option<mpsc::Sender<Job>>,
    worker: Option<JoinHandle<()>>,
}

impl PostgresStore {
    /// Connect with certificate and hostname verification and required TLS.
    pub fn connect(dsn: &str, namespace: &str) -> AtomicResult<Self> {
        Self::start(dsn, namespace, false)
    }

    /// Explicit plaintext connection for isolated local tests only.
    pub fn connect_no_tls(dsn: &str, namespace: &str) -> AtomicResult<Self> {
        Self::start(dsn, namespace, true)
    }

    fn start(dsn: &str, namespace: &str, plaintext: bool) -> AtomicResult<Self> {
        let dsn = dsn.to_owned();
        let worker_namespace = namespace.to_owned();
        let (sender, receiver) = mpsc::channel::<Job>();
        let (ready_sender, ready_receiver) = mpsc::sync_channel(1);
        let worker = std::thread::Builder::new()
            .name("atomic-postgres".to_owned())
            .spawn(move || {
                let result = if plaintext {
                    WorkerStore::connect_no_tls(&dsn, &worker_namespace)
                } else {
                    WorkerStore::connect(&dsn, &worker_namespace)
                };
                match result {
                    Ok(store) => {
                        if ready_sender.send(Ok(())).is_ok() {
                            for job in receiver {
                                job(&store);
                            }
                        }
                        // Client and its private runtime are destroyed here.
                    }
                    Err(error) => {
                        let _ = ready_sender.send(Err(error));
                    }
                }
            })
            .map_err(|_| error("PostgreSQL KV worker could not start"))?;
        match ready_receiver.recv() {
            Ok(Ok(())) => Ok(Self {
                namespace: namespace.to_owned(),
                sender: Some(sender),
                worker: Some(worker),
            }),
            result => {
                drop(sender);
                let _ = worker.join();
                match result {
                    Ok(Err(error)) => Err(error),
                    _ => Err(error("PostgreSQL KV worker initialization failed")),
                }
            }
        }
    }

    pub fn namespace(&self) -> &str {
        &self.namespace
    }

    fn call<T, F>(&self, operation: F) -> AtomicResult<T>
    where
        T: Send + 'static,
        F: FnOnce(&WorkerStore) -> AtomicResult<T> + Send + 'static,
    {
        let (sender, receiver) = mpsc::sync_channel(1);
        self.sender
            .as_ref()
            .ok_or_else(|| error("PostgreSQL KV worker unavailable"))?
            .send(Box::new(move |store| {
                let _ = sender.send(operation(store));
            }))
            .map_err(|_| error("PostgreSQL KV worker unavailable"))?;
        receiver
            .recv()
            .map_err(|_| error("PostgreSQL KV worker stopped"))?
    }
}

impl Drop for PostgresStore {
    fn drop(&mut self) {
        // Disconnect before joining; this also releases the writer lease before
        // Drop returns, making immediate reopen reliable across runtime types.
        drop(self.sender.take());
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
    }
}

impl KvStore for PostgresStore {
    fn get(&self, tree: Tree, key: &[u8]) -> AtomicResult<Option<Vec<u8>>> {
        let key = key.to_vec();
        self.call(move |store| store.get(tree, &key))
    }
    fn insert(&self, tree: Tree, key: &[u8], value: &[u8]) -> AtomicResult<()> {
        let key = key.to_vec();
        let value = value.to_vec();
        self.call(move |store| store.insert(tree, &key, &value))
    }
    fn remove(&self, tree: Tree, key: &[u8]) -> AtomicResult<()> {
        let key = key.to_vec();
        self.call(move |store| store.remove(tree, &key))
    }
    fn contains_key(&self, tree: Tree, key: &[u8]) -> AtomicResult<bool> {
        Ok(self.get(tree, key)?.is_some())
    }
    fn scan_prefix(&self, tree: Tree, prefix: &[u8]) -> KvIter {
        let prefix = prefix.to_vec();
        WorkerStore::iterator(self.call(move |store| store.scan_prefix(tree, &prefix).collect()))
    }
    fn range(&self, tree: Tree, start: Vec<u8>, end: Vec<u8>, reverse: bool) -> KvIter {
        WorkerStore::iterator(
            self.call(move |store| store.range(tree, start, end, reverse).collect()),
        )
    }
    fn range_page(
        &self,
        tree: Tree,
        start: Vec<u8>,
        end: Vec<u8>,
        limit: usize,
    ) -> AtomicResult<Vec<KvPair>> {
        self.call(move |store| store.range_page(tree, start, end, limit))
    }
    fn range_value_sizes(
        &self,
        tree: Tree,
        start: Vec<u8>,
        end: Vec<u8>,
        limit: usize,
    ) -> AtomicResult<Vec<(Vec<u8>, u64)>> {
        self.call(move |store| store.range_value_sizes(tree, start, end, limit))
    }
    fn iter_tree(&self, tree: Tree) -> KvIter {
        WorkerStore::iterator(self.call(move |store| store.iter_tree(tree).collect()))
    }
    fn first_entry(&self, tree: Tree) -> AtomicResult<Option<KvPair>> {
        self.call(move |store| store.first_entry(tree))
    }
    fn clear_tree(&self, tree: Tree) -> AtomicResult<()> {
        self.call(move |store| store.clear_tree(tree))
    }
    fn apply_batch(&self, operations: &[Operation]) -> AtomicResult<()> {
        let operations = operations.to_vec();
        self.call(move |store| store.apply_batch(&operations))
    }
    fn flush(&self) -> AtomicResult<()> {
        self.call(|store| store.flush())
    }
    fn begin_batch(&self) {
        // The trait cannot return an error. Refuse to proceed if the worker has
        // failed rather than silently turning a buffered batch into live writes.
        self.call(|store| {
            store.begin_batch();
            Ok(())
        })
        .expect("PostgreSQL KV batch worker unavailable");
    }
    fn commit_batch(&self) -> AtomicResult<()> {
        self.call(|store| store.commit_batch())
    }
    fn len(&self, tree: Tree) -> AtomicResult<usize> {
        self.call(move |store| store.len(tree))
    }
}

fn error(message: &str) -> AtomicError {
    AtomicError::other_error(message.to_owned())
}

fn database_error(stage: &str, source: postgres::Error) -> AtomicError {
    // Error DETAIL can contain a key, resource, secret, or connection string.
    // A SQLSTATE is useful for diagnosis without exposing those values.
    match source.code() {
        Some(code) => error(&format!("PostgreSQL KV {stage} failed ({})", code.code())),
        None => error(&format!("PostgreSQL KV {stage} failed")),
    }
}

fn scoped<'a>(client: &'a mut Client, namespace: &str) -> AtomicResult<Transaction<'a>> {
    let mut transaction = client
        .transaction()
        .map_err(|e| database_error("transaction", e))?;
    transaction
        .query_one(
            "SELECT set_config('ledgerloops.atomic_namespace', $1, true)",
            &[&namespace],
        )
        .map_err(|e| database_error("scope", e))?;
    transaction
        .batch_execute("SET LOCAL synchronous_commit = on")
        .map_err(|e| database_error("durability", e))?;
    Ok(transaction)
}

/// Exclusive upper bound for all byte strings beginning with `prefix`.
/// An empty or all-0xff prefix has no finite upper bound.
fn prefix_successor(prefix: &[u8]) -> Option<Vec<u8>> {
    let mut end = prefix.to_vec();
    for index in (0..end.len()).rev() {
        if end[index] != u8::MAX {
            end[index] += 1;
            end.truncate(index + 1);
            return Some(end);
        }
    }
    None
}

impl WorkerStore {
    /// Connect with verified TLS. The default/prefer mode is tightened to
    /// require TLS; plaintext local tests must explicitly use `connect_no_tls`.
    pub fn connect(dsn: &str, namespace: &str) -> AtomicResult<Self> {
        let mut config: Config = dsn
            .parse()
            .map_err(|_| error("Invalid PostgreSQL configuration"))?;
        if config.get_ssl_mode() == postgres::config::SslMode::Disable {
            return Err(error(
                "PostgreSQL TLS disabled; use explicit local-test connection",
            ));
        }
        config.ssl_mode(postgres::config::SslMode::Require);
        let tls = native_tls::TlsConnector::builder()
            .build()
            .map_err(|_| error("PostgreSQL TLS initialization failed"))?;
        let client = config
            .connect(MakeTlsConnector::new(tls))
            .map_err(|e| database_error("connection", e))?;
        Self::from_client(client, namespace)
    }

    /// Explicit plaintext connection for isolated local tests only.
    pub fn connect_no_tls(dsn: &str, namespace: &str) -> AtomicResult<Self> {
        let client = Client::connect(dsn, NoTls).map_err(|e| database_error("connection", e))?;
        Self::from_client(client, namespace)
    }

    fn from_client(mut client: Client, namespace: &str) -> AtomicResult<Self> {
        if namespace.is_empty() || namespace.len() > 200 || namespace.contains('\0') {
            return Err(error(
                "A nonempty bounded PostgreSQL KV namespace is required",
            ));
        }
        let role = client
            .query_one(
                "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user",
                &[],
            )
            .map_err(|e| database_error("role check", e))?;
        if role.get::<_, bool>(0) || role.get::<_, bool>(1) {
            return Err(error(
                "PostgreSQL KV requires a role without SUPERUSER or BYPASSRLS",
            ));
        }
        // Atomic's resource caches and subject locks are local to one Db. Hold
        // one session lease for its entire lifetime so another process cannot
        // open a second authoritative Db over the same namespace. A failed
        // connection is never transparently replaced (which would lose this
        // fencing guarantee while retaining stale application caches).
        let lease = format!("ledgerloops-atomic-writer:{namespace}");
        let acquired: bool = client
            .query_one(
                "SELECT pg_try_advisory_lock(hashtextextended($1,0))",
                &[&lease],
            )
            .map_err(|e| database_error("writer lease", e))?
            .get(0);
        if !acquired {
            return Err(error(
                "PostgreSQL Atomic namespace already has an active writer",
            ));
        }
        let mut transaction = scoped(&mut client, namespace)?;
        transaction
            .batch_execute(
                "SELECT pg_advisory_xact_lock(hashtext('ledgerloops-atomic-kv-schema-v1'));
                 CREATE TABLE IF NOT EXISTS public.atomic_kv (
                   namespace TEXT NOT NULL,
                   tree_name TEXT NOT NULL,
                   key_digest BYTEA NOT NULL CHECK (octet_length(key_digest)=32),
                   key BYTEA NOT NULL,
                   value BYTEA NOT NULL,
                   PRIMARY KEY(namespace, tree_name, key_digest)
                 );
                 ALTER TABLE public.atomic_kv ENABLE ROW LEVEL SECURITY;
                 ALTER TABLE public.atomic_kv FORCE ROW LEVEL SECURITY;
                 DROP POLICY IF EXISTS namespace_scope ON public.atomic_kv;
                 CREATE POLICY namespace_scope ON public.atomic_kv
                   USING (namespace = NULLIF(current_setting('ledgerloops.atomic_namespace', true), ''))
                   WITH CHECK (namespace = NULLIF(current_setting('ledgerloops.atomic_namespace', true), ''));",
            )
            .map_err(|e| database_error("schema initialization", e))?;
        transaction
            .commit()
            .map_err(|e| database_error("schema commit", e))?;
        Ok(Self {
            namespace: namespace.to_owned(),
            state: Mutex::new(State {
                client,
                pending: None,
            }),
        })
    }

    fn lock(&self) -> AtomicResult<MutexGuard<'_, State>> {
        self.state
            .lock()
            .map_err(|_| error("PostgreSQL KV lock poisoned"))
    }

    fn execute_commands(&self, client: &mut Client, commands: &[Command]) -> AtomicResult<()> {
        if commands.is_empty() {
            return Ok(());
        }
        let mut transaction = scoped(client, &self.namespace)?;
        for command in commands {
            match command {
                Command::Clear(tree) => {
                    transaction
                        .execute(
                            "DELETE FROM public.atomic_kv WHERE namespace=$1 AND tree_name=$2",
                            &[&self.namespace, &tree.name()],
                        )
                        .map_err(|e| database_error("clear", e))?;
                }
                Command::Write(operation) => {
                    match operation.method {
                        Method::Insert => {
                            let value = operation
                                .val
                                .as_ref()
                                .ok_or_else(|| error("KV insert requires a value"))?;
                            // Index a fixed-size fingerprint, not the arbitrary
                            // Atomic key: PostgreSQL btrees cannot index long keys.
                            // An unlikely digest collision is rejected, never an
                            // overwrite of another logical key.
                            let digest = Sha256::digest(&operation.key).to_vec();
                            let changed = transaction.execute(
                            "INSERT INTO public.atomic_kv(namespace,tree_name,key_digest,key,value)
                             VALUES($1,$2,$3,$4,$5)
                             ON CONFLICT(namespace,tree_name,key_digest) DO UPDATE SET value=excluded.value
                             WHERE atomic_kv.key=excluded.key",
                            &[&self.namespace, &operation.tree.name(), &digest, &operation.key, value],
                        ).map_err(|e| database_error("insert", e))?;
                            if changed != 1 {
                                return Err(error("PostgreSQL KV key digest collision"));
                            }
                        }
                        Method::Delete => {
                            let digest = Sha256::digest(&operation.key).to_vec();
                            transaction.execute(
                            "DELETE FROM public.atomic_kv WHERE namespace=$1 AND tree_name=$2
                             AND key_digest=$3 AND key=$4",
                            &[&self.namespace, &operation.tree.name(), &digest, &operation.key],
                        ).map_err(|e| database_error("remove", e))?;
                        }
                    }
                }
            }
        }
        transaction
            .commit()
            .map_err(|e| database_error("commit", e))
    }

    fn write(&self, commands: Vec<Command>) -> AtomicResult<()> {
        let mut state = self.lock()?;
        if let Some(pending) = state.pending.as_mut() {
            pending.extend(commands);
            return Ok(());
        }
        self.execute_commands(&mut state.client, &commands)
    }

    fn pairs(
        &self,
        tree: Tree,
        start: &[u8],
        end: Option<&[u8]>,
        reverse: bool,
        limit: Option<usize>,
    ) -> AtomicResult<Vec<KvPair>> {
        if end.is_some_and(|end| start >= end) || limit == Some(0) {
            return Ok(Vec::new());
        }
        let mut state = self.lock()?;
        let sql_limit = if state.pending.is_some() { None } else { limit };
        let bound = end.map(<[u8]>::to_vec);
        let sql_limit = sql_limit
            .map(i64::try_from)
            .transpose()
            .map_err(|_| error("PostgreSQL KV range limit is too large"))?;
        let mut transaction = scoped(&mut state.client, &self.namespace)?;
        let sql = if reverse {
            "SELECT key,value FROM public.atomic_kv
             WHERE namespace=$1 AND tree_name=$2 AND key >= $3
               AND ($4::bytea IS NULL OR key < $4) ORDER BY key DESC LIMIT $5"
        } else {
            "SELECT key,value FROM public.atomic_kv
             WHERE namespace=$1 AND tree_name=$2 AND key >= $3
               AND ($4::bytea IS NULL OR key < $4) ORDER BY key ASC LIMIT $5"
        };
        let rows = transaction
            .query(
                sql,
                &[&self.namespace, &tree.name(), &start, &bound, &sql_limit],
            )
            .map_err(|e| database_error("range", e))?;
        transaction
            .commit()
            .map_err(|e| database_error("read commit", e))?;
        let mut pairs: BTreeMap<Vec<u8>, Vec<u8>> = rows
            .into_iter()
            .map(|row| (row.get(0), row.get(1)))
            .collect();
        if let Some(pending) = &state.pending {
            for command in pending {
                match command {
                    Command::Clear(current) if *current == tree => pairs.clear(),
                    Command::Write(op)
                        if op.tree == tree
                            && op.key.as_slice() >= start
                            && end.is_none_or(|end| op.key.as_slice() < end) =>
                    {
                        match op.method {
                            Method::Insert => {
                                let value = op
                                    .val
                                    .as_ref()
                                    .ok_or_else(|| error("KV insert requires a value"))?;
                                pairs.insert(op.key.clone(), value.clone());
                            }
                            Method::Delete => {
                                pairs.remove(&op.key);
                            }
                        }
                    }
                    _ => {}
                }
            }
        }
        let mut pairs: Vec<_> = pairs.into_iter().collect();
        if reverse {
            pairs.reverse();
        }
        if let Some(limit) = limit {
            pairs.truncate(limit);
        }
        Ok(pairs)
    }

    fn iterator(result: AtomicResult<Vec<KvPair>>) -> KvIter {
        match result {
            Ok(pairs) => Box::new(pairs.into_iter().map(Ok)),
            Err(error) => Box::new(std::iter::once(Err(error))),
        }
    }
}

impl KvStore for WorkerStore {
    fn get(&self, tree: Tree, key: &[u8]) -> AtomicResult<Option<Vec<u8>>> {
        let mut state = self.lock()?;
        if let Some(pending) = &state.pending {
            for command in pending.iter().rev() {
                match command {
                    Command::Clear(current) if *current == tree => return Ok(None),
                    Command::Write(op) if op.tree == tree && op.key == key => {
                        return Ok(match op.method {
                            Method::Insert => op.val.clone(),
                            Method::Delete => None,
                        });
                    }
                    _ => {}
                }
            }
        }
        let mut transaction = scoped(&mut state.client, &self.namespace)?;
        let digest = Sha256::digest(key).to_vec();
        let row = transaction
            .query_opt(
                "SELECT value FROM public.atomic_kv WHERE namespace=$1 AND tree_name=$2
                 AND key_digest=$3 AND key=$4",
                &[&self.namespace, &tree.name(), &digest, &key],
            )
            .map_err(|e| database_error("get", e))?;
        transaction
            .commit()
            .map_err(|e| database_error("read commit", e))?;
        Ok(row.map(|row| row.get(0)))
    }

    fn insert(&self, tree: Tree, key: &[u8], val: &[u8]) -> AtomicResult<()> {
        self.apply_batch(&[Operation {
            tree,
            method: Method::Insert,
            key: key.to_vec(),
            val: Some(val.to_vec()),
        }])
    }

    fn remove(&self, tree: Tree, key: &[u8]) -> AtomicResult<()> {
        self.apply_batch(&[Operation {
            tree,
            method: Method::Delete,
            key: key.to_vec(),
            val: None,
        }])
    }

    fn contains_key(&self, tree: Tree, key: &[u8]) -> AtomicResult<bool> {
        Ok(self.get(tree, key)?.is_some())
    }

    fn scan_prefix(&self, tree: Tree, prefix: &[u8]) -> KvIter {
        Self::iterator(self.pairs(
            tree,
            prefix,
            prefix_successor(prefix).as_deref(),
            false,
            None,
        ))
    }

    fn range(&self, tree: Tree, start: Vec<u8>, end: Vec<u8>, reverse: bool) -> KvIter {
        Self::iterator(self.pairs(tree, &start, Some(&end), reverse, None))
    }

    fn range_page(
        &self,
        tree: Tree,
        start: Vec<u8>,
        end: Vec<u8>,
        limit: usize,
    ) -> AtomicResult<Vec<KvPair>> {
        self.pairs(tree, &start, Some(&end), false, Some(limit))
    }

    fn range_value_sizes(
        &self,
        tree: Tree,
        start: Vec<u8>,
        end: Vec<u8>,
        limit: usize,
    ) -> AtomicResult<Vec<(Vec<u8>, u64)>> {
        let mut state = self.lock()?;
        if state.pending.is_some() {
            drop(state);
            return Ok(self
                .range_page(tree, start, end, limit)?
                .into_iter()
                .map(|(key, value)| (key, value.len() as u64))
                .collect());
        }
        if start >= end || limit == 0 {
            return Ok(Vec::new());
        }
        let limit =
            i64::try_from(limit).map_err(|_| error("PostgreSQL KV range limit is too large"))?;
        let mut transaction = scoped(&mut state.client, &self.namespace)?;
        let rows = transaction
            .query(
                "SELECT key,octet_length(value)::bigint FROM public.atomic_kv
             WHERE namespace=$1 AND tree_name=$2 AND key >= $3 AND key < $4 ORDER BY key LIMIT $5",
                &[&self.namespace, &tree.name(), &start, &end, &limit],
            )
            .map_err(|e| database_error("size range", e))?;
        transaction
            .commit()
            .map_err(|e| database_error("read commit", e))?;
        rows.into_iter()
            .map(|row| {
                let size: i64 = row.get(1);
                Ok((
                    row.get(0),
                    u64::try_from(size).map_err(|_| error("Invalid PostgreSQL value size"))?,
                ))
            })
            .collect()
    }

    fn iter_tree(&self, tree: Tree) -> KvIter {
        Self::iterator(self.pairs(tree, &[], None, false, None))
    }

    fn first_entry(&self, tree: Tree) -> AtomicResult<Option<KvPair>> {
        Ok(self
            .pairs(tree, &[], None, false, Some(1))?
            .into_iter()
            .next())
    }

    fn clear_tree(&self, tree: Tree) -> AtomicResult<()> {
        self.write(vec![Command::Clear(tree)])
    }

    fn apply_batch(&self, operations: &[Operation]) -> AtomicResult<()> {
        if operations
            .iter()
            .any(|op| matches!(op.method, Method::Insert) && op.val.is_none())
        {
            return Err(error("KV insert requires a value"));
        }
        self.write(operations.iter().cloned().map(Command::Write).collect())
    }

    fn flush(&self) -> AtomicResult<()> {
        let state = self.lock()?;
        if state.pending.as_ref().is_some_and(|ops| !ops.is_empty()) {
            return Err(error(
                "Commit the buffered PostgreSQL KV batch before flushing",
            ));
        }
        // Every completed write transaction requested synchronous_commit=on.
        Ok(())
    }

    fn begin_batch(&self) {
        let mut state = self.state.lock().expect("PostgreSQL KV lock poisoned");
        state.pending.get_or_insert_with(Vec::new);
    }

    fn commit_batch(&self) -> AtomicResult<()> {
        let mut state = self.lock()?;
        if let Some(commands) = state.pending.take() {
            if let Err(error) = self.execute_commands(&mut state.client, &commands) {
                state.pending = Some(commands);
                return Err(error);
            }
        }
        Ok(())
    }

    fn len(&self, tree: Tree) -> AtomicResult<usize> {
        let mut state = self.lock()?;
        if state.pending.is_some() {
            drop(state);
            return Ok(self.pairs(tree, &[], None, false, None)?.len());
        }
        let mut transaction = scoped(&mut state.client, &self.namespace)?;
        let count: i64 = transaction
            .query_one(
                "SELECT count(*) FROM public.atomic_kv WHERE namespace=$1 AND tree_name=$2",
                &[&self.namespace, &tree.name()],
            )
            .map_err(|e| database_error("count", e))?
            .get(0);
        transaction
            .commit()
            .map_err(|e| database_error("read commit", e))?;
        usize::try_from(count).map_err(|_| error("PostgreSQL KV count is too large"))
    }
}

#[cfg(test)]
mod tests {
    use super::{prefix_successor, PostgresStore};

    #[test]
    fn byte_prefix_boundaries() {
        assert_eq!(prefix_successor(&[]), None);
        assert_eq!(prefix_successor(&[255]), None);
        assert_eq!(prefix_successor(&[255, 255]), None);
        assert_eq!(prefix_successor(&[4, 255]), Some(vec![5]));
        assert_eq!(prefix_successor(&[4, 0]), Some(vec![4, 1]));
    }

    #[test]
    fn verified_connection_rejects_disabled_tls_without_exposing_dsn() {
        let result = PostgresStore::connect(
            "host=127.0.0.1 user=fictional password=fabricated-secret sslmode=disable",
            "test-namespace",
        );
        let failure = match result {
            Err(error) => error,
            Ok(_) => panic!("TLS-disabled connection unexpectedly accepted"),
        };
        assert!(failure.to_string().contains("TLS disabled"));
        assert!(!failure.to_string().contains("fabricated-secret"));
    }
}
