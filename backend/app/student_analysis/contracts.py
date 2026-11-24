from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, FiniteFloat, model_validator

ANALYSIS_FILE = "analysis.json"


class AnalysisConfig(BaseModel):
    dataset_path: Path
    target: str = Field(min_length=1)
    features: list[str] = Field(min_length=1)
    prediction_context: str = Field(min_length=1)
    dataset_source: str | None = None
    dataset_name: str | None = None
    delimiter: Literal[",", ";", "\t"] = ","
    random_seed: int = Field(default=42, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def check_columns(self):
        if not self.target.strip() or any(not name.strip() for name in self.features):
            raise ValueError("Target and feature column names must not be blank")
        if self.target in self.features:
            raise ValueError("The target column must not be used as a feature")
        if len(self.features) != len(set(self.features)):
            raise ValueError("Features must not contain duplicate columns")
        if not self.prediction_context.strip():
            raise ValueError("Prediction context must not be blank")
        return self


class TargetSummary(BaseModel):
    minimum: FiniteFloat
    median: FiniteFloat
    maximum: FiniteFloat


class DatasetSummary(BaseModel):
    filename: str
    source: str | None
    rows: int
    columns: int
    rows_dropped_missing_target: int
    missing_by_selected_column: dict[str, int]
    target_summary: TargetSummary


class Metrics(BaseModel):
    mae: FiniteFloat
    rmse: FiniteFloat
    r2: FiniteFloat | None


class Evaluation(BaseModel):
    random_seed: int
    train_rows: int
    test_rows: int
    numeric_features: list[str]
    categorical_features: list[str]
    forest_trees: int
    baseline: Metrics
    random_forest: Metrics


class FeatureImportance(BaseModel):
    feature: str
    mean_mae_increase: FiniteFloat


class Artifacts(BaseModel):
    model: Literal["model.joblib"] = "model.joblib"
    importance_chart: Literal["feature-importance.png"] = "feature-importance.png"
    prediction_chart: Literal["actual-vs-predicted.png"] = "actual-vs-predicted.png"


class AnalysisResult(BaseModel):
    target: str
    features: list[str]
    prediction_context: str
    dataset: DatasetSummary
    evaluation: Evaluation
    permutation_repeats: int
    feature_importance: list[FeatureImportance]
    artifacts: Artifacts = Field(default_factory=Artifacts)
