//! Atomic-backed LedgerLoops protocol/storage foundation.
//!
//! A private actor decision and its outbound intent share one Resource save.
//! Public log projection is recoverable and idempotent, not a distributed transaction.

pub mod actor_store;
pub mod bilateral;
pub mod model;
pub mod postgres_store;
