use ed25519_dalek::SigningKey;
use ledgerloops_atomic::bilateral::{BilateralActor, BilateralError, Phase};
use ledgerloops_atomic::model::*;
use std::collections::BTreeMap;

fn alice() -> SigningKey {
    SigningKey::from_bytes(&[7; 32])
}
fn bob() -> SigningKey {
    SigningKey::from_bytes(&[9; 32])
}
fn prefs() -> Preferences {
    Preferences {
        revision: 1,
        credit_limit: 10,
        comfort_min: -5,
        comfort_max: 5,
        auto_adjust: false,
    }
}
fn actor(owner: &SigningKey, peer: &SigningKey, balance: i64) -> BilateralActor {
    BilateralActor::new(TrustlineState {
        version: FORMAT_VERSION,
        channel_id: "trustline-1".into(),
        incarnation: 1,
        owner: agent_id(&owner.verifying_key()),
        counterparty: agent_id(&peer.verifying_key()),
        unit: "TEST".into(),
        balance,
        own_preferences: prefs(),
        peer_preferences: prefs(),
        reservations: BTreeMap::new(),
        applied_requests: BTreeMap::new(),
        local_revision: 1,
    })
    .unwrap()
}
fn terms() -> OfferTerms {
    OfferTerms {
        request_id: "request-1".into(),
        origin: agent_id(&alice().verifying_key()),
        recipient: agent_id(&bob().verifying_key()),
        unit: "TEST".into(),
        amount: 3,
        direction: Direction::IOwe,
        description: "shared lunch".into(),
        before: 0,
        after: -3,
        origin_revision: 1,
        recipient_revision: 1,
        created_at_ms: 1_792_992_000_000,
    }
}
fn restore(actor: &BilateralActor) -> BilateralActor {
    serde_json::from_slice(&serde_json::to_vec(actor).unwrap()).unwrap()
}
fn peer_message(
    sender: &BilateralActor,
    key: &SigningKey,
    payload: MessagePayload,
) -> SignedEnvelope {
    SignedEnvelope::sign(
        MessageEnvelope {
            version: FORMAT_VERSION,
            channel_id: sender.trustline.channel_id.clone(),
            incarnation: sender.trustline.incarnation,
            author: sender.trustline.owner.clone(),
            recipient: sender.trustline.counterparty.clone(),
            sequence: sender.outgoing.frontier.sequence + 1,
            previous_hash: sender.outgoing.frontier.hash.clone(),
            message_id: format!("test-extra-{}", sender.outgoing.frontier.sequence + 1),
            payload,
        },
        key,
    )
    .unwrap()
}

#[test]
fn explicit_consent_and_four_steps_survive_restart_and_reply_retries() {
    let (ak, bk) = (alice(), bob());
    let mut a = actor(&ak, &bk, 0);
    let mut b = actor(&bk, &ak, 0);
    let t = terms();
    let hash = t.hash().unwrap();
    let offer = a.propose(t.clone(), &ak).unwrap().outbound.remove(0);
    assert_eq!(a.trustline.balance, 0);
    assert_eq!(a.transactions["request-1"].phase, Phase::Offered);
    assert_eq!(a.propose(t, &ak).unwrap().outbound, vec![offer.clone()]);

    let received = b.receive(&offer, &bk).unwrap();
    assert_eq!(received.phase, Phase::PendingApproval);
    assert!(received.outbound.is_empty());
    assert_eq!(b.trustline.balance, 0);
    assert_eq!(
        b.trustline.reservations["request-1"].phase,
        ReservationPhase::Prepared
    );
    a = restore(&a);
    b = restore(&b);
    assert!(!b.receive(&offer, &bk).unwrap().changed);

    let accept = b
        .approve("request-1", &hash, &bk)
        .unwrap()
        .outbound
        .remove(0);
    assert_eq!(b.trustline.balance, 0);
    assert_eq!(
        b.approve("request-1", &hash, &bk).unwrap().outbound,
        vec![accept.clone()]
    );
    b = restore(&b);
    let commit = a.receive(&accept, &ak).unwrap().outbound.remove(0);
    assert_eq!(a.trustline.balance, -3);
    assert_eq!(a.transactions["request-1"].phase, Phase::Committing);
    assert_eq!(
        a.trustline.reservations["request-1"].phase,
        ReservationPhase::AppliedAwaitingSettlement
    );
    let before = a.clone();
    let retry = a.receive(&accept, &ak).unwrap();
    assert!(!retry.changed);
    assert_eq!(retry.outbound, vec![commit.clone()]);
    assert_eq!(a, before);
    a = restore(&a);

    let settled = b.receive(&commit, &bk).unwrap().outbound.remove(0);
    assert_eq!(b.trustline.balance, 3);
    assert!(b.trustline.reservations.is_empty());
    let retry = b.receive(&commit, &bk).unwrap();
    assert!(!retry.changed);
    assert_eq!(retry.outbound, vec![settled.clone()]);
    b = restore(&b);
    let final_step = a.receive(&settled, &ak).unwrap();
    assert_eq!(final_step.phase, Phase::Committed);
    assert!(final_step.outbound.is_empty());
    assert!(a.trustline.reservations.is_empty());
    assert_eq!(a.trustline.balance + b.trustline.balance, 0);
    assert!(!a.receive(&settled, &ak).unwrap().changed);
    assert_eq!(a.outgoing.frontier.sequence, 2);
    assert_eq!(b.outgoing.frontier.sequence, 2);

    // Even a re-signed semantic retry at a new peer sequence cannot apply twice.
    let another_accept = peer_message(
        &b,
        &bk,
        MessagePayload::Accept {
            request_id: "request-1".into(),
            terms_hash: hash,
        },
    );
    let financial = a.trustline.clone();
    let replay = a.receive(&another_accept, &ak).unwrap();
    assert!(replay.changed); // only the verified incoming cursor advances
    assert_eq!(a.trustline, financial);
    assert_eq!(replay.outbound, vec![commit]);
    assert_eq!(a.outgoing.frontier.sequence, 2);
}

#[test]
fn recipient_approval_pins_the_displayed_hash_and_cannot_be_skipped() {
    let (ak, bk) = (alice(), bob());
    let mut a = actor(&ak, &bk, 0);
    let mut b = actor(&bk, &ak, 0);
    let offer = a.propose(terms(), &ak).unwrap().outbound.remove(0);
    b.receive(&offer, &bk).unwrap();
    let before = b.clone();
    assert_eq!(
        b.approve("request-1", &"0".repeat(64), &bk),
        Err(BilateralError::TermsMismatch)
    );
    assert_eq!(b, before);
    let premature_commit = peer_message(
        &a,
        &ak,
        MessagePayload::Commit {
            request_id: "request-1".into(),
            terms_hash: terms().hash().unwrap(),
        },
    );
    assert_eq!(
        b.receive(&premature_commit, &bk),
        Err(BilateralError::InvalidTransition)
    );
    assert_eq!(b, before);
    assert_eq!(
        b.approve("request-1", &terms().hash().unwrap(), &ak),
        Err(BilateralError::WrongSigner)
    );
    assert_eq!(b, before);
}

#[test]
fn signed_ingress_rejects_tampering_wrong_context_and_wrong_terms_without_mutation() {
    let (ak, bk) = (alice(), bob());
    let mut a = actor(&ak, &bk, 0);
    let mut b = actor(&bk, &ak, 0);
    let offer = a.propose(terms(), &ak).unwrap().outbound.remove(0);
    let before = b.clone();
    let mut tampered = offer.clone();
    if let MessagePayload::Offer { terms } = &mut tampered.envelope.payload {
        terms.description = "different consent".into();
    }
    assert!(b.receive(&tampered, &bk).is_err());
    assert_eq!(b, before);
    let mut envelope = offer.envelope.clone();
    envelope.channel_id = "another-trustline".into();
    let wrong_channel = SignedEnvelope::sign(envelope, &ak).unwrap();
    assert!(b.receive(&wrong_channel, &bk).is_err());
    assert_eq!(b, before);
    let eve = SigningKey::from_bytes(&[11; 32]);
    let mut envelope = offer.envelope.clone();
    envelope.author = agent_id(&eve.verifying_key());
    if let MessagePayload::Offer { terms } = &mut envelope.payload {
        terms.origin = agent_id(&eve.verifying_key());
    }
    let wrong_author = SignedEnvelope::sign(envelope, &eve).unwrap();
    assert!(b.receive(&wrong_author, &bk).is_err());
    assert_eq!(b, before);

    b.receive(&offer, &bk).unwrap();
    let wrong_accept = peer_message(
        &b,
        &bk,
        MessagePayload::Accept {
            request_id: "request-1".into(),
            terms_hash: "0".repeat(64),
        },
    );
    let before = a.clone();
    assert_eq!(
        a.receive(&wrong_accept, &ak),
        Err(BilateralError::TermsMismatch)
    );
    assert_eq!(a, before);
}

#[test]
fn durable_decline_releases_capacity_and_prevents_request_resurrection() {
    let (ak, bk) = (alice(), bob());
    let mut a = actor(&ak, &bk, 0);
    let mut b = actor(&bk, &ak, 0);
    let t = terms();
    let hash = t.hash().unwrap();
    let offer = a.propose(t.clone(), &ak).unwrap().outbound.remove(0);
    b.receive(&offer, &bk).unwrap();
    let decline = b
        .decline("request-1", &hash, "No thanks".into(), &bk)
        .unwrap()
        .outbound
        .remove(0);
    assert_eq!(
        b.decline("request-1", &hash, "Changed reason".into(), &bk)
            .unwrap()
            .outbound,
        vec![decline.clone()]
    );
    a.receive(&decline, &ak).unwrap();
    a = restore(&a);
    b = restore(&b);
    assert!(a.trustline.reservations.is_empty());
    assert!(b.trustline.reservations.is_empty());
    assert_eq!(a.trustline.balance, 0);
    assert_eq!(b.trustline.balance, 0);
    let retry = a.propose(t, &ak).unwrap();
    assert!(!retry.changed);
    assert_eq!(retry.phase, Phase::Aborted);
    assert!(retry.outbound.is_empty());
    let retry = b.receive(&offer, &bk).unwrap();
    assert!(!retry.changed);
    assert_eq!(retry.outbound, vec![decline]);
    let before = b.clone();
    assert_eq!(
        b.approve("request-1", &hash, &bk),
        Err(BilateralError::InvalidTransition)
    );
    assert_eq!(b, before);
    let mut conflicting = terms();
    conflicting.amount = 4;
    conflicting.after = -4;
    let before = a.clone();
    assert!(a.propose(conflicting, &ak).is_err());
    assert_eq!(a, before);
}

#[test]
fn approval_is_irrevocable_and_applied_balance_cannot_be_aborted() {
    let (ak, bk) = (alice(), bob());
    let mut a = actor(&ak, &bk, 0);
    let mut b = actor(&bk, &ak, 0);
    let hash = terms().hash().unwrap();
    let offer = a.propose(terms(), &ak).unwrap().outbound.remove(0);
    b.receive(&offer, &bk).unwrap();
    let accept = b
        .approve("request-1", &hash, &bk)
        .unwrap()
        .outbound
        .remove(0);
    let before = b.clone();
    assert_eq!(
        b.decline("request-1", &hash, "too late".into(), &bk),
        Err(BilateralError::InvalidTransition)
    );
    assert_eq!(b, before);
    a.receive(&accept, &ak).unwrap();
    let false_decline = peer_message(
        &b,
        &bk,
        MessagePayload::Decline {
            request_id: "request-1".into(),
            terms_hash: hash,
            reason: "too late".into(),
        },
    );
    let before = a.clone();
    assert_eq!(
        a.receive(&false_decline, &ak),
        Err(BilateralError::InvalidTransition)
    );
    assert_eq!(a, before);
    assert_eq!(a.trustline.balance, -3);
}

#[test]
fn stale_quote_is_a_durable_decline_and_exclusive_holds_prevent_double_spend() {
    let (ak, bk) = (alice(), bob());
    let mut a = actor(&ak, &bk, 0);
    let mut b = actor(&bk, &ak, 1); // independently known state differs from quote
    let offer = a.propose(terms(), &ak).unwrap().outbound.remove(0);
    let rejected = b.receive(&offer, &bk).unwrap();
    assert_eq!(rejected.phase, Phase::Aborted);
    assert!(b.trustline.reservations.is_empty());
    a.receive(&rejected.outbound[0], &ak).unwrap();
    assert!(a.trustline.reservations.is_empty());

    let mut a = actor(&ak, &bk, 0);
    a.propose(terms(), &ak).unwrap();
    let mut second = terms();
    second.request_id = "request-2".into();
    let before = a.clone();
    assert_eq!(
        a.propose(second.clone(), &ak),
        Err(BilateralError::Model(ModelError::ReservationConflict))
    );
    assert_eq!(a, before);
    let mut b = actor(&bk, &ak, 0);
    second.origin = agent_id(&bk.verifying_key());
    second.recipient = agent_id(&ak.verifying_key());
    let peer_offer = b.propose(second, &bk).unwrap().outbound.remove(0);
    let rejected = a.receive(&peer_offer, &ak).unwrap();
    assert_eq!(rejected.phase, Phase::Aborted);
    assert_eq!(a.trustline.reservations.len(), 1);
    assert!(a.trustline.reservations.contains_key("request-1"));
}

#[test]
fn crossed_proposals_decline_without_releasing_the_other_request_hold() {
    let (ak, bk) = (alice(), bob());
    let mut a = actor(&ak, &bk, 0);
    let mut b = actor(&bk, &ak, 0);
    let first = a.propose(terms(), &ak).unwrap().outbound.remove(0);
    let mut reverse = terms();
    reverse.request_id = "request-2".into();
    reverse.origin = agent_id(&bk.verifying_key());
    reverse.recipient = agent_id(&ak.verifying_key());
    let second = b.propose(reverse, &bk).unwrap().outbound.remove(0);
    let a_decline = a.receive(&second, &ak).unwrap().outbound.remove(0);
    let b_decline = b.receive(&first, &bk).unwrap().outbound.remove(0);
    assert!(a.trustline.reservations.contains_key("request-1"));
    assert!(b.trustline.reservations.contains_key("request-2"));
    a.receive(&b_decline, &ak).unwrap();
    b.receive(&a_decline, &bk).unwrap();
    assert!(a.trustline.reservations.is_empty());
    assert!(b.trustline.reservations.is_empty());
    assert!(a.transactions.values().all(|r| r.phase == Phase::Aborted));
    assert!(b.transactions.values().all(|r| r.phase == Phase::Aborted));
    assert_eq!(a.trustline.balance + b.trustline.balance, 0);
}

#[test]
fn grandfathered_out_of_limit_debt_requires_a_separate_migration_policy() {
    let (ak, bk) = (alice(), bob());
    let mut a = actor(&ak, &bk, 5);
    a.trustline.own_preferences.credit_limit = 2;
    a.trustline.validate().unwrap(); // representable history, not new capacity
    let mut reduction = terms();
    reduction.before = 5;
    reduction.after = 2;
    let before = a.clone();
    assert_eq!(
        a.propose(reduction, &ak),
        Err(BilateralError::Model(ModelError::CapacityExceeded))
    );
    assert_eq!(a, before);
}
