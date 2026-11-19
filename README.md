# Kett

聊天界面使用 Svelte / Vite，账号认证使用 Python / FastAPI。后端以 SQLModel 管理 SQLite 中的用户和登录会话；聊天记录、项目和主题仍仅保存在当前浏览器中，**不会按账号同步或隔离**。

## 本地启动

建议使用 Python 3.11+（SQLite 3.35+）和 Node.js 22+。首次在项目根目录安装依赖：

```bash
python -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
npm --prefix frontend ci
```

Windows PowerShell 将第二行换为 `.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt`（不需要激活虚拟环境）。

安装完成后，在项目根目录运行：

```bash
python start.py
```

脚本同时启动前端 `http://localhost:5173` 和后端 `http://127.0.0.1:8000`（API 文档在 `/docs`）。按 `Ctrl+C` 停止两端。如果任一服务退出，脚本会停止另一端。后端首次启动会创建 `backend/kett.sqlite3`，可通过 `DATABASE_URL` 指定其他 SQLite 文件。

## 本地启用 Google 登录（可选）

1. 在 Google Cloud 创建 **Web application** 类型的 OAuth 客户端，将 `http://localhost:5173` 添加到 **Authorized JavaScript origins**。弹窗登录不需要客户端密钥或重定向 URI。如果应用处于测试模式，将登录账号添加到测试用户列表。
2. 在 `frontend/.env.local` 设置 `VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com`。同时在启动脚本的终端中设置相同的 `GOOGLE_CLIENT_ID`，例如 `export GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com`（PowerShell：`$env:GOOGLE_CLIENT_ID = 'your-client-id.apps.googleusercontent.com'`）。
3. 运行 `python start.py`，打开 `http://localhost:5173`，在 **Settings** 中使用 Google 登录。如果用 `127.0.0.1` 访问，Google 授权来源和后端的 `APP_ORIGIN` 都要改为 `http://127.0.0.1:5173`。

未配置 `VITE_GOOGLE_CLIENT_ID` 时保留前端演示登录，不访问后端，也不会生成有效会话。

## 认证流程

- `POST /api/auth/google/challenge` 发放有效期为 10 分钟的一次性挑战。
- `POST /api/auth/google` 接收 Google ID Token，验证签名、签发方、受众、有效期及挑战值。通过后按 Google `sub` 创建或更新 `users` 表中的用户，不使用邮箱匹配账户。
- `GET /api/auth/me` 根据 `HttpOnly` Cookie 查验后端会话，未登录或已过期返回 `401`。会话有效期为 7 天，数据库仅保存会话令牌的哈希，不保存 Google ID Token。
- `POST /api/auth/logout` 撤销当前 Kett 会话，不影响 Google 账号的登录状态。

开发时 Vite 将 `/api` 代理到 `127.0.0.1:8000`。部署时让静态前端和 `/api` 通过同一 HTTPS 来源提供服务，将 `APP_ORIGIN` 设为该公开来源，以启用 `Secure` Cookie。后端需能访问 `www.googleapis.com` 获取 Google 公钥。

## 测试

- 后端：在 `backend/` 中运行 `python -m pip install -r requirements-dev.txt` 和 `python -m pytest`。测试用本地签名密钥替代 Google 公钥请求，不需要 Google 账号。
- 前端：见 [frontend/README.md](frontend/README.md)。
