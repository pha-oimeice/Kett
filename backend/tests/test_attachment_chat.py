import json

import httpx
import pytest
from app import main
from app.student_analysis import api
from app.student_analysis.contracts import ReportEvidence
from fastapi.testclient import TestClient

ORIGIN = "https://kett.example"
TABLE = (
    "score;hours;school\n" + "\n".join(f"{i * 2};{i};A" for i in range(30))
).encode()


def reply(text="", tool=None, arguments=None):
    message = {"role": "assistant", "content": text}
    if tool:
        message["tool_calls"] = [
            {"function": {"name": tool, "arguments": arguments or {}}}
        ]
    return httpx.Response(200, json={"message": message})


class Ollama:
    def __init__(self):
        self.calls = []
        self.replies = []

    def __call__(self, request):
        assert request.url.path == "/api/chat"
        self.calls.append(json.loads(request.content))
        return self.replies.pop(0)


@pytest.fixture
def ollama():
    return Ollama()


@pytest.fixture
def client(tmp_path, ollama):
    app = main.create_app(
        database_url=f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}",
        app_origin=ORIGIN,
        http_transport=httpx.MockTransport(ollama),
    )
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
        yield client


def upload(client, text, *, name="exam.csv", content=TABLE, **options):
    chat = {
        "model": "general",
        "messages": [{"role": "user", "content": text}],
        **options,
    }
    response = client.post(
        "/api/chat/attachments",
        files={"file": (name, content)},
        data={"options": json.dumps(chat)},
    )
    assert response.status_code == 200, response.text
    return [json.loads(line) for line in response.text.splitlines()]


def test_table_inspection_does_not_train(client, ollama, monkeypatch):
    def should_not_run(*_):
        pytest.fail("A metadata or ordinary question must not train a model")

    monkeypatch.setattr(api, "generate_report", should_not_run)
    ollama.replies = [
        reply(tool="inspect_table"),
        reply("30 rows; columns are score, hours and school."),
    ]
    events = upload(client, "What are the columns?")
    assert events[-1]["text"] == "30 rows; columns are score, hours and school."
    request, follow_up = ollama.calls
    assert {tool["function"]["name"] for tool in request["tools"]} == {
        "inspect_table",
        "generate_regression_report",
    }
    assert request["model"] == "general"
    assert request["messages"][-1]["content"].startswith("What are the columns?")
    assert "score;hours;school" not in json.dumps(request)
    assert json.loads(follow_up["messages"][-1]["content"])["rows"] == 30
    assert follow_up["messages"][-1]["tool_name"] == "inspect_table"


def test_regression_combines_three_evidence_branches_before_the_report_agent(
    client, ollama, monkeypatch
):
    def report_agent(path, *, model):
        assert model == "writer"
        result = ReportEvidence.model_validate_json(path.read_bytes())
        assert result.dataset.filename == "exam.csv"
        assert result.features == ["hours"]
        assert result.target == "score"
        assert result.schema_evidence is not None
        assert [
            (field.name, field.kind, field.role) for field in result.schema_evidence
        ] == [
            ("score", "numeric", "target"),
            ("hours", "numeric", "feature"),
            ("school", "text", "unused"),
        ]
        assert result.quality_evidence is not None
        assert result.quality_evidence.duplicate_rows == 1
        assert result.quality_evidence.missing_by_column == {
            "score": 1,
            "hours": 0,
            "school": 1,
        }
        assert result.evaluation.random_forest.mae < result.evaluation.baseline.mae
        report_path = path.with_name("report.md")
        report_path.write_text(
            "## Findings\n![Feature importance](feature-importance.png)\n",
            encoding="utf-8",
        )
        return report_path

    monkeypatch.setattr(api, "run_report_agent", report_agent)
    ollama.replies = [
        reply(
            tool="generate_regression_report",
            arguments={"target": "score", "features": ["hours"]},
        )
    ]
    events = upload(
        client,
        "Predict score from hours and write a report",
        content=TABLE + b"\n0;0;A\n;30;\n",
        report_model="writer",
    )
    assert len(ollama.calls) == 1
    assert events[-1]["type"] == "report"
    assert events[-1]["mode"] == "ollama"
    assert "## Findings" in events[-1]["report"]
    assert "data:image/png;base64," in events[-1]["report"]


def test_disabled_analysis_is_not_advertised_or_executed(client, ollama, monkeypatch):
    def should_not_run(*_):
        pytest.fail("A disabled tool must not run, even if the model asks for it")

    monkeypatch.setattr(api, "generate_report", should_not_run)
    ollama.replies = [
        reply(
            tool="generate_regression_report",
            arguments={"target": "score", "features": ["hours"]},
        ),
        reply(tool="inspect_table"),
        reply(
            "The table has 30 rows. To generate a report, enable the tool in Settings."
        ),
    ]
    events = upload(client, "Predict score from hours", mat_enabled=False)
    assert all(
        [entry["function"]["name"] for entry in turn["tools"]] == ["inspect_table"]
        for turn in ollama.calls
    )
    assert (
        "Multi-Agent Data Analysis is disabled"
        in ollama.calls[1]["messages"][-1]["content"]
    )
    assert json.loads(ollama.calls[2]["messages"][-1]["content"])["rows"] == 30
    assert not any(item["type"] == "report" for item in events)


def test_missing_arguments_are_sent_back_to_main_model(client, ollama, monkeypatch):
    def should_not_run(*_):
        pytest.fail("Missing features cannot train a model")

    monkeypatch.setattr(api, "generate_report", should_not_run)
    ollama.replies = [
        reply(tool="generate_regression_report", arguments={"target": "score"}),
        reply("Which columns should be features?"),
    ]
    assert (
        upload(client, "Predict score")[-1]["text"]
        == "Which columns should be features?"
    )
    assert "Specify a target" in ollama.calls[-1]["messages"][-1]["content"]


def test_plain_text_uses_a_bounded_excerpt_tool(client, ollama):
    ollama.replies = [reply(tool="read_text"), reply("It contains study notes.")]
    events = upload(
        client, "Summarize the text", name="notes.txt", content=b"Study notes. " * 1500
    )
    assert events[-1]["text"] == "It contains study notes."
    first, second = ollama.calls
    assert [item["function"]["name"] for item in first["tools"]] == ["read_text"]
    assert "Study notes" not in json.dumps(first)
    tool_result = json.loads(second["messages"][-1]["content"])
    assert tool_result["truncated"] and len(tool_result["excerpt"]) == 12_000


def test_unsupported_files_are_accepted_but_no_tool_can_open_them(client, ollama):
    ollama.replies = [
        reply(tool="generate_regression_report"),
        reply("I can't open this PDF."),
    ]
    events = upload(
        client, "Summarize this PDF", name="slides.pdf", content=b"%PDF-1.7\nExample"
    )
    assert events[-1]["text"] == "I can't open this PDF."
    assert "tools" not in ollama.calls[0]
    assert "unsupported" in ollama.calls[0]["messages"][-1]["content"]
    assert "not available" in ollama.calls[1]["messages"][-1]["content"]


def test_non_tool_model_gets_a_clear_error(client, ollama):
    ollama.replies = [
        httpx.Response(400, json={"error": "model does not support tools"})
    ]
    events = upload(client, "What is in the table?")
    assert events[-1]["type"] == "error"
    assert "tool-capable main model" in events[-1]["message"]
