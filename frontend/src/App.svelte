<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { marked } from 'marked';
  import DOMPurify from 'dompurify';
  import Icon from './lib/Icon.svelte';
  import {
    suggestions,
    seedConversations,
    demoReply,
    artifactSource,
    type Conversation,
    type Message,
    type Attachment,
  } from './lib/demo';

  let conversations = $state<Conversation[]>(seedConversations());
  let activeId = $state<string | null>(null);
  let input = $state('');
  let sidebarOpen = $state(true);
  let mobileSidebar = $state(false);
  let searchOpen = $state(false);
  let search = $state('');
  let settingsOpen = $state(false);
  let projectsOpen = $state(false);
  let projectName = $state('');
  let projects = $state(['Personal website', 'Ideas & inspiration']);
  let selectedProject = $state('');
  let dark = $state(false);
  let model = $state('Claude Sonnet 4.5');
  let modelMenu = $state(false);
  let thinking = $state(false);
  let streaming = $state(false);
  let workbench = $state(false);
  let previewTab = $state<'preview' | 'code'>('preview');
  let attachments = $state<Attachment[]>([]);
  let notification = $state('');
  let copiedId = $state('');
  let clearConfirm = $state(false);
  let loaded = $state(false);
  let textarea: HTMLTextAreaElement;
  let fileInput: HTMLInputElement;
  let messageArea = $state<HTMLDivElement>();
  let streamTimer: ReturnType<typeof setInterval> | undefined;
  let toastTimer: ReturnType<typeof setTimeout>;
  let copyTimer: ReturnType<typeof setTimeout>;
  const models = ['Claude Sonnet 4.5', 'Claude Opus 4.5', 'GPT-5.2'];
  const active = $derived(conversations.find((c) => c.id === activeId));
  const messages = $derived(active?.messages ?? []);
  const filtered = $derived(
    conversations.filter((c) =>
      c.title.toLowerCase().includes(search.toLowerCase()),
    ),
  );
  const today = $derived(
    conversations.filter((c) => Date.now() - c.updatedAt < 86400000),
  );
  const older = $derived(
    conversations.filter((c) => Date.now() - c.updatedAt >= 86400000),
  );

  onMount(() => {
    try {
      const saved = JSON.parse(
        localStorage.getItem('kett-workspace-v1') ?? 'null',
      );
      if (saved && Array.isArray(saved.conversations)) {
        const defaults = seedConversations();
        const projectNames: Record<string, string> = {
          个人网站: 'Personal website',
          灵感收集站: 'Ideas & inspiration',
        };
        conversations = saved.conversations
          .filter(
            (c: Conversation) =>
              typeof c.id === 'string' &&
              typeof c.title === 'string' &&
              Array.isArray(c.messages),
          )
          .map((c: Conversation) => {
            const demo = defaults.find((item) => item.id === c.id);
            return {
              ...c,
              title: demo?.title ?? c.title,
              project: c.project
                ? (projectNames[c.project] ?? c.project)
                : undefined,
              messages: c.messages.map((message) => ({
                ...message,
                content:
                  demo?.messages.find((item) => item.id === message.id)
                    ?.content ?? message.content,
              })),
            };
          });
        dark = !!saved.dark;
        if (Array.isArray(saved.projects))
          projects = saved.projects
            .filter((p: unknown) => typeof p === 'string')
            .map((name: string) => projectNames[name] ?? name);
      }
    } catch {
      /* An unavailable or invalid local store should not block the UI. */
    }
    loaded = true;
    return () => {
      clearInterval(streamTimer);
      clearTimeout(toastTimer);
      clearTimeout(copyTimer);
    };
  });

  $effect(() => {
    if (!loaded) return;
    try {
      localStorage.setItem(
        'kett-workspace-v1',
        JSON.stringify({ conversations, dark, projects }),
      );
    } catch {
      /* The workspace also works without persistent browser storage. */
    }
  });

  function notify(text: string) {
    notification = text;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (notification = ''), 3000);
  }

  function stop() {
    clearInterval(streamTimer);
    streaming = false;
  }

  function newChat(project = '') {
    stop();
    activeId = null;
    input = '';
    attachments = [];
    selectedProject = project;
    workbench = false;
    mobileSidebar = false;
    tick().then(() => textarea?.focus());
  }

  function openChat(id: string) {
    stop();
    activeId = id;
    input = '';
    attachments = [];
    selectedProject = conversations.find((c) => c.id === id)?.project ?? '';
    searchOpen = false;
    mobileSidebar = false;
    workbench = false;
    tick().then(scrollBottom);
  }

  function deleteChat(id: string) {
    if (activeId === id) newChat();
    conversations = conversations.filter((c) => c.id !== id);
    notify('Conversation deleted');
  }

  function scrollBottom() {
    if (messageArea) messageArea.scrollTop = messageArea.scrollHeight;
  }

  async function send() {
    if (streaming || (!input.trim() && !attachments.length)) return;
    const text = input.trim() || 'Could you take a look at these attachments?';
    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      attachments: [...attachments],
    };
    if (!activeId) {
      const id = crypto.randomUUID();
      conversations = [
        {
          id,
          title: text.slice(0, 20) + (text.length > 20 ? '…' : ''),
          messages: [],
          updatedAt: Date.now(),
          project: selectedProject || undefined,
        },
        ...conversations,
      ];
      activeId = id;
    }
    const conversation = conversations.find((c) => c.id === activeId)!;
    conversation.messages.push(userMessage);
    conversation.updatedAt = Date.now();
    conversations = [...conversations].sort(
      (a, b) => b.updatedAt - a.updatedAt,
    );
    input = '';
    attachments = [];
    await respond(conversation, text);
  }

  async function respond(conversation: Conversation, text: string) {
    const reply = demoReply(text);
    const id = crypto.randomUUID();
    conversation.messages.push({ id, role: 'assistant', content: '' });
    streaming = true;
    await tick();
    scrollBottom();
    let position = 0;
    streamTimer = setInterval(async () => {
      const message = conversation.messages.find((m) => m.id === id);
      if (!message) {
        stop();
        return;
      }
      position += 7;
      message.content = reply.content.slice(0, position);
      if (position >= reply.content.length) {
        message.artifact = reply.artifact;
        stop();
      }
      await tick();
      scrollBottom();
    }, 18);
  }

  function useSuggestion(prompt: string) {
    input = prompt;
    textarea?.focus();
  }

  function keyboard(event: KeyboardEvent) {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      searchOpen = !searchOpen;
      search = '';
    }
    if (event.key === 'Escape') {
      searchOpen = false;
      settingsOpen = false;
      projectsOpen = false;
      modelMenu = false;
      mobileSidebar = false;
    }
  }

  function inputKey(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      send();
    }
  }

  function attach(event: Event) {
    const files = (event.target as HTMLInputElement).files;
    if (files) {
      const additions = Array.from(files)
        .slice(0, 5 - attachments.length)
        .map((file) => ({
          name: file.name,
          size:
            file.size > 1048576
              ? `${(file.size / 1048576).toFixed(1)} MB`
              : `${Math.max(1, Math.round(file.size / 1024))} KB`,
        }));
      attachments = [...attachments, ...additions];
      notify(
        'Attachment added · Files are not uploaded or analyzed in this demo',
      );
    }
    fileInput.value = '';
  }

  async function copy(text: string, id: string) {
    try {
      await navigator.clipboard.writeText(text);
      copiedId = id;
      clearTimeout(copyTimer);
      copyTimer = setTimeout(() => (copiedId = ''), 2000);
    } catch {
      notify(
        'Clipboard unavailable. Please select and copy the text manually.',
      );
    }
  }

  function download(content: string, filename: string, type = 'text/plain') {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    notify('File exported');
  }

  function addProject(event: SubmitEvent) {
    event.preventDefault();
    const name = projectName.trim();
    if (!name) return;
    if (projects.includes(name)) {
      notify('A project with this name already exists');
      return;
    }
    projects = [...projects, name];
    projectName = '';
    notify('Project created');
  }

  function retry() {
    if (!active || streaming) return;
    const lastUser = [...active.messages]
      .reverse()
      .find((m) => m.role === 'user');
    if (!lastUser) return;
    if (active.messages.at(-1)?.role === 'assistant') active.messages.pop();
    respond(active, lastUser.content);
  }

  function focusDialog(node: HTMLDivElement) {
    const previous = document.activeElement as HTMLElement | null;
    const focusable = () =>
      Array.from(
        node.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input, [tabindex="0"]',
        ),
      );
    (focusable()[0] ?? node).focus();
    function trap(event: KeyboardEvent) {
      if (event.key !== 'Tab') return;
      const items = focusable();
      const first = items[0];
      const last = items.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
    node.addEventListener('keydown', trap);
    return {
      destroy() {
        node.removeEventListener('keydown', trap);
        previous?.focus();
      },
    };
  }

  function renderMarkdown(text: string) {
    return DOMPurify.sanitize(
      marked.parse(text, { breaks: true, async: false }) as string,
    );
  }
</script>

<svelte:window
  onkeydown={keyboard}
  onpointerdown={(event) => {
    if (modelMenu && !(event.target as Element)?.closest('.model-select'))
      modelMenu = false;
  }}
/>

<div class:dark class="app-shell">
  {#if mobileSidebar}<button
      class="mobile-scrim"
      aria-label="Close sidebar"
      onclick={() => (mobileSidebar = false)}
    ></button>{/if}
  <aside
    class:collapsed={!sidebarOpen}
    class:mobile-open={mobileSidebar}
    class="sidebar"
  >
    <div class="sidebar-top">
      <button class="brand" onclick={() => newChat()} aria-label="Kett home">
        <span class="brand-mark">
          <span></span><span></span><span></span><span></span>
        </span>
        <span class="brand-name">kett<span class="brand-dot">.</span></span>
      </button>
      <button
        class="icon-button sidebar-hide"
        aria-label="Collapse sidebar"
        title="Collapse sidebar"
        onclick={() => {
          sidebarOpen = false;
          mobileSidebar = false;
        }}
      >
        <Icon name="panel" size={18} />
      </button>
    </div>

    <button class="new-chat" onclick={() => newChat()}>
      <Icon name="plus" size={18} /><span>New conversation</span><span
        class="new-shortcut"
      >
        ↗
      </span>
    </button>
    <nav class="primary-nav" aria-label="Workspace navigation">
      <button
        onclick={() => {
          searchOpen = true;
          search = '';
        }}
      >
        <Icon name="search" size={18} /><span>Search conversations</span><kbd>
          ⌘ K
        </kbd>
      </button>
      <button onclick={() => (projectsOpen = true)}>
        <Icon name="folder" size={18} /><span>My projects</span><span
          class="nav-count"
        >
          {projects.length}
        </span>
      </button>
    </nav>

    <div class="history">
      <div class="section-caption">
        Recent conversations <span><Icon name="clock" size={13} /></span>
      </div>
      {#each [{ label: 'Today', items: today }, { label: 'Previous days', items: older }] as group}
        {#if group.items.length}
          <div class="history-label">{group.label}</div>
          {#each group.items as chat (chat.id)}
            <div class:active={activeId === chat.id} class="history-item">
              <button class="history-link" onclick={() => openChat(chat.id)}>
                <Icon name="chat" size={16} /><span>{chat.title}</span>
              </button>
              <button
                class="history-delete icon-button"
                aria-label={`Delete conversation: ${chat.title}`}
                onclick={() => deleteChat(chat.id)}
              >
                <Icon name="trash" size={14} />
              </button>
            </div>
          {/each}
        {/if}
      {/each}
      {#if !conversations.length}<p class="empty-history">
          No conversations yet.<br />Start with a little idea.
        </p>{/if}
      <div class="sidebar-note">
        <span class="note-line"></span>
        <p>A little room to think.<br />A little space to grow.</p>
        <Icon name="leaf" size={25} />
      </div>
    </div>

    <div class="sidebar-bottom">
      <button
        class="local-banner"
        onclick={() =>
          notify(
            'Frontend demo · Conversations stay in this browser, never sent to a server',
          )}
      >
        <span class="status-dot"></span><span>Local demo workspace</span><Icon
          name="external"
          size={13}
        />
      </button>
      <button
        class="profile"
        aria-label="Open workspace settings"
        onclick={() => (settingsOpen = true)}
      >
        <span class="avatar">L<span></span></span><span class="profile-text">
          <strong>Lin</strong><span>
            Personal workspace <Icon name="down" size={11} />
          </span>
        </span><Icon name="settings" size={17} />
      </button>
    </div>
  </aside>

  <main class="main">
    <header class="topbar">
      <div class="breadcrumb">
        <button
          class="icon-button sidebar-show"
          class:visible={!sidebarOpen}
          aria-label="Expand sidebar"
          onclick={() => {
            sidebarOpen = true;
            mobileSidebar = true;
          }}
        >
          <Icon name="panel" size={19} />
        </button>
        <span class="workspace-icon">
          <Icon name={selectedProject ? 'folder' : 'grid'} size={15} />
        </span><span>{selectedProject || 'Personal space'}</span><span
          class="breadcrumb-slash"
        >
          /
        </span><span class="breadcrumb-current">
          {active ? active.title : 'New conversation'}
        </span>
      </div>
      <div class="header-actions">
        <span class="private-label">
          <span class="status-dot"></span>Only you
        </span>
        <div class="view-switch">
          <button class:chosen={!workbench} onclick={() => (workbench = false)}>
            <Icon name="chat" size={14} /><span>Chat</span>
          </button><button
            class:chosen={workbench}
            onclick={() => (workbench = true)}
          >
            <Icon name="code" size={15} /><span>Workbench</span>
          </button>
        </div>
        {#if active}<button
            class="icon-button export-chat"
            title="Export conversation"
            aria-label="Export conversation"
            onclick={() =>
              download(
                active!.messages
                  .map(
                    (m) =>
                      `## ${m.role === 'user' ? 'You' : 'Kett'}\n\n${m.content}`,
                  )
                  .join('\n\n---\n\n'),
                'kett-conversation.md',
              )}
          >
            <Icon name="download" size={17} />
          </button>{/if}
      </div>
    </header>

    <div class="workspace-body" class:with-workbench={workbench}>
      <section
        class="conversation-pane"
        class:has-messages={messages.length > 0}
        aria-label="Chat area"
      >
        {#if !messages.length}
          <div class="welcome-scroll">
            <div class="welcome">
              <div class="welcome-eyebrow">
                <span class="tiny-sun">✳</span><span>
                  YOUR SPACE TO THINK
                </span><span class="eyebrow-line"></span>
              </div>
              <h1>
                A little clarity.<br />A lot of
                <span class="headline-accent">
                  possibility<svg
                    class="headline-scribble"
                    viewBox="0 0 150 12"
                    aria-hidden="true"
                  >
                    <path d="M3 8C40 0 100 2 147 6M24 10c35-4 72-3 99-1" />
                  </svg>
                </span>.
              </h1>
              <p class="welcome-description">
                A question, a line of code, or an idea still taking shape.<br
                  class="desktop-break"
                />Wherever you start, let's take the next step together.
              </p>
              <div class="welcome-composer-slot">
                {@render composer()}
              </div>
              <div class="suggestions-header">
                <span>A few places to begin</span><span class="suggestions-line"
                ></span><Icon name="spark" size={13} />
              </div>
              <div class="suggestions">
                {#each suggestions as suggestion}<button
                    class="suggestion-card {suggestion.color}"
                    onclick={() => useSuggestion(suggestion.prompt)}
                  >
                    <span class="suggestion-top">
                      <span class="suggestion-icon">
                        <Icon name={suggestion.icon} size={19} />
                      </span><span class="suggestion-arrow">↗</span>
                    </span><strong>{suggestion.title}</strong>
                    <p>{suggestion.text}</p>
                    <span class="suggestion-tag">{suggestion.tag}</span>
                  </button>{/each}
              </div>
              <p class="welcome-footnote">
                <Icon name="leaf" size={14} /> You don't need all the answers. Just
                a beginning.
              </p>
            </div>
          </div>
        {:else}
          <div
            class="messages"
            bind:this={messageArea}
            role="log"
            aria-label="Conversation history"
            aria-busy={streaming}
          >
            <div class="message-list">
              <div class="conversation-date">A little time for a good idea</div>
              {#each messages as message (message.id)}
                <article class="message {message.role}">
                  <div class="message-avatar">
                    {#if message.role === 'user'}L{:else}<span
                        class="assistant-sun"
                      >
                        ✳
                      </span>{/if}
                  </div>
                  <div class="message-body">
                    <div class="message-name">
                      {message.role === 'user'
                        ? 'You'
                        : 'Kett'}{#if message.role === 'assistant'}<span>
                          {model}
                        </span>{/if}
                    </div>
                    {#if message.attachments?.length}<div
                        class="message-attachments"
                      >
                        {#each message.attachments as file}<span>
                            <Icon name="file" size={15} />{file.name}<small>
                              {file.size}
                            </small>
                          </span>{/each}
                      </div>{/if}
                    {#if message.role === 'user'}<div class="user-text">
                        {message.content}
                      </div>{:else}<div class="markdown">
                        {@html renderMarkdown(message.content)}
                      </div>
                      {#if !message.content && streaming}<span class="typing">
                          <i></i><i></i><i></i>
                        </span>{/if}{/if}
                    {#if message.artifact}<button
                        class="artifact-card"
                        onclick={() => (workbench = true)}
                      >
                        <span class="artifact-icon">
                          <Icon name="code" size={22} />
                        </span><span>
                          <strong>Slow Isle · Coffee website</strong><small>
                            Website artifact · HTML / CSS
                          </small>
                        </span><Icon name="external" size={17} />
                      </button>{/if}
                    {#if message.role === 'assistant' && message.content && (!streaming || message.id !== messages.at(-1)?.id)}<div
                        class="message-actions"
                      >
                        <button
                          class="icon-button"
                          aria-label="Copy response"
                          title="Copy response"
                          onclick={() => copy(message.content, message.id)}
                        >
                          <Icon
                            name={copiedId === message.id ? 'check' : 'copy'}
                            size={15}
                          />
                        </button><button
                          class:liked={message.liked}
                          class="icon-button"
                          aria-pressed={!!message.liked}
                          aria-label="Like this response"
                          title="Like"
                          onclick={() => (message.liked = !message.liked)}
                        >
                          <Icon name="thumbs" size={15} />
                        </button>{#if message.id === messages.at(-1)?.id}<button
                            class="icon-button"
                            aria-label="Regenerate"
                            title="Regenerate demo response"
                            onclick={retry}
                          >
                            <Icon name="refresh" size={15} />
                          </button>{/if}<span>Local demo response</span>
                      </div>{/if}
                  </div>
                </article>
              {/each}
            </div>
          </div>
          <div class="chat-composer">
            {@render composer()}
            <div class="chat-disclaimer">
              <span class="status-dot"></span>Frontend demo · No AI connected ·
              Saved on this device
            </div>
          </div>
        {/if}
        {#if !messages.length}<footer class="main-footer">
            <span>KETT / A SPACE FOR POSSIBILITY</span><span>
              Frontend demo <span class="footer-dot">·</span> Stored locally
            </span>
          </footer>{/if}
      </section>

      {#if workbench}
        <aside class="workbench" aria-label="Code workbench">
          <div class="workbench-heading">
            <span>
              <span class="workbench-dot"></span>Slow Isle · Brand website
              <span class="demo-badge">DEMO</span>
            </span><button
              class="icon-button"
              aria-label="Close workbench"
              onclick={() => (workbench = false)}
            >
              <Icon name="close" size={17} />
            </button>
          </div>
          <div class="workbench-toolbar">
            <div class="preview-tabs">
              <button
                class:active={previewTab === 'preview'}
                onclick={() => (previewTab = 'preview')}
              >
                <Icon name="grid" size={13} />Preview
              </button><button
                class:active={previewTab === 'code'}
                onclick={() => (previewTab = 'code')}
              >
                <Icon name="code" size={14} />Code
              </button>
            </div>
            <div>
              <button
                class="icon-button"
                aria-label="Copy source"
                title="Copy source"
                onclick={() => copy(artifactSource, 'artifact')}
              >
                <Icon
                  name={copiedId === 'artifact' ? 'check' : 'copy'}
                  size={15}
                />
              </button><button
                class="icon-button"
                aria-label="Download HTML"
                title="Download HTML"
                onclick={() =>
                  download(artifactSource, 'slow-isle-cafe.html', 'text/html')}
              >
                <Icon name="download" size={16} />
              </button>
            </div>
          </div>
          {#if previewTab === 'preview'}<div class="browser-bar">
              <span class="browser-dots"><i></i><i></i><i></i></span><span>
                <Icon name="file" size={11} /> slow-isle-cafe / index.html
              </span><Icon name="refresh" size={12} />
            </div>
            <iframe
              title="Slow Isle coffee website preview"
              srcdoc={artifactSource}
              sandbox=""
            ></iframe>{:else}<div class="code-filename">
              <Icon name="code" size={14} />index.html<span>HTML</span>
            </div>
            <pre class="artifact-code"><code>{artifactSource}</code></pre>{/if}
          <div class="workbench-footer">
            <span class="status-dot"></span>Static preview · No dependencies<span>
              HTML / CSS
            </span>
          </div>
        </aside>
      {/if}
    </div>
  </main>
  <input
    class="hidden-input"
    type="file"
    multiple
    bind:this={fileInput}
    onchange={attach}
    aria-label="Choose attachments"
  />

  {#if searchOpen || settingsOpen || projectsOpen}
    <div
      class="modal-backdrop"
      role="presentation"
      onclick={(event) => {
        if (event.target === event.currentTarget) {
          searchOpen = false;
          settingsOpen = false;
          projectsOpen = false;
        }
      }}
    >
      <div
        class="modal"
        class:search-modal={searchOpen}
        role="dialog"
        aria-modal="true"
        aria-label={searchOpen
          ? 'Search conversations'
          : projectsOpen
            ? 'My projects'
            : 'Workspace settings'}
        tabindex="-1"
        use:focusDialog
      >
        {#if searchOpen}
          <div class="search-input-row">
            <Icon name="search" size={21} /><input
              aria-label="Search conversation titles"
              placeholder="Search your ideas and conversations…"
              bind:value={search}
            /><button class="key-button" onclick={() => (searchOpen = false)}>
              Esc
            </button>
          </div>
          <div class="search-results">
            <div class="dropdown-caption">
              {search
                ? `${filtered.length} conversation${filtered.length === 1 ? '' : 's'} found`
                : 'Recent conversations'}
            </div>
            {#each filtered as chat}<button onclick={() => openChat(chat.id)}>
                <Icon name="chat" size={18} /><span>
                  {chat.title}<small>
                    {chat.project || 'Personal space'} · {chat.messages.length}
                    {chat.messages.length === 1 ? 'message' : 'messages'}
                  </small>
                </span><Icon name="chevron" size={15} />
              </button>{/each}{#if !filtered.length}<div class="modal-empty">
                <Icon name="search" size={26} />
                <p>No conversations found</p>
                <span>Try another keyword or start a new conversation.</span>
              </div>{/if}
          </div>
          <div class="search-footer">
            Conversations stay in this browser <span>⌘ / Ctrl + K</span>
          </div>
        {:else if projectsOpen}
          <div class="modal-heading">
            <div>
              <span class="modal-eyebrow">MAKE ROOM FOR YOUR IDEAS</span>
              <h2>My projects</h2>
            </div>
            <button
              class="icon-button"
              aria-label="Close projects"
              onclick={() => (projectsOpen = false)}
            >
              <Icon name="close" />
            </button>
          </div>
          <p class="modal-description">
            A home for related ideas, with room for inspiration to grow.
          </p>
          <div class="project-list">
            {#each projects as project, index}{@const count =
                conversations.filter(
                  (c) => c.project === project,
                ).length}<button
                onclick={() => {
                  projectsOpen = false;
                  newChat(project);
                }}
              >
                <span class="project-folder" class:sage={index % 2 === 1}>
                  <Icon name="folder" size={22} />
                </span><span>
                  <strong>{project}</strong><small>
                    {count}
                    {count === 1 ? 'conversation' : 'conversations'}
                    · Start a new chat
                  </small>
                </span><Icon name="chevron" size={17} />
              </button>{/each}
          </div>
          <form class="project-form" onsubmit={addProject}>
            <input
              bind:value={projectName}
              maxlength={32}
              placeholder="Name your new project"
              aria-label="New project name"
            /><button class="primary-button" disabled={!projectName.trim()}>
              <Icon name="plus" size={16} />Create project
            </button>
          </form>
        {:else}
          <div class="modal-heading">
            <div>
              <span class="modal-eyebrow">YOUR OWN LITTLE SPACE</span>
              <h2>Workspace settings</h2>
            </div>
            <button
              class="icon-button"
              aria-label="Close settings"
              onclick={() => (settingsOpen = false)}
            >
              <Icon name="close" />
            </button>
          </div>
          <div class="settings-profile">
            <span class="avatar">L</span>
            <div>
              <strong>Lin</strong>
              <p>Personal workspace · Local demo</p>
            </div>
            <span class="settings-badge">LOCAL</span>
          </div>
          <div class="setting-row">
            <span>
              <Icon name={dark ? 'moon' : 'sun'} size={19} /><span>
                Dark appearance<small>
                  A softer space for late-night ideas
                </small>
              </span>
            </span><button
              class:checked={dark}
              class="toggle"
              role="switch"
              aria-checked={dark}
              aria-label="Dark appearance"
              onclick={() => (dark = !dark)}
            >
              <span></span>
            </button>
          </div>
          <div class="setting-row">
            <span>
              <Icon name="trash" size={18} /><span>
                Clear conversations<small>
                  Delete all chats saved in this browser
                </small>
              </span>
            </span><button
              class="danger-button"
              onclick={() => {
                if (clearConfirm) {
                  newChat();
                  conversations = [];
                  clearConfirm = false;
                  notify('All conversations cleared');
                } else clearConfirm = true;
              }}
            >
              {clearConfirm ? 'Confirm clear?' : 'Clear'}
            </button>
          </div>
          <div class="settings-about">
            <span class="assistant-sun">✳</span><strong>
              Kett <small>v1.0</small>
            </strong>
            <p>A little space for your next big idea.</p>
            <span>Built with Svelte 5 · Frontend only · No sign-in</span>
          </div>
        {/if}
      </div>
    </div>
  {/if}
  {#if notification}<div class="toast" role="status">
      <span class="toast-icon">
        <Icon name="check" size={14} />
      </span>{notification}
    </div>{/if}
</div>

{#snippet composer()}
  <div class:focused={input.length > 0} class="composer">
    {#if attachments.length}<div class="attachment-list">
        {#each attachments as attachment, i}<div class="attachment">
            <Icon name="file" size={16} /><span>
              {attachment.name}<small>{attachment.size}</small>
            </span><button
              class="icon-button"
              aria-label={`Remove ${attachment.name}`}
              onclick={() =>
                (attachments = attachments.filter((_, index) => i !== index))}
            >
              <Icon name="close" size={13} />
            </button>
          </div>{/each}
      </div>{/if}
    <textarea
      bind:this={textarea}
      bind:value={input}
      onkeydown={inputKey}
      aria-label="Message Kett"
      placeholder="What would you like to explore?"
      rows="2"
      maxlength={16000}></textarea>
    <div class="composer-toolbar">
      <div class="composer-tools">
        <button
          class="attach-button icon-button"
          title="Add attachments (local demo)"
          aria-label="Add attachments"
          disabled={attachments.length >= 5}
          onclick={() => fileInput.click()}
        >
          <Icon name="plus" size={20} />
        </button>
        <span class="toolbar-separator"></span>
        <button
          class:enabled={thinking}
          class="thinking-button"
          aria-pressed={thinking}
          title="Toggle thinking mode (demo)"
          onclick={() => {
            thinking = !thinking;
            notify(
              thinking
                ? 'Thinking enabled · Interface demo only'
                : 'Thinking disabled',
            );
          }}
        >
          <Icon name="brain" size={16} /><span>
            Think deeper
          </span>{#if thinking}<span class="thinking-dot"></span>{/if}
        </button>
      </div>
      <div class="composer-submit">
        <div class="model-select">
          <button
            class="model-button"
            aria-expanded={modelMenu}
            onclick={() => (modelMenu = !modelMenu)}
          >
            {model}<Icon name="down" size={13} />
          </button>
          {#if modelMenu}<div class="model-menu">
              <div class="dropdown-caption">
                Choose a model <span>Interface demo</span>
              </div>
              {#each models as item}<button
                  onclick={() => {
                    model = item;
                    modelMenu = false;
                  }}
                >
                  <span class="model-symbol">
                    {item.startsWith('Claude') ? '✳' : '◎'}
                  </span><span>
                    {item}<small>
                      {item.includes('Opus')
                        ? 'Deeper thinking for complex tasks'
                        : item.includes('GPT')
                          ? 'Versatile reasoning and coding'
                          : 'A balance of creativity, speed, and capability'}
                    </small>
                  </span>{#if model === item}<Icon
                      name="check"
                      size={15}
                    />{/if}
                </button>{/each}
            </div>{/if}
        </div>
        {#if streaming}<button
            class="send-button stop-button"
            aria-label="Stop generating"
            title="Stop generating"
            onclick={stop}
          >
            <span></span>
          </button>{:else}<button
            class="send-button"
            disabled={!input.trim() && !attachments.length}
            aria-label="Send message"
            title="Send message · Enter"
            onclick={send}
          >
            <Icon name="arrow" size={19} stroke={2} />
          </button>{/if}
      </div>
    </div>
  </div>
  <div class="composer-hint">
    <span>
      <Icon name="paperclip" size={12} /> Words, code, and possibilities
    </span><span>
      <kbd>Enter</kbd> to send <span class="hint-dot">·</span>
      <kbd>Shift + Enter</kbd> for a new line
    </span>
  </div>
{/snippet}
