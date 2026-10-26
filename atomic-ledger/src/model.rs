//! Versioned LedgerLoops messages and projections for two authored Atomic logs.
//!
//! Signatures use the explicitly defined LedgerLoops integer-JSON encoding below.
//! This is not RFC 8785: floats and integers outside JavaScript's exact range are
//! rejected, and object keys are ordered by their UTF-8 bytes.

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use ed25519_dalek::{Signature, Signer, SigningKey, VerifyingKey};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fmt;

pub const FORMAT_VERSION: u16 = 1;
pub const MAX_AMOUNT: i64 = 1_000_000_000_000;
pub const MAX_EXACT_INTEGER: u64 = 9_007_199_254_740_991;
const MESSAGE_DOMAIN: &[u8] = b"LedgerLoops/Atomic/message/v1\0";
const SIGNED_DOMAIN: &[u8] = b"LedgerLoops/Atomic/signed-message/v1\0";
const TERMS_DOMAIN: &[u8] = b"LedgerLoops/Atomic/offer-terms/v1\0";
const CHECKPOINT_DOMAIN: &[u8] = b"LedgerLoops/Atomic/checkpoint/v1\0";

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ModelError {
    Invalid(&'static str),
    InvalidSignature,
    WrongAuthor,
    WrongContext,
    Gap { expected: u64, received: u64 },
    Equivocation { sequence: u64 },
    ReusedMessageId,
    CapacityExceeded,
    ReservationConflict,
    UnknownReservation,
    StaleQuote,
    InvalidTransition,
    Overflow,
}
impl fmt::Display for ModelError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for ModelError {}
pub type Result<T> = std::result::Result<T, ModelError>;

/// Atomic's canonical URL-safe unpadded Ed25519 agent identifier.
pub fn agent_id(key: &VerifyingKey) -> String {
    format!("atomic:agent:{}", URL_SAFE_NO_PAD.encode(key.as_bytes()))
}

pub fn verifying_key(agent: &str) -> Result<VerifyingKey> {
    let encoded = agent
        .strip_prefix("atomic:agent:")
        .ok_or(ModelError::WrongAuthor)?;
    let bytes = URL_SAFE_NO_PAD
        .decode(encoded)
        .map_err(|_| ModelError::WrongAuthor)?;
    let bytes: [u8; 32] = bytes.try_into().map_err(|_| ModelError::WrongAuthor)?;
    if URL_SAFE_NO_PAD.encode(bytes) != encoded {
        return Err(ModelError::WrongAuthor);
    }
    VerifyingKey::from_bytes(&bytes).map_err(|_| ModelError::WrongAuthor)
}

/// Canonical UTF-8 JSON with sorted map keys and exact integers only.
pub fn canonical_json(value: &Value) -> Result<Vec<u8>> {
    fn write(value: &Value, out: &mut String) -> Result<()> {
        match value {
            Value::Null => out.push_str("null"),
            Value::Bool(v) => out.push_str(if *v { "true" } else { "false" }),
            Value::Number(n) => {
                let valid = n
                    .as_i64()
                    .map(|x| x.unsigned_abs() <= MAX_EXACT_INTEGER)
                    .or_else(|| n.as_u64().map(|x| x <= MAX_EXACT_INTEGER))
                    .unwrap_or(false);
                if !valid {
                    return Err(ModelError::Invalid("signed JSON requires exact integers"));
                }
                out.push_str(&n.to_string());
            }
            Value::String(v) => out.push_str(
                &serde_json::to_string(v).map_err(|_| ModelError::Invalid("JSON string"))?,
            ),
            Value::Array(items) => {
                out.push('[');
                for (index, item) in items.iter().enumerate() {
                    if index != 0 {
                        out.push(',');
                    }
                    write(item, out)?;
                }
                out.push(']');
            }
            Value::Object(map) => {
                out.push('{');
                let mut keys = map.keys().collect::<Vec<_>>();
                keys.sort_by(|a, b| a.as_bytes().cmp(b.as_bytes()));
                for (index, key) in keys.into_iter().enumerate() {
                    if index != 0 {
                        out.push(',');
                    }
                    out.push_str(
                        &serde_json::to_string(key).map_err(|_| ModelError::Invalid("JSON key"))?,
                    );
                    out.push(':');
                    write(&map[key], out)?;
                }
                out.push('}');
            }
        }
        Ok(())
    }
    let mut out = String::new();
    write(value, &mut out)?;
    Ok(out.into_bytes())
}

/// Alias used by resource persistence and cross-language format fixtures.
pub fn canonical_bytes(value: &Value) -> Result<Vec<u8>> {
    canonical_json(value)
}

fn encoded<T: Serialize>(domain: &[u8], value: &T) -> Result<Vec<u8>> {
    let value = serde_json::to_value(value).map_err(|_| ModelError::Invalid("serialization"))?;
    let mut bytes = domain.to_vec();
    bytes.extend(canonical_json(&value)?);
    Ok(bytes)
}
fn digest(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}
fn bounded_id(value: &str) -> bool {
    !value.is_empty() && value.len() <= 200 && !value.chars().any(char::is_control)
}
fn valid_hash(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn validate_hash(value: &str) -> Result<()> {
    if valid_hash(value) {
        Ok(())
    } else {
        Err(ModelError::Invalid("expected lowercase SHA-256 hash"))
    }
}
fn validate_revision(revision: u64) -> Result<()> {
    if (1..=MAX_EXACT_INTEGER).contains(&revision) {
        Ok(())
    } else {
        Err(ModelError::Invalid("revision"))
    }
}
fn bounded_amount(value: i64) -> bool {
    value.unsigned_abs() <= MAX_AMOUNT as u64
}
fn signature_bytes(encoded: &str) -> Result<Signature> {
    let bytes = URL_SAFE_NO_PAD
        .decode(encoded)
        .map_err(|_| ModelError::InvalidSignature)?;
    if URL_SAFE_NO_PAD.encode(&bytes) != encoded {
        return Err(ModelError::InvalidSignature);
    }
    Signature::from_slice(&bytes).map_err(|_| ModelError::InvalidSignature)
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Direction {
    IOwe,
    PeerOwes,
}
impl Direction {
    pub fn delta(self, amount: i64) -> i64 {
        match self {
            Self::IOwe => -amount,
            Self::PeerOwes => amount,
        }
    }
}

/// Exact bilateral terms, expressed from the proposer's balance perspective.
/// Integer milliseconds deliberately replace the legacy floating-point timestamp.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct OfferTerms {
    pub request_id: String,
    pub origin: String,
    pub recipient: String,
    pub unit: String,
    pub amount: i64,
    pub direction: Direction,
    pub description: String,
    pub before: i64,
    pub after: i64,
    pub origin_revision: u64,
    pub recipient_revision: u64,
    pub created_at_ms: u64,
}
impl OfferTerms {
    pub fn validate(&self) -> Result<()> {
        if !bounded_id(&self.request_id) || !bounded_id(&self.unit) || self.unit.len() > 64 {
            return Err(ModelError::Invalid("request identity or unit"));
        }
        verifying_key(&self.origin)?;
        verifying_key(&self.recipient)?;
        if self.origin == self.recipient {
            return Err(ModelError::Invalid("distinct participants required"));
        }
        if !(1..=MAX_AMOUNT).contains(&self.amount)
            || !bounded_amount(self.before)
            || !bounded_amount(self.after)
        {
            return Err(ModelError::Invalid("bounded exact amounts required"));
        }
        if self.before.checked_add(self.direction.delta(self.amount)) != Some(self.after) {
            return Err(ModelError::Invalid("before/delta/after mismatch"));
        }
        if self.description.chars().count() > 200
            || self
                .description
                .chars()
                .any(|c| c.is_control() && c != '\n' && c != '\t')
        {
            return Err(ModelError::Invalid("description"));
        }
        validate_revision(self.origin_revision)?;
        validate_revision(self.recipient_revision)?;
        if self.created_at_ms > MAX_EXACT_INTEGER {
            return Err(ModelError::Invalid("timestamp"));
        }
        Ok(())
    }
    pub fn hash(&self) -> Result<String> {
        self.validate()?;
        Ok(digest(&encoded(TERMS_DOMAIN, self)?))
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Preferences {
    pub revision: u64,
    pub credit_limit: i64,
    pub comfort_min: i64,
    pub comfort_max: i64,
    pub auto_adjust: bool,
}
impl Preferences {
    pub fn validate(&self) -> Result<()> {
        validate_revision(self.revision)?;
        if !(0..=MAX_AMOUNT).contains(&self.credit_limit)
            || !bounded_amount(self.comfort_min)
            || !bounded_amount(self.comfort_max)
            || self.comfort_min > self.comfort_max
        {
            return Err(ModelError::Invalid("credit or comfort preferences"));
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ReservationPhase {
    Prepared,
    Approved,
    AppliedAwaitingSettlement,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Reservation {
    pub request_id: String,
    pub terms_hash: String,
    pub delta: i64,
    pub before: i64,
    pub own_revision: u64,
    pub peer_revision: u64,
    pub phase: ReservationPhase,
    pub condition: Option<String>,
}
impl Reservation {
    pub fn validate(&self) -> Result<()> {
        if !bounded_id(&self.request_id)
            || self.delta == 0
            || !bounded_amount(self.delta)
            || !bounded_amount(self.before)
        {
            return Err(ModelError::Invalid("reservation"));
        }
        validate_hash(&self.terms_hash)?;
        validate_revision(self.own_revision)?;
        validate_revision(self.peer_revision)?;
        if let Some(condition) = &self.condition {
            validate_hash(condition)?;
        }
        Ok(())
    }
}

/// Reserved/fulfill are versioned envelope types, not an implemented clearing protocol.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum MessagePayload {
    Offer {
        terms: OfferTerms,
    },
    Accept {
        request_id: String,
        terms_hash: String,
    },
    Commit {
        request_id: String,
        terms_hash: String,
    },
    Settled {
        request_id: String,
        terms_hash: String,
    },
    Decline {
        request_id: String,
        terms_hash: String,
        reason: String,
    },
    GrantUpdate {
        previous_revision: u64,
        revision: u64,
        credit_limit: i64,
    },
    ComfortUpdate {
        previous_revision: u64,
        revision: u64,
        comfort_min: i64,
        comfort_max: i64,
        auto_adjust: bool,
    },
    Reserved {
        reservation: Reservation,
    },
    Fulfill {
        request_id: String,
        condition: String,
        preimage: String,
    },
}
impl MessagePayload {
    pub fn validate(&self) -> Result<()> {
        match self {
            Self::Offer { terms } => terms.validate(),
            Self::Accept {
                request_id,
                terms_hash,
            }
            | Self::Commit {
                request_id,
                terms_hash,
            }
            | Self::Settled {
                request_id,
                terms_hash,
            }
            | Self::Decline {
                request_id,
                terms_hash,
                ..
            } => {
                if !bounded_id(request_id) {
                    return Err(ModelError::Invalid("request id"));
                }
                validate_hash(terms_hash)?;
                if let Self::Decline { reason, .. } = self {
                    if reason.len() > 500 || reason.chars().any(char::is_control) {
                        return Err(ModelError::Invalid("decline reason"));
                    }
                }
                Ok(())
            }
            Self::GrantUpdate {
                previous_revision,
                revision,
                credit_limit,
            } => {
                validate_update_revision(*previous_revision, *revision)?;
                if !(0..=MAX_AMOUNT).contains(credit_limit) {
                    return Err(ModelError::Invalid("credit limit"));
                }
                Ok(())
            }
            Self::ComfortUpdate {
                previous_revision,
                revision,
                comfort_min,
                comfort_max,
                ..
            } => {
                validate_update_revision(*previous_revision, *revision)?;
                if !bounded_amount(*comfort_min)
                    || !bounded_amount(*comfort_max)
                    || comfort_min > comfort_max
                {
                    return Err(ModelError::Invalid("comfort interval"));
                }
                Ok(())
            }
            Self::Reserved { reservation } => reservation.validate(),
            Self::Fulfill {
                request_id,
                condition,
                preimage,
            } => {
                if !bounded_id(request_id) {
                    return Err(ModelError::Invalid("request id"));
                }
                validate_hash(condition)?;
                // This format validates evidence shape only. Clearing must verify
                // the protocol-specific context-bound hashlock before applying it.
                validate_hash(preimage)
            }
        }
    }
}
fn validate_update_revision(previous: u64, revision: u64) -> Result<()> {
    validate_revision(previous)?;
    validate_revision(revision)?;
    if previous.checked_add(1) != Some(revision) {
        return Err(ModelError::Invalid("revision must advance exactly once"));
    }
    Ok(())
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct MessageEnvelope {
    pub version: u16,
    pub channel_id: String,
    pub incarnation: u64,
    pub author: String,
    pub recipient: String,
    pub sequence: u64,
    pub previous_hash: Option<String>,
    pub message_id: String,
    pub payload: MessagePayload,
}
impl MessageEnvelope {
    pub fn validate(&self) -> Result<()> {
        if self.version != FORMAT_VERSION {
            return Err(ModelError::Invalid("message version"));
        }
        if !bounded_id(&self.channel_id) || !bounded_id(&self.message_id) {
            return Err(ModelError::Invalid("channel or message id"));
        }
        if self.incarnation > MAX_EXACT_INTEGER
            || self.sequence == 0
            || self.sequence > MAX_EXACT_INTEGER
        {
            return Err(ModelError::Invalid("incarnation or sequence"));
        }
        verifying_key(&self.author)?;
        verifying_key(&self.recipient)?;
        if self.author == self.recipient {
            return Err(ModelError::Invalid("distinct participants required"));
        }
        match (self.sequence, &self.previous_hash) {
            (1, None) => {}
            (1, Some(_)) | (_, None) => return Err(ModelError::Invalid("log predecessor")),
            (_, Some(previous)) => validate_hash(previous)?,
        }
        self.payload.validate()?;
        if let MessagePayload::Offer { terms } = &self.payload {
            if terms.origin != self.author || terms.recipient != self.recipient {
                return Err(ModelError::WrongContext);
            }
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct SignedEnvelope {
    pub envelope: MessageEnvelope,
    pub signature: String,
}
impl SignedEnvelope {
    pub fn sign(envelope: MessageEnvelope, key: &SigningKey) -> Result<Self> {
        envelope.validate()?;
        if envelope.author != agent_id(&key.verifying_key()) {
            return Err(ModelError::WrongAuthor);
        }
        let signature = key.sign(&encoded(MESSAGE_DOMAIN, &envelope)?);
        Ok(Self {
            envelope,
            signature: URL_SAFE_NO_PAD.encode(signature.to_bytes()),
        })
    }
    pub fn verify(&self, expected_key: &VerifyingKey) -> Result<()> {
        self.envelope.validate()?;
        if self.envelope.author != agent_id(expected_key) {
            return Err(ModelError::WrongAuthor);
        }
        expected_key
            .verify_strict(
                &encoded(MESSAGE_DOMAIN, &self.envelope)?,
                &signature_bytes(&self.signature)?,
            )
            .map_err(|_| ModelError::InvalidSignature)
    }
    pub fn hash(&self) -> Result<String> {
        self.envelope.validate()?;
        signature_bytes(&self.signature)?;
        Ok(digest(&encoded(SIGNED_DOMAIN, self)?))
    }
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub enum AppendOutcome {
    Appended,
    Duplicate,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct LogFrontier {
    pub sequence: u64,
    pub hash: Option<String>,
}
impl LogFrontier {
    pub fn validate(&self) -> Result<()> {
        if self.sequence > MAX_EXACT_INTEGER {
            return Err(ModelError::Invalid("frontier sequence"));
        }
        match (self.sequence, &self.hash) {
            (0, None) => Ok(()),
            (0, Some(_)) | (_, None) => Err(ModelError::Invalid("frontier hash")),
            (_, Some(hash)) => validate_hash(hash),
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct AcceptedMessage {
    pub message_id: String,
    pub hash: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct LogCursor {
    pub channel_id: String,
    pub incarnation: u64,
    pub author: String,
    pub recipient: String,
    pub frontier: LogFrontier,
    pub accepted: BTreeMap<u64, AcceptedMessage>,
}
impl LogCursor {
    pub fn new(channel_id: String, incarnation: u64, author: String, recipient: String) -> Self {
        Self {
            channel_id,
            incarnation,
            author,
            recipient,
            frontier: LogFrontier::default(),
            accepted: BTreeMap::new(),
        }
    }
    pub fn accept(
        &mut self,
        message: &SignedEnvelope,
        expected_key: &VerifyingKey,
    ) -> Result<AppendOutcome> {
        message.verify(expected_key)?;
        self.frontier.validate()?;
        let envelope = &message.envelope;
        if envelope.channel_id != self.channel_id
            || envelope.incarnation != self.incarnation
            || envelope.author != self.author
            || envelope.recipient != self.recipient
        {
            return Err(ModelError::WrongContext);
        }
        let hash = message.hash()?;
        if let Some(previous) = self.accepted.get(&envelope.sequence) {
            return if previous.hash == hash && previous.message_id == envelope.message_id {
                Ok(AppendOutcome::Duplicate)
            } else {
                Err(ModelError::Equivocation {
                    sequence: envelope.sequence,
                })
            };
        }
        if self
            .accepted
            .values()
            .any(|known| known.message_id == envelope.message_id)
        {
            return Err(ModelError::ReusedMessageId);
        }
        let expected = self
            .frontier
            .sequence
            .checked_add(1)
            .ok_or(ModelError::Overflow)?;
        if envelope.sequence != expected {
            return Err(ModelError::Gap {
                expected,
                received: envelope.sequence,
            });
        }
        if envelope.previous_hash != self.frontier.hash {
            return Err(ModelError::Invalid("hash chain mismatch"));
        }
        self.accepted.insert(
            envelope.sequence,
            AcceptedMessage {
                message_id: envelope.message_id.clone(),
                hash: hash.clone(),
            },
        );
        self.frontier = LogFrontier {
            sequence: envelope.sequence,
            hash: Some(hash),
        };
        Ok(AppendOutcome::Appended)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct TrustlineState {
    pub version: u16,
    pub channel_id: String,
    pub incarnation: u64,
    pub owner: String,
    pub counterparty: String,
    pub unit: String,
    pub balance: i64,
    pub own_preferences: Preferences,
    pub peer_preferences: Preferences,
    pub reservations: BTreeMap<String, Reservation>,
    /// Stable request ID -> terms hash, retained across replay and restart.
    pub applied_requests: BTreeMap<String, String>,
    pub local_revision: u64,
}
impl TrustlineState {
    pub fn validate(&self) -> Result<()> {
        if self.version != FORMAT_VERSION
            || !bounded_id(&self.channel_id)
            || !bounded_id(&self.unit)
            || self.incarnation > MAX_EXACT_INTEGER
            || !bounded_amount(self.balance)
            || self.owner == self.counterparty
        {
            return Err(ModelError::Invalid("trustline state"));
        }
        verifying_key(&self.owner)?;
        verifying_key(&self.counterparty)?;
        self.own_preferences.validate()?;
        self.peer_preferences.validate()?;
        validate_revision(self.local_revision)?;
        for (id, reservation) in &self.reservations {
            reservation.validate()?;
            if id != &reservation.request_id {
                return Err(ModelError::Invalid("reservation key"));
            }
        }
        for (id, hash) in &self.applied_requests {
            if !bounded_id(id) {
                return Err(ModelError::Invalid("applied request id"));
            }
            validate_hash(hash)?;
        }
        Ok(())
    }
    pub fn bounds(&self) -> (i64, i64) {
        (
            -self.peer_preferences.credit_limit,
            self.own_preferences.credit_limit,
        )
    }
    pub fn directional_reservations(&self) -> Result<(i64, i64)> {
        let (mut increase, mut decrease) = (0_i64, 0_i64);
        for hold in self
            .reservations
            .values()
            .filter(|r| r.phase != ReservationPhase::AppliedAwaitingSettlement)
        {
            if hold.delta >= 0 {
                increase = increase
                    .checked_add(hold.delta)
                    .ok_or(ModelError::Overflow)?;
            } else {
                decrease = decrease
                    .checked_sub(hold.delta)
                    .ok_or(ModelError::Overflow)?;
            }
        }
        Ok((increase, decrease))
    }
    /// Strict in-range admission. A lowered grant can leave existing debt outside
    /// bounds; that historical state remains representable, but cannot reserve
    /// new capacity through this method. Debt-reduction policy is actor work.
    pub fn validate_capacity(&self) -> Result<()> {
        self.validate()?;
        let (increase, decrease) = self.directional_reservations()?;
        let (lower, upper) = self.bounds();
        if self
            .balance
            .checked_add(increase)
            .ok_or(ModelError::Overflow)?
            > upper
            || self
                .balance
                .checked_sub(decrease)
                .ok_or(ModelError::Overflow)?
                < lower
        {
            return Err(ModelError::CapacityExceeded);
        }
        Ok(())
    }
    /// Initial quoted protocol reserves the whole edge. The gross accounting
    /// above remains useful for checking a future explicitly concurrent design.
    pub fn reserve(&mut self, reservation: Reservation) -> Result<bool> {
        self.validate()?;
        reservation.validate()?;
        if let Some(existing) = self.reservations.get(&reservation.request_id) {
            return if existing == &reservation {
                Ok(false)
            } else {
                Err(ModelError::ReservationConflict)
            };
        }
        if self.applied_requests.contains_key(&reservation.request_id) {
            return Err(ModelError::ReservationConflict);
        }
        if !self.reservations.is_empty() || reservation.phase != ReservationPhase::Prepared {
            return Err(ModelError::ReservationConflict);
        }
        if reservation.before != self.balance
            || reservation.own_revision != self.own_preferences.revision
            || reservation.peer_revision != self.peer_preferences.revision
        {
            return Err(ModelError::StaleQuote);
        }
        let mut candidate = self.clone();
        candidate
            .reservations
            .insert(reservation.request_id.clone(), reservation);
        candidate.validate_capacity()?;
        candidate.bump_revision()?;
        *self = candidate;
        Ok(true)
    }
    pub fn approve_reservation(&mut self, id: &str) -> Result<bool> {
        let reservation = self
            .reservations
            .get(id)
            .ok_or(ModelError::UnknownReservation)?;
        if reservation.phase == ReservationPhase::Approved {
            return Ok(false);
        }
        if reservation.phase != ReservationPhase::Prepared {
            return Err(ModelError::InvalidTransition);
        }
        let mut candidate = self.clone();
        candidate.reservations.get_mut(id).unwrap().phase = ReservationPhase::Approved;
        candidate.bump_revision()?;
        *self = candidate;
        Ok(true)
    }
    /// Called only after the actor verifies bilateral/conditional commit evidence.
    /// Keep the edge locked until the counterparty's settled confirmation.
    pub fn apply_reservation(&mut self, id: &str) -> Result<bool> {
        if let Some(hash) = self.applied_requests.get(id) {
            return if self
                .reservations
                .get(id)
                .is_none_or(|r| hash == &r.terms_hash)
            {
                Ok(false)
            } else {
                Err(ModelError::ReservationConflict)
            };
        }
        let reservation = self
            .reservations
            .get(id)
            .ok_or(ModelError::UnknownReservation)?;
        if reservation.phase != ReservationPhase::Approved {
            return Err(ModelError::InvalidTransition);
        }
        if reservation.before != self.balance
            || reservation.own_revision != self.own_preferences.revision
            || reservation.peer_revision != self.peer_preferences.revision
        {
            return Err(ModelError::StaleQuote);
        }
        let mut candidate = self.clone();
        candidate.balance = candidate
            .balance
            .checked_add(reservation.delta)
            .ok_or(ModelError::Overflow)?;
        candidate.reservations.get_mut(id).unwrap().phase =
            ReservationPhase::AppliedAwaitingSettlement;
        candidate
            .applied_requests
            .insert(id.into(), reservation.terms_hash.clone());
        candidate.validate_capacity()?;
        candidate.bump_revision()?;
        *self = candidate;
        Ok(true)
    }
    pub fn settle_reservation(&mut self, id: &str) -> Result<bool> {
        let Some(reservation) = self.reservations.get(id) else {
            return if self.applied_requests.contains_key(id) {
                Ok(false)
            } else {
                Err(ModelError::UnknownReservation)
            };
        };
        if reservation.phase != ReservationPhase::AppliedAwaitingSettlement {
            return Err(ModelError::InvalidTransition);
        }
        let mut candidate = self.clone();
        candidate.reservations.remove(id);
        candidate.bump_revision()?;
        *self = candidate;
        Ok(true)
    }
    /// Release only after the actor verifies a durable abort/decline decision.
    /// This method deliberately supplies no timer or unilateral-expiry policy.
    pub fn release_aborted_reservation(&mut self, id: &str) -> Result<bool> {
        let reservation = self
            .reservations
            .get(id)
            .ok_or(ModelError::UnknownReservation)?;
        if reservation.phase == ReservationPhase::AppliedAwaitingSettlement {
            return Err(ModelError::InvalidTransition);
        }
        let mut candidate = self.clone();
        candidate.reservations.remove(id);
        candidate.bump_revision()?;
        *self = candidate;
        Ok(true)
    }
    fn bump_revision(&mut self) -> Result<()> {
        self.local_revision = self
            .local_revision
            .checked_add(1)
            .ok_or(ModelError::Overflow)?;
        validate_revision(self.local_revision)
    }
}

/// A shared checkpoint excludes local revisions, inbox state, secrets and intents.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct TrustlineCheckpoint {
    pub version: u16,
    pub channel_id: String,
    pub incarnation: u64,
    pub unit: String,
    pub owner: String,
    pub counterparty: String,
    pub balance: i64,
    pub own_preferences: Preferences,
    pub peer_preferences: Preferences,
    pub own_log: LogFrontier,
    pub peer_log: LogFrontier,
    pub previous_checkpoint_hash: Option<String>,
}
impl TrustlineCheckpoint {
    pub fn from_state(
        state: &TrustlineState,
        own_log: LogFrontier,
        peer_log: LogFrontier,
        previous: Option<String>,
    ) -> Result<Self> {
        state.validate()?;
        if !state.reservations.is_empty() {
            return Err(ModelError::ReservationConflict);
        }
        let checkpoint = Self {
            version: FORMAT_VERSION,
            channel_id: state.channel_id.clone(),
            incarnation: state.incarnation,
            unit: state.unit.clone(),
            owner: state.owner.clone(),
            counterparty: state.counterparty.clone(),
            balance: state.balance,
            own_preferences: state.own_preferences.clone(),
            peer_preferences: state.peer_preferences.clone(),
            own_log,
            peer_log,
            previous_checkpoint_hash: previous,
        };
        checkpoint.validate()?;
        Ok(checkpoint)
    }
    pub fn validate(&self) -> Result<()> {
        if self.version != FORMAT_VERSION
            || !bounded_id(&self.channel_id)
            || !bounded_id(&self.unit)
            || self.incarnation > MAX_EXACT_INTEGER
            || !bounded_amount(self.balance)
            || self.owner == self.counterparty
        {
            return Err(ModelError::Invalid("checkpoint"));
        }
        verifying_key(&self.owner)?;
        verifying_key(&self.counterparty)?;
        self.own_preferences.validate()?;
        self.peer_preferences.validate()?;
        self.own_log.validate()?;
        self.peer_log.validate()?;
        if let Some(previous) = &self.previous_checkpoint_hash {
            validate_hash(previous)?;
        }
        Ok(())
    }
    pub fn hash(&self) -> Result<String> {
        self.validate()?;
        Ok(digest(&encoded(CHECKPOINT_DOMAIN, self)?))
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct SignedCheckpoint {
    pub checkpoint: TrustlineCheckpoint,
    pub signatures: BTreeMap<String, String>,
}
impl SignedCheckpoint {
    pub fn acknowledge(&mut self, key: &SigningKey) -> Result<()> {
        self.checkpoint.validate()?;
        let author = agent_id(&key.verifying_key());
        if author != self.checkpoint.owner && author != self.checkpoint.counterparty {
            return Err(ModelError::WrongAuthor);
        }
        self.signatures.insert(
            author,
            URL_SAFE_NO_PAD.encode(
                key.sign(&encoded(CHECKPOINT_DOMAIN, &self.checkpoint)?)
                    .to_bytes(),
            ),
        );
        Ok(())
    }
    pub fn verify(&self) -> Result<()> {
        self.checkpoint.validate()?;
        if self.signatures.len() != 2 {
            return Err(ModelError::Invalid("checkpoint requires both signatures"));
        }
        let bytes = encoded(CHECKPOINT_DOMAIN, &self.checkpoint)?;
        for author in [&self.checkpoint.owner, &self.checkpoint.counterparty] {
            let signature = self
                .signatures
                .get(author)
                .ok_or(ModelError::InvalidSignature)?;
            verifying_key(author)?
                .verify_strict(&bytes, &signature_bytes(signature)?)
                .map_err(|_| ModelError::InvalidSignature)?;
        }
        Ok(())
    }
    /// A valid self-described checkpoint is insufficient for bootstrap: pin the
    /// expected channel and both identities from the accepted trustline first.
    pub fn verify_for(
        &self,
        channel_id: &str,
        incarnation: u64,
        owner: &str,
        counterparty: &str,
    ) -> Result<()> {
        if self.checkpoint.channel_id != channel_id
            || self.checkpoint.incarnation != incarnation
            || self.checkpoint.owner != owner
            || self.checkpoint.counterparty != counterparty
        {
            return Err(ModelError::WrongContext);
        }
        self.verify()
    }
}
