# PrivPortal API 参考

所有 API 端点前缀为 `http://127.0.0.1:12790`（默认），请求/响应格式为 JSON。

## 目录

- [Health Check](#health-check)
- [Vault](#vault)
- [Onboarding](#onboarding)
- [Projects](#projects)
- [Identities](#identities)
- [Secrets](#secrets)
- [Bindings](#bindings)
- [Dashboard](#dashboard)
- [Audit Log](#audit-log)
- [Render](#render)
- [Export](#export)
- [Test Center](#test-center)
- [Settings](#settings)
- [Logs](#logs)
- [Proxy](#proxy)

---

## Health Check

### `GET /health`

健康检查端点。

**响应**: `200 OK`

```json
{ "status": "ok", "vault_unlocked": false }
```

| 字段              | 类型   | 说明                        |
| ----------------- | ------ | --------------------------- |
| `status`          | string | 始终为 `"ok"`               |
| `vault_unlocked`  | bool   | Vault 当前是否已解锁        |

---

## Vault

### `GET /api/vault/status`

返回 Vault 锁定状态。

**响应**: `200 OK`

```json
{ "locked": true }
```

### `POST /api/vault/unlock`

使用 Master Password 解锁 Vault。

**请求体**:

```json
{ "master_password": "your_password" }
```

**响应**:
- `200 OK` → `{"status": "unlocked"}`
- `401 Unauthorized` → `{"detail": "invalid master password", "code": "AUTH_FAILED"}`
- `429 Too Many Requests` → `{"detail": "Too many failed attempts. Try again in Xs.", "code": "RATE_LIMITED"}`（连续 10 次失败后触发 60 秒锁定）

### `POST /api/vault/change-password`

更换 Master Password。需要 Vault 已解锁。

**请求体**:

```json
{
  "current_password": "old_password",
  "new_password": "new_password_min_8_chars"
}
```

**响应**:
- `200 OK` → `{"status": "password_changed"}`
- `401 Unauthorized` → `{"detail": "invalid current password", "code": "AUTH_FAILED"}`
- `423 Locked` → Vault 未解锁

---

## Onboarding

### `GET /api/onboarding/status`

检查初始化状态。

**响应**: `200 OK`

```json
{
  "completed": false,
  "has_db": true,
  "has_vault": false
}
```

### `POST /api/onboarding/init-db`

运行 Alembic 迁移初始化数据库。

**响应**: `200 OK` → `{"ok": true}`

### `POST /api/onboarding/complete`

标记 Onboarding 完成。

**响应**: `200 OK` → `{"ok": true}`

### `POST /api/onboarding/import-demo`

导入 Demo 项目数据。需要 Vault 已解锁。

**响应**: `200 OK`

```json
{
  "project_id": "uuid",
  "identities": 3,
  "secrets": 2,
  "bindings": 2
}
```

---

## Projects

### `GET /api/projects`

列出所有项目。

**查询参数**:

| 参数     | 类型 | 默认值 | 说明                |
| -------- | ---- | ------ | ------------------- |
| `offset` | int  | 0      | 分页偏移            |
| `limit`  | int  | 50     | 每页数量 (0-200)    |

**响应**: `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Demo Project",
      "description": "...",
      "created_at": "2026-04-10T12:00:00Z",
      "updated_at": "2026-04-10T12:00:00Z"
    }
  ],
  "total": 1
}
```

### `POST /api/projects`

创建项目。

**请求体**:

```json
{
  "name": "My Project",
  "description": "Optional description"
}
```

**响应**: `201 Created` → ProjectOut 对象

### `GET /api/projects/{project_id}`

获取单个项目。

**响应**: `200 OK` → ProjectOut 对象 / `404`

### `PATCH /api/projects/{project_id}`

更新项目。

**请求体** (仅传需要更新的字段):

```json
{
  "name": "New Name",
  "description": "New description"
}
```

**校验**: `name` 不可设为 `null`（返回 422 `VALIDATION_ERROR`）

**响应**: `200 OK` → ProjectOut 对象

### `DELETE /api/projects/{project_id}`

删除项目（级联删除关联数据）。

**响应**: `204 No Content`

---

## Identities

### `GET /api/identities`

列出 Identity 条目。

**查询参数**:

| 参数         | 类型   | 默认值 | 说明                    |
| ------------ | ------ | ------ | ----------------------- |
| `offset`     | int    | 0      | 分页偏移                |
| `limit`      | int    | 50     | 每页数量 (0-200)        |
| `q`          | string | —      | 按 key 或 value 模糊搜索|
| `category`   | string | —      | 按分类精确筛选          |
| `project_id` | string | —      | 按项目筛选              |

**响应**: `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "key": "identity.student.name",
      "value": "张三",
      "project_id": "uuid | null",
      "category": "student | null",
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "total": 3
}
```

### `POST /api/identities`

创建 Identity。

**请求体**:

```json
{
  "key": "identity.student.name",
  "value": "张三",
  "project_id": "uuid | null",
  "category": "student"
}
```

**校验**: `key` 必须包含至少一个 `.`。

**响应**: `201 Created` → IdentityOut 对象

### `GET /api/identities/{identity_id}`

获取单个 Identity。

**响应**: `200 OK` → IdentityOut / `404`

### `PATCH /api/identities/{identity_id}`

更新 Identity（仅传需要更新的字段）。

**校验**: `key` 和 `value` 不可设为 `null`（返回 422 `VALIDATION_ERROR`）

**响应**: `200 OK` → IdentityOut

### `DELETE /api/identities/{identity_id}`

删除 Identity。

**响应**: `204 No Content`

---

## Secrets

### `GET /api/secrets`

列出 Secret 条目（不含密文值）。

**查询参数**:

| 参数         | 类型   | 默认值 | 说明             |
| ------------ | ------ | ------ | ---------------- |
| `offset`     | int    | 0      | 分页偏移         |
| `limit`      | int    | 50     | 每页数量 (0-200) |
| `q`          | string | —      | 按 key 模糊搜索  |
| `category`   | string | —      | 按分类筛选       |
| `project_id` | string | —      | 按项目筛选       |

**响应**: `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "key": "secret.openai.default",
      "enabled": true,
      "project_id": "uuid | null",
      "base_url": "https://api.openai.com/v1",
      "category": "openai",
      "rotated_at": "... | null",
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "total": 2
}
```

注意：响应不包含 `value` 字段（密文/明文都不暴露）。

### `POST /api/secrets`

创建 Secret。需要 Vault 已解锁。

**请求体**:

```json
{
  "key": "secret.openai.default",
  "value": "sk-xxxxxxxxxxxx",
  "project_id": "uuid | null",
  "enabled": true,
  "base_url": "https://api.openai.com/v1",
  "category": "openai"
}
```

`value` 以明文提交，后端自动 Fernet 加密后存储。

**校验**: `key` 必须包含至少一个 `.`。

**响应**: `201 Created` → SecretOut（不含 value）

### `GET /api/secrets/{secret_id}`

获取单个 Secret 元数据（不含 value）。

### `PATCH /api/secrets/{secret_id}`

更新 Secret。`value` 字段可选；如果提供，需要 Vault 已解锁。

**请求体**:

```json
{
  "key": "secret.openai.v2",
  "value": "new-key-value",
  "enabled": false,
  "base_url": "https://api.openai.com/v1",
  "category": "openai-v2",
  "project_id": "uuid"
}
```

**校验**: `key` 和 `value` 不可设为 `null`（返回 422 `VALIDATION_ERROR`）

### `POST /api/secrets/{secret_id}/reveal`

获取 Secret 明文值。需要 Vault 已解锁。

**响应**: `200 OK`

```json
{ "value": "sk-xxxxxxxxxxxx" }
```

此端点仅供 GUI 使用，返回值不应被记录到日志。

### `POST /api/secrets/{secret_id}/rotate`

轮换 Secret 值。需要 Vault 已解锁。

**请求体**:

```json
{ "value": "new-api-key-value" }
```

**响应**: `200 OK` → SecretOut（`rotated_at` 更新为当前时间）

### `DELETE /api/secrets/{secret_id}`

删除指定 Secret。

**响应**: `204 No Content`

---

### `POST /api/secrets/{secret_id}/test-connectivity`

测试 Secret 的 `base_url` 连通性。

**响应**: `200 OK`

```json
{
  "reachable": true,
  "status_code": 200,
  "latency_ms": 156.34,
  "error": null
}
```

---

## Bindings

### `GET /api/bindings`

列出 Binding 条目。

**查询参数**:

| 参数         | 类型   | 默认值 | 说明             |
| ------------ | ------ | ------ | ---------------- |
| `offset`     | int    | 0      | 分页偏移         |
| `limit`      | int    | 50     | 每页数量 (0-200) |
| `project_id` | string | —      | 按项目筛选       |

**响应**: `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "service_name": "llm.openai",
      "secret_ref_key": "secret.openai.default",
      "auth_header": null,
      "project_id": "uuid | null",
      "resolved": true,
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "total": 2
}
```

`resolved` 字段动态计算：引用的 Secret 存在且 `enabled=true` 时为 `true`。

### `POST /api/bindings`

创建 Binding。

**请求体**:

```json
{
  "service_name": "llm.openai",
  "secret_ref_key": "secret.openai.default",
  "project_id": "uuid | null",
  "auth_header": "Authorization"
}
```

**校验**:
- `secret_ref_key` 必须包含 `.`
- `auth_header` 如设置则不能为空字符串

**响应**: `201 Created` → BindingOut

### `GET /api/bindings/{binding_id}`

获取单个 Binding。

### `PATCH /api/bindings/{binding_id}`

更新 Binding 的部分字段（仅发送需要修改的字段）。

**校验**:
- `secret_ref_key` 不可设为 `null`（返回 422 `VALIDATION_ERROR`）
- `service_name` 不可设为 `null`（返回 422 `VALIDATION_ERROR`）
- 如修改 `service_name` 或 `project_id`，不得与同项目下现有 Binding 重名

**响应**: `200 OK` → BindingOut

### `DELETE /api/bindings/{binding_id}`

删除 Binding。

**响应**: `204 No Content`

---

## Dashboard

### `GET /api/dashboard/summary`

获取数据概览统计。

**查询参数**:

| 参数         | 类型   | 说明       |
| ------------ | ------ | ---------- |
| `project_id` | string | 按项目筛选 |

**响应**: `200 OK`

```json
{
  "identity_count": 3,
  "secret_count": 2,
  "binding_count": 2,
  "project_id": "uuid | null"
}
```

---

## Audit Log

### `GET /api/audit-log`

获取审计日志。

**查询参数**:

| 参数         | 类型   | 默认值 | 说明                |
| ------------ | ------ | ------ | ------------------- |
| `offset`     | int    | 0      | 跳过前 N 条 (≥0)    |
| `limit`      | int    | 50     | 返回条数 (1-200)    |
| `project_id` | string | —      | 按项目筛选          |

**响应**: `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "action": "vault.unlock",
      "detail": null,
      "project_id": null,
      "created_at": "2026-04-10T12:00:00Z"
    }
  ]
}
```

**已记录的 action 类型**:

| Action                  | 说明                |
| ----------------------- | ------------------- |
| `vault.unlock`          | 成功解锁 Vault      |
| `vault.change_password` | 更改 Master Password |
| `project.create`        | 创建项目            |
| `project.delete`        | 删除项目            |
| `secret.create`         | 创建 Secret         |
| `secret.rotate`         | 轮换 Secret         |
| `secret.delete`         | 删除 Secret         |

---

## Render

### `POST /api/render`

渲染模板，替换 `[[placeholder]]` 占位符。

**请求体**:

```json
{
  "template": "Hello [[identity.student.name]], your binding is [[binding.llm.openai]]",
  "project_id": "uuid | null"
}
```

**响应**: `200 OK`

```json
{
  "rendered": "Hello 张三, your binding is [secret_ref:secret.openai.default]",
  "warnings": [],
  "stats": {
    "resolved_identity": 1,
    "unresolved_identity": 0,
    "resolved_binding": 1,
    "unresolved_binding": 0,
    "secret_ref_rendered": 0,
    "malformed": 0
  }
}
```

---

## Export

### `POST /api/export`

渲染模板并导出为指定格式。

**请求体**:

```json
{
  "template": "# Report\nAuthor: [[identity.student.name]]",
  "format": "html",
  "project_id": "uuid | null"
}
```

`format` 可选值: `"markdown"`, `"html"`, `"txt"`

**响应**: 对应格式的文件内容。

| 格式       | Content-Type                  |
| ---------- | ----------------------------- |
| `markdown` | `text/markdown; charset=utf-8`|
| `html`     | `text/html; charset=utf-8`   |
| `txt`      | `text/plain; charset=utf-8`  |

---

## Test Center

### `POST /api/test-center/run`

运行指定类型的测试。

**请求体**:

```json
{
  "test_type": "identity_render",
  "project_id": "uuid | null"
}
```

`test_type` 可选值:
- `"identity_render"` — 测试 Identity 模板替换
- `"api_connectivity"` — 测试渲染和导出 API 路径
- `"binding_probe"` — 测试所有 Binding 关联的上游 URL 连通性

**响应**: `200 OK`

```json
{
  "results": [
    {
      "name": "identity_render",
      "status": "pass",
      "message": "identity 'identity.student.name' resolved",
      "duration_ms": 5
    }
  ]
}
```

`status` 可选值: `"pass"`, `"fail"`, `"skip"`

---

## Settings

### `GET /api/settings`

获取应用设置。

**响应**: `200 OK`

```json
{
  "api_port": 12790,
  "preferences": { "onboarding_completed": true }
}
```

### `PUT /api/settings`

更新应用设置。

**请求体**:

```json
{
  "api_port": 9090,
  "preferences": { "theme": "dark" }
}
```

`api_port` 范围: 1024-65535。端口更改在下次启动时生效。

**响应**: `200 OK` → SettingsGetResponse

---

## Logs

### `GET /api/logs`

查询内存日志缓冲区。

**查询参数**:

| 参数     | 类型   | 默认值 | 说明                          |
| -------- | ------ | ------ | ----------------------------- |
| `level`  | string | —      | 按级别筛选 (info/warning/error) |
| `source` | string | —      | 按来源模块筛选                |
| `q`      | string | —      | 消息内容全文搜索              |
| `limit`  | int    | 200    | 返回条数 (1-500)              |

**响应**: `200 OK`

```json
{
  "items": [
    {
      "timestamp": "2026-04-10T12:00:00Z",
      "level": "INFO",
      "source": "app.api.proxy",
      "message": "{\"event\": \"proxy_forward\", ...}"
    }
  ]
}
```

日志内容已经过脱敏处理（敏感信息替换为 `[REDACTED]`）。

---

## Proxy

### `{METHOD} /proxy/{service_name}/{path}`

反向代理端点。支持所有 HTTP 方法: GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS。

**路径参数**:

| 参数           | 说明                        |
| -------------- | --------------------------- |
| `service_name` | Binding 中注册的服务名称    |
| `path`         | 转发到上游的路径（可多级）  |

**查询参数**:

| 参数         | 类型   | 说明                              |
| ------------ | ------ | --------------------------------- |
| `project_id` | string | 指定使用哪个项目的 Binding/Secret |

**行为**:

1. 按 `service_name` + `project_id` 查找 Binding
2. 按 Binding 的 `secret_ref_key` 查找 Secret
3. 解密 Secret 获取 API Key
4. 注入认证头（默认 `Authorization: Bearer <key>`，可通过 Binding 的 `auth_header` 自定义）
5. 转发到 `Secret.base_url + "/" + path + "?" + query_string`
6. 如果请求体包含 `"stream": true`（JSON POST），使用流式转发
7. **R8: Prompt 超长自动截断** — 检测 messages 的 token 数，超过阈值（默认 120k，`PRIVPORTAL_MAX_TOKENS`）时保留 system + 最后 4 条消息
8. **R8: 扩展超时** — 非流式 300s / 流式 180s / 写入 30s
9. **R8: 上游错误结构化包装** — 所有 4xx/5xx 返回统一 JSON `{ok, error, upstream_status, suggestion}`
10. **R8: 自动重试** — 上游 500/502/503 时自动重试一次
11. 响应原样返回（过滤掉 `Authorization` header）

> **注意**: `path` 会直接拼接到 `Secret.base_url` 后面。如果 `base_url` 已包含 `/v1`（如 DashScope），请勿在 `path` 中重复 `/v1`。

**示例**:

```bash
# 通过代理调用 DashScope Chat Completions（base_url 含 /v1）
curl -X POST http://127.0.0.1:12790/proxy/llm.aliyun.codingplan/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-coder-plus",
    "messages": [{"role": "user", "content": "Hello"}]
  }'

# 流式响应
curl -X POST http://127.0.0.1:12790/proxy/llm.aliyun.codingplan/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-coder-plus",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true
  }'

# 通过天翼云息壤 codingPlan 调用 GLM-5.1（base_url: https://wishub-x6.ctyun.cn/coding/v1）
curl -X POST http://127.0.0.1:12790/proxy/llm.ctyun.codingplan/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "GLM-5.1",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

> **天翼云 codingPlan 限制**: 编码套餐额度仅在 AI 编程工具中生效，不可用于 API 调用形式的自动化脚本或自定义应用程序后端，违规可能导致停用或封号。

**错误响应**:
- `404` — Binding 未找到（返回 `available_bindings` 列表）
- `403` — Secret 已禁用
- `400` — Secret 缺少 `base_url`；或上游返回 token 超限提示
- `423` — Vault 未解锁
- `429` — 上游限流（返回 `Retry-After` 头和 `retry_after_seconds`）
- `502` — 上游服务不可达
- `504` — 上游超时（300s / 180s）

**R8 结构化错误格式**（代理转发场景）:

```json
{
  "ok": false,
  "error": "upstream error message",
  "upstream_status": 429,
  "upstream_code": "rate_limit_exceeded",
  "service": "llm.aliyun.codingplan",
  "suggestion": "Rate limited by upstream. Wait 60s and retry.",
  "retry_after_seconds": 60
}
```

**环境变量**:

| 变量                      | 默认值   | 说明                           |
| ------------------------ | -------- | ------------------------------ |
| `PRIVPORTAL_MAX_TOKENS`  | `120000` | Prompt 自动截断的 token 阈值   |
| `PRIVPORTAL_RETRY_AFTER` | `60`     | 429 无上游 Retry-After 时的默认等待秒数 |

---

## 通用错误格式

非代理 API 错误返回统一的 JSON 格式：

```json
{
  "detail": "human-readable error message",
  "code": "ERROR_CODE"
}
```
