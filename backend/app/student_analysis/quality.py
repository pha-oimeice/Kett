import numpy as np
import pandas as pd

from .contracts import QualityEvidence


def inspect_quality(data: pd.DataFrame) -> QualityEvidence:
    """Check the full table before filtering or splitting; do not change any rows."""
    numeric = data.select_dtypes(include="number")
    infinite = np.isinf(numeric).sum()
    return QualityEvidence(
        missing_by_column=data.isna().sum().to_dict(),
        duplicate_rows=int(data.duplicated().sum()),
        infinite_by_column={
            name: int(count) for name, count in infinite.items() if count
        },
    )
