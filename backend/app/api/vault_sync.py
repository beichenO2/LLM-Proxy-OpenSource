"""Encrypted vault backup & restore for cross-device sync via git.

POST /api/vault/backup  — export all data as a single Fernet-encrypted JSON blob
POST /api/vault/restore — import from an encrypted backup, merging or replacing data
POST /api/vault/sync-push — backup + git commit + push
POST /api/vault/sync-pull — git pull + auto-restore

Supports two encryption modes:
  - "vault" (v2, default): encrypted with the vault's own Fernet key (derived from Master Password)
  - "backup_password" (v3): encrypted with an independent backup password — decouples backup
    security from the vault key lifecycle so old backups remain decryptable after password changes.
"""

from __future__ import annotations

import json
import os
import subprocess
from base64 import urlsafe_b64encode, urlsafe_b64decode
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_vault, require_unlocked_vault
from app.db.models import AuditLog, Binding, DbMetadata, Project, Secret, UserAccount
from app.services.audit import append_audit_log
from app.services.vault import PBKDF2_ITERATIONS, SALT_LENGTH_BYTES, VaultService

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SYNC_DIR = _PROJECT_ROOT / "sync"
_BACKUP_FILE = _SYNC_DIR / "vault-backup.json"

router = APIRouter(prefix="/vault", tags=["vault-sync"])


class BackupRequest(BaseModel):
    backup_password: str | None = Field(default=None, min_length=8)


class BackupResponse(BaseModel):
    version: int = 2
    encryption: str = "vault"  # "vault" | "backup_password"
    created_at: str
    salt: str  # base64-encoded: vault salt (v2) or backup-specific salt (v3)
    payload: str  # Fernet-encrypted JSON


class RestoreRequest(BaseModel):
    payload: str = Field(min_length=1)
    salt: str = Field(min_length=1)
    master_password: str | None = Field(default=None, min_length=8)
    backup_password: str | None = Field(default=None, min_length=8)
    strategy: Literal["merge", "replace"] = "merge"
    encryption: str | None = None  # hint; auto-detected from version if absent


class RestoreResponse(BaseModel):
    projects: int
    secrets: int
    bindings: int
    skipped: int


def _serialize_vault(session: Session, vault: VaultService) -> dict:
    """Serialize all vault data into a plain dict with secrets decrypted."""
    projects = list(session.scalars(select(Project)).all())
    secrets = list(session.scalars(select(Secret)).all())
    bindings = list(session.scalars(select(Binding)).all())
    user_accounts = list(session.scalars(select(UserAccount)).all())

    def dt(v: datetime | None) -> str | None:
        return v.isoformat() if v else None

    return {
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "created_at": dt(p.created_at),
                "updated_at": dt(p.updated_at),
            }
            for p in projects
        ],
        "secrets": [
            {
                "id": s.id,
                "project_id": s.project_id,
                "key": s.key,
                "plaintext": vault.decrypt_secret_value(s.value),
                "enabled": s.enabled,
                "base_url": s.base_url,
                "category": s.category,
                "rotated_at": dt(s.rotated_at),
                "created_at": dt(s.created_at),
                "updated_at": dt(s.updated_at),
            }
            for s in secrets
        ],
        "bindings": [
            {
                "id": b.id,
                "project_id": b.project_id,
                "service_name": b.service_name,
                "secret_ref_key": b.secret_ref_key,
                "auth_header": b.auth_header,
                "created_at": dt(b.created_at),
                "updated_at": dt(b.updated_at),
            }
            for b in bindings
        ],
        "user_accounts": [
            {
                "id": u.id,
                "username": u.username,
                "salt": urlsafe_b64encode(u.salt).decode("ascii"),
                "sentinel_ciphertext": u.sentinel_ciphertext,
                "role": u.role,
                "created_at": dt(u.created_at),
                "updated_at": dt(u.updated_at),
            }
            for u in user_accounts
        ],
    }


@router.post("/backup", response_model=BackupResponse)
def backup_vault(
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_admin_vault)],
    body: BackupRequest | None = None,
) -> BackupResponse:
    """Export entire vault as a Fernet-encrypted JSON payload.

    If ``backup_password`` is provided, the backup is encrypted with a
    separate key derived from that password (v3 format).  Otherwise the
    vault's own Fernet key is used (v2 format, backward compatible).
    """
    meta = session.scalar(select(DbMetadata).where(DbMetadata.id == 1))
    if meta is None:
        raise HTTPException(status_code=500, detail="Vault metadata missing")

    data = _serialize_vault(session, vault)
    plaintext_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    use_backup_pw = body and body.backup_password
    if use_backup_pw:
        backup_salt = os.urandom(SALT_LENGTH_BYTES)
        backup_key = VaultService._derive_fernet_key(body.backup_password, backup_salt)  # type: ignore[union-attr]
        backup_fernet = Fernet(backup_key)
        encrypted = backup_fernet.encrypt(plaintext_str.encode("utf-8")).decode("ascii")
        out_salt = urlsafe_b64encode(backup_salt).decode("ascii")
        version = 3
        encryption = "backup_password"
    else:
        encrypted = vault.encrypt_secret_value(plaintext_str)
        out_salt = urlsafe_b64encode(meta.salt).decode("ascii")
        version = 2
        encryption = "vault"

    append_audit_log(
        session,
        action="vault.backup",
        detail=f"encryption={encryption},projects={len(data['projects'])},secrets={len(data['secrets'])}",
    )

    return BackupResponse(
        version=version,
        encryption=encryption,
        salt=out_salt,
        payload=encrypted,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s)


@router.post("/restore", response_model=RestoreResponse)
def restore_vault(
    body: RestoreRequest,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_admin_vault)],
) -> RestoreResponse:
    """Import data from an encrypted backup.

    Supports two decryption modes:
      - backup_password provided → derive key from backup_password + salt
      - master_password provided → derive key from master_password + salt (v2 compat)
    At least one password must be provided.
    """
    decrypt_pw = body.backup_password or body.master_password
    if not decrypt_pw:
        raise HTTPException(
            status_code=422,
            detail="Provide either backup_password or master_password to decrypt the backup",
        )

    try:
        source_salt = urlsafe_b64decode(body.salt)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid salt encoding")

    source_key = VaultService._derive_fernet_key(decrypt_pw, source_salt)
    source_fernet = Fernet(source_key)
    try:
        decrypted = source_fernet.decrypt(body.payload.encode("ascii")).decode("utf-8")
    except InvalidToken:
        raise HTTPException(status_code=400, detail="Cannot decrypt backup — wrong password or corrupted payload")

    try:
        data = json.loads(decrypted)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Decrypted payload is not valid JSON")

    counts = {"projects": 0, "secrets": 0, "bindings": 0, "skipped": 0}

    if body.strategy == "replace":
        session.query(Binding).delete()
        session.query(Secret).delete()
        session.query(AuditLog).filter(AuditLog.project_id.isnot(None)).delete()
        session.query(Project).delete()
        session.flush()

    for p in data.get("projects", []):
        existing = session.get(Project, p["id"])
        if existing and body.strategy == "merge":
            counts["skipped"] += 1
            continue
        if not existing:
            row = Project(
                id=p["id"],
                name=p["name"],
                description=p.get("description"),
            )
            session.add(row)
            counts["projects"] += 1

    session.flush()

    for s in data.get("secrets", []):
        existing = session.get(Secret, s["id"])
        if existing and body.strategy == "merge":
            counts["skipped"] += 1
            continue
        if not existing:
            row = Secret(
                id=s["id"],
                project_id=s.get("project_id"),
                key=s["key"],
                value=vault.encrypt_secret_value(s["plaintext"]),
                enabled=s.get("enabled", True),
                base_url=s.get("base_url"),
                category=s.get("category"),
                rotated_at=_parse_dt(s.get("rotated_at")),
            )
            session.add(row)
            counts["secrets"] += 1

    session.flush()

    for b in data.get("bindings", []):
        existing = session.get(Binding, b["id"])
        if existing and body.strategy == "merge":
            counts["skipped"] += 1
            continue
        if not existing:
            row = Binding(
                id=b["id"],
                project_id=b.get("project_id"),
                service_name=b["service_name"],
                secret_ref_key=b["secret_ref_key"],
                auth_header=b.get("auth_header"),
            )
            session.add(row)
            counts["bindings"] += 1

    # Restore user accounts (without wrapped_fernet_keys — device-specific)
    for u in data.get("user_accounts", []):
        existing = session.scalar(
            select(UserAccount).where(UserAccount.username == u["username"])
        )
        if existing and body.strategy == "merge":
            counts["skipped"] += 1
            continue
        if not existing:
            try:
                user_salt = urlsafe_b64decode(u["salt"])
            except Exception:
                counts["skipped"] += 1
                continue
            row = UserAccount(
                id=u["id"],
                username=u["username"],
                salt=user_salt,
                sentinel_ciphertext=u["sentinel_ciphertext"],
                wrapped_fernet_keys=None,  # Must be re-initialized on this device
                role=u.get("role", "user"),
            )
            session.add(row)

    append_audit_log(
        session,
        action="vault.restore",
        detail=f"strategy={body.strategy},projects={counts['projects']},secrets={counts['secrets']},skipped={counts['skipped']}",
    )

    return RestoreResponse(**counts)


class SyncPushRequest(BaseModel):
    backup_password: str | None = Field(default=None, min_length=8)


class SyncPushResponse(BaseModel):
    backup_chars: int
    git_pushed: bool
    encryption: str  # "vault" | "backup_password"
    message: str


@router.post("/sync-push", response_model=SyncPushResponse)
def sync_push(
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_admin_vault)],
    body: SyncPushRequest | None = None,
) -> SyncPushResponse:
    """Backup vault, write to sync/vault-backup.json, commit and push to git."""
    meta = session.scalar(select(DbMetadata).where(DbMetadata.id == 1))
    if meta is None:
        raise HTTPException(status_code=500, detail="Vault metadata missing")

    data = _serialize_vault(session, vault)
    plaintext_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    use_backup_pw = body and body.backup_password
    if use_backup_pw:
        backup_salt = os.urandom(SALT_LENGTH_BYTES)
        backup_key = VaultService._derive_fernet_key(body.backup_password, backup_salt)  # type: ignore[union-attr]
        backup_fernet = Fernet(backup_key)
        encrypted = backup_fernet.encrypt(plaintext_str.encode("utf-8")).decode("ascii")
        out_salt = urlsafe_b64encode(backup_salt).decode("ascii")
        version = 3
        encryption = "backup_password"
    else:
        encrypted = vault.encrypt_secret_value(plaintext_str)
        out_salt = urlsafe_b64encode(meta.salt).decode("ascii")
        version = 2
        encryption = "vault"

    backup_obj = {
        "version": version,
        "encryption": encryption,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "salt": out_salt,
        "payload": encrypted,
    }

    _SYNC_DIR.mkdir(parents=True, exist_ok=True)
    _BACKUP_FILE.write_text(json.dumps(backup_obj, indent=2), encoding="utf-8")

    git_pushed = False
    git_msg = ""
    try:
        cwd = str(_PROJECT_ROOT)
        subprocess.run(["git", "add", "sync/vault-backup.json"], cwd=cwd, check=True, capture_output=True)

        diff = subprocess.run(["git", "diff", "--cached", "--quiet", "sync/vault-backup.json"], cwd=cwd, capture_output=True)
        if diff.returncode != 0:
            ts = datetime.now().strftime("%Y-%m-%d-%H%M")
            subprocess.run(
                ["git", "commit", "-m", f"chore: vault backup {ts}", "--no-verify"],
                cwd=cwd, check=True, capture_output=True,
            )
            subprocess.run(["git", "push", "origin", "HEAD"], cwd=cwd, check=True, capture_output=True, timeout=30)
            git_pushed = True
            git_msg = "备份已提交并推送到远程仓库。"
        else:
            git_msg = "备份内容无变化，跳过推送。"
    except subprocess.TimeoutExpired:
        git_msg = "git push 超时，备份文件已保存到本地。"
    except subprocess.CalledProcessError as exc:
        git_msg = f"git 操作失败: {exc.stderr.decode('utf-8', errors='replace')[:200] if exc.stderr else 'unknown'}"

    append_audit_log(session, action="vault.sync_push", detail=f"pushed={git_pushed}")

    return SyncPushResponse(
        backup_chars=len(encrypted),
        git_pushed=git_pushed,
        encryption=encryption,
        message=git_msg,
    )


class SyncPullRequest(BaseModel):
    master_password: str | None = Field(default=None, min_length=8)
    backup_password: str | None = Field(default=None, min_length=8)
    strategy: Literal["merge", "replace"] = "merge"


class SyncPullResponse(BaseModel):
    git_pulled: bool
    restored: bool
    message: str
    projects: int = 0
    secrets: int = 0
    bindings: int = 0
    skipped: int = 0


@router.post("/sync-pull", response_model=SyncPullResponse)
def sync_pull(
    body: SyncPullRequest,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_admin_vault)],
) -> SyncPullResponse:
    """Pull latest from git, then restore from sync/vault-backup.json."""
    cwd = str(_PROJECT_ROOT)
    git_pulled = False
    try:
        subprocess.run(["git", "pull", "--ff-only", "origin", "main"], cwd=cwd, check=True, capture_output=True, timeout=30)
        git_pulled = True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        try:
            subprocess.run(["git", "pull", "origin", "main"], cwd=cwd, check=True, capture_output=True, timeout=30)
            git_pulled = True
        except Exception:
            pass

    if not _BACKUP_FILE.exists():
        return SyncPullResponse(git_pulled=git_pulled, restored=False, message="未找到备份文件 sync/vault-backup.json。")

    try:
        backup = json.loads(_BACKUP_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return SyncPullResponse(git_pulled=git_pulled, restored=False, message=f"备份文件读取失败: {exc}")

    payload = backup.get("payload", "")
    salt_b64 = backup.get("salt", "")
    if not payload or not salt_b64:
        return SyncPullResponse(git_pulled=git_pulled, restored=False, message="备份文件格式不正确。")

    try:
        source_salt = urlsafe_b64decode(salt_b64)
    except Exception:
        return SyncPullResponse(git_pulled=git_pulled, restored=False, message="备份文件 salt 解码失败。")

    decrypt_pw = body.backup_password or body.master_password
    if not decrypt_pw:
        return SyncPullResponse(
            git_pulled=git_pulled, restored=False,
            message="需要提供 backup_password 或 master_password 来解密备份。",
        )

    source_key = VaultService._derive_fernet_key(decrypt_pw, source_salt)
    source_fernet = Fernet(source_key)
    try:
        decrypted = source_fernet.decrypt(payload.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return SyncPullResponse(git_pulled=git_pulled, restored=False, message="解密失败 — 密码不正确或备份已损坏。")

    restore_body = RestoreRequest(
        payload=payload,
        salt=salt_b64,
        master_password=body.master_password,
        backup_password=body.backup_password,
        strategy=body.strategy,
    )
    result = restore_vault(restore_body, session, vault)

    return SyncPullResponse(
        git_pulled=git_pulled,
        restored=True,
        message="同步恢复完成。",
        projects=result.projects,
        secrets=result.secrets,
        bindings=result.bindings,
        skipped=result.skipped,
    )


# ── PeerSync integration with SOTAgent ───────────────────────────────

_SOTAGENT_URL = os.environ.get("SOTAGENT_URL", "http://127.0.0.1:4800")


class PeerSyncStatusResponse(BaseModel):
    peer_reachable: bool
    peer_hostname: str | None = None
    last_heartbeat: str | None = None
    vault_in_sync: bool
    local_backup_exists: bool
    message: str


@router.get("/peer-status", response_model=PeerSyncStatusResponse)
def get_peer_sync_status() -> PeerSyncStatusResponse:
    """Check PeerSync status via SOTAgent."""
    import urllib.request
    import urllib.error

    local_backup = _BACKUP_FILE.exists()

    try:
        req = urllib.request.Request(f"{_SOTAGENT_URL}/api/peer/status", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            peer_data = json.loads(resp.read())
    except (urllib.error.URLError, OSError):
        return PeerSyncStatusResponse(
            peer_reachable=False,
            vault_in_sync=False,
            local_backup_exists=local_backup,
            message="SOTAgent 不可达，无法获取 PeerSync 状态",
        )

    peer = peer_data.get("peer", {})
    is_reachable = peer.get("reachable", False)
    hostname = peer.get("hostname")
    last_hb = peer.get("last_heartbeat")

    vault_synced = True
    if local_backup:
        cwd = str(_PROJECT_ROOT)
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD", "origin/main", "--", "sync/vault-backup.json"],
                cwd=cwd, capture_output=True, text=True, timeout=5,
            )
            vault_synced = not result.stdout.strip()
        except Exception:
            vault_synced = False

    return PeerSyncStatusResponse(
        peer_reachable=is_reachable,
        peer_hostname=hostname,
        last_heartbeat=last_hb,
        vault_in_sync=vault_synced,
        local_backup_exists=local_backup,
        message="PeerSync 正常" if is_reachable and vault_synced else "需要同步",
    )


@router.post("/peer-notify")
def notify_peer_of_backup(
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_admin_vault)],
) -> dict:
    """Notify SOTAgent peer that a new vault backup is available."""
    import urllib.request
    import urllib.error

    notify_payload = json.dumps({
        "project": "PolarPrivate",
        "event": "vault_backup_updated",
        "sync_file": "sync/vault-backup.json",
    }).encode()

    try:
        req = urllib.request.Request(
            f"{_SOTAGENT_URL}/api/peer/notify",
            data=notify_payload,
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return {"notified": True, "peer_response": json.loads(resp.read())}
    except (urllib.error.URLError, OSError) as e:
        return {"notified": False, "error": str(e)}
