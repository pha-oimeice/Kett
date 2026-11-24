import base64
import csv
import io
import tempfile
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from .contracts import ANALYSIS_FILE, AnalysisConfig
from .report import ReportError, render_template_report, run_report_agent
from .scientist import AnalysisError, run_data_scientist

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_FORM_BYTES = MAX_FILE_BYTES + 64 * 1024
MAX_ROWS = 25_000
MAX_FEATURES = 32
MAX_COLUMNS = 128
Delimiter = Literal[",", ";", "\t"]


class TableColumns(BaseModel):
    columns: list[str]
    delimiter: Delimiter
    max_features: int = MAX_FEATURES


class ReportOptions(BaseModel):
    target: str = Field(min_length=1, max_length=120)
    features: list[str] = Field(min_length=1, max_length=MAX_FEATURES)
    prediction_context: str = Field(default="", max_length=500)
    model: str | None = Field(default=None, max_length=200)


class ReportResponse(BaseModel):
    report: str
    mode: Literal["ollama", "template"]


@asynccontextmanager
async def table_form(request: Request):
    if (
        request.headers.get("content-type", "").split(";", 1)[0]
        != "multipart/form-data"
    ):
        raise HTTPException(415, "Use a multipart form with one CSV or TSV file")
    if "transfer-encoding" in request.headers:
        raise HTTPException(411, "Dataset uploads must have a fixed Content-Length")
    try:
        length = int(request.headers.get("content-length", ""))
    except ValueError:
        raise HTTPException(
            411, "Content-Length is required for dataset uploads"
        ) from None
    if not 0 < length <= MAX_FORM_BYTES:
        raise HTTPException(413, "Dataset uploads are limited to 5 MiB")
    async with request.form(max_files=1, max_fields=1, max_part_size=16 * 1024) as form:
        upload = form.get("file")
        if not isinstance(upload, UploadFile) or not upload.filename:
            raise HTTPException(422, "Select one CSV or TSV file")
        name = upload.filename.replace("\\", "/").rsplit("/", 1)[-1]
        if Path(name).suffix.lower() not in {".csv", ".tsv"}:
            raise HTTPException(415, "Only structured CSV or TSV files are supported")
        if len(name) > 200:
            raise HTTPException(422, "Dataset filename is too long")
        content = await upload.read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(413, "Dataset uploads are limited to 5 MiB")
        yield name, content, form.get("options")


def inspect_table(name: str, content: bytes) -> TableColumns:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "Save the table as UTF-8 CSV or TSV") from None
    if "\x00" in text:
        raise HTTPException(422, "The uploaded file is not a valid text table")
    candidates: tuple[Delimiter, ...] = (
        ("\t",) if name.lower().endswith(".tsv") else (",", ";", "\t")
    )
    columns: list[str] = []
    delimiter: Delimiter = candidates[0]
    for candidate in candidates:
        try:
            reader = csv.reader(
                io.StringIO(text, newline=""), delimiter=candidate, strict=True
            )
            header = next((row for row in reader if row), [])
        except csv.Error:
            continue
        if len(header) > len(columns):
            delimiter, columns = candidate, header
    if not 2 <= len(columns) <= MAX_COLUMNS or any(
        not column.strip() or len(column) > 120 for column in columns
    ):
        raise HTTPException(
            422,
            f"The table must have 2–{MAX_COLUMNS} named columns (up to 120 characters per name)",
        )
    if len(set(columns)) != len(columns):
        raise HTTPException(422, "Table column names must be unique")

    try:
        reader = csv.reader(
            io.StringIO(text, newline=""), delimiter=delimiter, strict=True
        )
        rows = (row for row in reader if row)
        next(rows)  # Header was checked above.
        count = 0
        for count, row in enumerate(rows, start=1):
            if len(row) != len(columns):
                raise HTTPException(
                    422, f"Data row {count} does not match the header's column count"
                )
            if count > MAX_ROWS:
                raise HTTPException(
                    422, f"Dataset must contain at most {MAX_ROWS:,} rows"
                )
    except csv.Error:
        raise HTTPException(
            422, "The uploaded file is not a valid text table"
        ) from None
    if not count:
        raise HTTPException(422, "The table has no data rows")
    return TableColumns(columns=columns, delimiter=delimiter)


def generate_report(
    name: str, content: bytes, options: ReportOptions
) -> ReportResponse:
    table = inspect_table(name, content)
    with tempfile.TemporaryDirectory(prefix="kett-analysis-") as workspace:
        directory = Path(workspace)
        dataset_path = directory / "table.csv"
        try:
            config = AnalysisConfig(
                dataset_name=name,
                dataset_path=dataset_path,
                target=options.target,
                features=options.features,
                delimiter=table.delimiter,
                prediction_context=options.prediction_context.strip()
                or "Not specified; verify which features are available at prediction time.",
            )
        except ValidationError as exc:
            raise HTTPException(422, exc.errors()[0]["msg"]) from None
        dataset_path.write_bytes(content)
        try:
            analysis = run_data_scientist(config, directory)
        except AnalysisError as exc:
            detail = (
                str(exc)
                if exc.__cause__ is None
                else "Could not read the dataset as a table"
            )
            raise HTTPException(422, detail) from None
        except ValueError:
            raise HTTPException(
                422, "The dataset could not be modeled with these columns"
            ) from None

        mode: Literal["ollama", "template"] = "template"
        note = "No Ollama model was selected."
        if options.model and options.model.strip():
            try:
                path = run_report_agent(directory / ANALYSIS_FILE, model=options.model)
                report = path.read_text(encoding="utf-8")
                mode = "ollama"
            except ReportError:
                note = "The selected Ollama model could not generate the report."
        if mode == "template":
            report = render_template_report(analysis, directory, note=note)

        # Embed the plots so the browser and the downloaded report outlive the temp files.
        for label, chart in (
            ("Feature importance", analysis.artifacts.importance_chart),
            ("Actual vs. predicted", analysis.artifacts.prediction_chart),
        ):
            image = base64.b64encode((directory / chart).read_bytes()).decode("ascii")
            report = report.replace(
                f"![{label}]({chart})", f"![{label}](data:image/png;base64,{image})"
            )
        return ReportResponse(report=report, mode=mode)


def create_analysis_router(require_same_origin: Callable) -> APIRouter:
    router = APIRouter(
        prefix="/api/analysis", dependencies=[Depends(require_same_origin)]
    )
    active_run = Lock()

    @router.post("/columns")
    async def columns(request: Request) -> TableColumns:
        async with table_form(request) as (name, content, _):
            return await run_in_threadpool(inspect_table, name, content)

    @router.post("/report")
    async def report(request: Request) -> ReportResponse:
        async with table_form(request) as (name, content, raw_options):
            try:
                options = ReportOptions.model_validate_json(
                    raw_options if isinstance(raw_options, str) else "{}"
                )
            except ValidationError:
                raise HTTPException(
                    422, f"Specify a target column and 1–{MAX_FEATURES} feature columns"
                ) from None
        if not active_run.acquire(blocking=False):
            raise HTTPException(
                503, "Another report is running. Please try again shortly."
            )
        try:
            return await run_in_threadpool(generate_report, name, content, options)
        finally:
            active_run.release()

    return router
