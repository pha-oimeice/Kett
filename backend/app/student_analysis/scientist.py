import csv
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from .contracts import (
    ANALYSIS_FILE,
    AnalysisConfig,
    AnalysisResult,
    DatasetSummary,
    Evaluation,
    FeatureImportance,
    Metrics,
    TargetSummary,
)

TEST_FRACTION = 0.2
MIN_LABELED_ROWS = 10
FOREST_TREES = 200
PERMUTATION_REPEATS = 10


class AnalysisError(ValueError):
    pass


def read_dataset(config: AnalysisConfig) -> pd.DataFrame:
    try:
        with config.dataset_path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, delimiter=config.delimiter, strict=True)
            header = next((row for row in reader if row), [])
            if not header or any(not name.strip() for name in header):
                raise AnalysisError(
                    "CSV must have a header with non-blank column names"
                )
            if len(set(header)) != len(header):
                raise AnalysisError("CSV column names must be unique")
            source.seek(0)
            data = pd.read_csv(source, sep=config.delimiter)
    except (OSError, UnicodeError, csv.Error, pd.errors.ParserError) as exc:
        raise AnalysisError(
            f"Could not read dataset {config.dataset_path}: {exc}"
        ) from exc

    if not isinstance(data.index, pd.RangeIndex):
        raise AnalysisError("CSV rows must not contain more fields than the header")
    missing = [name for name in [config.target, *config.features] if name not in data]
    if missing:
        raise AnalysisError(f"Columns missing from CSV: {', '.join(missing)}")
    return data


def score(actual, predicted) -> Metrics:
    return Metrics(
        mae=mean_absolute_error(actual, predicted),
        rmse=root_mean_squared_error(actual, predicted),
        r2=r2_score(actual, predicted) if actual.nunique() > 1 else None,
    )


def write_charts(result: AnalysisResult, actual, predicted, output_dir: Path) -> None:
    ranks = result.feature_importance[:10]
    figure = Figure(figsize=(8, max(3, 1.6 + 0.4 * len(ranks))), layout="constrained")
    FigureCanvasAgg(figure)
    ax = figure.subplots()
    positions = range(len(ranks))
    ax.barh(positions, [item.mean_mae_increase for item in ranks])
    ax.set_yticks(positions, [item.feature for item in ranks], parse_math=False)
    ax.invert_yaxis()
    ax.axvline(0, color="grey", linewidth=1)
    ax.set(
        xlabel="Mean increase in test MAE after shuffling", title="Feature importance"
    )
    figure.savefig(output_dir / result.artifacts.importance_chart, dpi=140)

    figure = Figure(figsize=(5.5, 5), layout="constrained")
    FigureCanvasAgg(figure)
    ax = figure.subplots()
    ax.scatter(actual, predicted, alpha=0.55, label="Test rows")
    bounds = [min(actual.min(), predicted.min()), max(actual.max(), predicted.max())]
    ax.plot(bounds, bounds, "--", color="grey", label="Perfect prediction")
    ax.set_aspect("equal", adjustable="box")
    ax.set(xlabel="Actual", ylabel="Predicted")
    ax.set_title(f"Actual vs. predicted: {result.target}", parse_math=False)
    ax.legend()
    figure.savefig(output_dir / result.artifacts.prediction_chart, dpi=140)


def run_data_scientist(config: AnalysisConfig, output_dir: Path) -> AnalysisResult:
    """Fit and evaluate a regression pipeline and write its artifacts to a run directory."""
    data = read_dataset(config)
    available = data[config.target].notna()
    observed = data.loc[available, config.target]
    y = pd.to_numeric(observed, errors="coerce")
    if pd.api.types.is_bool_dtype(y) or not np.isfinite(y).all():
        raise AnalysisError(
            f"Target {config.target!r} must contain finite numeric values"
        )
    if len(y) < MIN_LABELED_ROWS or y.nunique() < 2:
        raise AnalysisError(
            f"Need at least {MIN_LABELED_ROWS} labeled rows and two distinct target values"
        )

    x = data.loc[available, config.features]
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=TEST_FRACTION, random_state=config.random_seed
    )
    numeric = x_train.select_dtypes(include="number").columns.tolist()
    if np.isinf(x[numeric].to_numpy(dtype=float)).any():
        raise AnalysisError("Numeric features must not contain infinite values")
    categorical = [name for name in config.features if name not in numeric]
    preprocess = ColumnTransformer(
        [
            (
                "numeric",
                SimpleImputer(strategy="median", keep_empty_features=True),
                numeric,
            ),
            (
                "categorical",
                OneHotEncoder(handle_unknown="infrequent_if_exist", max_categories=64),
                categorical,
            ),
        ]
    )
    model = Pipeline(
        [
            ("preprocess", preprocess),
            (
                "regressor",
                RandomForestRegressor(
                    n_estimators=FOREST_TREES, random_state=config.random_seed
                ),
            ),
        ]
    )
    model.fit(x_train, y_train)
    predicted = model.predict(x_test)
    baseline = DummyRegressor(strategy="mean").fit(x_train, y_train)
    permutation = permutation_importance(
        model,
        x_test,
        y_test,
        scoring="neg_mean_absolute_error",
        n_repeats=PERMUTATION_REPEATS,
        random_state=config.random_seed,
    )
    ranks = sorted(
        (
            FeatureImportance(feature=name, mean_mae_increase=value)
            for name, value in zip(
                config.features, permutation.importances_mean, strict=True
            )
        ),
        key=lambda item: item.mean_mae_increase,
        reverse=True,
    )
    result = AnalysisResult(
        target=config.target,
        features=config.features,
        prediction_context=config.prediction_context,
        dataset=DatasetSummary(
            filename=config.dataset_name or config.dataset_path.name,
            source=config.dataset_source,
            rows=len(data),
            columns=len(data.columns),
            rows_dropped_missing_target=len(data) - len(y),
            missing_by_selected_column=data[[config.target, *config.features]]
            .isna()
            .sum()
            .to_dict(),
            target_summary=TargetSummary(
                minimum=y.min(), median=y.median(), maximum=y.max()
            ),
        ),
        evaluation=Evaluation(
            random_seed=config.random_seed,
            train_rows=len(x_train),
            test_rows=len(x_test),
            numeric_features=numeric,
            categorical_features=categorical,
            forest_trees=FOREST_TREES,
            baseline=score(y_test, baseline.predict(x_test)),
            random_forest=score(y_test, predicted),
        ),
        permutation_repeats=PERMUTATION_REPEATS,
        feature_importance=ranks,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output_dir / result.artifacts.model)
    write_charts(result, y_test, predicted, output_dir)
    (output_dir / ANALYSIS_FILE).write_text(
        result.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return result
