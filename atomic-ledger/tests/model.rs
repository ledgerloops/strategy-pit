use ed25519_dalek::SigningKey;
use ledgerloops_atomic::model::*;
use serde_json::json;
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
fn first() -> MessageEnvelope {
    MessageEnvelope {
        version: FORMAT_VERSION,
        channel_id: "trustline-1".into(),
        incarnation: 1,
        author: agent_id(&alice().verifying_key()),
        recipient: agent_id(&bob().verifying_key()),
        sequence: 1,
        previous_hash: None,
        message_id: "message-1".into(),
        payload: MessagePayload::Offer { terms: terms() },
    }
}
fn cursor() -> LogCursor {
    LogCursor::new(
        "trustline-1".into(),
        1,
        agent_id(&alice().verifying_key()),
        agent_id(&bob().verifying_key()),
    )
}
fn state(balance: i64) -> TrustlineState {
    TrustlineState {
        version: FORMAT_VERSION,
        channel_id: "trustline-1".into(),
        incarnation: 1,
        owner: agent_id(&alice().verifying_key()),
        counterparty: agent_id(&bob().verifying_key()),
        unit: "TEST".into(),
        balance,
        own_preferences: prefs(),
        peer_preferences: prefs(),
        reservations: BTreeMap::new(),
        applied_requests: BTreeMap::new(),
        local_revision: 1,
    }
}
fn hold(id: &str, delta: i64, before: i64) -> Reservation {
    Reservation {
        request_id: id.into(),
        terms_hash: terms().hash().unwrap(),
        delta,
        before,
        own_revision: 1,
        peer_revision: 1,
        phase: ReservationPhase::Prepared,
        condition: None,
    }
}

#[test]
fn integer_json_encoding_is_explicit_and_rejects_floats() {
    assert_eq!(
        canonical_bytes(&json!({"é": "literal é", "a": [true, null, -2, "\n"]})).unwrap(),
        "{\"a\":[true,null,-2,\"\\n\"],\"é\":\"literal é\"}".as_bytes()
    );
    for value in [
        json!(1.0),
        json!(-0.0),
        json!({"amount": 0.5}),
        json!(9_007_199_254_740_992_u64),
    ] {
        assert!(canonical_bytes(&value).is_err());
    }
    let reordered: serde_json::Value = serde_json::from_str("{\"z\":2,\"a\":1}").unwrap();
    assert_eq!(canonical_bytes(&reordered).unwrap(), b"{\"a\":1,\"z\":2}");
}

#[test]
fn signed_envelope_roundtrips_and_matches_atomic_agent_identity() {
    let key = alice();
    let signed = SignedEnvelope::sign(first(), &key).unwrap();
    signed.verify(&key.verifying_key()).unwrap();
    assert_eq!(
        verifying_key(&agent_id(&key.verifying_key())).unwrap(),
        key.verifying_key()
    );
    let encoded = serde_json::to_vec(&signed).unwrap();
    let restored: SignedEnvelope = serde_json::from_slice(&encoded).unwrap();
    assert_eq!(signed.hash().unwrap(), restored.hash().unwrap());
    assert!(!signed.signature.contains('='));
    assert!(signed.envelope.author.starts_with("atomic:agent:"));
    assert_eq!(
        signed.envelope.author,
        atomic_lib::identifiers::agent_subject(&atomic_lib::agents::encode_base64(
            key.verifying_key().as_bytes()
        ))
    );
}

#[test]
fn independent_python_ed25519_fixture_pins_the_wire_encoding() {
    // Independently calculated with Python's json (sorted UTF-8 keys,
    // ensure_ascii=False, compact separators) and cryptography's Ed25519.
    // All keys and values are invented fixtures; seeds are deliberately public.
    let signed = SignedEnvelope::sign(first(), &alice()).unwrap();
    assert_eq!(
        signed.signature,
        "emuURg3eImY6ZVG8mvjzXJYL19YwQEd4byAgK25lP37M8y1m5sWyOHtTmDXsC97urxmQrWxbaTnogS0a9Bf6DQ"
    );
    assert_eq!(
        signed.hash().unwrap(),
        "08c20560f070de2917e5cde992fd45e9c3b7c8ce62752efbfe037d717d5ed648"
    );
    assert_eq!(
        terms().hash().unwrap(),
        "ddabf086eee85dc2e5ccbf0c1597c099ddcd2bb2b342014dd04c11f3d95ba86b"
    );
}

#[test]
fn invalid_author_tampering_and_noncanonical_signature_are_rejected() {
    let signed = SignedEnvelope::sign(first(), &alice()).unwrap();
    assert_eq!(
        signed.verify(&bob().verifying_key()),
        Err(ModelError::WrongAuthor)
    );
    assert_eq!(
        SignedEnvelope::sign(first(), &bob()),
        Err(ModelError::WrongAuthor)
    );
    let mut tampered = signed.clone();
    tampered.envelope.message_id = "different-id".into();
    assert_eq!(
        tampered.verify(&alice().verifying_key()),
        Err(ModelError::InvalidSignature)
    );
    let mut padded = signed;
    padded.signature.push('=');
    assert_eq!(
        padded.verify(&alice().verifying_key()),
        Err(ModelError::InvalidSignature)
    );
}

#[test]
fn chain_duplicates_are_noops_and_forks_or_reused_ids_fail() {
    let mut log = cursor();
    let first = SignedEnvelope::sign(first(), &alice()).unwrap();
    assert_eq!(
        log.accept(&first, &alice().verifying_key()),
        Ok(AppendOutcome::Appended)
    );
    let after = log.clone();
    assert_eq!(
        log.accept(&first, &alice().verifying_key()),
        Ok(AppendOutcome::Duplicate)
    );
    assert_eq!(after, log);
    let mut fork = first.envelope.clone();
    fork.message_id = "fork".into();
    let fork = SignedEnvelope::sign(fork, &alice()).unwrap();
    assert_eq!(
        log.accept(&fork, &alice().verifying_key()),
        Err(ModelError::Equivocation { sequence: 1 })
    );
    let mut next = first.envelope.clone();
    next.sequence = 2;
    next.previous_hash = Some(first.hash().unwrap());
    let reused = SignedEnvelope::sign(next.clone(), &alice()).unwrap();
    assert_eq!(
        log.accept(&reused, &alice().verifying_key()),
        Err(ModelError::ReusedMessageId)
    );
    next.message_id = "message-2".into();
    let next = SignedEnvelope::sign(next, &alice()).unwrap();
    assert_eq!(
        log.accept(&next, &alice().verifying_key()),
        Ok(AppendOutcome::Appended)
    );
    assert_eq!(log.frontier.sequence, 2);
    let saved = serde_json::to_vec(&log).unwrap();
    let mut restored: LogCursor = serde_json::from_slice(&saved).unwrap();
    assert_eq!(
        restored.accept(&next, &alice().verifying_key()),
        Ok(AppendOutcome::Duplicate)
    );
}

#[test]
fn gaps_wrong_predecessors_and_cross_channel_replay_fail_without_mutation() {
    let mut log = cursor();
    let first = SignedEnvelope::sign(first(), &alice()).unwrap();
    let mut next = first.envelope.clone();
    next.sequence = 2;
    next.message_id = "message-2".into();
    next.previous_hash = Some(first.hash().unwrap());
    let next = SignedEnvelope::sign(next, &alice()).unwrap();
    assert_eq!(
        log.accept(&next, &alice().verifying_key()),
        Err(ModelError::Gap {
            expected: 1,
            received: 2
        })
    );
    assert_eq!(log.frontier.sequence, 0);
    let mut other = first.envelope.clone();
    other.channel_id = "other-channel".into();
    let other = SignedEnvelope::sign(other, &alice()).unwrap();
    assert_eq!(
        log.accept(&other, &alice().verifying_key()),
        Err(ModelError::WrongContext)
    );
    log.accept(&first, &alice().verifying_key()).unwrap();
    let before = log.clone();
    let mut wrong = next.envelope;
    wrong.previous_hash = Some("a".repeat(64));
    let wrong = SignedEnvelope::sign(wrong, &alice()).unwrap();
    assert!(log.accept(&wrong, &alice().verifying_key()).is_err());
    assert_eq!(log, before);
}

#[test]
fn exact_offer_terms_and_strict_versioned_parsing() {
    let mut invalid = terms();
    invalid.after = 3;
    assert!(invalid.validate().is_err());
    invalid = terms();
    invalid.amount = MAX_AMOUNT + 1;
    assert!(invalid.validate().is_err());
    let mut value = serde_json::to_value(first()).unwrap();
    value["unexpected"] = json!(true);
    assert!(serde_json::from_value::<MessageEnvelope>(value).is_err());
    let mut future = first();
    future.version = FORMAT_VERSION + 1;
    assert!(SignedEnvelope::sign(future, &alice()).is_err());
}

#[test]
fn reservations_count_gross_directions_and_not_only_the_all_commit_sum() {
    let mut cache = state(5);
    cache.peer_preferences.credit_limit = 0; // Bounds [0, 10].
    cache.reservations.insert("one".into(), hold("one", 4, 5));
    cache.reservations.insert("two".into(), hold("two", 4, 5));
    cache
        .reservations
        .insert("three".into(), hold("three", -4, 5));
    assert_eq!(5 + 4 + 4 - 4, 9); // All commit is in-range; a subset reaches 13.
    assert_eq!(cache.directional_reservations().unwrap(), (8, 4));
    assert_eq!(cache.validate_capacity(), Err(ModelError::CapacityExceeded));
}

#[test]
fn reservation_replay_pinned_quote_and_settlement_lifecycle() {
    let mut cache = state(0);
    let hold = hold("request-1", -3, 0);
    assert_eq!(cache.reserve(hold.clone()), Ok(true));
    assert_eq!(cache.reserve(hold), Ok(false));
    assert_eq!(
        cache.reserve(hold_for_second_request()),
        Err(ModelError::ReservationConflict)
    );
    assert_eq!(
        cache.apply_reservation("request-1"),
        Err(ModelError::InvalidTransition)
    );
    assert_eq!(cache.approve_reservation("request-1"), Ok(true));
    assert_eq!(cache.apply_reservation("request-1"), Ok(true));
    assert_eq!(cache.balance, -3);
    assert_eq!(cache.directional_reservations().unwrap(), (0, 0));
    assert_eq!(cache.apply_reservation("request-1"), Ok(false));
    assert_eq!(
        cache.release_aborted_reservation("request-1"),
        Err(ModelError::InvalidTransition)
    );
    assert_eq!(cache.settle_reservation("request-1"), Ok(true));
    assert_eq!(cache.settle_reservation("request-1"), Ok(false));
    assert_eq!(cache.apply_reservation("request-1"), Ok(false));
    assert_eq!(cache.balance, -3);
    let mut stale = state(0);
    let mut quote = hold_for_second_request();
    quote.own_revision = 2;
    assert_eq!(stale.reserve(quote), Err(ModelError::StaleQuote));
}
fn hold_for_second_request() -> Reservation {
    hold("request-2", -2, 0)
}

#[test]
fn all_subset_capacity_condition_matches_exhaustive_small_cases() {
    for balance in -3_i64..=3 {
        for a in -3_i64..=3 {
            for b in -3_i64..=3 {
                for c in -3_i64..=3 {
                    let mut cache = state(balance);
                    cache.own_preferences.credit_limit = 3;
                    cache.peer_preferences.credit_limit = 3;
                    for (i, delta) in [a, b, c].into_iter().enumerate().filter(|(_, d)| *d != 0) {
                        let id = format!("r{i}");
                        cache
                            .reservations
                            .insert(id.clone(), hold(&id, delta, balance));
                    }
                    let every_subset_safe = (0..8).all(|mask| {
                        let sum = [a, b, c]
                            .into_iter()
                            .enumerate()
                            .filter(|(i, _)| mask & (1 << i) != 0)
                            .fold(balance, |sum, (_, delta)| sum + delta);
                        (-3..=3).contains(&sum)
                    });
                    assert_eq!(cache.validate_capacity().is_ok(), every_subset_safe);
                }
            }
        }
    }
}

#[test]
fn lowered_credit_limit_preserves_historical_state_but_rejects_new_capacity() {
    let mut cache = state(5);
    cache.own_preferences.credit_limit = 2;
    cache.validate().unwrap();
    assert_eq!(cache.validate_capacity(), Err(ModelError::CapacityExceeded));
    let previous = cache.clone();
    assert!(cache.reserve(hold("new", 1, 5)).is_err());
    assert_eq!(cache, previous);
}

#[test]
fn checkpoints_require_both_peers_pin_context_and_exclude_private_bookkeeping() {
    let cache = state(0);
    let checkpoint = TrustlineCheckpoint::from_state(
        &cache,
        LogFrontier::default(),
        LogFrontier::default(),
        None,
    )
    .unwrap();
    let value = serde_json::to_value(&checkpoint).unwrap();
    for private in ["local_revision", "applied_requests", "reservations"] {
        assert!(value.get(private).is_none());
    }
    let mut signed = SignedCheckpoint {
        checkpoint,
        signatures: BTreeMap::new(),
    };
    signed.acknowledge(&alice()).unwrap();
    assert!(signed.verify().is_err());
    signed.acknowledge(&bob()).unwrap();
    signed
        .verify_for(
            &cache.channel_id,
            cache.incarnation,
            &cache.owner,
            &cache.counterparty,
        )
        .unwrap();
    assert_eq!(
        signed.verify_for("other-channel", 1, &cache.owner, &cache.counterparty),
        Err(ModelError::WrongContext)
    );
    signed.checkpoint.balance = 1;
    assert_eq!(signed.verify(), Err(ModelError::InvalidSignature));
    let mut pending = cache;
    pending.reserve(hold("pending", 1, 0)).unwrap();
    assert_eq!(
        TrustlineCheckpoint::from_state(
            &pending,
            LogFrontier::default(),
            LogFrontier::default(),
            None
        ),
        Err(ModelError::ReservationConflict)
    );
}
