# PrivPortal 故障排查

## 常见问题

### 启动类问题

#### Q: `privportal` 命令找不到

**症状**: `command not found: privportal`

**原因**: 后端包未安装到当前 Python 环境。

**解决**:

```bash
cd backend
pip install -e .
# 或
uv sync
```

确认安装后 `privportal` 可执行文件在 PATH 中。

---

#### Q: 启动时报端口占用

**症状**: `OSError: [Errno 48] Address already in use`

**原因**: 端口 12790（默认）已被其他进程占用。

**解决**:

```bash
# 查找占用端口的进程
lsof -i :12790

# 方法 1: 终止占用进程
kill <PID>

# 方法 2: 使用其他端口
PRIVPORTAL_API_PORT=9090 privportal start
```

---

#### Q: 前端连接不上后端

**症状**: 浏览器控制台显示 `Failed to fetch` 或 CORS 错误

**原因**:
1. 后端未启动
2. 后端监听地址/端口与前端配置不匹配
3. CORS 配置不包含前端地址

**解决**:

1. 确认后端已启动: `curl http://127.0.0.1:12790/health`
2. 如果后端使用非默认端口，前端需配置环境变量:

```bash
VITE_API_BASE=http://127.0.0.1:9090 npm run dev
```

3. 后端 CORS 默认允许 `localhost:5170` 和 `127.0.0.1:5170`。如果前端在其他端口运行，需修改 `backend/app/main.py` 中的 `allow_origins`。

---

### 数据库类问题

#### Q: Onboarding 向导初始化数据库失败

**症状**: 点击 Next 后显示 "Database was not initialized"

**原因**: Alembic 迁移失败，通常是 `alembic/` 目录或配置问题。

**解决**:

```bash
cd backend
privportal init-db
```

手动运行观察具体错误信息。常见原因：
- `alembic.ini` 中数据库 URL 配置错误
- 缺少 `alembic/versions/` 目录下的迁移文件
- 数据库文件权限问题

---

#### Q: 数据库文件损坏

**症状**: SQLite 操作抛出 `DatabaseError` 或 `OperationalError`

**解决**:

```bash
# 备份当前数据库
cp privportal.db privportal.db.bak

# 尝试 SQLite 修复
sqlite3 privportal.db ".clone repaired.db"
mv repaired.db privportal.db

# 如果无法修复，重建数据库（会丢失所有数据）
rm privportal.db
privportal init-db
```

---

### Vault / 加密类问题

#### Q: 忘记 Master Password

**症状**: 无法解锁 Vault

**严重程度**: 不可恢复

**解决**: Master Password 没有重置机制。唯一的选择是删除数据库并重新初始化：

```bash
cd backend
rm privportal.db
privportal init-db
```

所有已存储的 Secret 将丢失。Identity（明文数据）也会丢失。

**预防**: 将 Master Password 安全记录在密码管理器中。

---

#### Q: Vault 解锁返回 "invalid master password"

**症状**: HTTP 401 + `{"detail": "invalid master password", "code": "AUTH_FAILED"}`

**原因**:
1. 密码输入错误
2. 数据库的 `db_metadata` 行被意外修改

**解决**:
1. 仔细检查密码是否正确（注意大小写、空格）
2. 检查数据库是否指向正确文件（可能存在多个 `.db` 文件）

---

#### Q: 操作提示 "Vault is locked" (HTTP 423)

**症状**: 创建/修改/reveal Secret 或使用代理时返回 423

**原因**: Vault 未解锁。后端进程重启后需要重新解锁。

**解决**:
1. 通过 GUI 的 Unlock 弹窗输入 Master Password
2. 或通过 API 调用:

```bash
curl -X POST http://127.0.0.1:12790/api/vault/unlock \
  -H "Content-Type: application/json" \
  -d '{"master_password": "your_password"}'
```

---

### 代理类问题

#### Q: 代理返回 502 Bad Gateway

**症状**: `{"detail": "...", "code": "UPSTREAM_ERROR"}`

**原因**: 上游服务不可达。

**排查**:

1. 检查 Secret 的 `base_url` 是否正确
2. 使用 **Test connectivity** 功能验证连通性
3. 检查网络连接（VPN、防火墙等）
4. 查看 **Logs** 页面获取详细错误信息

---

#### Q: 代理返回 404 "Binding not found"

**症状**: `{"detail": "Binding not found", "code": "BINDING_NOT_FOUND"}`

**原因**:
1. 请求的 `service_name` 没有对应的 Binding
2. Binding 存在但属于不同的 `project_id`

**解决**:
1. 检查 Binding 列表确认 service_name 拼写
2. 确认 `project_id` 参数是否正确（或省略以使用全局 Binding）

```bash
# 带 project_id 的代理请求
curl http://127.0.0.1:12790/proxy/llm.openai/v1/models?project_id=xxx
```

---

#### Q: 代理返回 403 "Secret is disabled"

**症状**: `{"detail": "Secret is disabled", "code": "SECRET_DISABLED"}`

**原因**: Binding 引用的 Secret 已被禁用。

**解决**: 在 Secret Vault 页面找到对应 Secret，编辑并启用 (`enabled = true`)。

---

#### Q: 代理返回 400 "base_url is required"

**症状**: `{"detail": "base_url is required on the secret for proxy forwarding", "code": "VALIDATION_ERROR"}`

**原因**: Binding 引用的 Secret 没有设置 `base_url`。

**解决**: 编辑 Secret，填写 `base_url`（如 `https://api.openai.com/v1`）。

---

### API 数据类问题

#### Q: 创建 Identity/Secret 时提示 "duplicate key"

**症状**: HTTP 409 + `{"detail": "duplicate identity key", "code": "DUPLICATE_KEY"}`

**原因**: 同一 `project_id` 下已存在相同 `key` 的记录。

**解决**: 使用不同的 key，或先删除/编辑已有记录。

---

#### Q: Key 格式验证失败

**症状**: `"key must use dot notation (contain at least one '.')"`

**原因**: Identity、Secret、Binding 的 key 必须使用点号分隔的层级格式。

**正确格式**:
- `identity.student.name` (Identity)
- `secret.openai.default` (Secret)
- `service_name` (Binding 的 service_name 无此限制)
- `secret.xxx.yyy` (Binding 的 secret_ref_key 需要点号)

---

### 日志与调试

#### Q: 如何查看后端详细日志？

**方法 1**: 通过 GUI 的 **Logs** 页面（内存缓冲区，最多 1000 条）

**方法 2**: 后端启动时 structlog 输出到 stdout，直接查看终端

**方法 3**: 通过 API 查询

```bash
# 最新 50 条日志
curl "http://127.0.0.1:12790/api/logs?limit=50"

# 仅 ERROR 级别
curl "http://127.0.0.1:12790/api/logs?level=error"

# 按来源筛选
curl "http://127.0.0.1:12790/api/logs?source=app.api.proxy"

# 全文搜索
curl "http://127.0.0.1:12790/api/logs?q=upstream"
```

---

#### Q: 日志中出现 [REDACTED]

**这是预期行为**。PrivPortal 的 structlog 脱敏处理器会自动将以下内容替换为 `[REDACTED]`：

1. 已注册的密钥子串（Master Password）
2. 匹配 `sk-*` 模式的 API Key 形式字符串

如果需要调试时看到完整日志，**不建议**关闭脱敏——这可能导致密钥泄露到日志文件。

---

## 错误代码参考

| 错误代码           | HTTP 状态码 | 含义                             |
| ------------------ | ----------- | -------------------------------- |
| `AUTH_FAILED`      | 401         | Master Password 错误             |
| `RATE_LIMITED`     | 429         | 暴力破解锁定（连续10次失败后60秒）|
| `VAULT_LOCKED`     | 423         | Vault 未解锁                     |
| `ENTITY_NOT_FOUND` | 404         | 请求的资源不存在                 |
| `DUPLICATE_KEY`    | 409         | 同一作用域下 Key 重复            |
| `BINDING_NOT_FOUND`| 404         | 代理找不到匹配的 Binding         |
| `SECRET_DISABLED`  | 403         | Secret 已禁用                    |
| `UPSTREAM_ERROR`   | 502         | 上游服务不可达                   |
| `VALIDATION_ERROR` | 400/422     | 请求参数验证失败                 |
| `INTERNAL_ERROR`   | 500         | 未捕获的内部错误（不暴露异常详情）|
| `HTTP_ERROR`       | 各种        | 通用 HTTP 错误                   |

## 测试与验证

### 运行单元测试

```bash
cd backend
privportal test
```

### 运行特定测试

```bash
cd backend
privportal test -- -k test_vault
privportal test -- -k test_api_proxy
privportal test -- -k test_security
```

### 测试模块说明

| 测试文件                          | 覆盖范围                             |
| --------------------------------- | ------------------------------------ |
| `test_vault*.py`                  | VaultService 加密/解密/密码更换/lock |
| `test_api_secrets*.py`            | Secret CRUD / reveal / rotate / 去重 |
| `test_api_identities*.py`         | Identity CRUD / 搜索 / 去重          |
| `test_api_bindings*.py`           | Binding CRUD / resolved 状态         |
| `test_api_projects*.py`           | Project CRUD / 级联删除              |
| `test_api_proxy*.py`              | 代理转发 / 流式 / 错误处理 / 脱敏   |
| `test_security*.py`               | 日志脱敏 / 异常处理 / 代理脱敏 / 暴力破解 / 模板注入 / 审计日志泄露回归 |
| `test_log_buffer.py`              | 环形缓冲区 / 线程安全                |
| `test_template_render*.py`        | 模板占位符替换                       |
| `test_api_test_center*.py`        | 测试中心三种探针                     |
| `test_api_onboarding*.py`         | Onboarding 初始化 / Demo 导入        |
| `test_api_vault*.py`              | Vault API / 密码更换                 |
| `test_api_settings*.py`           | 应用设置 CRUD                        |
| `test_exceptions.py`              | 统一错误响应 / 异常处理器            |
| `test_demo_seed.py`               | Demo 数据种子 / 幂等性               |
| `test_smoke_e2e.py`               | 端到端冒烟测试                       |

### 运行冒烟测试

```bash
cd backend
privportal smoke
```

冒烟测试使用临时数据库，覆盖完整的用户旅程：Vault → Project → Identity → Secret → Binding → Render → Export → Test Center → Logs → Settings → Password Change → 错误场景。

### 测试基础设施

测试使用 `conftest.py` 中的 fixtures：
- `db_session` — 在 `tmp_path` 下创建 SQLite 文件，用 `create_all` 快速建表
- `client` — TestClient 覆盖 `get_db` 依赖，自动初始化和解锁 Vault（密码: `test-master-password`）
