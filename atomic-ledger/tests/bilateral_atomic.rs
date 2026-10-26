//! A complete bilateral exchange persisted as actual Atomic actor Resources.
use atomic_lib::{db::redb_store::RedbStore, runtime::AtomicNode, Storelike, Value};
use ed25519_dalek::SigningKey;
use ledgerloops_atomic::{actor_store::*, bilateral::*, model::*};
use serde_json::json;
use std::{collections::BTreeMap, sync::Arc};

fn state(owner: &SigningKey, peer: &SigningKey) -> TrustlineState {
    let preferences = Preferences {
        revision: 1,
        credit_limit: 10,
        comfort_min: -5,
        comfort_max: 5,
        auto_adjust: false,
    };
    TrustlineState {
        version: FORMAT_VERSION,
        channel_id: "edge".into(),
        incarnation: 1,
        owner: agent_id(&owner.verifying_key()),
        counterparty: agent_id(&peer.verifying_key()),
        unit: "TEST".into(),
        balance: 0,
        own_preferences: preferences.clone(),
        peer_preferences: preferences,
        reservations: BTreeMap::new(),
        applied_requests: BTreeMap::new(),
        local_revision: 1,
    }
}

async fn decide<F>(
    store: &AtomicActorStore,
    actor: &str,
    log: &str,
    id: &str,
    hash: &str,
    action: F,
) where
    F: FnOnce(&mut BilateralActor) -> ledgerloops_atomic::bilateral::Result<Reduction>,
{
    store
        .apply::<BilateralActor, _>(actor, id, hash, None, |state| {
            let reduction = action(state)?;
            let publications = reduction
                .outbound
                .iter()
                .cloned()
                .map(|message| Publication {
                    log_resource: log.into(),
                    message,
                })
                .collect();
            Ok((serde_json::to_value(reduction)?, publications))
        })
        .await
        .unwrap();
}

async fn messages(store: &AtomicActorStore, log: &str) -> Vec<SignedEnvelope> {
    let resource = store.node().db().get_resource(&log.into()).await.unwrap();
    match resource.get(LOG_MESSAGES).unwrap() {
        Value::Json(value) => serde_json::from_value(value.clone()).unwrap(),
        _ => panic!("typed log required"),
    }
}

#[tokio::test]
async fn consent_commit_and_settlement_resume_after_atomic_restart() {
    let kv = Arc::new(RedbStore::new_memory().unwrap());
    let node = AtomicNode::open_with_store(kv.clone(), Some("https://localhost".into()))
        .await
        .unwrap();
    let (service, drive) = node.db().setup("Service fixture").await.unwrap();
    install_model(&node).await.unwrap();
    let store = AtomicActorStore::new(node);
    let alice = SigningKey::from_bytes(&[7; 32]);
    let bob = SigningKey::from_bytes(&[9; 32]);
    let a = store
        .create("alice", BilateralActor::new(state(&alice, &bob)).unwrap())
        .await
        .unwrap();
    let b = store
        .create("bob", BilateralActor::new(state(&bob, &alice)).unwrap())
        .await
        .unwrap();
    let a_log = store
        .node()
        .db()
        .create_resource(
            LOG_CLASS,
            &drive,
            "Alice half",
            Some(vec![(LOG_MESSAGES, Value::Json(json!([])))]),
        )
        .await
        .unwrap();
    let b_log = store
        .node()
        .db()
        .create_resource(
            LOG_CLASS,
            &drive,
            "Bob half",
            Some(vec![(LOG_MESSAGES, Value::Json(json!([])))]),
        )
        .await
        .unwrap();
    let terms = OfferTerms {
        request_id: "lunch".into(),
        origin: agent_id(&alice.verifying_key()),
        recipient: agent_id(&bob.verifying_key()),
        unit: "TEST".into(),
        amount: 3,
        direction: Direction::IOwe,
        description: "Lunch".into(),
        before: 0,
        after: -3,
        origin_revision: 1,
        recipient_revision: 1,
        created_at_ms: 1_792_992_000_000,
    };
    let terms_hash = terms.hash().unwrap();
    decide(&store, &a, &a_log, "propose", &terms_hash, |state| {
        state.propose(terms, &alice)
    })
    .await;
    store.project_pending::<BilateralActor>(&a).await.unwrap();
    let offer = messages(&store, &a_log).await.remove(0);
    decide(
        &store,
        &b,
        &b_log,
        "receive-offer",
        &offer.hash().unwrap(),
        |state| state.receive(&offer, &bob),
    )
    .await;
    assert_eq!(
        store
            .load::<BilateralActor>(&b)
            .await
            .unwrap()
            .state
            .trustline
            .balance,
        0
    );
    decide(&store, &b, &b_log, "approve", &terms_hash, |state| {
        state.approve("lunch", &terms_hash, &bob)
    })
    .await;
    // Crash before projecting Bob's acceptance: only its private actor is saved.
    drop(store);
    let node = AtomicNode::open_with_store(kv, Some("https://localhost".into()))
        .await
        .unwrap();
    node.set_agent(service);
    let store = AtomicActorStore::new(node);
    let bob_state = store.load::<BilateralActor>(&b).await.unwrap();
    assert_eq!(bob_state.state.trustline.balance, 0);
    assert_eq!(bob_state.outbound.len(), 1);
    store.project_pending::<BilateralActor>(&b).await.unwrap();
    let acceptance = messages(&store, &b_log).await.remove(0);
    decide(
        &store,
        &a,
        &a_log,
        "receive-accept",
        &acceptance.hash().unwrap(),
        |state| state.receive(&acceptance, &alice),
    )
    .await;
    let alice_state = store.load::<BilateralActor>(&a).await.unwrap();
    assert_eq!(alice_state.state.trustline.balance, -3);
    assert_eq!(alice_state.state.trustline.reservations.len(), 1);
    store.project_pending::<BilateralActor>(&a).await.unwrap();
    let commit = messages(&store, &a_log).await.remove(1);
    decide(
        &store,
        &b,
        &b_log,
        "receive-commit",
        &commit.hash().unwrap(),
        |state| state.receive(&commit, &bob),
    )
    .await;
    store.project_pending::<BilateralActor>(&b).await.unwrap();
    let settled = messages(&store, &b_log).await.remove(1);
    decide(
        &store,
        &a,
        &a_log,
        "receive-settled",
        &settled.hash().unwrap(),
        |state| state.receive(&settled, &alice),
    )
    .await;
    let a_state = store.load::<BilateralActor>(&a).await.unwrap().state;
    let b_state = store.load::<BilateralActor>(&b).await.unwrap().state;
    assert_eq!(
        (a_state.trustline.balance, b_state.trustline.balance),
        (-3, 3)
    );
    assert!(a_state.trustline.reservations.is_empty());
    assert!(b_state.trustline.reservations.is_empty());
    assert_eq!(messages(&store, &a_log).await.len(), 2);
    assert_eq!(messages(&store, &b_log).await.len(), 2);
    // Browser/action retry and network redelivery both remain harmless.
    decide(
        &store,
        &a,
        &a_log,
        "receive-settled",
        &settled.hash().unwrap(),
        |_| panic!("receipt must replay"),
    )
    .await;
    decide(
        &store,
        &b,
        &b_log,
        "redeliver-commit",
        &commit.hash().unwrap(),
        |state| state.receive(&commit, &bob),
    )
    .await;
    store.project_pending::<BilateralActor>(&b).await.unwrap();
    assert_eq!(messages(&store, &b_log).await.len(), 2);
    assert_eq!(
        store
            .load::<BilateralActor>(&b)
            .await
            .unwrap()
            .state
            .trustline
            .balance,
        3
    );
}
