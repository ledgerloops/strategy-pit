//! Integration through Atomic's real bootstrap, commit and resource paths.
use atomic_lib::{db::kv_store::KvStore, db::trees::Tree, runtime::AtomicNode};
use ledgerloops_atomic::{actor_store::*, postgres_store::PostgresStore};
use serde_json::json;
use std::{
    sync::Arc,
    time::{SystemTime, UNIX_EPOCH},
};

#[test]
#[ignore = "requires disposable PostgreSQL via LEDGERLOOPS_TEST_POSTGRES_DSN"]
fn atomic_actor_reopens_from_postgres_with_identity_receipt_and_state() {
    let dsn =
        std::env::var("LEDGERLOOPS_TEST_POSTGRES_DSN").expect("disposable test database required");
    let namespace = format!(
        "actor_pg_{}_{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    );
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()
        .unwrap();
    let kv = Arc::new(PostgresStore::connect_no_tls(&dsn, &namespace).unwrap());
    let (subject, agent) = runtime.block_on(async {
        let node = AtomicNode::open_with_store(kv.clone(), Some("https://localhost".into()))
            .await
            .unwrap();
        let (agent, _) = node.db().setup("PG actor fixture").await.unwrap();
        install_model(&node).await.unwrap();
        let store = AtomicActorStore::new(node);
        let subject = store.create("alice", 0_i64).await.unwrap();
        store
            .apply::<i64, _>(&subject, "decision-1", "digest-1", Some(0), |balance| {
                *balance = 7;
                Ok((json!({"balance":7}), vec![]))
            })
            .await
            .unwrap();
        assert!(!store.node().outbox().has_pending(&subject));
        (subject, agent)
    });
    drop(kv);
    // A fresh client and Atomic node rule out an in-memory cache-only success.
    let kv = Arc::new(PostgresStore::connect_no_tls(&dsn, &namespace).unwrap());
    runtime.block_on(async {
        let node = AtomicNode::open_with_store(kv.clone(), Some("https://localhost".into()))
            .await
            .unwrap();
        node.set_agent(agent);
        let store = AtomicActorStore::new(node);
        let document: ActorDocument<i64> = store.load(&subject).await.unwrap();
        assert_eq!(document.state, 7);
        assert_eq!(document.revision, 1);
        assert_eq!(document.actor_id, "alice");
        let receipt = store
            .apply::<i64, _>(&subject, "decision-1", "digest-1", Some(0), |_| {
                panic!("must not reapply after restart")
            })
            .await
            .unwrap();
        assert_eq!(receipt.result, json!({"balance":7}));
    });
    for tree in Tree::ALL {
        kv.clear_tree(tree).unwrap();
    }
}
