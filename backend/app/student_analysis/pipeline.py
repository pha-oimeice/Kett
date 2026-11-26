from pathlib import Path

from .basic import BasicEvidence, describe_table
from .contracts import AnalysisConfig, ReportEvidence, ReportLevel, ReportLevels
from .quality import inspect_quality
from .schema import inspect_schema
from .scientist import fit_data_scientist, read_dataset


def collect_evidence(
    config: AnalysisConfig, output_dir: Path, levels: ReportLevels
) -> dict[ReportLevel, BasicEvidence | ReportEvidence]:
    """Build separate report inputs from one parsed table, in notebook order."""
    data = read_dataset(config)
    quality = inspect_quality(data)
    reports: dict[ReportLevel, BasicEvidence | ReportEvidence] = {}
    if "basic" in levels:
        reports["basic"] = describe_table(data, config, quality)
    if "advanced" in levels:
        schema = inspect_schema(data, config)
        analysis = fit_data_scientist(data, config, output_dir)
        reports["advanced"] = ReportEvidence(
            **analysis.model_dump(), schema_evidence=schema, quality_evidence=quality
        )
    return reports
