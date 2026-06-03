# Opaque model codes

调用方在 `model` 字段里只传**码**，不传厂商名、不传 Ollama 标签、不传端口号。  
每个码 = **接口类型 + 模型槽位**；PolarPrivate 在服务端解析成真实模型并转发。

**零兼容**：只认下表中的码。

---

## QCS 三位含义（云端 `000`–`111`）

从左到右：**Q**uality · **C**ontext · **S**peed（每位 `0` 或 `1`）。

---

## 云端对话 `POST /v1/chat/completions`

| 码 | QCS | 槽位含义 | 默认上游模型 | Binding |
|----|-----|----------|--------------|---------|
| `000` | 000 | 默认均衡 | `qwen3.5-plus` | `llm.aliyun.codingplan` |
| `001` | 001 | 快速 | `MiniMax-M3`（Token Plan 普通版；`POLARPRIVATE_MINIMAX_FAST_MODEL` 可覆盖） | `llm.minimax` |
| `010` | 010 | 长上下文 | `qwen3-max-2026-01-23` | `llm.aliyun.codingplan` |
| `100` | 100 | 高质量 | `GLM-5.1` | `llm.ctyun.codingplan` |
| `101` | 101 | 视觉（云端） | `qwen3.5-plus` | `llm.aliyun.codingplan` |
| `110` | 110 | 预留 | `GLM-5.1` | `llm.ctyun.codingplan` |
| `111` | 111 | 预留 | `GLM-5.1` | `llm.ctyun.codingplan` |

映射源码：`app/core/model_routing.py` → `CAPABILITY_CLOUD_MAP`。

---

## 本地对话 `POST /v1/chat/completions`

本地 Ollama **只有 3 个权重**，对应 **3 个 L 码**（`L` + 3-bit，但仅下列组合有效）：

| 码 | QCS | 槽位 | 默认 Ollama 模型 | 说明 |
|----|-----|------|------------------|------|
| **`L000`** | `000` | 8B 对话 | `qwen3:8b` | 千问 8B，默认本地对话 |
| **`L100`** | `100` | 32B 对话 | `qwen3:32b` | 千问 32B（**Q=1** 表示大模型） |
| **`L101`** | `101` | 8B VLM | `qwen3-vl:8b` | 视觉专用（**Q=1,S=1**，与纯文本槽区分） |

环境变量：`OLLAMA_MODEL_L000` / `L100` / `L101`。

其他 `L001`、`L010` 等 **一律 422**（未部署对应权重）。

映射源码：`app/core/local_model_routing.py` → `DEFAULT_OLLAMA_BY_L_CODE`。

---

## Cursor CLI 对话 `POST /v1/chat/completions`

通过本机已登录的 Cursor Agent CLI（`agent login`）转发，**无需** PolarPrivate binding / API key。

| 码 | CLI 模型 slug | 说明 |
|----|---------------|------|
| **`C000`** | `composer-2.5-fast` | Composer 2.5 Fast（opaque 码） |
| **`composer-2.5-fast`** | `composer-2.5-fast` | Composer 2.5 Fast（可读名，与 C000 同后端） |

两个名字均可调用，响应里的 `model` 字段回显你传入的名字。

环境变量：

- `CURSOR_AGENT_BIN` — CLI 路径（默认 `agent`）
- `CURSOR_AGENT_WORKSPACE` — 工作目录（默认 `/tmp/cursor-agent-smoke`，空目录）
- `CURSOR_AGENT_TIMEOUT` — 超时秒数（默认 `180`）
- `CURSOR_AGENT_HTTP_PROXY` / `CURSOR_AGENT_HTTPS_PROXY` — 传给 CLI 子进程的代理（macOS 会自动读取系统代理 127.0.0.1:7897 等）
- `CURSOR_MODEL_C000` — 覆盖 CLI `--model` slug

映射源码：`app/core/cursor_cli_routing.py`。

**网络**：若 CLI 出现 `Connection lost, reconnecting`，在 `~/.cursor/cli-config.json` 设置 `"network": { "useHttp1ForAgent": true }`。

**限制**：暂不支持 `stream: true`（CLI 代理仅非流式）。

---

## 本地嵌入 `POST /v1/embeddings`

| 码 | 默认 Ollama 模型 |
|----|------------------|
| **`E000`** | `qwen3-embedding:8b` |

环境变量：`OLLAMA_EMBED_MODEL_E000` 或 `OLLAMA_EMBED_MODEL`。

---

## 响应里的 `model` 字段

API 回显调用方传入的码（如 `L101`、`E000`），不回显上游/Ollama 真实模型名。
