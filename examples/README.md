# PolarUI 集成示例

本文件复制自 PolarUI `src/sdk/llm-proxy.ts`，展示生态组件如何通过 LLM Proxy 获取 LLM 服务。

**前提**：LLM Proxy 运行于 `http://127.0.0.1:12790`，Vault 已解锁，且已配置对应模型的 Binding。

在 PolarUI 中直接使用：

```typescript
import { getLLMClient, chatCompletion, isPrivPortalHealthy } from "../src/sdk/llm-proxy";

if (!(await isPrivPortalHealthy())) {
  throw new Error("请先启动 LLM Proxy 并解锁 Vault");
}

const reply = await chatCompletion("GLM-5.1", [
  { role: "user", content: "Hello" },
]);
```

也可改用本仓库 SDK：

```typescript
import { chatCompletion, isHealthy } from "llm-proxy-sdk/llm";
```

完整客户端实现见同目录 `polarui-client.ts`。
