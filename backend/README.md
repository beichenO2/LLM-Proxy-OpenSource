# PrivPortal Backend

Python 后端服务，提供 REST API、加密保险库和反向代理。

## 安装

```bash
# 推荐使用 uv
uv sync

# 或使用 pip
pip install -e .

# 开发依赖 (pytest, ruff)
uv sync --extra dev
```

## CLI 命令

安装后提供 `privportal` 命令行工具：

```bash
privportal init-db       # 运行 Alembic 迁移
privportal start         # 启动 API 服务器 (127.0.0.1:12790)
privportal import-demo   # 导入 Demo 数据
privportal test          # 运行 pytest
privportal smoke         # 运行端到端冒烟测试
```

## 配置

通过 `PRIVPORTAL_*` 前缀的环境变量或 `.env` 文件配置：

| 变量                      | 默认值                     | 说明            |
| ------------------------- | -------------------------- | --------------- |
| `PRIVPORTAL_API_HOST`     | `127.0.0.1`                | 监听地址        |
| `PRIVPORTAL_API_PORT`     | `12790`                    | 监听端口        |
| `PRIVPORTAL_DATABASE_URL` | `sqlite:///./privportal.db`| 数据库路径      |

## 目录结构

```
app/
├── main.py            # FastAPI 应用工厂
├── cli.py             # Typer CLI
├── core/config.py     # pydantic-settings 配置
├── db/                # ORM 模型、会话、迁移引导
├── api/               # REST API 路由 (vault, projects, identities, secrets, bindings, ...)
├── services/          # 业务逻辑 (VaultService, 模板渲染, 日志缓冲区)
└── logging_config.py  # structlog + 脱敏处理器
```

## 测试

```bash
# 全部测试
pytest -q

# 特定模块
pytest -k test_vault
pytest -k test_api_proxy

# 冒烟测试
pytest tests/test_smoke_e2e.py -v
```

## 依赖

核心依赖见 `pyproject.toml`：FastAPI、SQLAlchemy、cryptography、httpx、structlog、Alembic、Typer、Pydantic、uvicorn、markdown-it-py。
