use atomic_lib::{db::redb_store::RedbStore, runtime::AtomicNode, urls, Storelike, Value};
use ed25519_dalek::SigningKey;
use ledgerloops_atomic::{actor_store::*, model::*};
use serde_json::json;
use std::sync::Arc;

async fn fixture() -> (
    Arc<RedbStore>,
    AtomicActorStore,
    atomic_lib::agents::Agent,
    String,
) {
    let kv = Arc::new(RedbStore::new_memory().unwrap());
    let node = AtomicNode::open_with_store(kv.clone(), Some("https://localhost".into()))
        .await
        .unwrap();
    let (agent, drive) = node.db().setup("Actor fixture").await.unwrap();
    install_model(&node).await.unwrap();
    (kv, AtomicActorStore::new(node), agent, drive)
}

fn message() -> SignedEnvelope {
    let key = SigningKey::from_bytes(&[7; 32]);
    SignedEnvelope::sign(
        MessageEnvelope {
            version: FORMAT_VERSION,
            channel_id: "edge".into(),
            incarnation: 1,
            author: agent_id(&key.verifying_key()),
            recipient: agent_id(&SigningKey::from_bytes(&[9; 32]).verifying_key()),
            sequence: 1,
            previous_hash: None,
            message_id: "message-1".into(),
            payload: MessagePayload::GrantUpdate {
                previous_revision: 1,
                revision: 2,
                credit_limit: 10,
            },
        },
        &key,
    )
    .unwrap()
}

async fn log(store: &AtomicActorStore, drive: &str) -> String {
    store
        .node()
        .db()
        .create_resource(
            LOG_CLASS,
            drive,
            "Message log",
            Some(vec![(LOG_MESSAGES, Value::Json(json!([])))]),
        )
        .await
        .unwrap()
}

#[tokio::test]
async fn decision_receipt_and_intent_survive_reopen_together() {
    let (kv, store, agent, drive) = fixture().await;
    let actor = store.create("alice", 0_i64).await.unwrap();
    let log = log(&store, &drive).await;
    let publication = Publication {
        log_resource: log.clone(),
        message: message(),
    };
    store
        .apply::<i64, _>(&actor, "command-1", "hash-1", Some(0), |balance| {
            *balance -= 3;
            Ok((json!({"balance": *balance}), vec![publication]))
        })
        .await
        .unwrap();
    assert!(!store.node().outbox().has_pending(&actor));
    drop(store);
    let node = AtomicNode::open_with_store(kv, Some("https://localhost".into()))
        .await
        .unwrap();
    node.set_agent(agent);
    let store = AtomicActorStore::new(node);
    let document: ActorDocument<i64> = store.load(&actor).await.unwrap();
    assert_eq!(document.state, -3);
    assert_eq!(document.revision, 1);
    assert_eq!(document.processed_requests.len(), 1);
    assert_eq!(document.outbound.len(), 1);
    let receipt = store
        .apply::<i64, _>(&actor, "command-1", "hash-1", Some(0), |_| {
            panic!("must not replay")
        })
        .await
        .unwrap();
    assert_eq!(receipt.result, json!({"balance": -3}));
    assert_eq!(store.project_pending::<i64>(&actor).await.unwrap(), 1);
    assert_eq!(store.project_pending::<i64>(&actor).await.unwrap(), 0);
    let document: ActorDocument<i64> = store.load(&actor).await.unwrap();
    assert!(document.outbound.is_empty());
    assert_eq!(document.state, -3);
    let resource = store.node().db().get_resource(&log.into()).await.unwrap();
    assert_eq!(
        resource.get(LOG_MESSAGES).unwrap().to_string(),
        Value::Json(json!([message()])).to_string()
    );
}

#[tokio::test]
async fn crash_after_projection_before_cleanup_does_not_append_twice() {
    let (_, store, _, drive) = fixture().await;
    let actor = store.create("alice", 0_i64).await.unwrap();
    let log = log(&store, &drive).await;
    let publication = Publication {
        log_resource: log.clone(),
        message: message(),
    };
    store
        .apply::<i64, _>(&actor, "command", "hash", None, |_| {
            Ok((json!(true), vec![publication]))
        })
        .await
        .unwrap();
    // Simulate the durable write immediately before the actor's intent cleanup.
    let mut resource = store
        .node()
        .db()
        .get_resource(&log.as_str().into())
        .await
        .unwrap();
    resource
        .push_list_item(LOG_MESSAGES, serde_json::to_value(message()).unwrap())
        .unwrap();
    resource.save_locally(store.node().db()).await.unwrap();
    assert_eq!(store.project_pending::<i64>(&actor).await.unwrap(), 1);
    let resource = store.node().db().get_resource(&log.into()).await.unwrap();
    assert_eq!(
        resource.get(LOG_MESSAGES).unwrap().to_string(),
        Value::Json(json!([message()])).to_string()
    );
}

#[tokio::test]
async fn stale_conflicting_and_failed_commands_preserve_state() {
    let (_, store, _, _) = fixture().await;
    let actor = store.create("alice", 0_i64).await.unwrap();
    store
        .apply::<i64, _>(&actor, "one", "hash", Some(0), |state| {
            *state = 3;
            Ok((json!(3), vec![]))
        })
        .await
        .unwrap();
    assert!(store
        .apply::<i64, _>(&actor, "one", "other", None, |_| panic!())
        .await
        .is_err());
    assert!(store
        .apply::<i64, _>(&actor, "two", "hash", Some(0), |_| panic!())
        .await
        .is_err());
    assert!(store
        .apply::<i64, _>(&actor, "three", "hash", Some(1), |state| {
            *state = 99;
            Err("invalid decision".into())
        })
        .await
        .is_err());
    let document: ActorDocument<i64> = store.load(&actor).await.unwrap();
    assert_eq!(document.state, 3);
    assert_eq!(document.revision, 1);
    assert_eq!(document.processed_requests.len(), 1);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn concurrent_handles_serialize_revision_check() {
    let (_, store, _, _) = fixture().await;
    let actor = store.create("alice", 0_i64).await.unwrap();
    let first = store.clone();
    let second = AtomicActorStore::new(store.node().clone());
    let alias = format!("{actor}?hint=1");
    let barrier = Arc::new(tokio::sync::Barrier::new(2));
    let start = barrier.clone();
    let first_subject = actor.clone();
    let a = tokio::spawn(async move {
        start.wait().await;
        first
            .apply::<i64, _>(&first_subject, "one", "hash", Some(0), |state| {
                std::thread::sleep(std::time::Duration::from_millis(100));
                *state += 1;
                Ok((json!(1), vec![]))
            })
            .await
    });
    let b = tokio::spawn(async move {
        barrier.wait().await;
        second
            .apply::<i64, _>(&alias, "two", "hash", Some(0), |state| {
                std::thread::sleep(std::time::Duration::from_millis(100));
                *state += 1;
                Ok((json!(1), vec![]))
            })
            .await
    });
    assert_ne!(a.await.unwrap().is_ok(), b.await.unwrap().is_ok());
    assert_eq!(store.load::<i64>(&actor).await.unwrap().state, 1);
}

#[tokio::test]
async fn rejects_actor_with_public_acl() {
    let (_, store, _, _) = fixture().await;
    let actor = store.create("alice", 0_i64).await.unwrap();
    let mut resource = store
        .node()
        .db()
        .get_resource(&actor.as_str().into())
        .await
        .unwrap();
    resource
        .set_unsafe(
            urls::READ.into(),
            Value::ResourceArray(vec![urls::PUBLIC_AGENT.into()]),
        )
        .unwrap();
    resource.save_locally(store.node().db()).await.unwrap();
    assert!(store.load::<i64>(&actor).await.is_err());
}

#[tokio::test]
async fn projection_orders_messages_by_sequence_and_rejects_forgery() {
    let (_, store, _, drive) = fixture().await;
    let actor = store.create("alice", 0_i64).await.unwrap();
    let log = log(&store, &drive).await;
    let first = message();
    let mut second = first.envelope.clone();
    second.sequence = 2;
    second.previous_hash = Some(first.hash().unwrap());
    // Deliberately sort before message-1 when ordered by stable ID.
    second.message_id = "a-second-message".into();
    let second = SignedEnvelope::sign(second, &SigningKey::from_bytes(&[7; 32])).unwrap();
    let publications = vec![
        Publication {
            log_resource: log.clone(),
            message: second.clone(),
        },
        Publication {
            log_resource: log.clone(),
            message: first.clone(),
        },
    ];
    store
        .apply::<i64, _>(&actor, "ordered", "hash", None, |_| {
            Ok((json!(true), publications))
        })
        .await
        .unwrap();
    store.project_pending::<i64>(&actor).await.unwrap();
    let resource = store
        .node()
        .db()
        .get_resource(&log.as_str().into())
        .await
        .unwrap();
    assert_eq!(
        resource.get(LOG_MESSAGES).unwrap().to_string(),
        Value::Json(json!([first, second.clone()])).to_string()
    );
    let mut forged = second;
    forged.envelope.sequence = 3;
    forged.envelope.message_id = "forged".into();
    let failure = store
        .apply::<i64, _>(&actor, "forgery", "hash", None, |_| {
            Ok((
                json!(true),
                vec![Publication {
                    log_resource: log.clone(),
                    message: forged,
                }],
            ))
        })
        .await;
    assert!(failure.is_err());
    let document = store.load::<i64>(&actor).await.unwrap();
    assert_eq!(document.outbound.len(), 0);
    assert_eq!(document.revision, 1);
}

#[tokio::test]
async fn refuses_to_reinterpret_existing_ontology() {
    let (_, store, _, _) = fixture().await;
    let mut definition = store
        .node()
        .db()
        .get_resource(&ACTOR_STATE.into())
        .await
        .unwrap();
    definition
        .set_unsafe(
            urls::DATATYPE_PROP.into(),
            Value::AtomicUrl(urls::STRING.into()),
        )
        .unwrap();
    store
        .node()
        .db()
        .add_resource_opts(&definition, false, true, true)
        .await
        .unwrap();
    assert!(install_model(store.node()).await.is_err());
}
