import base64
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .contracts import ReportLevel
from .report import ReportMode


class ReportCell(BaseModel):
    cell_type: Literal["markdown"] = "markdown"
    id: ReportLevel
    metadata: dict[str, ReportMode]
    source: str
    attachments: dict[str, dict[Literal["image/png"], str]]


class ReportNotebook(BaseModel):
    nbformat: Literal[4] = 4
    nbformat_minor: Literal[5] = 5
    metadata: dict = Field(default_factory=dict)
    cells: list[ReportCell]


def report_cell(
    level: ReportLevel, report: str, mode: ReportMode, charts: tuple[Path, ...] = ()
) -> ReportCell:
    attachments = {}
    for chart in charts:
        report = report.replace(f"]({chart.name})", f"](attachment:{chart.name})")
        attachments[chart.name] = {
            "image/png": base64.b64encode(chart.read_bytes()).decode("ascii")
        }
    return ReportCell(
        id=level,
        metadata={"kett_report_mode": mode},
        source=report,
        attachments=attachments,
    )
