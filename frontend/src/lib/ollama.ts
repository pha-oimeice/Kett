// The Kett backend talks to Ollama and the search service; see backend/app/chat.py.
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
  | { type: 'sources'; sources: Source[] };

export async function listChatModels(signal?: AbortSignal): Promise<string[]> {
  const response = await fetch('/api/models', { signal, cache: 'no-store' });
  if (!response.ok)
    throw new Error('Could not load models from the configured server.');
  const data = await response.json();
  return Array.isArray(data)
    ? data.filter((name) => typeof name === 'string')
    : [];
}

export async function* streamChat(
  model: string,
  messages: ChatMessage[],
  search: boolean,
  signal: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, messages, search }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(
      response.status === 403
        ? 'the backend does not trust this address; open Kett at the APP_ORIGIN address (http://localhost:5173 by default)'
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
