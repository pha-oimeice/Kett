# The Data Scientist Agent produces reproducible evidence in Python

The Data Scientist Agent is the **Analysis Agent** in the [target multi-agent architecture](../multi_agent_pipeline_architecture.png). The backend uses a Python pipeline to read tables, train models, and calculate metrics rather than asking an LLM to write analysis code or supply results. This makes the computation independently testable and keeps the evidence unchanged when the chat or report model changes, given the same data, settings, and environment.

## Responsibilities

| Role | Responsibility |
| --- | --- |
| **Supervisor (main chat model)** | Routes requests based on user intent. Inspecting a table does not train a model. If the requested regression target or features are unclear, the Supervisor asks for clarification. |
| **Data Scientist Agent** | Validates modeling inputs, trains and evaluates the model, and produces charts. It does not use an LLM and has no Ollama model selector. If algorithm selection is added, expose it as **Training algorithm**, separate from LLM settings. |
| **Report Agent** | Uses aggregate evidence (`analysis.json` in standalone runs) without reading the raw table or training a model. The writing model can be selected independently; code renders the metrics table directly from the evidence. |

## Current analysis rules

- **Inputs:** A UTF-8 CSV or TSV file, one numeric target column, one or more explicitly selected feature columns, and a prediction context. The pipeline checks that the columns exist and rejects the target as a feature. Users must decide which features are available at prediction time. For example, `G2` can be used to predict `G3` in the UCI math dataset only after `G2` is available.
- **Evaluation:** Drop rows with missing targets, then use a seeded 80/20 random train/test split (default seed: `42`). Fit numeric median imputation and categorical one-hot encoding on the training data only. Compare random forest regression against the training-set mean baseline on the same held-out test set. Report MAE, RMSE, and R²; R² is undefined when the test target is constant.
- **Evidence and artifacts:** Rank original columns by the mean increase in test MAE after shuffling each feature. Produce `analysis.json`, `model.joblib`, a feature-importance chart, and an actual-versus-predicted chart. Feature importance does not imply causation, and a single random split does not establish generalization to other schools or time periods.

## Integration with the analysis tool

The Data Scientist Agent handles the modeling branch for Advanced reports. The [Multi-Agent Data Analysis tool](../multi-agent-tool.md) adds separate **Schema Agent** and **Data Quality Agent** modules and combines their evidence with the modeling results before invoking the Report Agent. Basic reports use descriptive statistics without training. The standalone Data Scientist Agent still works without those branches.

Implementation: [training and evaluation](../../backend/app/student_analysis/scientist.py) · [analysis result contract](../../backend/app/student_analysis/contracts.py) · [report generation](../../backend/app/student_analysis/report.py)
