import base64
import json
import re

import pytest
from app import main
from app.student_analysis import api
from app.student_analysis.contracts import AnalysisResult
from app.student_analysis.report import ReportError
from fastapi.testclient import TestClient

ORIGIN = "https://kett.example"
TABLE = (
    "score;hours;school\n" + "\n".join(f"{i * 2};{i};A" for i in range(30))
).encode()
OPTIONS = {
    "target": "score",
    "features": ["hours"],
    "prediction_context": "Before the exam",
}


@pytest.fixture
def client(tmp_path):
    app = main.create_app(
        database_url=f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}",
        app_origin=ORIGIN,
    )
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
        yield client


def upload(client, action, *, name="exam.csv", content=TABLE, options=None, **request):
    return client.post(
        f"/api/analysis/{action}",
        files={"file": (name, content)},
        data={"options": json.dumps(options)} if options is not None else None,
        **request,
    )


@pytest.mark.parametrize(
    ("name", "content", "delimiter"),
    [
        ("student.csv", TABLE, ";"),
        ("student.CSV", b'\xef\xbb\xbfscore,"hours, total",school\n8,2,A\n', ","),
        ("student.tsv", b"score\thours\tschool\n8\t2\tA\n", "\t"),
    ],
)
def test_uploaded_table_lists_columns(client, name, content, delimiter):
    response = upload(client, "columns", name=name, content=content)
    assert response.status_code == 200
    assert response.json()["delimiter"] == delimiter
    assert response.json()["columns"][0] == "score"
    assert len(response.json()["columns"]) == 3


@pytest.mark.parametrize(
    ("name", "content", "status"),
    [
        ("exam.pdf", TABLE, 415),
        ("exam.txt", TABLE, 415),
        ("exam.xlsx", TABLE, 415),
        ("renamed.csv", b"This is unstructured text", 422),
        ("binary.csv", b"\xff\x00", 422),
        ("malformed.csv", b"score,hours\n8,2,extra\n", 422),
        ("empty.csv", b"score,hours\n", 422),
    ],
)
def test_rejects_unsupported_or_unstructured_files(client, name, content, status):
    assert upload(client, "columns", name=name, content=content).status_code == status
    assert (
        upload(
            client, "report", name=name, content=content, options=OPTIONS
        ).status_code
        == status
    )


def test_upload_limits_and_origin(client, monkeypatch):
    assert (
        upload(
            client, "columns", headers={"Origin": "https://other.example"}
        ).status_code
        == 403
    )
    monkeypatch.setattr(api, "MAX_FILE_BYTES", 16)
    assert upload(client, "columns").status_code == 413
    monkeypatch.setattr(api, "MAX_FILE_BYTES", 5 * 1024 * 1024)
    monkeypatch.setattr(api, "MAX_ROWS", 10)
    assert "at most 10 rows" in upload(client, "columns").json()["detail"]


def test_csv_report_contains_real_metrics_and_portable_charts(client):
    response = upload(client, "report", options=OPTIONS)
    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "template"
    report = result["report"]
    assert "No Ollama model was selected" in report
    assert "exam.csv (30 rows, 3 columns)" in report
    assert "Before the exam" in report
    assert "24 training rows / 6 test rows" in report
    assert "| Random forest |" in report
    assert re.findall(r"^## (.+)$", report, re.MULTILINE) == [
        "Executive Summary",
        "Methodology",
        "Findings",
        "Limitations",
        "Recommendations",
    ]
    charts = re.findall(r"data:image/png;base64,([A-Za-z0-9+/=]+)", report)
    assert len(charts) == 2
    assert all(
        base64.b64decode(chart).startswith(b"\x89PNG\r\n\x1a\n") for chart in charts
    )


def test_report_rejects_invalid_columns_and_nonnumeric_targets(client):
    response = upload(client, "report", options=OPTIONS | {"features": ["score"]})
    assert response.status_code == 422
    assert "target column must not be used" in response.json()["detail"]
    response = upload(client, "report", options=OPTIONS | {"target": "school"})
    assert response.status_code == 422
    assert "finite numeric values" in response.json()["detail"]


@pytest.mark.parametrize("available", [True, False])
def test_selected_model_receives_the_analysis_then_temp_files_are_removed(
    client, monkeypatch, available
):
    workspaces = []

    def run_agent(path, *, model):
        assert model == "demo-model"
        result = AnalysisResult.model_validate_json(path.read_bytes())
        assert result.evaluation.test_rows == 6
        workspaces.append(path.parent)
        if not available:
            raise ReportError("Off")
        report = path.with_name("report.md")
        report.write_text("## Findings\nGenerated using Ollama", encoding="utf-8")
        return report

    monkeypatch.setattr(api, "run_report_agent", run_agent)
    response = upload(client, "report", options=OPTIONS | {"model": "demo-model"})
    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == ("ollama" if available else "template")
    assert (
        "Generated using Ollama" if available else "selected Ollama model could not"
    ) in result["report"]
    assert len(workspaces) == 1 and not workspaces[0].exists()
