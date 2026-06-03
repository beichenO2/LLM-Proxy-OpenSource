# PrivPortal 安全模型

## 首要原则：明文外发禁令

PolarPrivate 的安全设计围绕一个首要承诺：

> **Secret 明文永远不进入 Agent 可达边界。**

具体约束：

1. **强承诺** — 没有任何 API 端点将 Secret 明文作为 HTTP 响应体返回。`/api/secrets/{id}/reveal` 已永久删除，`/api/vault/service-session` 已永久删除，`service_tokens` 表已通过 alembic migration 011 删除。
2. **弱承诺** — Secret 明文仅在以下三类封闭路径中流动：
   - **A 类（反向代理）** — `/proxy/{service_name}/{path}` — Secret 在代理内部注入 auth header，明文不出现在请求或响应中。
   - **B 类（HMAC 签名）** — `/sign/{provider}/{action}` — Secret 在签名运算中使用，仅返回签名后的 header dict。
   - **D 类（受控信道）** — `/api/d-class/grant` — 唯一的明文授予路径，受 SHA256 白名单约束，仅限第三方 SDK 场景（如 tqsdk 期货）。Agent 进程 hash 不在白名单中。
3. **GUI 只写不可读** — 前端 SecretsPage 已移除所有 reveal/hide 交互，编辑时重新输入新明文。

## 核心安全约束

1. **Secret 不明文存储** — 所有 Secret 在 SQLite 中以 Fernet 密文形式存储。
2. **Secret 不出现在日志中** — structlog 处理器自动脱敏所有已注册的密钥子串。
3. **Secret 不暴露给 Agent 工作区** — Agent 通过代理访问 API，密钥在代理层注入，Agent 永远看不到明文。

## 加密体系

### 主密码派生 (KDF)

```
用户输入 Master Password
    │
    ▼
PBKDF2-HMAC-SHA256
    ├── iterations: 480,000
    ├── salt: 16 字节随机数 (os.urandom)
    └── output: 32 字节密钥 → base64 编码为 Fernet key
```

- **算法**: `cryptography.hazmat.primitives.kdf.pbkdf2.PBKDF2HMAC`
- **迭代次数**: 480,000（OWASP 2023 推荐的 SHA-256 最低标准）
- **Salt**: 每次创建数据库或更换密码时随机生成，存储在 `db_metadata.salt`

### Fernet 对称加密

所有 Secret 值使用 **Fernet** 加密（基于 AES-128-CBC + HMAC-SHA256）：

| 组件               | 说明                                              |
| ------------------ | ------------------------------------------------- |
| **Fernet**         | 单密钥加密/解密，提供认证加密（ciphertext tampering 可检测）|
| **MultiFernet**    | 多密钥容器，支持密钥轮换（用第一个密钥加密，用任一密钥解密）|
| **Sentinel**       | 固定明文 `PRIVPORTAL_V1_UNLOCK_SENTINEL` 的密文，用于验证密码正确性 |

### 密钥存储结构

`db_metadata` 表（单行，`id=1`）：

| 字段                  | 类型     | 说明                                     |
| --------------------- | -------- | ---------------------------------------- |
| `salt`                | BLOB     | PBKDF2 盐值                              |
| `sentinel_ciphertext` | TEXT     | Sentinel 明文的 Fernet 加密结果           |
| `schema_version`      | INTEGER  | Schema 版本号                             |
| `fernet_keys_json`    | TEXT     | JSON 数组，包含一个或多个 base64 Fernet key |

### 密码更换流程

```
验证旧密码 (解密 sentinel)
    │
    ▼
解密所有 Secret 行 → 暂存明文
    │
    ▼
生成新 salt + 新 Fernet key
    │
    ▼
更新 db_metadata (salt, sentinel, fernet_keys_json)
    │
    ▼
用新密钥重新加密所有 Secret
    │
    ▼
session.flush() 验证所有 DB 变更
    │
    ▼
切换内存中的 MultiFernet 为新密钥
    │
    ▼
清除旧密码的脱敏注册 → 注册新密码
```

安全保证：内存中的 MultiFernet 只在 `session.flush()` 成功后才替换。如果 DB 写入失败，session 回滚，下次 unlock 会从 DB 状态重新派生密钥。

## Vault 生命周期

### 状态机

```
                 create_new_database()
    [不存在] ──────────────────────────→ [已初始化/锁定]
                                              │
                                    unlock(password)
                                              │
                                              ▼
                                        [已解锁]
                                         │      │
                          change_master_password()  lock()
                                         │      │
                                         ▼      ▼
                                   [已解锁/新密钥] [锁定]
```

- **锁定状态**: `VaultService._unlocked = False`，所有加密/解密操作抛出 `RuntimeError("vault is locked")`。
- **解锁状态**: `VaultService._multi_fernet` 持有有效的 MultiFernet 实例。
- **主动锁定**: `lock()` 方法丢弃内存中的密钥材料，回到锁定状态。
- **进程级**: Vault 状态绑定到 FastAPI `app.state.vault`，进程重启后需要重新解锁。

### HTTP 访问控制

- `GET /api/vault/status` — 返回 `{"locked": true/false}`，无鉴权。
- `POST /api/vault/unlock` — 输入 master_password 解锁 Vault。
  - **暴力破解保护**: 连续 10 次失败后锁定 60 秒，返回 **HTTP 429 Too Many Requests**（错误码 `RATE_LIMITED`）。成功解锁后计数器和锁定时间均归零。计数器使用线程锁保护，为进程级内存状态。
- 需要解锁的端点通过 `require_unlocked_vault` 依赖保护，未解锁返回 **HTTP 423 Locked**:
  - Secret 创建/更新/reveal/rotate
  - 代理转发
  - Onboarding 导入 Demo 数据

## 日志脱敏

### 脱敏处理器

`logging_config.py` 实现两层脱敏：

#### 1. 注册密钥脱敏

```python
_REDACTION_SUBSTRINGS: set[str]  # 全局注册表
```

- 当 Vault 解锁时，`register_secrets_for_redaction([master_password])` 将密码注册。
- `redact_processor` 递归遍历 structlog 事件字典所有叶子节点（str、bytes、嵌套 dict/list/tuple），将匹配的子串替换为 `[REDACTED]`。bytes 值会尝试 UTF-8 解码后脱敏再编码回 bytes。
- 多个密钥按长度降序替换，避免短密钥是长密钥前缀时的部分泄露。

#### 2. API Key 模式匹配

```python
_SK_LIKE_PATTERN = re.compile(r"sk-[a-zA-Z0-9_-]{10,}")
```

- `sanitize_user_facing_string()` 在注册脱敏之外，额外匹配 OpenAI 风格的 `sk-*` API Key。
- 用于测试中心等面向用户的输出，确保即使密钥未注册也不会泄露。

### 日志不记录的内容

- **代理请求/响应体** — `_forward_streaming()` 注释标注 "no request/response body logging (D-70)"。
- **Secret 明文** — `SecretRevealOut` 的 docstring 标注 "never log this payload"。
- **上游响应内容** — 代理日志仅记录元数据（service_name、method、upstream_host），不记录 body。

## 网络安全

### 仅本地运行

- 后端监听 `127.0.0.1:12790`（默认）。
- CORS 仅允许 `http://127.0.0.1:5170` 和 `http://localhost:5170`。
- 无 TLS（本地 loopback 不需要）。
- 无外部访问端口暴露。

### 代理安全

- 代理路由 (`/proxy/{service_name}/{path}`) 通过 Binding 映射确定上游目标，不接受任意 URL。
- Secret 解密后的明文仅在 `proxy_request()` 函数作用域内存在，不写入日志或响应。
- 上游响应中的 `Authorization` header 被过滤，不回传给客户端。
- 如果 Secret 被禁用 (`enabled=false`)，代理返回 **HTTP 403**。
- **上游响应体脱敏** — `_sanitize_upstream_body()` 在返回上游错误响应前，将响应体中出现的明文 Secret 替换为 `[REDACTED]`，防止上游 echo 回 API Key。
- **异常信息脱敏** — `_sanitize_error_detail()` 从 httpx 异常消息中移除可能包含的 Secret 材料。

## 审计日志覆盖

所有安全相关操作通过 `append_audit_log()` 记录到 `audit_log` 表，支持事后审计和异常检测。

| Action                  | 触发时机           | Detail 内容           |
| ----------------------- | ------------------ | --------------------- |
| `vault.unlock`          | 成功解锁 Vault     | —                     |
| `vault.change_password` | 更改 Master Password | —                   |
| `project.create`        | 创建项目           | `name=<项目名>`       |
| `project.delete`        | 删除项目           | `name=<项目名>`       |
| `secret.create`         | 创建 Secret        | `key=<Secret key>`    |
| `secret.rotate`         | 轮换 Secret        | `key=<Secret key>`    |
| `secret.delete`         | 删除 Secret        | `key=<Secret key>`    |

> **注意**: detail 字段仅记录 key 名称，不记录 Secret 明文值。此约束由 `test_security_audit_log.py` 中的回归测试保护，确保审计日志永远不会泄露 secret 值或 master password。

## 数据保护层次

| 层次       | 保护机制                                         | 攻击场景                        |
| ---------- | ------------------------------------------------ | ------------------------------- |
| 磁盘       | Fernet 加密 Secret 值                            | 数据库文件被复制                |
| 内存       | 明文仅在加密/解密/代理转发时短暂存在             | 内存转储                        |
| 日志       | structlog 脱敏处理器 + sk-* 模式匹配             | 日志文件泄露                    |
| 网络       | 仅 localhost、CORS 限制                          | 远程访问尝试                    |
| API        | Vault 锁定状态保护加密端点                       | 未授权 API 调用                 |
| 代理       | 不记录请求/响应体、过滤 Authorization header     | 代理日志分析                    |
| 导出       | 模板渲染不解密 Secret（渲染为 `[secret_ref:...]`） | 导出文件包含密钥                |

## 已知限制

1. **单用户模型** — 浏览器 session cookie 认证，无多用户 RBAC。适用于个人本地使用。
2. **无自动锁定** — Vault 解锁后直到进程终止都保持解锁状态。
3. **Master Password 不存储** — 忘记密码无法恢复，只能重建数据库。
4. **SQLite 文件保护** — 依赖操作系统文件权限，PrivPortal 不加密整个数据库文件。
5. **无审计日志加密** — `audit_log` 表中的 `detail` 字段为明文（但不应包含 Secret 值）。
6. **Fernet Key 明文存储** — `db_metadata.fernet_keys_json` 中存储的 Fernet key 是明文 base64 编码。任何能读取 SQLite 文件的人可以直接解密所有 Secret。对于 v1 localhost-only 模型，SQLite 文件的访问权限即为信任边界。未来可加密此字段或改为 unlock 时重新派生。
