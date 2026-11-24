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
2. 在运行 `python start.py` 的终端设置 `GOOGLE_CLIENT_ID`：PowerShell 用 `$env:GOOGLE_CLIENT_ID = 'your-client-id.apps.googleusercontent.com'`，Bash 用 `export GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com`。前后端共用该值，无须再创建 `frontend/.env.local`。如果前端独立构建或启动，且进程没有收到 `GOOGLE_CLIENT_ID`，可用 `VITE_GOOGLE_CLIENT_ID` 设置与后端相同的公开 Client ID。
3. 运行 `python start.py`，打开 `http://localhost:5173`，在 **Settings** 中使用 Google 登录。如果用 `127.0.0.1` 访问，Google 授权来源和后端的 `APP_ORIGIN` 都要改为 `http://127.0.0.1:5173`。

如果设置里显示 **Try demo sign-in**，说明前端没有读到 Client ID。演示不会弹出 Google、不访问后端，也不会生成有效会话。设置变量后需重启 `python start.py`；已部署的静态前端需要重新构建。

## 认证流程

- `POST /api/auth/google/challenge` 发放有效期为 10 分钟的一次性挑战。
- `POST /api/auth/google` 接收 Google ID Token，验证签名、签发方、受众、有效期及挑战值。通过后按 Google `sub` 创建或更新 `users` 表中的用户，不使用邮箱匹配账户。
- `GET /api/auth/me` 根据 `HttpOnly` Cookie 查验后端会话，未登录或已过期返回 `401`。会话有效期为 7 天，数据库仅保存会话令牌的哈希，不保存 Google ID Token。
- `POST /api/auth/logout` 撤销当前 Kett 会话，不影响 Google 账号的登录状态。

开发时 Vite 将 `/api` 代理到 `127.0.0.1:8000`。部署时让静态前端和 `/api` 通过同一 HTTPS 来源提供服务，将 `APP_ORIGIN` 设为该公开来源，以启用 `Secure` Cookie。后端需能访问 `www.googleapis.com` 获取 Google 公钥。

## 添加模型

展开 **Select model**，点击 **Add model（+）**，可以发现并选择页面打开后新增到 Ollama 的模型。模型需已安装在后端配置的 `OLLAMA_URL` 服务器上（默认 `http://127.0.0.1:11434`）。前端不能输入自定义服务器地址，也不会替服务器下载模型。

## 学生成绩分析 Agent

启动 Kett，在输入框旁点击 **Upload dataset**（+），上传带表头的 UTF-8 `.csv` 或 `.tsv`。选择一个数值型 **Target column** 和至少一个 **Feature column**，可填写预测时点，然后点击 **Generate report**。后端自动校验数据、训练并评估模型、生成五节报告。报告在对话中展示，可以下载 `report.md`（包含两张内嵌图表）。

- 只接受结构化 CSV/TSV，支持逗号、分号或制表符分隔；Excel 文件需先导出为 CSV。单个文件上限 5 MiB、25,000 行、128 列，每次最多选择 32 个特征。
- 选中 Ollama 模型时，用该模型写报告正文；没有选择或模型调用失败时，返回标注为模板的报告，指标和图表仍来自真实训练结果。原始数据不会发送给 Ollama，后端处理完毕后删除临时文件。
- API：`POST /api/analysis/columns` 和 `POST /api/analysis/report` 均接收 `multipart/form-data` 的 `file` 文件字段。报告接口另需 `options` 字段（JSON，如 `{"target":"G3","features":["G1","G2"]}`；可选 `prediction_context`、`model`）。

两个 Agent 也可独立调用。安装 `backend/requirements.txt` 后，从仓库根目录使用 Python 运行以下示例。先从 [UCI Student Performance](https://archive.ics.uci.edu/dataset/320/student+performance) 下载数据，解开下载包内的 `student.zip`，将 `student-mat.csv` 放在 `dataset/` 下。

```python
from pathlib import Path

from backend.app.student_analysis.contracts import AnalysisConfig
from backend.app.student_analysis.report import run_report_agent
from backend.app.student_analysis.scientist import run_data_scientist

run_dir = Path("runs/uci-math")  # 不同运行请使用不同目录

# Data Scientist Agent：不需要 Ollama。
run_data_scientist(
    AnalysisConfig(
        dataset_path=Path("dataset/student-mat.csv"),
        target="G3",
        features=["school", "G1", "G2"],
        prediction_context="Predict the final math grade after G2 is available.",
        dataset_source="https://archive.ics.uci.edu/dataset/320/student+performance",
        delimiter=";",
    ),
    run_dir,
)

# Report Agent：只读取 analysis.json；将 model 换成本机 `ollama list` 中的名称。
run_report_agent(run_dir / "analysis.json", model="qwen2.5:7b")
```

分析目录包含 `analysis.json`、`model.joblib`、`feature-importance.png` 和 `actual-vs-predicted.png`。Report Agent 将同目录中的图表链接进 `report.md`；Ollama 默认地址是 `http://127.0.0.1:11434`，可用 `OLLAMA_URL` 修改。报告生成失败不会删除分析产物，可以单独重跑报告。

分析目前支持 UTF-8 的回归 CSV：目标列必须是数值，至少有 10 个带目标值的样本和 2 个不同的目标值。更换数据集时修改数据路径、目标、特征和分隔符，无需改 Agent 代码；选特征时要确保它们在预测时点已经可用。

## 测试

- 后端：在 `backend/` 中运行 `python -m pip install -r requirements-dev.txt` 和 `python -m pytest`。测试用本地签名密钥替代 Google 公钥请求，不需要 Google 账号。
- 前端：见 [frontend/README.md](frontend/README.md)。
