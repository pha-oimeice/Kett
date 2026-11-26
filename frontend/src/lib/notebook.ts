export type ReportLevel = 'basic' | 'advanced';

export interface ReportNotebook {
  nbformat: 4;
  nbformat_minor: 5;
  metadata: object;
  cells: {
    cell_type: 'markdown';
    id: ReportLevel;
    metadata: { kett_report_mode: 'ollama' | 'template' };
    source: string;
    attachments: Record<string, { 'image/png': string }>;
  }[];
}

export function notebookMarkdown(
  notebook: ReportNotebook,
  includeCharts = true,
) {
  return notebook.cells
    .map(({ source, attachments }) =>
      source.replace(/\]\(attachment:([^)]+)\)/g, (_, name: string) => {
        const png = attachments[name]?.['image/png'];
        return includeCharts && png
          ? `](data:image/png;base64,${png})`
          : '](chart-omitted.png)';
      }),
    )
    .join('\n\n');
}
