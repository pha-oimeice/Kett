import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from .contracts import AnalysisConfig, FieldSchema


def inspect_schema(data: pd.DataFrame, config: AnalysisConfig) -> list[FieldSchema]:
    """Describe parsed columns and their assigned modeling roles without guessing field meanings."""
    fields = []
    features = set(config.features)
    for name, column in data.items():
        if not column.notna().any():
            kind = "unknown"
        elif is_bool_dtype(column):
            kind = "boolean"
        elif is_numeric_dtype(column):
            kind = "numeric"
        else:
            kind = "text"
        role = (
            "target"
            if name == config.target
            else "feature"
            if name in features
            else "unused"
        )
        fields.append(FieldSchema(name=name, kind=kind, role=role))
    return fields
