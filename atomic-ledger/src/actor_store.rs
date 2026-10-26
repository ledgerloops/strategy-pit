//! Durable actor state and recoverable publication using real Atomic Resources.
//!
//! This first-party adapter exercises Db compatibility paths currently documented
//! as internal; it does not emulate SQL on top of resource properties. Its node
//! must have one fenced authoritative writer (the PostgreSQL backend holds a lease).

use atomic_lib::{runtime::AtomicNode, urls, Resource, Storelike, Subject, Value};
use serde::{de::DeserializeOwned, Deserialize, Serialize};
use serde_json::Value as Json;
use std::{
    collections::BTreeMap,
    sync::{Arc, LazyLock, Mutex as SyncMutex, Weak},
};
use tokio::sync::Mutex;

use crate::model::{verifying_key, LogCursor, SignedEnvelope};

pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;
pub const ACTOR_STATE: &str = "https://ledgerloops.com/atomic/v1/actorState";
pub const LOG_MESSAGES: &str = "https://ledgerloops.com/atomic/v1/messages";
pub const ACTOR_CLASS: &str = "https://ledgerloops.com/atomic/v1/Actor";
pub const LOG_CLASS: &str = "https://ledgerloops.com/atomic/v1/MessageLog";

/// Install this version's local ontology without fetching or overwriting an
/// existing definition. Publishing its public vocabulary is a deployment step.
pub async fn install_model(node: &AtomicNode) -> Result<()> {
    for (subject, class, property, value) in [
        (
            ACTOR_STATE,
            urls::PROPERTY,
            urls::DATATYPE_PROP,
            Value::AtomicUrl(urls::JSON.into()),
        ),
        (
            LOG_MESSAGES,
            urls::PROPERTY,
            urls::DATATYPE_PROP,
            Value::AtomicUrl(urls::JSON.into()),
        ),
        (
            ACTOR_CLASS,
            urls::CLASS,
            urls::REQUIRES,
            Value::ResourceArray(vec![ACTOR_STATE.into()]),
        ),
        (
            LOG_CLASS,
            urls::CLASS,
            urls::REQUIRES,
            Value::ResourceArray(vec![LOG_MESSAGES.into()]),
        ),
    ] {
        if let Ok(existing) = node.db().get_resource_shallow(&subject.into()) {
            if serde_json::to_value(existing.get(property)?)? != serde_json::to_value(&value)?
                || existing.get_main_class()? != class
            {
                return Err("Existing LedgerLoops ontology conflicts with version 1".into());
            }
            continue;
        }
        let mut definition = Resource::new(subject.into());
        definition.set_class(class)?;
        definition.set_unsafe(property.into(), value)?;
        definition.set_unsafe(
            urls::SHORTNAME.into(),
            Value::String(subject.rsplit('/').next().unwrap().into()),
        )?;
        definition.set_unsafe(
            urls::DESCRIPTION.into(),
            Value::String("LedgerLoops Atomic version 1".into()),
        )?;
        node.db()
            .add_resource_opts(&definition, false, true, false)
            .await?;
    }
    node.db().kv.flush()?;
    Ok(())
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CommandReceipt {
    pub request_hash: String,
    pub result: Json,
    pub revision: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Publication {
    pub log_resource: String,
    pub message: SignedEnvelope,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ActorDocument<T> {
    pub version: u16,
    pub actor_id: String,
    pub revision: u64,
    pub state: T,
    pub processed_requests: BTreeMap<String, CommandReceipt>,
    pub outbound: BTreeMap<String, Publication>,
}

type ResourceLocks = Mutex<BTreeMap<String, Arc<Mutex<()>>>>;
static NODE_LOCKS: LazyLock<SyncMutex<BTreeMap<usize, Weak<ResourceLocks>>>> =
    LazyLock::new(|| SyncMutex::new(BTreeMap::new()));

fn canonical_subject(subject: &str) -> String {
    Subject::from(subject).pure_id()
}

/// All handles from one store share a resource lock. Backend writer fencing also
/// excludes another process: an in-process mutex alone would not prevent forks.
#[derive(Clone)]
pub struct AtomicActorStore {
    node: AtomicNode,
    locks: Arc<ResourceLocks>,
}

impl AtomicActorStore {
    pub fn new(node: AtomicNode) -> Self {
        // Cloned Atomic nodes share their KV Arc. Independently wrapping one
        // must share the same lock registry too, not just cloning this wrapper.
        let identity = Arc::as_ptr(&node.db().kv) as *const () as usize;
        let mut nodes = NODE_LOCKS.lock().expect("Actor lock registry poisoned");
        nodes.retain(|_, locks| locks.strong_count() > 0);
        let locks = nodes
            .get(&identity)
            .and_then(Weak::upgrade)
            .unwrap_or_else(|| {
                let locks = Arc::new(ResourceLocks::default());
                nodes.insert(identity, Arc::downgrade(&locks));
                locks
            });
        Self { node, locks }
    }

    pub fn node(&self) -> &AtomicNode {
        &self.node
    }

    async fn lock(&self, subject: &str) -> Arc<Mutex<()>> {
        self.locks
            .lock()
            .await
            .entry(canonical_subject(subject))
            .or_default()
            .clone()
    }

    async fn private_drive(&self) -> Result<String> {
        let drive = self.node.db().ensure_private_drive().await?;
        let resource = self.resource(&drive).await?;
        let agent = self
            .node
            .agent()
            .ok_or("Signing agent required")?
            .subject
            .to_string();
        for property in [urls::READ, urls::WRITE] {
            if resource.get(property)?.to_subjects(None)? != vec![agent.clone()] {
                return Err("Actor drive must be private to its signing agent".into());
            }
        }
        if resource.get(urls::PARENT).is_ok() {
            return Err("Actor drive must not inherit another parent's rights".into());
        }
        Ok(drive)
    }

    async fn private_resource(&self, subject: &str) -> Result<Resource> {
        let drive = self.private_drive().await?;
        let resource = self.resource(subject).await?;
        if resource.get(urls::PARENT)?.to_string() != drive {
            return Err("Actor resource must belong to its private drive".into());
        }
        let agent = self
            .node
            .agent()
            .ok_or("Signing agent required")?
            .subject
            .to_string();
        for property in [urls::READ, urls::WRITE] {
            if let Ok(value) = resource.get(property) {
                if value.to_subjects(None)? != vec![agent.clone()] {
                    return Err("Actor resource has non-private rights".into());
                }
            }
        }
        Ok(resource)
    }

    /// Store private state under the node agent's derived private drive. The
    /// service identity must remain stable; never change it per HTTP request.
    pub async fn create<T: Serialize>(&self, actor_id: &str, state: T) -> Result<String> {
        let drive = self.private_drive().await?;
        let document = ActorDocument {
            version: 1,
            actor_id: actor_id.to_owned(),
            revision: 0,
            state,
            processed_requests: BTreeMap::new(),
            outbound: BTreeMap::new(),
        };
        let subject = self
            .node
            .db()
            .create_resource(
                ACTOR_CLASS,
                &drive,
                actor_id,
                Some(vec![(
                    ACTOR_STATE,
                    Value::Json(serde_json::to_value(document)?),
                )]),
            )
            .await?;
        self.node.db().kv.flush()?;
        Ok(subject)
    }

    async fn resource(&self, subject: &str) -> Result<Resource> {
        Ok(self.node.db().get_resource(&subject.into()).await?)
    }

    async fn log_resource(&self, subject: &str) -> Result<Resource> {
        let resource = self.resource(subject).await?;
        if resource.get_main_class()? != LOG_CLASS || resource.get(ACTOR_STATE).is_ok() {
            return Err("Projection target must be a message log, not private actor state".into());
        }
        Ok(resource)
    }

    /// Reject malformed durable intents before acknowledging their decision.
    /// Actor-to-log ownership remains the typed service's responsibility: this
    /// internal adapter is not a public authorization boundary.
    async fn preflight(&self, outbound: &BTreeMap<String, Publication>) -> Result<()> {
        let mut logs: BTreeMap<String, Vec<&SignedEnvelope>> = BTreeMap::new();
        for publication in outbound.values() {
            logs.entry(canonical_subject(&publication.log_resource))
                .or_default()
                .push(&publication.message);
        }
        for (subject, mut messages) in logs {
            messages.sort_by_key(|message| message.envelope.sequence);
            let resource = self.log_resource(&subject).await?;
            let Value::Json(Json::Array(existing)) = resource.get(LOG_MESSAGES)? else {
                return Err("Message log is not a JSON array".into());
            };
            let first = &messages[0].envelope;
            let key = verifying_key(&first.author)?;
            let mut cursor = LogCursor::new(
                first.channel_id.clone(),
                first.incarnation,
                first.author.clone(),
                first.recipient.clone(),
            );
            for message in existing {
                cursor.accept(&serde_json::from_value(message.clone())?, &key)?;
            }
            for message in messages {
                cursor.accept(message, &key)?;
            }
        }
        Ok(())
    }

    fn document<T: DeserializeOwned>(resource: &Resource) -> Result<ActorDocument<T>> {
        match resource.get(ACTOR_STATE)? {
            Value::Json(value) => {
                let document: ActorDocument<T> = serde_json::from_value(value.clone())?;
                if document.version != 1 {
                    return Err("Unsupported actor document version".into());
                }
                Ok(document)
            }
            _ => Err("Actor state must be typed JSON".into()),
        }
    }

    pub async fn load<T: DeserializeOwned>(&self, subject: &str) -> Result<ActorDocument<T>> {
        Self::document(&self.private_resource(subject).await?)
    }

    async fn save<T: Serialize>(
        &self,
        resource: &mut Resource,
        document: &ActorDocument<T>,
    ) -> Result<()> {
        resource.set_unsafe(
            ACTOR_STATE.into(),
            Value::Json(serde_json::to_value(document)?),
        )?;
        // Private state is never queued for public sync. Its payload contains
        // both the decision and intent, so log-publication recovery needs no
        // multi-resource transaction or separate Atomic sync-outbox success.
        resource.save_locally(self.node.db()).await?;
        self.node.db().kv.flush()?;
        Ok(())
    }

    pub async fn apply<T, F>(
        &self,
        subject: &str,
        request_id: &str,
        request_hash: &str,
        expected_revision: Option<u64>,
        mutate: F,
    ) -> Result<CommandReceipt>
    where
        T: Serialize + DeserializeOwned,
        F: FnOnce(&mut T) -> Result<(Json, Vec<Publication>)>,
    {
        if request_id.is_empty() || request_hash.is_empty() {
            return Err("Stable request identity required".into());
        }
        let lock = self.lock(subject).await;
        let _guard = lock.lock().await;
        let mut resource = self.private_resource(subject).await?;
        let mut document: ActorDocument<T> = Self::document(&resource)?;
        if let Some(receipt) = document.processed_requests.get(request_id) {
            if receipt.request_hash != request_hash {
                return Err("Request ID reused with different content".into());
            }
            return Ok(receipt.clone());
        }
        if expected_revision.is_some_and(|revision| revision != document.revision) {
            return Err("Stale actor revision".into());
        }
        let (result, publications) = mutate(&mut document.state)?;
        for mut publication in publications {
            publication.log_resource = canonical_subject(&publication.log_resource);
            let id = publication.message.envelope.message_id.clone();
            if let Some(existing) = document.outbound.get(&id) {
                if serde_json::to_value(existing)? != serde_json::to_value(&publication)? {
                    return Err("Outbound message ID reused with different content".into());
                }
            }
            document.outbound.insert(id, publication);
        }
        self.preflight(&document.outbound).await?;
        document.revision = document
            .revision
            .checked_add(1)
            .ok_or("Actor revision exhausted")?;
        let receipt = CommandReceipt {
            request_hash: request_hash.to_owned(),
            result,
            revision: document.revision,
        };
        document
            .processed_requests
            .insert(request_id.to_owned(), receipt.clone());
        self.save(&mut resource, &document).await?;
        Ok(receipt)
    }

    /// Materialize local log Resources after a crash before projection, or
    /// between projection and cleanup. This does not acknowledge network
    /// delivery: a transport must reconcile these Resources separately.
    pub async fn project_pending<T: Serialize + DeserializeOwned>(
        &self,
        subject: &str,
    ) -> Result<usize> {
        let lock = self.lock(subject).await;
        let _guard = lock.lock().await;
        let mut actor = self.private_resource(subject).await?;
        let mut document: ActorDocument<T> = Self::document(&actor)?;
        let mut pending: Vec<_> = document
            .outbound
            .iter()
            .map(|(id, p)| (id.clone(), p.clone()))
            .collect();
        pending.sort_by(|(_, left), (_, right)| {
            (&left.log_resource, left.message.envelope.sequence)
                .cmp(&(&right.log_resource, right.message.envelope.sequence))
        });
        let mut published = 0;
        for (id, publication) in pending {
            if canonical_subject(&publication.log_resource) == canonical_subject(subject) {
                return Err("Private actor resource cannot be a public log".into());
            }
            // Check before taking another resource lock: invalid cross-actor
            // destinations must not form an actor-A -> actor-B lock cycle.
            self.log_resource(&publication.log_resource).await?;
            let log_lock = self.lock(&publication.log_resource).await;
            let _log_guard = log_lock.lock().await;
            let mut log = self.log_resource(&publication.log_resource).await?;
            let messages: Vec<SignedEnvelope> = match log.get(LOG_MESSAGES) {
                Ok(Value::Json(Json::Array(items))) => {
                    serde_json::from_value(Json::Array(items.clone()))?
                }
                _ => return Err("Message log is not a JSON array".into()),
            };
            let envelope = &publication.message.envelope;
            let key = verifying_key(&envelope.author)?;
            let mut cursor = LogCursor::new(
                envelope.channel_id.clone(),
                envelope.incarnation,
                envelope.author.clone(),
                envelope.recipient.clone(),
            );
            for message in &messages {
                cursor.accept(message, &key)?;
            }
            cursor.accept(&publication.message, &key)?;
            if let Some(existing) = messages.iter().find(|m| m.envelope.message_id == id) {
                if serde_json::to_value(existing)? != serde_json::to_value(&publication.message)? {
                    return Err("Published message conflicts with durable intent".into());
                }
            } else {
                log.push_list_item(LOG_MESSAGES, serde_json::to_value(&publication.message)?)?;
                log.save_locally(self.node.db()).await?;
                self.node.db().kv.flush()?;
            }
            document.outbound.remove(&id);
            self.save(&mut actor, &document).await?;
            published += 1;
        }
        Ok(published)
    }
}
