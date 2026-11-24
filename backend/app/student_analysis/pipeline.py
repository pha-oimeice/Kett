from pathlib import Path

from .contracts import ANALYSIS_FILE, AnalysisConfig, ReportEvidence
from .quality import inspect_quality
from .schema import inspect_schema
from .scientist import fit_data_scientist, read_dataset


def collect_evidence(config: AnalysisConfig, output_dir: Path) -> ReportEvidence:
    """Run the Schema, Data Quality, and Data Scientist agents on one parsed table."""
    data = read_dataset(config)
    schema = inspect_schema(data, config)
    quality = inspect_quality(data)
    analysis = fit_data_scientist(data, config, output_dir)
    evidence = ReportEvidence(
        **analysis.model_dump(), schema_evidence=schema, quality_evidence=quality
    )
    (output_dir / ANALYSIS_FILE).write_text(
        evidence.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return evidence
