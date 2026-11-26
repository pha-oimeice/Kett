# Kett

Kett is a Svelte and Vite chat workspace backed by FastAPI. The backend uses SQLModel and SQLite for user accounts and sign-in sessions. Conversations, projects, and themes are stored in the current browser; they are **not synced or isolated by account**.

## Run locally

Use Python 3.11+ with SQLite 3.35+ and Node.js 22+. Install dependencies from the repository root:

```bash
python -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
npm --prefix frontend ci
```

In Windows PowerShell, replace the second line with `.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt`. You do not need to activate the virtual environment.

Start both services from the repository root:

```bash
python start.py
```

The frontend runs at `http://localhost:5173` and the backend at `http://127.0.0.1:8000` (OpenAPI docs at `/docs`). Press `Ctrl+C` to stop both. If either service exits, the script stops the other. The backend creates `backend/kett.sqlite3` on first startup; set `DATABASE_URL` to use a different SQLite file.

## Enable Google sign-in locally (optional)

1. In Google Cloud, create a **Web application** OAuth client and add `http://localhost:5173` to **Authorized JavaScript origins**. The popup flow does not require a client secret or redirect URI. If the app is in testing mode, add the accounts you intend to use as test users.
2. Set `GOOGLE_CLIENT_ID` in the shell that runs `python start.py`: use `$env:GOOGLE_CLIENT_ID = 'your-client-id.apps.googleusercontent.com'` in PowerShell or `export GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com` in Bash. The frontend and backend share this value. If you run or build the frontend separately without that variable, use `VITE_GOOGLE_CLIENT_ID` with the same public client ID as the backend.
3. Run `python start.py`, open `http://localhost:5173`, and sign in from **Workspace settings**. If you use `127.0.0.1` instead, set both the Google authorized origin and the backend's `APP_ORIGIN` to `http://127.0.0.1:5173`.

If settings shows **Try demo sign-in**, the frontend has not received a client ID. Demo sign-in does not open Google, contact the backend, or create a valid session. After changing the environment variable, restart `python start.py` or rebuild the deployed static frontend.

## Authentication

- `POST /api/auth/google/challenge` issues a single-use challenge valid for 10 minutes.
- `POST /api/auth/google` verifies the Google ID token's signature, issuer, audience, expiration, and challenge. It creates or updates the user by Google's `sub` claim, not by email address.
- `GET /api/auth/me` checks the backend session using an `HttpOnly` cookie. It returns `401` for a missing or expired session. Sessions last seven days. The database stores only a hash of the session token, not the Google ID token.
- `POST /api/auth/logout` revokes the current Kett session without signing the user out of Google.

In development, Vite proxies `/api` to `127.0.0.1:8000`. In production, serve the frontend and `/api` from the same HTTPS origin and set `APP_ORIGIN` to that public origin to enable secure cookies. The backend needs access to `www.googleapis.com` to fetch Google's public keys.

## Add models

Open **Select model** and click **Add model (+)** to discover models installed since the page loaded. Models must already be installed on the Ollama server configured by the backend's `OLLAMA_URL` (default: `http://127.0.0.1:11434`). The frontend cannot set a custom server address or download models.

## Student performance analysis

Choose a general-purpose Ollama model that supports tool calling under **Select model**. Use **+** to add a file, then ask a question. For example, ask “What columns are in this table?” to inspect it without training a model, or “Use `G1` and `G2` to predict `G3` and generate a report.” The main model selects a tool based on the request and asks for clarification if the target or features are unclear. The file stays attached for follow-up questions until you remove it. You can preview the reports in chat or download a single `report.ipynb` with embedded charts.

- Chat accepts one file of any type at a time, up to 5 MiB. Tools can inspect UTF-8 CSV or TSV with a header (up to 25,000 rows, 128 columns, and 32 training features), or read the first 12,000 characters of UTF-8 text. PDF, Excel, and image contents are not parsed. Web search is not available on turns with attachments.
- **Workspace settings → Tools → Multi-Agent Data Analysis** controls whether the main model can invoke the report pipeline. It is enabled by default, and the preference is saved in this browser. Turning it off does not disable ordinary chat, table inspection, or text reading. The same tab lets you set a separate **Report Agent model**, which defaults to the main model.
- **Workspace settings → Tools → Report detail level** offers **Basic** (default: mean, median, Q1, Q3, and IQR for the selected numeric columns) and **Advanced** (regression evaluation with MAE, RMSE, R², feature importance, and charts). You can enable both, but at least one must stay on. Basic alone does not train a model.
- The pipeline parses the table once. The Report Agent independently writes each selected report from its own aggregate evidence, with a labeled template as fallback. Raw table rows are not sent to the Report Agent. Each report occupies its own Markdown cell in the same notebook.
- `POST /api/chat/attachments` accepts multipart fields `file` and `options` (JSON with `model`, `messages`, and optional `mat_enabled`, `report_model`, and `report_levels`) and returns NDJSON. `mat_enabled: false` removes the report tool from that request. The direct endpoints `POST /api/analysis/columns` and `POST /api/analysis/report` are independent of browser settings. For example, pass `{"target":"G3","features":["G1","G2"],"report_levels":["basic","advanced"]}` as the report endpoint's `options`. The report and attachment-chat routes both default `report_levels` to `["basic"]` and reject an empty list. The direct report response and the chat `report` event include a `notebook` object that can be saved as `.ipynb`.

See the [target architecture](docs/multi_agent_pipeline_architecture.png), the [implemented tool workflow](docs/multi-agent-tool.md), and the [Data Scientist Agent decision record](docs/adr/0001-data-scientist-agent.md).

### Run the agents independently

After installing `backend/requirements.txt`, run this example from the repository root. Download the [UCI Student Performance dataset](https://archive.ics.uci.edu/dataset/320/student+performance), extract the nested `student.zip`, and place `student-mat.csv` in `dataset/`.

```python
from pathlib import Path

from backend.app.student_analysis.contracts import AnalysisConfig
from backend.app.student_analysis.report import run_report_agent
from backend.app.student_analysis.scientist import run_data_scientist

run_dir = Path("runs/uci-math")  # Use a separate directory for each run.

# Data Scientist Agent: does not require Ollama.
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

# Report Agent: replace the model name with one listed by `ollama list`.
run_report_agent(run_dir / "analysis.json", model="qwen2.5:7b")
```

The run directory contains `analysis.json`, `model.joblib`, `feature-importance.png`, and `actual-vs-predicted.png`. The Report Agent reads `analysis.json` and links to the charts in `report.md`. If report generation fails, you can rerun it without retraining.

Advanced reports and the standalone regression workflow require a numeric target and at least 10 labeled rows with at least two distinct target values. To use a different dataset, change its path, target, features, and delimiter. Choose only features that are available at prediction time.

## Tests

- **Backend:** From `backend/`, run `python -m pip install -r requirements-dev.txt` and `python -m pytest`. Authentication tests use local signing keys instead of contacting Google.
- **Frontend:** See the [frontend guide](frontend/README.md).
