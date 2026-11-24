import csv
import json

import httpx
import joblib
import pandas as pd
import pytest
from app.student_analysis.contracts import ANALYSIS_FILE, AnalysisConfig, AnalysisResult
from app.student_analysis.report import REPORT_FILE, ReportError, run_report_agent
from app.student_analysis.scientist import AnalysisError, run_data_scientist
from pydantic import ValidationError
from sklearn.model_selection import train_test_split


@pytest.fixture
def dataset(tmp_path):
    path = tmp_path / "exam.csv"
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter=";")
        writer.writerow(["exam_score", "study_hours", "school", "student_id"])
        for i in range(60):
            writer.writerow([i * 1.5, i, "north" if i % 2 else "south", f"id-{i}"])
        writer.writerow(["", 10, "north", "unlabeled-student"])
        writer.writerow([50, "", "", "incomplete-student"])
    return path


@pytest.fixture
def config(dataset):
    return AnalysisConfig(
        dataset_path=dataset,
        target="exam_score",
        features=["study_hours", "school"],
        prediction_context="Before the final exam",
        delimiter=";",
    )


def test_scientist_outputs_evaluated_model_summary_and_charts(tmp_path, config):
    output = tmp_path / "analysis"
    result = run_data_scientist(config, output)
    assert (
        AnalysisResult.model_validate_json((output / ANALYSIS_FILE).read_bytes())
        == result
    )
    assert result.dataset.rows == 62
    assert result.dataset.rows_dropped_missing_target == 1
    assert result.dataset.target_summary.maximum == 88.5
    assert result.dataset.missing_by_selected_column == {
        "exam_score": 1,
        "study_hours": 1,
        "school": 1,
    }
    assert result.evaluation.train_rows == 48
    assert result.evaluation.test_rows == 13
    assert result.evaluation.numeric_features == ["study_hours"]
    assert result.evaluation.categorical_features == ["school"]
    data = pd.read_csv(config.dataset_path, sep=";").dropna(subset=[config.target])
    x_train, x_test, y_train, y_test = train_test_split(
        data[config.features],
        data[config.target],
        test_size=0.2,
        random_state=config.random_seed,
    )
    model = joblib.load(output / result.artifacts.model)
    assert model.named_steps["preprocess"].named_transformers_["numeric"].statistics_[
        0
    ] == pytest.approx(x_train["study_hours"].median())
    errors = (y_test - model.predict(x_test)).abs()
    assert result.evaluation.baseline.mae == pytest.approx(
        (y_test - y_train.mean()).abs().mean()
    )
    assert result.evaluation.random_forest.mae == pytest.approx(errors.mean())
    assert result.evaluation.random_forest.rmse == pytest.approx(
        (errors**2).mean() ** 0.5
    )
    assert result.evaluation.random_forest.mae < result.evaluation.baseline.mae
    assert result.feature_importance[0].feature == "study_hours"
    assert result.feature_importance[0].mean_mae_increase > 0
    for chart in (result.artifacts.importance_chart, result.artifacts.prediction_chart):
        assert (output / chart).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_scientist_rejects_target_as_a_feature(config):
    with pytest.raises(ValidationError, match="target column must not be used"):
        AnalysisConfig(**(config.model_dump() | {"features": [config.target]}))


@pytest.mark.parametrize(
    ("content", "error"),
    [
        ("exam_score;study_hours\n5;3\n", "Columns missing.*school"),
        ("exam_score;study_hours;school\npass;3;north\n", "finite numeric values"),
        ("exam_score;study_hours;school\ninf;3;north\n", "finite numeric values"),
        ("exam_score;study_hours;study_hours\n5;3;4\n", "column names must be unique"),
        ("exam_score;study_hours;school\n5;3;north\n", "at least 10 labeled rows"),
    ],
)
def test_scientist_rejects_invalid_data(tmp_path, config, content, error):
    config.dataset_path.write_text(content, encoding="utf-8")
    output = tmp_path / "unused"
    with pytest.raises(AnalysisError, match=error):
        run_data_scientist(config, output)
    assert not output.exists()


def test_scientist_marks_r2_undefined_for_constant_test_target(tmp_path, config):
    train_rows, _ = train_test_split(
        list(range(10)), test_size=0.2, random_state=config.random_seed
    )
    rows = [f"{i if i in train_rows else 0};{i};north" for i in range(10)]
    config.dataset_path.write_text(
        "exam_score;study_hours;school\n" + "\n".join(rows), encoding="utf-8"
    )
    result = run_data_scientist(config, tmp_path / "constant")
    assert result.evaluation.baseline.r2 is None
    assert result.evaluation.random_forest.r2 is None


@pytest.fixture
def analysis(tmp_path, config):
    output = tmp_path / "analysis"
    result = run_data_scientist(config, output)
    config.dataset_path.unlink()
    (output / result.artifacts.model).unlink()
    return output / ANALYSIS_FILE, result


def test_report_uses_analysis_only_and_renders_five_sections(analysis, monkeypatch):
    analysis_path, result = analysis
    monkeypatch.setenv("OLLAMA_URL", "http://ollama.test/")
    prose = {
        "executive_summary": "Predict the final score.",
        "methodology": "Evaluate on held-out rows.",
        "findings": "Study hours contributed to predictions.",
        "limitations": "One split does not establish generalizability.",
        "recommendations": "Validate the model in another school.",
    }

    def ollama(request):
        assert request.url == "http://ollama.test/api/chat"
        payload = json.loads(request.content)
        assert payload["model"] == "local-model"
        assert set(payload["format"]["required"]) == set(prose)
        assert (
            AnalysisResult.model_validate_json(payload["messages"][1]["content"])
            == result
        )
        assert b"unlabeled-student" not in request.content
        assert b"student_id" not in request.content
        return httpx.Response(200, json={"message": {"content": json.dumps(prose)}})

    report = run_report_agent(
        analysis_path, model="local-model", transport=httpx.MockTransport(ollama)
    )
    assert report == analysis_path.with_name(REPORT_FILE)
    content = report.read_text(encoding="utf-8")
    assert [line for line in content.splitlines() if line.startswith("## ")] == [
        "## Executive Summary",
        "## Methodology",
        "## Findings",
        "## Limitations",
        "## Recommendations",
    ]
    for paragraph in prose.values():
        assert paragraph in content
    metrics = result.evaluation.random_forest
    assert (
        f"| Random forest | {metrics.mae:.3f} | {metrics.rmse:.3f} | {metrics.r2:.3f} |"
        in content
    )
    assert f"]({result.artifacts.importance_chart})" in content
    assert f"]({result.artifacts.prediction_chart})" in content


@pytest.mark.parametrize(
    ("reply", "error"),
    [
        (
            httpx.Response(
                200, json={"message": {"content": '{"findings":"Incomplete"}'}}
            ),
            "all five valid report sections",
        ),
        (httpx.Response(404), "HTTP 404"),
        (None, "Could not reach Ollama"),
    ],
)
def test_report_failure_keeps_analysis_and_charts(analysis, reply, error):
    analysis_path, result = analysis

    def ollama(request):
        if reply is None:
            raise httpx.ConnectError("Service unavailable", request=request)
        return reply

    with pytest.raises(ReportError, match=error):
        run_report_agent(
            analysis_path, model="local-model", transport=httpx.MockTransport(ollama)
        )
    assert analysis_path.exists()
    assert (analysis_path.parent / result.artifacts.importance_chart).exists()
    assert not analysis_path.with_name(REPORT_FILE).exists()


def test_report_rejects_invalid_analysis_before_contacting_ollama(tmp_path):
    analysis_path = tmp_path / ANALYSIS_FILE
    analysis_path.write_text("{}", encoding="utf-8")

    def ollama(request):
        pytest.fail("Invalid analysis must not be sent to Ollama")

    with pytest.raises(ReportError, match="Could not load analysis results"):
        run_report_agent(
            analysis_path, model="local-model", transport=httpx.MockTransport(ollama)
        )
