import base64
import json
import re
from functools import partial

import httpx
import pytest
from app import main
from app.student_analysis import api, pipeline, report
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
    response = upload(
        client,
        "report",
        options=OPTIONS | {"report_levels": ["advanced"]},
        content=TABLE + b"\n;30;\n0;0;A\n62;31;B",
    )
    assert response.status_code == 200
    notebook = response.json()["notebook"]
    assert notebook["nbformat"] == 4 and notebook["nbformat_minor"] == 5
    (cell,) = notebook["cells"]
    assert cell["cell_type"] == "markdown" and cell["id"] == "advanced"
    assert cell["metadata"]["kett_report_mode"] == "template"
    report = cell["source"]
    assert report.startswith("# Advanced")
    assert "No Ollama model was selected" in report
    assert "exam.csv (33 rows, 3 columns)" in report
    assert "Before the exam" in report
    assert "25 training rows / 7 test rows" in report
    assert "### Data quality" in report
    assert "Duplicate rows beyond the first copy: 1" in report
    assert "Missing cells before filtering: 2" in report
    assert "### Schema" in report
    assert "| score | numeric | target | 1 | 0 |" in report
    assert "| hours | numeric | feature | 0 | 0 |" in report
    assert "| school | text | unused | 1 | 0 |" in report
    assert "| Random forest |" in report
    assert re.findall(r"^## (.+)$", report, re.MULTILINE) == [
        "Executive Summary",
        "Methodology",
        "Findings",
        "Limitations",
        "Recommendations",
    ]
    charts = cell["attachments"]
    assert set(charts) == {"feature-importance.png", "actual-vs-predicted.png"}
    for name, payload in charts.items():
        assert f"](attachment:{name})" in report
        assert base64.b64decode(payload["image/png"]).startswith(b"\x89PNG\r\n\x1a\n")


def test_report_rejects_invalid_columns_and_nonnumeric_targets(client):
    response = upload(client, "report", options=OPTIONS | {"features": ["score"]})
    assert response.status_code == 422
    assert "target column must not be used" in response.json()["detail"]
    response = upload(
        client,
        "report",
        options=OPTIONS | {"target": "school", "report_levels": ["advanced"]},
    )
    assert response.status_code == 422
    assert "finite numeric values" in response.json()["detail"]


def test_default_basic_report_describes_finite_values_without_training(
    client, monkeypatch
):
    def unexpected_training(*_):
        pytest.fail("Basic reports do not train a model")

    monkeypatch.setattr(pipeline, "fit_data_scientist", unexpected_training)
    response = upload(
        client,
        "report",
        options=OPTIONS | {"features": ["hours", "school"]},
        content=b"score,hours,school\n1,10,A\n2,,A\n3,inf,B\n5,30,B\n,20,B\n",
    )
    assert response.status_code == 200
    (cell,) = response.json()["notebook"]["cells"]
    assert cell["id"] == "basic"
    assert cell["attachments"] == {}
    source = cell["source"]
    assert source.startswith("# Basic")
    assert "| Mean | Median | Q1 | Q3 | IQR |" in source
    assert "| score | 4 | 2.75 | 2.5 | 1.75 | 3.5 | 1.75 |" in source
    assert "| hours | 3 | 20 | 20 | 15 | 25 | 10 |" in source
    assert "Not summarized (no usable numeric data): school" in source
    assert "RMSE" not in source


@pytest.mark.parametrize("levels", [[], ["expert"]])
def test_report_rejects_invalid_levels(client, levels):
    response = upload(client, "report", options=OPTIONS | {"report_levels": levels})
    assert response.status_code == 422
    assert "Select at least one valid report level" in response.json()["detail"]


def test_both_reports_share_one_parse_but_use_separate_model_calls(client, monkeypatch):
    paths = []
    read_dataset = pipeline.read_dataset

    def read_once(config):
        paths.append(config.dataset_path)
        return read_dataset(config)

    calls = []

    def ollama(request):
        payload = json.loads(request.content)
        assert payload["model"] == "demo-model"
        instructions, data = (message["content"] for message in payload["messages"])
        evidence = json.loads(data)
        calls.append(evidence)
        if "statistics" in evidence:
            assert "plain-English" in instructions
            assert "evaluation" not in evidence
            assert evidence["statistics"]["score"]["median"] == 29
            sections = {
                section: "Basic narrative from Ollama."
                for section in report.ReportSections.model_fields
            }
            return httpx.Response(
                200, json={"message": {"content": json.dumps(sections)}}
            )
        assert "held-out" in instructions
        assert evidence["evaluation"]["test_rows"] == 6
        return httpx.Response(503)

    monkeypatch.setattr(pipeline, "read_dataset", read_once)
    monkeypatch.setattr(
        report,
        "request_sections",
        partial(report.request_sections, transport=httpx.MockTransport(ollama)),
    )
    response = upload(
        client,
        "report",
        options=OPTIONS
        | {"model": "demo-model", "report_levels": ["advanced", "basic"]},
    )
    assert response.status_code == 200
    assert len(paths) == 1 and not paths[0].parent.exists()
    assert len(calls) == 2
    basic, advanced = response.json()["notebook"]["cells"]
    assert [basic["id"], advanced["id"]] == ["basic", "advanced"]
    assert basic["metadata"]["kett_report_mode"] == "ollama"
    assert "Basic narrative from Ollama." in basic["source"]
    assert "RMSE" not in basic["source"]
    assert advanced["metadata"]["kett_report_mode"] == "template"
    assert "selected Ollama model could not" in advanced["source"]
    assert "Test RMSE" in advanced["source"]
    assert "Basic narrative from Ollama." not in advanced["source"]
