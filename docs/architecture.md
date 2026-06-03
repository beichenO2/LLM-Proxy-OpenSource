# PrivPortal 系统架构

## 概览

PrivPortal 是一个**本地运行**的隐私代理与脱敏门户（Local Privacy Proxy & Sanitization Portal），为开发者提供集中管理文档类隐私信息（Identity）和运行时密钥（Secret）的能力。整个系统仅在 `localhost` 运行，不对外暴露。

## 技术栈

| 层        | 技术                                           | 版本要求         |
| --------- | ---------------------------------------------- | ---------------- |
| 后端运行时 | Python                                         | 3.12.x           |
| Web 框架   | FastAPI + Starlette                            | ≥0.135           |
| ASGI 服务器 | Uvicorn                                        | ≥0.44            |
| ORM        | SQLAlchemy 2.x (sync)                          | ≥2.0.49          |
| 数据库     | SQLite (WAL mode)                              | 3.x (Python 内置) |
| 数据库迁移 | Alembic                                        | ≥1.18            |
| 加密       | cryptography (Fernet / MultiFernet / PBKDF2)   | ≥46.0            |
| HTTP 客户端 | httpx (异步)                                   | ≥0.28            |
| 日志       | structlog                                      | ≥25.0            |
| 前端框架   | React + TypeScript                             | React 18.x       |
| 构建工具   | Vite                                           | ≥6.0             |
| 样式       | Tailwind CSS                                   | ≥3.4             |
| 状态管理   | TanStack React Query + Zustand                 | —                |
| 路由       | react-router-dom                               | ≥6.28            |

## 项目目录结构

```
PolarPrivate/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 应用工厂 + ASGI 入口
│   │   ├── cli.py               # Typer CLI (start / init-db / import-demo / test / smoke)
│   │   ├── core/
│   │   │   └── config.py        # pydantic-settings 配置 (PRIVPORTAL_* 环境变量)
│   │   ├── db/
│   │   │   ├── base.py          # SQLAlchemy declarative Base
│   │   │   ├── models.py        # ORM 模型 (DbMetadata, Project, Identity, Secret, Binding, AuditLog, AppSettings)
│   │   │   └── session.py       # 同步引擎和会话工厂
│   │   ├── api/                  # FastAPI 路由模块
│   │   │   ├── deps.py          # 依赖注入 (get_db, get_vault, require_unlocked_vault)
│   │   │   ├── vault_routes.py  # Vault 解锁 / 改密码
│   │   │   ├── onboarding.py    # 初始化引导
│   │   │   ├── projects.py      # 项目 CRUD
│   │   │   ├── identities.py   # Identity CRUD
│   │   │   ├── secrets.py       # Secret CRUD + reveal + rotate + 连通性测试
│   │   │   ├── bindings.py      # Binding CRUD
│   │   │   ├── dashboard.py     # 仪表盘汇总 + 审计日志
│   │   │   ├── render.py        # 模板渲染
│   │   │   ├── export.py        # 导出 (Markdown/HTML/TXT)
│   │   │   ├── proxy.py         # 反向代理 (httpx 转发)
│   │   │   ├── logs.py          # 内存日志查询
│   │   │   ├── settings.py      # 应用设置
│   │   │   ├── test_center.py   # 测试中心 (identity/api/binding 探针)
│   │   │   └── exceptions.py    # 统一 JSON 错误响应
│   │   ├── services/
│   │   │   ├── vault.py         # VaultService: 加密核心 (Fernet + PBKDF2)
│   │   │   ├── template_render.py # [[placeholder]] 模板引擎
│   │   │   ├── export_format.py # Markdown→HTML/TXT 转换
│   │   │   ├── audit.py         # 审计日志追加
│   │   │   ├── log_buffer.py    # 线程安全环形日志缓冲区
│   │   │   ├── db_bootstrap.py  # Alembic 迁移运行器
│   │   │   └── demo_seed.py     # Demo 数据种子
│   │   └── logging_config.py    # structlog 配置 + 密钥脱敏处理器
│   ├── tests/                    # pytest 测试套件 (35+ 测试模块)
│   ├── alembic/                  # 数据库迁移脚本
│   └── pyproject.toml            # Python 包配置
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # 路由定义 (React.lazy 代码分割)
│   │   ├── main.tsx             # React 入口
│   │   ├── lib/
│   │   │   ├── api.ts               # HTTP 客户端封装 (fetch → apiRequest)
│   │   │   ├── toast.ts             # 通知组件 (sonner 封装)
│   │   │   └── use-document-title.ts # 页面标题 Hook
│   │   ├── stores/
│   │   │   └── uiStore.ts       # Zustand UI 状态
│   │   ├── components/           # 布局与通用组件
│   │   │   ├── AppLayout.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   ├── TopBar.tsx
│   │   │   ├── UnlockModal.tsx
│   │   │   ├── OnboardingWizard.tsx
│   │   │   ├── ProjectSelect.tsx
│   │   │   ├── Modal.tsx          # 通用弹窗容器
│   │   │   ├── ConfirmDialog.tsx  # 删除确认对话框
│   │   │   ├── EmptyState.tsx     # 空状态提示组件
│   │   │   ├── Skeleton.tsx       # 加载骨架屏组件
│   │   │   ├── PageHeader.tsx     # 统一页面标题/描述/操作布局
│   │   │   └── CommandPalette.tsx # Cmd+K 快速导航面板
│   │   └── pages/                # 页面组件
│   │       ├── DashboardPage.tsx
│   │       ├── ProjectsPage.tsx
│   │       ├── IdentitiesPage.tsx
│   │       ├── SecretsPage.tsx
│   │       ├── BindingsPage.tsx
│   │       ├── TemplatePreviewPage.tsx
│   │       ├── ExportPage.tsx
│   │       ├── TestCenterPage.tsx
│   │       ├── SettingsPage.tsx
│   │       ├── LogsPage.tsx
│   │       └── NotFoundPage.tsx   # 404 页面
│   ├── package.json
│   └── vite.config.ts
└── docs/                         # 项目文档
```

## 核心架构分层

### 1. 应用入口层

**`app/main.py`** — FastAPI 应用工厂 `create_app()`:

- 通过 `lifespan` 上下文管理器在启动时配置 structlog。
- 将 `VaultService` 实例挂载到 `app.state.vault`（进程级单例）。
- 注册统一异常处理器。
- 配置 CORS 中间件，仅允许 `localhost:5170`（Vite 开发服务器）。
- 按前缀注册所有 API 路由（`/api/*`）和代理路由（`/proxy/*`）。

**`app/cli.py`** — Typer CLI，提供以下子命令:

| 命令           | 功能                                      |
| -------------- | ----------------------------------------- |
| `start`        | 启动 Uvicorn 服务器                       |
| `init-db`      | 运行 Alembic 迁移到 head                  |
| `import-demo`  | 初始化 Vault + 导入 Demo 数据             |
| `test`         | 运行 pytest                               |
| `smoke`        | 运行端到端冒烟测试                        |

### 2. 数据层

**数据库**: SQLite 单文件 (`privportal.db`)，同步引擎 + `sessionmaker`。使用 `check_same_thread=False` 支持 FastAPI 多线程访问。

**ORM 模型** (`app/db/models.py`):

| 模型         | 表名          | 说明                                                |
| ------------ | ------------- | --------------------------------------------------- |
| `DbMetadata` | `db_metadata` | 单行：salt、sentinel 密文、schema 版本、Fernet 密钥 |
| `AppSettings`| `app_settings`| 单行：API 端口、JSON 偏好设置                       |
| `Project`    | `projects`    | 顶层项目容器                                        |
| `Identity`   | `identities`  | 点号分隔键 + 明文值（非密钥 PII）                   |
| `Secret`     | `secrets`     | 点号分隔键 + Fernet 密文值                          |
| `Binding`    | `bindings`    | 服务名 → Secret 引用键的映射                        |
| `AuditLog`   | `audit_log`   | 追加写审计日志                                      |

**关系**: `Project` 与 `Identity`、`Secret`、`Binding`、`AuditLog` 为一对多关系，外键 `CASCADE` 或 `SET NULL` 删除。

### 3. 加密层

**`app/services/vault.py`** — `VaultService` 是整个系统的加密中枢:

```
Master Password
    │
    ▼
PBKDF2-HMAC-SHA256 (480,000 iterations) + random 16-byte salt
    │
    ▼
32-byte Fernet key (base64-encoded)
    │
    ▼
MultiFernet (支持密钥轮换)
    │
    ├── encrypt_secret_value(plaintext) → ciphertext
    └── decrypt_secret_value(ciphertext) → plaintext
```

- **初始化**: `create_new_database()` 生成随机 salt，派生 Fernet 密钥，用该密钥加密 sentinel 明文 `PRIVPORTAL_V1_UNLOCK_SENTINEL`。
- **解锁**: `unlock()` 用输入的密码 + 存储的 salt 重新派生密钥，尝试解密 sentinel；成功则构建 MultiFernet 并标记为 unlocked。
- **密码更换**: `change_master_password()` 生成新 salt + 新密钥，重新加密所有 Secret 行。

### 4. API 层

所有 API 路由挂载在 `/api` 前缀下，代理路由在 `/proxy` 下。

**依赖注入** (`app/api/deps.py`):

- `get_db()` — 同步 SQLAlchemy Session，自动 commit/rollback/close。
- `get_vault()` — 从 `app.state.vault` 获取 VaultService。
- `require_unlocked_vault()` — 检查 Vault 是否已解锁，未解锁返回 HTTP 423。

### 5. 反向代理层

**`app/api/proxy.py`** — `{method} /proxy/{service_name}/{path:path}`（支持所有 HTTP 方法）:

```
客户端请求 → PrivPortal 代理
    │
    ├── 1. 按 service_name 查找 Binding
    ├── 2. 通过 Binding.secret_ref_key 查找 Secret
    ├── 3. Vault 解密 Secret 获取明文 API Key
    ├── 4. 注入 Authorization header（或自定义 auth_header）
    ├── 5. httpx.AsyncClient 转发到 Secret.base_url + path
    └── 6. 流式（SSE stream=true）或标准响应返回客户端
```

关键安全特性：明文 API Key 仅在内存中短暂存在，不记录到日志。

### 6. 模板渲染与导出层

**`app/services/template_render.py`** — 正则替换 `[[placeholder]]`:

- `[[identity.xxx]]` → 从 DB 读取 Identity 明文值替换
- `[[binding.xxx]]` → 渲染为 `[secret_ref:...]` 标记（不解密）
- `[[secret_ref.xxx]]` → 直接渲染为 `[secret_ref:...]`

**`app/api/export.py`** — 支持三种导出格式:

- **Markdown**: 渲染后的原始文本
- **HTML**: Markdown → HTML（via `markdown-it-py`）+ 最小 HTML5 文档包装
- **TXT**: 去除 Markdown 标记的纯文本

### 7. 日志层

**`app/logging_config.py`** — structlog + stdlib 配置:

- `redact_processor` — 递归遍历日志事件字典，将注册的密钥子串替换为 `[REDACTED]`。
- `_SK_LIKE_PATTERN` — 额外匹配 `sk-*` 形式的 API Key 并脱敏。
- `_buffer_log_processor` — 将脱敏后的日志追加到内存环形缓冲区。

**`app/services/log_buffer.py`** — 线程安全的 1000 条环形缓冲区，前端通过 `GET /api/logs` 查询。

### 8. 前端层

React SPA 通过 Vite 开发服务器在 `localhost:5170` 运行。

**路由结构**:

| 路径             | 页面组件             | 功能           |
| ---------------- | -------------------- | -------------- |
| `/`              | DashboardPage        | 仪表盘         |
| `/projects`      | ProjectsPage         | 项目管理       |
| `/identities`    | IdentitiesPage       | Identity 管理  |
| `/secrets`       | SecretsPage          | Secret 管理    |
| `/bindings`      | BindingsPage         | Binding 管理   |
| `/template`      | TemplatePreviewPage  | 模板预览       |
| `/export`        | ExportPage           | 导出           |
| `/test-center`   | TestCenterPage       | 测试中心       |
| `/settings`      | SettingsPage         | 设置           |
| `/logs`          | LogsPage             | 日志查看       |
| `*`              | NotFoundPage         | 404 页面       |

所有页面组件通过 `React.lazy()` 懒加载并包裹在 `<Suspense>` 中，实现路由级代码分割。

**状态管理**:

- **TanStack React Query** — 管理所有 API 调用的服务器状态（缓存、失效、乐观更新）。
- **Zustand** — 管理 UI 偏好状态（`activeProjectId`、`sidebarCollapsed`），通过 `localStorage`（key: `privportal:ui`）持久化。注意：仅持久化非敏感的 UI 偏好，不存储任何密钥材料。

## 数据流

### 写入 Secret 的流程

```
用户在 GUI 输入明文 API Key
    │
    ▼
POST /api/secrets { key: "secret.openai.default", value: "sk-..." }
    │
    ▼
require_unlocked_vault() 检查 Vault 状态
    │
    ▼
vault.encrypt_secret_value("sk-...") → Fernet 加密
    │
    ▼
INSERT INTO secrets (value = <ciphertext>)
    │
    ▼
返回 SecretOut (不含 value 字段)
```

### 代理转发的流程

```
AI Agent 发送请求到 /proxy/llm.openai/v1/chat/completions
    │
    ▼
查找 Binding(service_name="llm.openai") → secret_ref_key
    │
    ▼
查找 Secret(key=secret_ref_key) → 解密获得 API Key
    │
    ▼
注入 Authorization: Bearer <key> 到请求头
    │
    ▼
httpx.AsyncClient → https://api.openai.com/v1/chat/completions
    │
    ▼
响应流式返回客户端（如果 stream=true，使用 StreamingResponse）
```

## 配置

所有后端配置通过 `PRIVPORTAL_*` 前缀的环境变量控制：

| 变量                      | 默认值                     | 说明            |
| ------------------------- | -------------------------- | --------------- |
| `PRIVPORTAL_API_HOST`     | `127.0.0.1`                | 监听地址        |
| `PRIVPORTAL_API_PORT`     | `12790`                    | 监听端口        |
| `PRIVPORTAL_DATABASE_URL` | `sqlite:///./privportal.db`| 数据库连接字符串 |

前端通过 `VITE_API_BASE` 环境变量指向后端（默认 `http://127.0.0.1:12790`）。
