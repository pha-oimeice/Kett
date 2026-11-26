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

from ..uploads import MAX_FILE_BYTES, one_file_form
from .contracts import (
    DEFAULT_REPORT_LEVELS,
    REPORT_LEVELS_ERROR,
    AnalysisConfig,
    ReportEvidence,
    ReportLevels,
)
from .notebook import ReportNotebook, report_cell
from .pipeline import collect_evidence
from .report import compose_report
from .scientist import AnalysisError

MAX_ROWS = 25_000
MAX_FEATURES = 32
MAX_COLUMNS = 128
active_run = Lock()
Delimiter = Literal[",", ";", "\t"]


class TableColumns(BaseModel):
    columns: list[str]
    delimiter: Delimiter
    rows: int
    max_features: int = MAX_FEATURES


class ReportOptions(BaseModel):
    target: str = Field(min_length=1, max_length=120)
    features: list[str] = Field(min_length=1, max_length=MAX_FEATURES)
    prediction_context: str = Field(default="", max_length=500)
    model: str | None = Field(default=None, max_length=200)
    report_levels: ReportLevels = DEFAULT_REPORT_LEVELS


class ReportResponse(BaseModel):
    notebook: ReportNotebook


@asynccontextmanager
async def table_form(request: Request):
    async with one_file_form(request, file_limit=MAX_FILE_BYTES) as (
        name,
        content,
        form,
    ):
        if Path(name).suffix.lower() not in {".csv", ".tsv"}:
            raise HTTPException(415, "Only structured CSV or TSV files are supported")
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
    return TableColumns(columns=columns, delimiter=delimiter, rows=count)


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
            reports = collect_evidence(config, directory, options.report_levels)
        except AnalysisError as exc:
            detail = (
                str(exc)
                if exc.__cause__ is None
                else "Could not read the dataset as a table"
            )
            raise HTTPException(422, detail) from None
        except ValueError:
            raise HTTPException(
                422, "The dataset could not be analyzed with these columns"
            ) from None

        cells = []
        for level, evidence in reports.items():
            markdown, mode = compose_report(evidence, directory, model=options.model)
            charts = ()
            if isinstance(evidence, ReportEvidence):
                charts = (
                    directory / evidence.artifacts.importance_chart,
                    directory / evidence.artifacts.prediction_chart,
                )
            cells.append(report_cell(level, markdown, mode, charts))
        return ReportResponse(notebook=ReportNotebook(cells=cells))


async def run_analysis_pipeline(
    name: str, content: bytes, options: ReportOptions
) -> ReportResponse:
    # Direct uploads and chat tool calls share the same worker limit.
    if not active_run.acquire(blocking=False):
        raise HTTPException(503, "Another report is running. Please try again shortly.")
    try:
        return await run_in_threadpool(generate_report, name, content, options)
    finally:
        active_run.release()


def create_analysis_router(require_same_origin: Callable) -> APIRouter:
    router = APIRouter(
        prefix="/api/analysis", dependencies=[Depends(require_same_origin)]
    )

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
            except ValidationError as exc:
                if any(
                    error["loc"][:1] == ("report_levels",) for error in exc.errors()
                ):
                    raise HTTPException(422, REPORT_LEVELS_ERROR) from None
                raise HTTPException(
                    422, f"Specify a target column and 1–{MAX_FEATURES} feature columns"
                ) from None
        return await run_analysis_pipeline(name, content, options)

    return router
