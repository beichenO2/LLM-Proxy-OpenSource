# PolarPrivate Proxy — Prompt 职责边界

## Proxy 层应做

- **安全底线 Prompt**：不可变的安全约束，附加在所有 LLM 请求的 messages 最后
- **append_system_prompt 机制**：允许上层（PolarClaw、PolarCopilot）注入入口特化 Prompt
- **上下文压缩**：超长 Prompt 自动截断（R8）
- **超时处理**：拉长非流式超时到 300s（R8）
- **错误包装**：上游错误解析为结构化响应（R8）

## Proxy 层不应做

- **角色策略**：不定义 Agent 角色（"你是 XX 助手"）——由 PolarClaw/PolarCopilot 管理
- **能力边界**：不限制 Agent 能做什么——由上层调用方决定
- **交互风格**：不规定语气/格式/回复长度——由上层调用方通过 append_system_prompt 控制

## 注入顺序

```
原始 messages → 调用方 append_system_prompt → 安全底线 Prompt（最后，不可覆盖）
```
