"""ORM models for Phase 1 schema (D-06–D-09)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DbMetadata(Base):
    """Single-row metadata: per-database salt, sentinel ciphertext, schema version, optional MultiFernet keys."""

    __tablename__ = "db_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    salt: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sentinel_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    fernet_keys_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_unlock_token: Mapped[str | None] = mapped_column(Text, nullable=True)


class AppSettings(Base):
    """Single-row application settings: optional API listen port and JSON preferences (STNG-01, STNG-03)."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    api_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferences_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class Project(Base):
    """Top-level project container for secrets and bindings."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    secrets: Mapped[list[Secret]] = relationship(back_populates="project")
    bindings: Mapped[list[Binding]] = relationship(back_populates="project")
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="project")


class Secret(Base):
    """Secret entries: dot-notation key; value is base64 Fernet ciphertext only (D-08)."""

    __tablename__ = "secrets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    owner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    key: Mapped[str] = mapped_column(String(512), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[Project | None] = relationship(back_populates="secrets")
    binding_associations: Mapped[list[BindingSecret]] = relationship(
        back_populates="secret", cascade="all, delete-orphan"
    )


class BindingSecret(Base):
    """Many-to-many association between Binding and Secret for sign providers.

    Sign providers like weex require multiple secrets (api_key, api_secret, passphrase).
    This association table allows a single binding to reference multiple secrets.
    """

    __tablename__ = "binding_secrets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    binding_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bindings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    secret_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("secrets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    binding: Mapped["Binding"] = relationship(back_populates="secrets")
    secret: Mapped["Secret"] = relationship(back_populates="binding_associations")


class Binding(Base):
    """Maps a service name to a secret reference key within a project.

    Fallback chain support (R10): when the primary binding fails (429/5xx),
    automatically try fallback bindings in order. Supports multi-key rotation
    and cross-provider failover.

    For sign providers (weex, feishu-webhook, aliyun-sigv1), use the `secrets`
    relationship to reference multiple secrets. For LLM services, use `secret_ref_key`.
    """

    __tablename__ = "bindings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_ref_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)  # For sign provider bindings
    auth_header: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Fallback chain: JSON array of service_name strings, e.g. ["llm.coding-2", "llm.minimax"]
    fallback_chain: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Weight for load balancing (higher = more traffic)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    # Cooldown: if set, this binding is temporarily unavailable for fallback
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Consecutive failure count (reset on success)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[Project | None] = relationship(back_populates="bindings")
    secrets: Mapped[list[BindingSecret]] = relationship(
        back_populates="binding", cascade="all, delete-orphan"
    )


class UserAccount(Base):
    """Non-admin user accounts with key-wrapped access to the vault."""

    __tablename__ = "user_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    salt: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sentinel_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    wrapped_fernet_keys: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, server_default="user")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BrowserSession(Base):
    """Persistent browser sessions — survive server restarts, carry per-session role."""

    __tablename__ = "browser_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, server_default="admin")
    username: Mapped[str] = mapped_column(String(255), nullable=False, server_default="admin")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IdentityBinding(Base):
    """Cross-service user identity bindings: maps external service usernames to a local user_id."""

    __tablename__ = "identity_bindings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service: Mapped[str] = mapped_column(String(128), nullable=False)
    external_username: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("service", "external_username", name="uq_service_external_user"),
    )


class AuditLog(Base):
    """Append-only style audit trail entries."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    project: Mapped[Project | None] = relationship(back_populates="audit_logs")


class CustomPiiPattern(Base):
    """User-defined PII detection regex patterns, persisted across restarts."""

    __tablename__ = "custom_pii_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    pattern: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProxyUsage(Base):
    """Tracks proxy request counts per service/day for usage dashboards."""

    __tablename__ = "proxy_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("service_name", "project_id", "date", name="uq_proxy_usage_per_day"),
    )


class LLMServiceStatus(Base):
    """Tracks last call status for each LLM service (R11).

    Records the result of the most recent call to each LLM service,
    enabling status dashboards without additional API calls.
    """

    __tablename__ = "llm_service_status"

    service_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    last_call_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_call_status: Mapped[str | None] = mapped_column(String(32), nullable=True)  # "success" / "error"
    last_call_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_call_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
