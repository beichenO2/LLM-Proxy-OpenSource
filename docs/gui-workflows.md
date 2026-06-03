# PrivPortal GUI 操作流程

## 整体布局

PrivPortal 的 Web GUI 采用经典的**左侧边栏 + 顶栏 + 主内容区**布局：

- **侧边栏 (Sidebar)** — 默认宽度 224px，可通过左上角汉堡按钮或 `Cmd+B`（macOS）/ `Ctrl+B`（Windows/Linux）快捷键折叠为 56px 图标模式。折叠/展开带有平滑动画过渡，折叠状态通过 `localStorage` 持久化。导航项按功能分组显示：Dashboard/Projects、Vault（Identity/Secret/Bindings）、Tools（Template/Export/Test Center）、System（Settings/Logs）
- **顶栏 (TopBar)** — 显示项目选择器、Vault 状态徽章（带锁/解锁图标）和解锁按钮
- **主内容区** — 根据路由渲染对应页面
- **命令面板 (Command Palette)** — 通过 `Cmd+K`（macOS）/ `Ctrl+K`（Windows/Linux）打开，支持关键字搜索快速导航到任意页面，支持箭头键选择和 Enter 确认
- **模态层** — Onboarding 向导和 Vault 解锁弹窗覆盖在最上层

## 首次使用：Onboarding 向导

当用户首次打开 PrivPortal 时，Onboarding 向导会自动弹出（全屏遮罩，`z-index: 60`），引导完成初始化配置。

### 步骤流程

```
Welcome (欢迎页)
    │
    ├── [如果数据库不存在] → 自动调用 POST /api/onboarding/init-db 初始化
    │
    ▼
Set master password (设置主密码)
    │
    ├── 输入密码 + 确认密码
    ├── 调用 POST /api/vault/unlock 解锁
    │
    ▼
Demo data (演示数据)
    │
    ├── [Import demo data] → POST /api/onboarding/import-demo
    │    创建 Demo Project (3 个 Identity + 2 个 Secret + 2 个 Binding)
    ├── [Skip] → 跳过演示数据
    │
    ▼
You're ready (完成)
    │
    └── [Get started] → POST /api/onboarding/complete → 进入 Dashboard
```

### 关键细节

- 如果 `init-db` 失败，页面显示提示并建议用户手动运行 `privportal init-db`。
- 密码输入需两次确认一致才能继续。
- Demo 数据导入是幂等的，重复导入不会创建重复项目。
- 完成后 Onboarding 状态写入 `app_settings.preferences_json`（`onboarding_completed: true`）。

## Vault 解锁

每次后端进程重启后，Vault 处于锁定状态。当 Vault 锁定时，**UnlockModal** 弹窗（`z-index: 50`）覆盖整个界面：

1. 用户输入 Master Password
2. 前端调用 `POST /api/vault/unlock`
3. 解锁成功 → 弹窗消失，正常使用所有功能
4. 解锁失败 → 显示错误信息（"invalid master password"）

前端每 30 秒轮询 `GET /api/vault/status` 检查 Vault 状态，切换窗口焦点时也会刷新。

## Dashboard（仪表盘）

路径: `/`

### 功能

1. **数据概览卡片** — 三列布局显示当前项目（或全局）的统计计数：
   - Identity 数量
   - Secret 数量
   - Binding 数量

2. **最近活动** — 表格展示最新 10 条审计日志，包含：
   - 操作类型（如 `project.create`、`vault.unlock`）
   - 详情
   - 时间戳

3. **模块快速入口** — 网格卡片链接到所有子模块

## Projects（项目管理）

路径: `/projects`

### 操作

- **查看列表** — 分页显示所有项目（名称、描述、创建时间）
- **创建项目** — 弹窗表单输入项目名称和描述
- **编辑项目** — 修改名称和描述
- **删除项目** — 级联删除关联的 Identity、Secret、Binding

### 项目切换

顶栏的 **ProjectSelect** 组件允许切换当前活动项目。选择项目后，所有页面自动按 `project_id` 过滤数据。选择"Global"则显示不属于任何项目的数据。

## Identity Vault（身份信息管理）

路径: `/identities`

### 操作

- **查看列表** — 表格展示 Key（点号分隔）、Value（明文）、Category
- **搜索** — 按 Key 或 Value 模糊搜索
- **按类别筛选** — 按 Category 过滤
- **添加 Identity** — 弹窗表单：
  - Key（必填，必须包含 `.`，如 `identity.student.name`）
  - Value（必填）
  - Category（可选）
  - 所属项目
- **编辑 Identity** — 修改 Key、Value、Category、项目归属
- **删除 Identity** — 确认后删除

### 与 Secret 的区别

Identity 是**非密钥的隐私信息**（姓名、邮箱等），**明文存储**，可在模板渲染和导出时回填。Secret 是**运行时密钥**（API Key），**加密存储**，不会在导出中回填。

## Secret Vault（密钥管理）

路径: `/secrets`

### 列表视图

表格显示每个 Secret 的：
- **Key** — 点号分隔的标识符（如 `secret.openai.default`）
- **Enabled** — 是否启用（禁用的 Secret 不能通过代理使用）
- **Category** — 分类标签
- **Rotated** — 最近一次轮换时间

### 操作按钮

每行提供四个操作：

1. **Reveal / Hide** — 调用 `POST /api/secrets/{id}/reveal` 获取明文并显示在行内。再次点击隐藏。需要 Vault 已解锁。
2. **Rotate** — 弹窗输入新的密钥值，调用 `POST /api/secrets/{id}/rotate`，用新值替换并记录 `rotated_at` 时间戳。
3. **Test connectivity** — 调用 `POST /api/secrets/{id}/test-connectivity`，向 `base_url` 发送 HEAD/GET 请求测试连通性。显示结果（HTTP 状态码、延迟）。
4. **Edit** — 弹窗修改 Key、Value（可选，留空不改）、Enabled、Base URL、Category、项目归属。

### 添加 Secret

点击"Add secret"打开弹窗：
- **Key** — 必填，点号分隔
- **Value** — 必填，明文输入（提交时后端加密存储）
- **Enabled** — 默认开启
- **Base URL** — 用于连通性测试和代理转发的目标地址
- **Category** — 分类标签
- **Project** — 下拉选择项目或"Global"

## Bindings（服务绑定）

路径: `/bindings`

### 概念

Binding 将一个**服务名称**（如 `llm.openai`）映射到一个 **Secret 引用键**（如 `secret.openai.default`）。代理通过服务名称查找 Binding，再通过 Binding 的引用键找到 Secret 并注入认证头。

### 操作

- **查看列表** — Service Name、Secret Ref Key、Auth Header、Resolved（是否指向有效的已启用 Secret）
- **添加 Binding** — Service Name、Secret Ref Key、Auth Header（可选，默认 `Authorization`）
- **编辑 Binding** — 修改以上字段
- **删除 Binding** — 确认后删除

### Resolved 状态

列表中的 **Resolved** 列动态计算：如果引用的 Secret 存在且 `enabled=true`，显示"Resolved"；否则显示"Unresolved"。

## Template Preview（模板预览）

路径: `/template`

### 操作流程

1. 在文本区域输入包含 `[[placeholder]]` 的模板文本
2. 点击"Render"按钮
3. 后端调用 `POST /api/render` 进行替换：
   - `[[identity.student.name]]` → `张三`（从 Identity 表查询）
   - `[[binding.llm.openai]]` → `[secret_ref:secret.openai.default]`（不解密）
4. 显示渲染结果、统计信息和警告

### 占位符语法

| 格式                      | 替换行为                              |
| ------------------------- | ------------------------------------- |
| `[[identity.xxx.yyy]]`    | 替换为 Identity 明文值                |
| `[[binding.service_name]]`| 替换为 `[secret_ref:...]` 标记        |
| `[[secret_ref.xxx.yyy]]`  | 直接渲染为 `[secret_ref:...]`         |

## Export（导出）

路径: `/export`

### 操作流程

1. 输入模板文本
2. 选择导出格式：**Markdown** / **HTML** / **TXT**
3. 提交后调用 `POST /api/export`
4. 浏览器下载生成的文件

### 格式说明

- **Markdown** — 直接输出渲染后的模板文本
- **HTML** — Markdown 转 HTML，包裹在最小化的 HTML5 文档中（带基础排版样式）
- **TXT** — 去除 Markdown 标记（标题 `#`、加粗 `**`、链接 `[text](url)` 等）

### 安全特性

导出时 **不回填 Secret**——Secret 以 `[secret_ref:...]` 标记形式出现在导出文件中，确保导出文件可以安全分享。

## Test Center（测试中心）

路径: `/test-center`

### 三种测试类型

1. **Identity Render** — 取第一个 Identity，构造模板 `VERIFY_START [[key]] VERIFY_END` 并渲染，验证 Identity 值是否正确替换。

2. **API Connectivity** — 调用内部渲染和导出路径，验证这两个 API 端点是否正常工作。

3. **Binding Probe** — 遍历所有 Binding：
   - 查找关联的 Secret 和 `base_url`
   - 对 `base_url` 发送 HEAD/GET 请求
   - 报告每个 Binding 的连通性状态（pass/fail/skip）

### 结果展示

每个测试项显示：
- 名称
- 状态（pass / fail / skip）
- 详细信息
- 耗时（毫秒）

## Settings（设置）

路径: `/settings`

### 可配置项

- **API Port** — 修改后端监听端口（需重启生效）
- **Preferences** — JSON 格式的偏好设置

### 密码更换

Settings 页面提供修改 Master Password 的功能：
1. 输入当前密码
2. 输入新密码（至少 8 个字符）
3. 后端验证当前密码 → 重新加密所有 Secret → 更新 Vault 密钥

## Logs（日志查看）

路径: `/logs`

### 功能

- 实时查看后端运行日志（来自内存环形缓冲区，最多 1000 条）
- **按级别筛选** — INFO / WARNING / ERROR
- **按来源筛选** — 模块名称
- **全文搜索** — 在日志消息中搜索关键字
- 日志已经过脱敏处理，Secret 值显示为 `[REDACTED]`

## 通用交互模式

### 弹窗 (Modal)

所有创建和编辑操作使用统一的弹窗模式：
- 全屏半透明遮罩（`bg-black/40`）
- 居中白色卡片
- 表单验证错误显示在提交按钮上方
- "Cancel" 和 "Create/Save" 双按钮

### 确认对话框 (ConfirmDialog)

删除操作使用专用的确认对话框（基于 Modal 组件）：
- 显示操作标题和确认消息
- 破坏性操作（删除）使用红色确认按钮
- 支持异步操作中的 pending 状态

### 通知 (Toast)

操作结果通过 `sonner` 库的 Toast 通知显示：
- 成功 → 绿色 Toast
- 失败 → 红色 Toast + 错误详情

### 加载状态

- **骨架屏 (Skeleton)** — 表格加载时显示灰色脉冲动画行，避免布局跳动
- **空状态 (EmptyState)** — 列表为空时显示提示文字和创建按钮引导
- **页面标题** — 每个页面通过 `useDocumentTitle` hook 动态设置浏览器标签标题（如 "Projects — PrivPortal"）

### 键盘快捷键

| 快捷键                    | 功能           |
| ------------------------- | -------------- |
| `Cmd+K` / `Ctrl+K`       | 打开命令面板   |
| `Cmd+B` / `Ctrl+B`       | 折叠/展开侧边栏 |
| `Esc`                     | 关闭弹窗/面板  |
| `↑` / `↓`                | 命令面板中选择 |
| `Enter`                   | 命令面板中确认 |

### 项目上下文

几乎所有数据列表页面都受顶栏项目选择器影响：
- 选中某项目 → 仅显示该项目下的数据
- 选中"Global" → 显示不属于任何项目的全局数据
- 当前项目 ID 和侧边栏折叠状态存储在 Zustand store（`useUiStore`），并通过 `localStorage`（key: `privportal:ui`）持久化，刷新页面后保持选择
