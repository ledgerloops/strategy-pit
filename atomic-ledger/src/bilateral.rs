//! Pure, single-writer bilateral obligation reducer.
//!
//! Persist this entire actor together with returned outbound intent in one
//! Atomic actor-document transaction. Calling a reducer method alone is not a
//! durable commit or a transaction across the two participants. Clearing,
//! grandfathered out-of-limit debt policy, and preference changes are separate
//! protocol work; this reducer admits ordinary obligations inside fixed limits.

use crate::model::{
    agent_id, canonical_bytes, verifying_key, LogCursor, MessageEnvelope, MessagePayload,
    ModelError, OfferTerms, Reservation, ReservationPhase, SignedEnvelope, TrustlineState,
    FORMAT_VERSION,
};
use ed25519_dalek::SigningKey;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fmt;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum BilateralError {
    Model(ModelError),
    WrongSigner,
    WrongParty,
    WrongUnit,
    UnknownRequest,
    RequestConflict,
    TermsMismatch,
    InvalidTransition,
    UnsupportedMessage,
    OrphanedReservation,
}
impl From<ModelError> for BilateralError {
    fn from(error: ModelError) -> Self {
        Self::Model(error)
    }
}
impl fmt::Display for BilateralError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for BilateralError {}
pub type Result<T> = std::result::Result<T, BilateralError>;

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Role {
    Proposer,
    Recipient,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    Offered,
    PendingApproval,
    Approved,
    Committing,
    Committed,
    Aborted,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct TransactionRecord {
    pub terms: OfferTerms,
    pub terms_hash: String,
    pub role: Role,
    pub phase: Phase,
    pub reason: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Reduction {
    pub changed: bool,
    pub request_id: String,
    pub phase: Phase,
    /// Already signed and assigned stable message IDs and sender sequences.
    /// A retry returns the same envelope, not a newly appended log entry.
    pub outbound: Vec<SignedEnvelope>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct BilateralActor {
    pub trustline: TrustlineState,
    pub incoming: LogCursor,
    pub outgoing: LogCursor,
    /// Terminal aborted records are retained: an ID cannot later be reused to
    /// resurrect a declined transaction with the same or different terms.
    pub transactions: BTreeMap<String, TransactionRecord>,
    pub sent_messages: BTreeMap<String, SignedEnvelope>,
}

impl BilateralActor {
    pub fn new(trustline: TrustlineState) -> Result<Self> {
        trustline.validate()?;
        if !trustline.reservations.is_empty() {
            return Err(BilateralError::OrphanedReservation);
        }
        let outgoing = LogCursor::new(
            trustline.channel_id.clone(),
            trustline.incarnation,
            trustline.owner.clone(),
            trustline.counterparty.clone(),
        );
        let incoming = LogCursor::new(
            trustline.channel_id.clone(),
            trustline.incarnation,
            trustline.counterparty.clone(),
            trustline.owner.clone(),
        );
        Ok(Self {
            trustline,
            incoming,
            outgoing,
            transactions: BTreeMap::new(),
            sent_messages: BTreeMap::new(),
        })
    }

    fn check_signer(&self, key: &SigningKey) -> Result<()> {
        self.trustline.validate()?;
        if agent_id(&key.verifying_key()) != self.trustline.owner {
            return Err(BilateralError::WrongSigner);
        }
        Ok(())
    }

    /// Submission is the proposer's consent to these exact terms. A separate
    /// explicit approval is still required from the recipient.
    pub fn propose(&mut self, terms: OfferTerms, key: &SigningKey) -> Result<Reduction> {
        self.check_signer(key)?;
        terms.validate()?;
        self.check_parties(&terms, Role::Proposer)?;
        let hash = terms.hash()?;
        let id = terms.request_id.clone();
        let mut next = self.clone();
        let payload = if let Some(record) = next.transactions.get(&id).cloned() {
            next.check_record(&record, Role::Proposer, &hash)?;
            if record.terms != terms {
                return Err(BilateralError::RequestConflict);
            }
            match record.phase {
                Phase::Offered => Some(MessagePayload::Offer { terms }),
                Phase::Committing => Some(reference(&record, Reference::Commit)),
                Phase::Committed | Phase::Aborted => None,
                _ => return Err(BilateralError::InvalidTransition),
            }
        } else {
            if next.trustline.applied_requests.contains_key(&id) {
                return Err(BilateralError::RequestConflict);
            }
            next.reserve_terms(&terms, Role::Proposer)?;
            next.transactions.insert(
                id.clone(),
                TransactionRecord {
                    terms: terms.clone(),
                    terms_hash: hash,
                    role: Role::Proposer,
                    phase: Phase::Offered,
                    reason: None,
                },
            );
            Some(MessagePayload::Offer { terms })
        };
        let outbound = next.emit_optional(payload, key)?;
        self.finish(next, id, outbound)
    }

    pub fn approve(
        &mut self,
        request_id: &str,
        terms_hash: &str,
        key: &SigningKey,
    ) -> Result<Reduction> {
        self.check_signer(key)?;
        let mut next = self.clone();
        let mut record = next.record(request_id)?.clone();
        next.check_record(&record, Role::Recipient, terms_hash)?;
        let payload = match record.phase {
            Phase::PendingApproval => {
                next.check_reserved_terms(&record)?;
                next.trustline.approve_reservation(request_id)?;
                record.phase = Phase::Approved;
                next.transactions.insert(request_id.into(), record.clone());
                reference(&record, Reference::Accept)
            }
            Phase::Approved => reference(&record, Reference::Accept),
            Phase::Committed => reference(&record, Reference::Settled),
            _ => return Err(BilateralError::InvalidTransition),
        };
        let outbound = vec![next.emit(payload, key)?];
        self.finish(next, request_id.into(), outbound)
    }

    /// Only a recipient who has not approved may decline. Approval cannot be
    /// reversed by timeout, decline, or a delayed conflicting message.
    pub fn decline(
        &mut self,
        request_id: &str,
        terms_hash: &str,
        reason: String,
        key: &SigningKey,
    ) -> Result<Reduction> {
        self.check_signer(key)?;
        let mut next = self.clone();
        let mut record = next.record(request_id)?.clone();
        next.check_record(&record, Role::Recipient, terms_hash)?;
        match record.phase {
            Phase::PendingApproval => {
                next.trustline.release_aborted_reservation(request_id)?;
                record.phase = Phase::Aborted;
                record.reason = Some(reason);
                next.transactions.insert(request_id.into(), record.clone());
            }
            Phase::Aborted => {}
            _ => return Err(BilateralError::InvalidTransition),
        }
        let outbound = vec![next.emit(decline_payload(&record), key)?];
        self.finish(next, request_id.into(), outbound)
    }

    /// The only peer ingress. Signature, author, channel, recipient and hash
    /// chain are checked against the accepted trustline before any transition.
    /// An error leaves both financial state and the log cursor unchanged.
    pub fn receive(&mut self, message: &SignedEnvelope, key: &SigningKey) -> Result<Reduction> {
        self.check_signer(key)?;
        let mut next = self.clone();
        next.incoming
            .accept(message, &verifying_key(&next.trustline.counterparty)?)?;
        let (id, payload) = next.reduce_peer(&message.envelope.payload)?;
        let outbound = next.emit_optional(payload, key)?;
        self.finish(next, id, outbound)
    }

    fn record(&self, id: &str) -> Result<&TransactionRecord> {
        self.transactions
            .get(id)
            .ok_or(BilateralError::UnknownRequest)
    }

    fn check_parties(&self, terms: &OfferTerms, role: Role) -> Result<()> {
        let (origin, recipient) = match role {
            Role::Proposer => (&self.trustline.owner, &self.trustline.counterparty),
            Role::Recipient => (&self.trustline.counterparty, &self.trustline.owner),
        };
        if &terms.origin != origin || &terms.recipient != recipient {
            return Err(BilateralError::WrongParty);
        }
        if terms.unit != self.trustline.unit {
            return Err(BilateralError::WrongUnit);
        }
        Ok(())
    }

    fn check_record(&self, record: &TransactionRecord, role: Role, hash: &str) -> Result<()> {
        self.check_parties(&record.terms, role)?;
        if record.role != role {
            return Err(BilateralError::WrongParty);
        }
        if record.terms_hash != hash || record.terms.hash()? != hash {
            return Err(BilateralError::TermsMismatch);
        }
        Ok(())
    }

    fn reservation(&self, terms: &OfferTerms, role: Role) -> Result<Reservation> {
        let (before, after, own_revision, peer_revision) = match role {
            Role::Proposer => (
                terms.before,
                terms.after,
                terms.origin_revision,
                terms.recipient_revision,
            ),
            Role::Recipient => (
                -terms.before,
                -terms.after,
                terms.recipient_revision,
                terms.origin_revision,
            ),
        };
        Ok(Reservation {
            request_id: terms.request_id.clone(),
            terms_hash: terms.hash()?,
            delta: after.checked_sub(before).ok_or(ModelError::Overflow)?,
            before,
            own_revision,
            peer_revision,
            phase: ReservationPhase::Prepared,
            condition: None,
        })
    }

    fn reserve_terms(&mut self, terms: &OfferTerms, role: Role) -> Result<()> {
        self.trustline.reserve(self.reservation(terms, role)?)?;
        Ok(())
    }

    fn check_reserved_terms(&self, record: &TransactionRecord) -> Result<()> {
        let expected = self.reservation(&record.terms, record.role)?;
        let hold = self
            .trustline
            .reservations
            .get(&record.terms.request_id)
            .ok_or(ModelError::UnknownReservation)?;
        if hold.request_id != expected.request_id
            || hold.terms_hash != expected.terms_hash
            || hold.delta != expected.delta
            || hold.before != expected.before
            || hold.own_revision != expected.own_revision
            || hold.peer_revision != expected.peer_revision
            || hold.condition.is_some()
        {
            return Err(ModelError::ReservationConflict.into());
        }
        if self.trustline.balance != expected.before
            || self.trustline.own_preferences.revision != expected.own_revision
            || self.trustline.peer_preferences.revision != expected.peer_revision
        {
            return Err(ModelError::StaleQuote.into());
        }
        Ok(())
    }

    fn reduce_peer(
        &mut self,
        payload: &MessagePayload,
    ) -> Result<(String, Option<MessagePayload>)> {
        match payload {
            MessagePayload::Offer { terms } => {
                terms.validate()?;
                self.check_parties(terms, Role::Recipient)?;
                let id = terms.request_id.clone();
                let hash = terms.hash()?;
                if let Some(record) = self.transactions.get(&id).cloned() {
                    self.check_record(&record, Role::Recipient, &hash)?;
                    if record.terms != *terms {
                        return Err(BilateralError::RequestConflict);
                    }
                    let reply = match record.phase {
                        Phase::PendingApproval => None,
                        Phase::Approved => Some(reference(&record, Reference::Accept)),
                        Phase::Committed => Some(reference(&record, Reference::Settled)),
                        Phase::Aborted => Some(decline_payload(&record)),
                        _ => return Err(BilateralError::InvalidTransition),
                    };
                    return Ok((id, reply));
                }
                if self.trustline.applied_requests.contains_key(&id) {
                    return Err(BilateralError::RequestConflict);
                }
                let mut record = TransactionRecord {
                    terms: terms.clone(),
                    terms_hash: hash,
                    role: Role::Recipient,
                    phase: Phase::PendingApproval,
                    reason: None,
                };
                let reply = match self.reserve_terms(terms, Role::Recipient) {
                    Ok(()) => None, // Receipt never automatically grants consent.
                    Err(BilateralError::Model(ModelError::StaleQuote)) => {
                        record.phase = Phase::Aborted;
                        record.reason = Some("Stale trustline quote".into());
                        Some(decline_payload(&record))
                    }
                    Err(BilateralError::Model(ModelError::CapacityExceeded)) => {
                        record.phase = Phase::Aborted;
                        record.reason = Some("Credit capacity unavailable".into());
                        Some(decline_payload(&record))
                    }
                    Err(BilateralError::Model(ModelError::ReservationConflict)) => {
                        record.phase = Phase::Aborted;
                        record.reason = Some("Trustline already reserved".into());
                        Some(decline_payload(&record))
                    }
                    Err(error) => return Err(error),
                };
                self.transactions.insert(id.clone(), record);
                Ok((id, reply))
            }
            MessagePayload::Accept {
                request_id,
                terms_hash,
            } => {
                let mut record = self.record(request_id)?.clone();
                self.check_record(&record, Role::Proposer, terms_hash)?;
                match record.phase {
                    Phase::Offered => {
                        self.check_reserved_terms(&record)?;
                        self.trustline.approve_reservation(request_id)?;
                        self.trustline.apply_reservation(request_id)?;
                        record.phase = Phase::Committing;
                        self.transactions.insert(request_id.clone(), record.clone());
                    }
                    Phase::Committing | Phase::Committed => {}
                    _ => return Err(BilateralError::InvalidTransition),
                }
                Ok((
                    request_id.clone(),
                    Some(reference(&record, Reference::Commit)),
                ))
            }
            MessagePayload::Commit {
                request_id,
                terms_hash,
            } => {
                let mut record = self.record(request_id)?.clone();
                self.check_record(&record, Role::Recipient, terms_hash)?;
                match record.phase {
                    Phase::Approved => {
                        self.check_reserved_terms(&record)?;
                        self.trustline.apply_reservation(request_id)?;
                        self.trustline.settle_reservation(request_id)?;
                        record.phase = Phase::Committed;
                        self.transactions.insert(request_id.clone(), record.clone());
                    }
                    Phase::Committed => {}
                    _ => return Err(BilateralError::InvalidTransition),
                }
                Ok((
                    request_id.clone(),
                    Some(reference(&record, Reference::Settled)),
                ))
            }
            MessagePayload::Settled {
                request_id,
                terms_hash,
            } => {
                let mut record = self.record(request_id)?.clone();
                self.check_record(&record, Role::Proposer, terms_hash)?;
                match record.phase {
                    Phase::Committing => {
                        self.trustline.settle_reservation(request_id)?;
                        record.phase = Phase::Committed;
                        self.transactions.insert(request_id.clone(), record);
                    }
                    Phase::Committed => {}
                    _ => return Err(BilateralError::InvalidTransition),
                }
                Ok((request_id.clone(), None))
            }
            MessagePayload::Decline {
                request_id,
                terms_hash,
                reason,
            } => {
                let mut record = self.record(request_id)?.clone();
                self.check_record(&record, Role::Proposer, terms_hash)?;
                match record.phase {
                    Phase::Offered => {
                        self.trustline.release_aborted_reservation(request_id)?;
                        record.phase = Phase::Aborted;
                        record.reason = Some(reason.clone());
                        self.transactions.insert(request_id.clone(), record);
                    }
                    Phase::Aborted => {}
                    _ => return Err(BilateralError::InvalidTransition),
                }
                Ok((request_id.clone(), None))
            }
            _ => Err(BilateralError::UnsupportedMessage),
        }
    }

    fn emit_optional(
        &mut self,
        payload: Option<MessagePayload>,
        key: &SigningKey,
    ) -> Result<Vec<SignedEnvelope>> {
        payload
            .map(|payload| self.emit(payload, key).map(|message| vec![message]))
            .unwrap_or_else(|| Ok(Vec::new()))
    }

    fn emit(&mut self, payload: MessagePayload, key: &SigningKey) -> Result<SignedEnvelope> {
        payload.validate()?;
        let value = serde_json::json!({
            "channel_id": self.trustline.channel_id,
            "incarnation": self.trustline.incarnation,
            "author": self.trustline.owner,
            "recipient": self.trustline.counterparty,
            "payload": payload,
        });
        let mut id_bytes = b"LedgerLoops/Atomic/bilateral-intent/v1\0".to_vec();
        id_bytes.extend(canonical_bytes(&value)?);
        let id = Sha256::digest(&id_bytes)
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<String>();
        if let Some(existing) = self.sent_messages.get(&id) {
            existing.verify(&key.verifying_key())?;
            if existing.envelope.payload != payload {
                return Err(BilateralError::RequestConflict);
            }
            return Ok(existing.clone());
        }
        let envelope = MessageEnvelope {
            version: FORMAT_VERSION,
            channel_id: self.trustline.channel_id.clone(),
            incarnation: self.trustline.incarnation,
            author: self.trustline.owner.clone(),
            recipient: self.trustline.counterparty.clone(),
            sequence: self
                .outgoing
                .frontier
                .sequence
                .checked_add(1)
                .ok_or(ModelError::Overflow)?,
            previous_hash: self.outgoing.frontier.hash.clone(),
            message_id: id.clone(),
            payload,
        };
        let message = SignedEnvelope::sign(envelope, key)?;
        self.outgoing.accept(&message, &key.verifying_key())?;
        self.sent_messages.insert(id, message.clone());
        Ok(message)
    }

    fn finish(
        &mut self,
        next: Self,
        request_id: String,
        outbound: Vec<SignedEnvelope>,
    ) -> Result<Reduction> {
        let phase = next.record(&request_id)?.phase;
        let changed = self != &next;
        *self = next;
        Ok(Reduction {
            changed,
            request_id,
            phase,
            outbound,
        })
    }
}

#[derive(Clone, Copy)]
enum Reference {
    Accept,
    Commit,
    Settled,
}
fn reference(record: &TransactionRecord, kind: Reference) -> MessagePayload {
    let request_id = record.terms.request_id.clone();
    let terms_hash = record.terms_hash.clone();
    match kind {
        Reference::Accept => MessagePayload::Accept {
            request_id,
            terms_hash,
        },
        Reference::Commit => MessagePayload::Commit {
            request_id,
            terms_hash,
        },
        Reference::Settled => MessagePayload::Settled {
            request_id,
            terms_hash,
        },
    }
}
fn decline_payload(record: &TransactionRecord) -> MessagePayload {
    MessagePayload::Decline {
        request_id: record.terms.request_id.clone(),
        terms_hash: record.terms_hash.clone(),
        reason: record
            .reason
            .clone()
            .unwrap_or_else(|| "Declined by counterparty".into()),
    }
}
