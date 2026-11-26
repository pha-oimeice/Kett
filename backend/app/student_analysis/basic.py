import numpy as np
import pandas as pd
from pydantic import BaseModel, FiniteFloat

from .contracts import AnalysisConfig, QualityEvidence


class DescriptiveStats(BaseModel):
    count: int
    mean: FiniteFloat
    median: FiniteFloat
    q1: FiniteFloat
    q3: FiniteFloat
    iqr: FiniteFloat


class BasicEvidence(BaseModel):
    filename: str
    rows: int
    columns: int
    selected_columns: list[str]
    statistics: dict[str, DescriptiveStats]
    missing_cells: int
    duplicate_rows: int
    infinite_values: int


def describe_table(
    data: pd.DataFrame, config: AnalysisConfig, quality: QualityEvidence
) -> BasicEvidence:
    selected = [config.target, *config.features]
    statistics = {}
    for name, column in data[selected].select_dtypes(include="number").items():
        values = column.astype(float)
        values = values[np.isfinite(values)]
        if values.empty:
            continue
        q1, median, q3 = values.quantile([0.25, 0.5, 0.75])
        statistics[name] = DescriptiveStats(
            count=len(values),
            mean=values.mean(),
            median=median,
            q1=q1,
            q3=q3,
            iqr=q3 - q1,
        )
    return BasicEvidence(
        filename=config.dataset_name or config.dataset_path.name,
        rows=len(data),
        columns=len(data.columns),
        selected_columns=selected,
        statistics=statistics,
        missing_cells=sum(quality.missing_by_column.values()),
        duplicate_rows=quality.duplicate_rows,
        infinite_values=sum(quality.infinite_by_column.values()),
    )
