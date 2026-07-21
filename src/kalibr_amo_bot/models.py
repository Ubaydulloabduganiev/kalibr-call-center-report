from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def uuid_str() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class KommoUser(Base, TimestampMixin):
    __tablename__ = "kommo_users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    email: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="ru", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    role_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    group_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    group_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    policy: Mapped[AccessPolicy | None] = relationship(back_populates="user", uselist=False)
    identity: Mapped[TelegramIdentity | None] = relationship(back_populates="user", uselist=False)


class AccessPolicy(Base, TimestampMixin):
    __tablename__ = "access_policies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    kommo_user_id: Mapped[int] = mapped_column(ForeignKey("kommo_users.id", ondelete="CASCADE"), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    access_level: Mapped[str] = mapped_column(String(30), default="blocked", nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="ru", nullable=False)
    managed_user_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    receive_scheduled_reports: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    user: Mapped[KommoUser] = relationship(back_populates="policy")


class TelegramIdentity(Base, TimestampMixin):
    __tablename__ = "telegram_identities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    kommo_user_id: Mapped[int] = mapped_column(ForeignKey("kommo_users.id", ondelete="CASCADE"), unique=True, nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user: Mapped[KommoUser] = relationship(back_populates="identity")


class LinkToken(Base, TimestampMixin):
    __tablename__ = "link_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    kommo_user_id: Mapped[int] = mapped_column(ForeignKey("kommo_users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AppConfig(Base, TimestampMixin):
    __tablename__ = "app_config"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[Any] = mapped_column(JSON, nullable=False)


class ReferenceItem(Base, TimestampMixin):
    __tablename__ = "reference_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    item_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    __table_args__ = (UniqueConstraint("item_type", "external_id", name="uq_reference_item"),)


class DiscoverySample(Base, TimestampMixin):
    __tablename__ = "discovery_samples"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    sample_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    __table_args__ = (UniqueConstraint("sample_type", "source_id", name="uq_discovery_sample"),)


class ContactSnapshot(Base, TimestampMixin):
    __tablename__ = "contact_snapshots"
    kommo_contact_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    responsible_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    kommo_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    kommo_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phone_hashes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class LeadSnapshot(Base, TimestampMixin):
    __tablename__ = "lead_snapshots"
    kommo_lead_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    responsible_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    pipeline_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    status_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    kommo_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    kommo_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    linked_contact_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class CallEvent(Base, TimestampMixin):
    __tablename__ = "call_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    responsible_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    contact_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    lead_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    target_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_category: Mapped[str] = mapped_column(String(30), default="no_result", nullable=False, index=True)
    result_raw: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_call_event_source"),
        Index("ix_call_event_user_period", "responsible_user_id", "event_at"),
    )


class SyncCursor(Base, TimestampMixin):
    __tablename__ = "sync_cursors"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(500), nullable=False)


class TelegramUpdate(Base):
    __tablename__ = "telegram_updates"
    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    processing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class WebhookEvent(Base, TimestampMixin):
    __tablename__ = "webhook_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeliveryLog(Base, TimestampMixin):
    __tablename__ = "delivery_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    kommo_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    report_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    period_key: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="claimed", nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("kommo_user_id", "report_kind", "period_key", name="uq_delivery"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    target: Mapped[str | None] = mapped_column(String(300), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
