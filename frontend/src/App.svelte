<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { marked } from 'marked';
  import DOMPurify from 'dompurify';
  import Icon from './lib/Icon.svelte';
  import {
    getCurrentUser,
    renderGoogleSignIn,
    signInWithGoogle,
    signOut,
  } from './lib/google-auth';
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
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID?.trim();
  const demoAccountKey = 'kett-google-demo-v1';
  let accountName = $state<string | null>(null);
  let accountBusy = $state(false);
  let accountChecked = $state(false);
  let signInError = $state('');
  let projectsOpen = $state(false);
  let projectName = $state('');
  let projects = $state(['Personal website', 'Ideas & inspiration']);
  let selectedProject = $state('');
  let dark = $state(false);
  let model = $state<string | null>(null);
  let modelMenu = $state(false);
  let thinking = $state(false);
  let streaming = $state(false);
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
  const models: string[] = [];
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
    if (!googleClientId) {
      try {
        if (sessionStorage.getItem(demoAccountKey)) accountName = 'Demo User';
      } catch {
        /* Demo sign-in works in memory without browser storage. */
      }
    }
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

  function toggleDemoAccount() {
    accountName = accountName ? null : 'Demo User';
    try {
      if (accountName) sessionStorage.setItem(demoAccountKey, accountName);
      else sessionStorage.removeItem(demoAccountKey);
    } catch {
      /* Demo sign-in works in memory without browser storage. */
    }
  }

  async function refreshAccount() {
    if (!googleClientId || accountBusy) return;
    accountChecked = false;
    signInError = '';
    accountBusy = true;
    try {
      accountName = (await getCurrentUser())?.name ?? null;
      accountChecked = true;
    } catch {
      accountName = null;
      signInError = 'Could not check your session. Please try again.';
    } finally {
      accountBusy = false;
    }
  }

  function mountGoogleButton(node: HTMLDivElement) {
    if (!googleClientId) return;
    void renderGoogleSignIn(node, googleClientId, finishGoogleSignIn).catch(
      () => {
        if (node.isConnected)
          signInError = 'Could not load Google sign-in. Please try again.';
      },
    );
  }

  async function finishGoogleSignIn(credential: string) {
    if (accountBusy) return;
    accountBusy = true;
    try {
      accountName = (await signInWithGoogle(credential)).name;
    } catch {
      signInError = 'Google sign-in failed. Please try again.';
    } finally {
      accountBusy = false;
    }
  }

  async function endSession() {
    if (accountBusy) return;
    accountBusy = true;
    signInError = '';
    try {
      await signOut();
      accountName = null;
    } catch {
      signInError = 'Could not sign out. Please try again.';
    } finally {
      accountBusy = false;
    }
  }

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
    modelMenu = false;
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
    modelMenu = false;
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
          'button:not(:disabled), input, iframe, [tabindex="0"]',
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
        <span class="brand-mark" aria-hidden="true">😅</span>
        <span class="brand-name">kett</span>
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
      <Icon name="plus" size={18} /><span>New conversation</span>
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
          No conversations yet.
        </p>{/if}
    </div>

    <div class="sidebar-bottom">
      <button
        class="settings-button"
        aria-label="Open workspace settings"
        onclick={() => {
          clearConfirm = false;
          settingsOpen = true;
          void refreshAccount();
        }}
      >
        <Icon name="settings" size={18} /> Settings
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
        {#if selectedProject}
          <Icon name="folder" size={15} />
          <span class="breadcrumb-project">{selectedProject}</span>
        {/if}
        {#if active}
          {#if selectedProject}
            <span class="breadcrumb-slash" aria-hidden="true">/</span>
          {/if}
          <span class="breadcrumb-current">{active.title}</span>
        {/if}
      </div>
      <div class="header-actions">
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
        <button
          class="icon-button theme-button"
          aria-label="Dark appearance"
          aria-pressed={dark}
          title={dark ? 'Switch to light theme' : 'Switch to dark theme'}
          onclick={() => (dark = !dark)}
        >
          <Icon name={dark ? 'sun' : 'moon'} size={18} />
        </button>
      </div>
    </header>

    <div class="workspace-body">
      <section class="conversation-pane" aria-label="Chat area">
        {#if !messages.length}
          <div class="welcome-scroll">
            <div class="welcome">
              <h1>New conversation</h1>
              {@render composer()}
              <h2 class="suggestions-header">Suggested prompts</h2>
              <div class="suggestions">
                {#each suggestions as suggestion}<button
                    class="suggestion-card {suggestion.color}"
                    onclick={() => useSuggestion(suggestion.prompt)}
                  >
                    <span class="suggestion-icon">
                      <Icon name={suggestion.icon} size={19} />
                    </span>
                    <strong>{suggestion.title}</strong>
                  </button>{/each}
              </div>
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
              {#each messages as message (message.id)}
                <article class="message {message.role}">
                  <div class="message-avatar" aria-hidden="true">
                    {#if message.role === 'user'}<Icon
                        name="user"
                        size={16}
                      />{:else}
                      <span class="assistant-emoji">😅</span>
                    {/if}
                  </div>
                  <div class="message-body">
                    <div class="message-name">
                      {message.role === 'user' ? 'You' : 'Kett'}
                      {#if message.role === 'assistant' && model}<span>
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
                        class="artifact-download"
                        onclick={() =>
                          download(
                            artifactSource,
                            'slow-isle-cafe.html',
                            'text/html',
                          )}
                      >
                        <Icon name="download" size={16} /> Download HTML
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
                          </button>{/if}
                      </div>{/if}
                  </div>
                </article>
              {/each}
            </div>
          </div>
          <div class="chat-composer">
            {@render composer()}
          </div>
        {/if}
      </section>
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
              placeholder="Search conversations"
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
                    {#if chat.project}{chat.project} ·
                    {/if}{chat.messages.length}
                    {chat.messages.length === 1 ? 'message' : 'messages'}
                  </small>
                </span><Icon name="chevron" size={15} />
              </button>{/each}{#if !filtered.length}<div class="modal-empty">
                <Icon name="search" size={26} />
                <p>No conversations found</p>
                <span>Try another keyword or start a new conversation.</span>
              </div>{/if}
          </div>
        {:else if projectsOpen}
          <div class="modal-heading">
            <h2>My projects</h2>
            <button
              class="icon-button"
              aria-label="Close projects"
              onclick={() => (projectsOpen = false)}
            >
              <Icon name="close" />
            </button>
          </div>
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
              placeholder="Project name"
              aria-label="New project name"
            /><button class="primary-button" disabled={!projectName.trim()}>
              <Icon name="plus" size={16} />Create project
            </button>
          </form>
        {:else}
          <div class="modal-heading">
            <h2>Workspace settings</h2>
            <button
              class="icon-button"
              aria-label="Close settings"
              onclick={() => (settingsOpen = false)}
            >
              <Icon name="close" />
            </button>
          </div>
          <div class="setting-row">
            <span class="account-label">
              <Icon name="user" size={18} />
              <span>
                <span aria-live="polite">{accountName ?? 'Guest'}</span>
                <small>
                  {accountBusy
                    ? 'Checking account…'
                    : !googleClientId
                      ? 'Google sign-in demo'
                      : accountName
                        ? 'Signed in with Google'
                        : 'Sign in with Google'}
                </small>
                {#if signInError}
                  <small class="sign-in-error" role="alert">
                    {signInError}
                  </small>
                {/if}
              </span>
            </span>
            {#if !googleClientId}
              <button
                class="primary-button account-button"
                onclick={toggleDemoAccount}
              >
                {accountName ? 'Sign out' : 'Sign in'}
              </button>
            {:else if accountName}
              <button
                class="primary-button account-button"
                disabled={accountBusy}
                onclick={endSession}
              >
                Sign out
              </button>
            {:else if signInError}
              <button
                class="primary-button account-button"
                onclick={refreshAccount}
              >
                Retry
              </button>
            {:else if accountChecked && !accountBusy}
              <div class="account-button" use:mountGoogleButton></div>
            {/if}
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
  <div class="composer">
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
      placeholder="Message Kett"
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
          aria-label="Thinking mode"
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
            Thinking mode
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
            {model ?? 'Select model'}<Icon name="down" size={13} />
          </button>
          {#if modelMenu}<div class="model-menu">
              {#each models as item}
                <button
                  aria-pressed={model === item}
                  onclick={() => {
                    model = item;
                    modelMenu = false;
                  }}
                >
                  {item}
                  {#if model === item}<Icon name="check" size={15} />{/if}
                </button>
              {:else}
                <div class="dropdown-caption">No models available</div>
              {/each}
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
    <span>Local demo · No AI connected</span>
    <span>
      <kbd>Enter</kbd> to send <span class="hint-dot">·</span>
      <kbd>Shift + Enter</kbd> for a new line
    </span>
  </div>
{/snippet}
