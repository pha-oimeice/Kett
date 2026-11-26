// The Kett backend talks to Ollama and the search service; see backend/app/chat.py.
import type { ReportLevel, ReportNotebook } from './notebook';
export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface Source {
  title: string;
  url: string;
}

export type ChatEvent =
  | { type: 'text'; text: string }
  | { type: 'status'; text: string }
  | { type: 'sources'; sources: Source[] }
  | { type: 'report'; notebook: ReportNotebook };

export async function listChatModels(signal?: AbortSignal): Promise<string[]> {
  const response = await fetch('/api/models', { signal, cache: 'no-store' });
  if (!response.ok)
    throw new Error('Could not load models from the configured server.');
  const data = await response.json();
  return Array.isArray(data)
    ? [
        ...new Set(
          data.filter((name): name is string => typeof name === 'string'),
        ),
      ]
    : [];
}

export async function* streamChat(
  model: string,
  messages: ChatMessage[],
  search: boolean,
  signal: AbortSignal,
  attachment?: {
    file: File;
    matEnabled: boolean;
    reportModel?: string;
    reportLevels: ReportLevel[];
  },
): AsyncGenerator<ChatEvent> {
  let response: Response;
  if (attachment) {
    const body = new FormData();
    body.append('file', attachment.file);
    const recent = messages
      .slice(-12)
      .map((message, index, history) =>
        index === history.length - 1
          ? message
          : { ...message, content: message.content.slice(0, 2500) },
      );
    body.append(
      'options',
      JSON.stringify({
        model,
        messages: recent,
        mat_enabled: attachment.matEnabled,
        report_model: attachment.reportModel,
        report_levels: attachment.reportLevels,
      }),
    );
    response = await fetch('/api/chat/attachments', {
      method: 'POST',
      body,
      signal,
    });
  } else {
    response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, messages, search }),
      signal,
    });
  }
  if (!response.ok || !response.body) {
    if (response.status === 403) {
      throw new Error(
        'the backend does not trust this address; open Kett at the APP_ORIGIN address (http://localhost:5173 by default)',
      );
    }
    const data = await response.json().catch(() => null);
    throw new Error(
      typeof data?.detail === 'string'
        ? data.detail
        : `the Kett backend returned ${response.status}`,
    );
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      if (event.type === 'error') throw new Error(event.message);
      yield event;
    }
  }
}
