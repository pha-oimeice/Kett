# Kett

基于 **Svelte 5 + TypeScript + Vite** 的纯前端 AI 对话界面。参考 Claude / Codex 的工作方式，采用暖白、陶土色与衬线标题，提供完整的英文界面与独立视觉设计。

## 启动

建议 Node.js 22 LTS 或更新版本。

```bash
npm install
npm run dev
```

打开终端显示的地址，默认是 `http://localhost:5173`。

```bash
npm run check    # Svelte / TypeScript 静态检查
npm test         # Playwright 浏览器测试
npm run build    # 构建到 dist/
npm run preview  # 预览生产构建
npm run format   # 格式化源代码
```

首次执行浏览器测试前，可能需要安装 Chromium：

```bash
npx playwright install chromium
```

## 已实现

- 可收起的会话侧栏、新建 / 切换 / 删除对话
- `⌘ / Ctrl + K` 搜索，`Esc` 关闭弹窗
- `Enter` 发送、`Shift + Enter` 换行，兼容中文输入法
- 本地模拟流式回复、停止、重新生成、复制与点赞
- 安全渲染 Markdown 和代码块
- 模型下拉菜单（暂未配置模型）、深度思考开关（界面演示）
- 附件选择与移除（仅展示文件名和大小，不读取文件内容）
- 在对话中下载演示 HTML 文件
- 本地项目创建、项目内新建对话
- 主界面右上角切换浅色 / 深色主题、对话 Markdown 导出
- 使用 localStorage 保存对话、项目和主题
- 手机适配、侧栏抽屉、键盘焦点管理与减少动态效果支持
- 英文界面、无障碍标签和示例对话；默认显示 Guest，支持 Google 登录和退出
- 自动将旧版内置示例切换为英文，保留用户自己的对话和项目

## Google 登录

默认无需配置。在 **Settings** 中点击 **Sign in**，可用演示账号走通登录和退出，不会联系 Google。

要启用真实 Google 登录，在 Google Cloud 创建 **Web application** 类型的 OAuth 客户端，并在 **Authorized JavaScript origins** 中添加访问前端的完整来源（例如 `http://localhost:5173`；如果用 `127.0.0.1` 访问，需要单独添加）。将客户端 ID 写入 `frontend/.env.local`，然后重启 Vite 或重新构建：

```dotenv
VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
```

弹窗流程不需要配置重定向 URI，也不需要客户端密钥。OAuth 令牌只用于读取 Google 个人资料，不会写入浏览器存储；只有显示名称保留在当前浏览器会话中。**Sign out** 只清除 Kett 的登录状态，不会退出 Google 账号。前端登录状态不用于后端认证或授权。

## 文件结构

```text
src/
├── App.svelte       # 聊天界面布局和交互
├── app.css          # 主题、排版与响应式样式
├── main.ts          # 应用入口
└── lib/
    ├── Icon.svelte  # SVG 图标
    ├── google-auth.ts # Google OAuth 弹窗和个人资料读取
    └── demo.ts      # 数据类型、示例对话、本地回复和示例 HTML
tests/
└── workspace.spec.ts # 浏览器交互测试
```

## 演示边界

**没有后端认证或 AI 服务。** 回复来自 `src/lib/demo.ts` 中的本地预设；思考模式不会调用模型。可下载的 HTML 是内置示例，而非动态生成的作品。附件不会上传，也不会解析。

对话内容仅保存在当前浏览器中，清理站点数据会将其删除。页面使用 Google Fonts 加载字体；字体不可用时会回退到系统字体，不影响功能。

Markdown 使用 DOMPurify 清理。生产依赖通过 `npm audit --omit=dev` 检查；完整审计目前会报告开发工具链中 picomatch 的已知问题，当前注册表尚无修复版本。仅在可信环境运行开发服务器，部署时使用 `dist/` 静态文件。
