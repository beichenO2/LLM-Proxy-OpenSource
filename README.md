# LLM Proxy（开源版）

**本地 OpenAI 兼容 LLM 网关 + 密钥保险库 + 管理前端**

本仓库从 [PolarPrivate](https://github.com/polarisor) 提取 **LLM Proxy 核心能力**并开源：统一 `/v1/chat/completions` 入口、多上游 Binding 路由、加密 Secret 存储、React 管理界面。生态内 PolarUI、PolarClaw、AutoOffice 等组件通过 **LLM Proxy 方式**获取 LLM 服务，无需各自配置厂商 API Key。

> 前端 UI **直接复用 PolarPrivate 前端**（React + Tailwind）；后端与 PolarPrivate 同源，默认端口 **`127.0.0.1:12790`** 保持不变，现有客户端无需改端口。

---

## 为什么需要 LLM Proxy

| 问题 | LLM Proxy 的解法 |
|------|------------------|
| 每个组件各自存 API Key | Secret 加密入库，**密钥不出内存** |
| 多厂商模型名、路由各异 | 调用方只传 `model`，网关按 Binding **自动路由** |
| 429 / 上游故障 | Binding **fallback 链** + 多 Key 轮换 |
| Prompt 超长 | 自动估算 token 并截断（R8） |
| 本地 Ollama / Cursor CLI | `/v1` 网关统一纳管（L000/L100/L101、Cursor 等） |

**安全原则**：客户端（Agent、IDE、脚本）只连 `http://127.0.0.1:12790/v1`，`api_key` 可为任意占位符；真实密钥由代理在内存解密后注入上游 Authorization。

---

## 快速开始

### 1. 安装

```bash
# 后端（Python 3.12）
cd backend
pip install -e .          # 或: uv sync

# 前端
cd ../frontend
npm install

# TypeScript SDK（可选）
cd ../sdk
npm install && npm run build
```

### 2. 初始化并启动

```bash
# 终端 A — 后端
cd backend
privportal init-db        # 首次
privportal start          # → http://127.0.0.1:12790

# 终端 B — 前端（PolarPrivate 同款 GUI）
cd frontend
npm run dev               # → http://127.0.0.1:5170
```

或使用一键脚本：

```bash
bash scripts/dev.sh
```

### 3. 配置

1. 浏览器打开 `http://127.0.0.1:5170`
2. 按引导设置 **Master Password** 解锁 Vault
3. **Secrets** 页添加上游 API Key（如阿里云、MiniMax、讯飞 GLM 等）
4. **Bindings** 页创建 `service_name` → Secret 绑定
5. **测试中心** 验证连通性

完成后，任意 OpenAI 兼容客户端即可使用。

---

## 调用方式（给其他组件）

### 方式 A：OpenAI SDK（推荐）

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:12790/v1",
    api_key="local",   # 被忽略，代理注入真实密钥
)
resp = client.chat.completions.create(
    model="100",       # 能力码或 catalog 中的模型 id
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)
```

```typescript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://127.0.0.1:12790/v1",
  apiKey: "local",
});
const res = await client.chat.completions.create({
  model: "qwen3.5-plus",
  messages: [{ role: "user", content: "Hello" }],
});
```

### 方式 B：curl

```bash
curl http://127.0.0.1:12790/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"100","messages":[{"role":"user","content":"Hi"}]}'
```

### 方式 C：本仓库 TypeScript SDK

```typescript
import { chatCompletion, isHealthy, listModels } from "llm-proxy-sdk/llm";

if (!(await isHealthy())) throw new Error("请先解锁 Vault");

const models = await listModels();
const reply = await chatCompletion("100", [
  { role: "user", content: "计算 17×23+5，只回复数字" },
]);
```

环境变量：`POLARPRIVATE_URL` 或 `POLARPRIVATE_PORT`（默认 `12790`）。

### 方式 D：PolarUI / 生态内嵌客户端

PolarUI 内置 `llm-proxy` 客户端，默认连 `127.0.0.1:12790`：

```typescript
import { getLLMClient, chatCompletion } from "./sdk/llm-proxy";

const text = await chatCompletion("GLM-5.1", [
  { role: "user", content: "..." },
]);
// 内部映射 GLM-5.1 → 能力码 100，POST /v1/chat/completions
```

参考实现见 [`examples/polarui-client.ts`](./examples/polarui-client.ts)（与 PolarUI `src/sdk/llm-proxy.ts` 同源）。

### 方式 E：直连 `/proxy/{service_name}`

适用于非 OpenAI 形态的上游，或显式指定服务：

```bash
curl http://127.0.0.1:12790/proxy/llm.aliyun.codingplan/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.5-plus","messages":[...]}'
```

---

## 核心 API

| 端点 | 说明 |
|------|------|
| `GET /health` | `{ status, vault_unlocked }` — 组件启动前应检查 |
| `GET /v1/models` | OpenAI 兼容模型列表（需 Vault 已解锁） |
| `POST /v1/chat/completions` | **统一 LLM 网关**（支持 stream、tools） |
| `/proxy/{service}/{path}` | 通用反向代理（LLM 与非 LLM API） |
| `/api/*` | 管理 API（Secrets、Bindings、审计、测试中心等） |

完整 API 见 [`docs/api-reference.md`](./docs/api-reference.md)。

---

## 架构

```
┌─────────────────────────────────────────────────────────┐
│  消费方（PolarUI / PolarClaw / 脚本 / OpenAI SDK）        │
│  base_url = http://127.0.0.1:12790/v1                   │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│  LLM Proxy 后端 (FastAPI, :12790)                        │
│  ├─ /v1/chat/completions  ← v1_gateway（模型路由）       │
│  ├─ /proxy/*              ← proxy（Binding + 转发）    │
│  ├─ Vault / Secret / Binding（Fernet 加密 SQLite）       │
│  └─ Prompt 压缩 · Fallback · 用量统计 · 脱敏日志         │
└───────────────────────────┬─────────────────────────────┘
                            │ httpx（内存注入 Authorization）
┌───────────────────────────▼─────────────────────────────┐
│  上游：阿里云 / MiniMax / 讯飞 GLM / Ollama / Cursor CLI … │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  管理前端 (React, :5170) — 复用 PolarPrivate frontend    │
│  Secrets · Bindings · 测试中心 · 用量 · 审计             │
└─────────────────────────────────────────────────────────┘
```

**路由逻辑**（`backend/app/core/model_routing.py` + `model_catalog.py`）：

- 调用方传 `model="100"` 等能力码 → 网关解析为具体上游模型与 Binding
- 也支持传 catalog 中的明文 id（如 `qwen3.5-plus`）
- 本地 tier：`L000` / `L100` / `L101` → Ollama

---

## 目录结构

```
LLM Proxy/
├── backend/              # FastAPI 后端（privportal CLI）
│   ├── app/
│   │   ├── api/          # v1_gateway.py, proxy.py, secrets, bindings…
│   │   ├── core/         # 模型路由、配置
│   │   ├── db/           # SQLite ORM
│   │   └── services/     # Vault、脱敏、Cursor CLI 适配…
│   ├── alembic/
│   └── tests/
├── frontend/             # PolarPrivate 同款 React GUI
│   └── src/pages/        # Secrets, Bindings, TestCenter, Usage…
├── sdk/                  # TypeScript SDK（chatCompletion / listModels）
├── examples/             # PolarUI 客户端参考
├── docs/                 # 架构、安全、API、故障排查
└── scripts/dev.sh        # 本地双进程启动
```

---

## 与 PolarPrivate 的关系

| 项目 | 关系 |
|------|------|
| **PolarPrivate** | 完整私有门户（含 Identity、Sanitize、D 类等扩展模块） |
| **本仓库（LLM Proxy 开源版）** | 提取 **Vault + Proxy + /v1 网关 + 管理前端**，MIT 发布 |
| **兼容性** | 端口、API 路径、`privportal` CLI **与 PolarPrivate 一致**，可互换后端 |

从 Polarisor monorepo 同步更新：

```bash
rsync -a --exclude node_modules --exclude privportal.db --exclude logs \
  PolarPrivate/backend/app/  "LLM Proxy/backend/app/"
rsync -a --exclude node_modules --exclude dist \
  PolarPrivate/frontend/src/ "LLM Proxy/frontend/src/"
```

---

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `PRIVPORTAL_API_HOST` | `127.0.0.1` | 后端监听地址 |
| `PRIVPORTAL_API_PORT` | `12790` | 后端端口 |
| `PRIVPORTAL_DATABASE_URL` | `sqlite:///./privportal.db` | 数据库 |
| `POLARPRIVATE_URL` | — | SDK 覆盖 base URL |
| `POLARPRIVATE_PORT` | `12790` | SDK 覆盖端口 |
| `VITE_API_BASE` | `http://127.0.0.1:12790` | 前端 API 目标 |

---

## 组件集成检查清单

1. `GET /health` → `vault_unlocked: true`
2. `GET /v1/models` 能列出已 Binding 的模型
3. `POST /v1/chat/completions` 测试题返回非空
4. 组件内 **只配置 `base_url`，不配置厂商 API Key**
5. 需要 function calling 时，请求体带 `tools`（PolarUI Claude Code 工作流已验证）

---

## 测试

```bash
cd backend
privportal test
privportal smoke
```

---

## 文档

| 文档 | 内容 |
|------|------|
| [docs/architecture.md](./docs/architecture.md) | 分层与数据流 |
| [docs/security-model.md](./docs/security-model.md) | 加密、脱敏、网络安全 |
| [docs/api-reference.md](./docs/api-reference.md) | REST API 全集 |
| [docs/usage.md](./docs/usage.md) | 安装与使用场景 |
| [docs/gui-workflows.md](./docs/gui-workflows.md) | 前端各页操作说明 |
| [docs/troubleshooting.md](./docs/troubleshooting.md) | 常见问题 |

---

## 许可证

MIT — 见 [LICENSE](./LICENSE)。

管理前端与后端核心逻辑源自 PolarPrivate；上游 LLM 服务须遵守各厂商条款。
