export interface DatasetColumns {
  columns: string[];
  delimiter: ',' | ';' | '\t';
  max_features: number;
}

export interface DatasetOptions {
  target: string;
  features: string[];
  prediction_context?: string;
  model?: string;
}

export interface DatasetReport {
  report: string;
  mode: 'ollama' | 'template';
}

async function upload<T>(
  action: 'columns' | 'report',
  file: File,
  signal: AbortSignal,
  options?: DatasetOptions,
): Promise<T> {
  const body = new FormData();
  body.append('file', file);
  if (options) body.append('options', JSON.stringify(options));
  const response = await fetch(`/api/analysis/${action}`, {
    method: 'POST',
    body,
    signal,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      typeof data?.detail === 'string'
        ? data.detail
        : `The analysis backend returned HTTP ${response.status}.`,
    );
  }
  if (!data) throw new Error('The analysis backend did not return a result.');
  return data;
}

export function inspectDataset(file: File, signal: AbortSignal) {
  return upload<DatasetColumns>('columns', file, signal);
}

export function generateDatasetReport(
  file: File,
  options: DatasetOptions,
  signal: AbortSignal,
) {
  return upload<DatasetReport>('report', file, signal, options);
}
