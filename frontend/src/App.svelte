<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { marked } from 'marked';
  import DOMPurify from 'dompurify';
  import Icon from './lib/Icon.svelte';
  import {
    getCurrentUser,
    GoogleSignInUnavailable,
    renderGoogleSignIn,
    signInWithGoogle,
    signOut,
    type UserProfile,
  } from './lib/google-auth';
  import {
    suggestions,
    seedConversations,
    demoReply,
    artifactSource,
    type Conversation,
    type Message,
  } from './lib/demo';
  import { listChatModels, streamChat } from './lib/ollama';
  import {
    generateDatasetReport,
    inspectDataset,
    type DatasetColumns,
    type DatasetOptions,
  } from './lib/dataset-analysis';

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
  type Account =
    | { status: 'unchecked' | 'checking' | 'guest' | 'signing-in' }
    | { status: 'unavailable' | 'sign-in-failed'; error: string }
    | {
        status: 'signed-in' | 'signing-out';
        profile: UserProfile;
        error?: string;
      };
  const accountStatus: Record<Account['status'], string> = {
    unchecked: 'Checking your session…',
    checking: 'Checking your session…',
    unavailable: 'Session status unavailable',
    guest: 'Sign in with Google',
    'sign-in-failed': 'Sign in with Google',
    'signing-in': 'Signing in…',
    'signed-in': 'Signed in with Google',
    'signing-out': 'Signing out…',
  };
  let demoSignedIn = $state(false);
  let account = $state<Account>({ status: 'unchecked' });
  let accountChannel: BroadcastChannel | undefined;
  let accountRefreshQueued = false;
  const accountName = $derived(
    !googleClientId
      ? demoSignedIn
        ? 'Demo User'
        : 'Guest'
      : 'profile' in account
        ? account.profile.name
        : ['unchecked', 'checking', 'unavailable', 'signing-in'].includes(
              account.status,
            )
          ? 'Account'
          : 'Guest',
  );
  let projectsOpen = $state(false);
  let projectName = $state('');
  let projects = $state(['Personal website', 'Ideas & inspiration']);
  let selectedProject = $state('');
  let dark = $state(false);
  let model = $state<string | null>(null);
  let modelMenu = $state(false);
  let modelButton: HTMLButtonElement;
  let addModelOpen = $state(false);
  let modelDiscovery = $state<
    { status: 'loading' | 'error' } | { status: 'ready'; names: string[] }
  >({ status: 'loading' });
  let discoverAbort: AbortController | undefined;
  let thinking = $state(false);
  let webSearch = $state(false);
  let searchStatus = $state('');
  let streaming = $state(false);
  let datasetFile = $state<File | null>(null);
  let datasetColumns = $state<DatasetColumns | null>(null);
  let datasetTarget = $state('');
  let datasetFeatures = $state<string[]>([]);
  let datasetError = $state('');
  let inspectingDataset = $state(false);
  let datasetInspectAbort: AbortController | undefined;
  const canSend = $derived(
    datasetFile
      ? !!datasetColumns && !!datasetTarget && datasetFeatures.length > 0
      : !!input.trim(),
  );
  let notification = $state('');
  let copiedId = $state('');
  let clearConfirm = $state(false);
  let loaded = $state(false);
  let textarea: HTMLTextAreaElement;
  let fileInput: HTMLInputElement;
  let messageArea = $state<HTMLDivElement>();
  let streamTimer: ReturnType<typeof setInterval> | undefined;
  let streamAbort: AbortController | undefined;
  let toastTimer: ReturnType<typeof setTimeout>;
  let copyTimer: ReturnType<typeof setTimeout>;
  let models = $state<string[]>([]);
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
        demoSignedIn = !!sessionStorage.getItem(demoAccountKey);
      } catch {
        /* Demo sign-in works in memory without browser storage. */
      }
    } else if (typeof BroadcastChannel !== 'undefined') {
      accountChannel = new BroadcastChannel('kett-auth-v1');
      accountChannel.onmessage = ({ data }) => {
        if (data === 'session-changed') void refreshAccount();
      };
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
    listChatModels()
      .then((names) => (models = names))
      .catch(() => {
        /* Without a reachable Ollama server the app keeps its preset replies. */
      });
    return () => {
      accountChannel?.close();
      accountChannel = undefined;
      clearInterval(streamTimer);
      streamAbort?.abort();
      datasetInspectAbort?.abort();
      discoverAbort?.abort();
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
    demoSignedIn = !demoSignedIn;
    try {
      if (demoSignedIn) sessionStorage.setItem(demoAccountKey, 'Demo User');
      else sessionStorage.removeItem(demoAccountKey);
    } catch {
      /* Demo sign-in works in memory without browser storage. */
    }
  }

  function refreshQueuedAccount() {
    if (!accountRefreshQueued) return;
    accountRefreshQueued = false;
    void refreshAccount();
  }

  function recheckVisibleAccount() {
    // Do not remount the Google button just because its popup lost focus.
    if (
      document.visibilityState === 'visible' &&
      account.status === 'signed-in'
    ) {
      void refreshAccount();
    }
  }

  async function refreshAccount() {
    if (!googleClientId || !settingsOpen) return;
    if (
      account.status === 'checking' ||
      account.status === 'signing-in' ||
      account.status === 'signing-out'
    ) {
      accountRefreshQueued = true;
      return;
    }
    account = { status: 'checking' };
    try {
      const profile = await getCurrentUser();
      account = profile
        ? { status: 'signed-in', profile }
        : { status: 'guest' };
    } catch {
      account = {
        status: 'unavailable',
        error: 'Could not check your session. Please try again.',
      };
    } finally {
      refreshQueuedAccount();
    }
  }

  function mountGoogleButton(node: HTMLDivElement) {
    if (!googleClientId) return;
    void renderGoogleSignIn(node, googleClientId, finishGoogleSignIn).catch(
      () => {
        if (node.isConnected && account.status === 'guest') {
          account = {
            status: 'sign-in-failed',
            error: 'Could not load Google sign-in. Please try again.',
          };
        }
      },
    );
  }

  async function finishGoogleSignIn(credential: string) {
    if (account.status !== 'guest') return;
    account = { status: 'signing-in' };
    try {
      const profile = await signInWithGoogle(credential);
      account = { status: 'signed-in', profile };
      accountChannel?.postMessage('session-changed');
    } catch (error) {
      account = {
        status: 'sign-in-failed',
        error:
          error instanceof GoogleSignInUnavailable
            ? 'Google sign-in is temporarily unavailable. Please try again.'
            : 'Google sign-in failed. Please try again.',
      };
    } finally {
      refreshQueuedAccount();
    }
  }

  async function endSession() {
    if (account.status !== 'signed-in') return;
    const { profile } = account;
    account = { status: 'signing-out', profile };
    try {
      await signOut();
      account = { status: 'guest' };
      accountChannel?.postMessage('session-changed');
    } catch {
      account = {
        status: 'signed-in',
        profile,
        error: 'Could not sign out. Please try again.',
      };
    } finally {
      refreshQueuedAccount();
    }
  }

  function notify(text: string) {
    notification = text;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (notification = ''), 3000);
  }

  function stop() {
    clearInterval(streamTimer);
    streamAbort?.abort();
    streamAbort = undefined;
    streaming = false;
    searchStatus = '';
  }

  async function discoverModels() {
    discoverAbort?.abort();
    const abort = new AbortController();
    discoverAbort = abort;
    modelDiscovery = { status: 'loading' };
    try {
      const names = await listChatModels(abort.signal);
      if (!abort.signal.aborted) {
        modelDiscovery = { status: 'ready', names: [...new Set(names)] };
      }
    } catch {
      if (!abort.signal.aborted) modelDiscovery = { status: 'error' };
    }
  }

  function openAddModel() {
    modelMenu = false;
    addModelOpen = true;
    void discoverModels();
  }

  function closeAddModel() {
    discoverAbort?.abort();
    discoverAbort = undefined;
    addModelOpen = false;
    void tick().then(() => modelButton?.focus());
  }

  function addModel(name: string) {
    if (!models.includes(name)) models = [...models, name];
    model = name;
    closeAddModel();
  }

  function clearDataset() {
    datasetInspectAbort?.abort();
    datasetInspectAbort = undefined;
    datasetFile = null;
    datasetColumns = null;
    datasetTarget = '';
    datasetFeatures = [];
    datasetError = '';
    inspectingDataset = false;
  }

  function newChat(project = '') {
    stop();
    activeId = null;
    input = '';
    clearDataset();
    selectedProject = project;
    modelMenu = false;
    mobileSidebar = false;
    tick().then(() => textarea?.focus());
  }

  function openChat(id: string) {
    stop();
    activeId = id;
    input = '';
    clearDataset();
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
    if (streaming || !canSend) return;
    const file = datasetFile;
    const columns = datasetColumns;
    const text = file ? `Analyze ${file.name}` : input.trim();
    const options: DatasetOptions = {
      target: datasetTarget,
      features: [...datasetFeatures],
      prediction_context: input.trim().slice(0, 500),
      model: model ?? undefined,
    };
    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: file
        ? `${text}\nTarget: ${options.target}\nFeatures: ${options.features.join(', ')}${options.prediction_context ? `\nPrediction context: ${options.prediction_context}` : ''}`
        : text,
      attachments: file
        ? [
            {
              name: file.name,
              size: `${Math.max(1, Math.ceil(file.size / 1024))} KB`,
            },
          ]
        : undefined,
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
    clearDataset();
    if (file && columns) await analyze(conversation, file, columns, options);
    else await respond(conversation, text);
  }

  async function analyze(
    conversation: Conversation,
    file: File,
    columns: DatasetColumns,
    options: DatasetOptions,
  ) {
    const id = crypto.randomUUID();
    const abort = new AbortController();
    streamAbort = abort;
    conversation.messages.push({
      id,
      role: 'assistant',
      content: '',
      datasetRun: 'error',
    });
    streaming = true;
    searchStatus =
      'Training and evaluating the model, then generating the report…';
    try {
      await tick();
      scrollBottom();
      const result = await generateDatasetReport(file, options, abort.signal);
      const message = conversation.messages.find((m) => m.id === id);
      if (message && !abort.signal.aborted) {
        message.content = result.report;
        message.datasetRun = 'report';
      }
    } catch (error) {
      if (!abort.signal.aborted) {
        const reason = error instanceof Error ? error.message : String(error);
        const message = conversation.messages.find((m) => m.id === id);
        if (message)
          message.content = `Could not generate the report: ${reason}`;
        datasetFile = file;
        datasetColumns = columns;
        datasetTarget = options.target;
        datasetFeatures = options.features;
        input = options.prediction_context ?? '';
      }
    } finally {
      if (streamAbort === abort) stop();
      await tick();
      scrollBottom();
    }
  }

  async function respond(conversation: Conversation, text: string) {
    const history = conversation.messages.map(({ role, content }) => ({
      role,
      content,
    }));
    const id = crypto.randomUUID();
    conversation.messages.push({ id, role: 'assistant', content: '' });
    streaming = true;
    await tick();
    scrollBottom();
    if (model) {
      const abort = new AbortController();
      streamAbort = abort;
      try {
        for await (const event of streamChat(
          model,
          history,
          webSearch,
          abort.signal,
        )) {
          const message = conversation.messages.find((m) => m.id === id);
          if (!message) break;
          if (event.type === 'status') searchStatus = event.text;
          else if (event.type === 'sources') message.sources = event.sources;
          else message.content += event.text;
          await tick();
          scrollBottom();
        }
      } catch (error) {
        if (!abort.signal.aborted) {
          const message = conversation.messages.find((m) => m.id === id);
          const reason = error instanceof Error ? error.message : String(error);
          if (message && !message.content)
            message.content = `Could not get a reply from ${model}: ${reason}`;
          notify('The model request failed');
        }
      } finally {
        if (streamAbort === abort) stop();
      }
      return;
    }
    const reply = demoReply(text);
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
      if (addModelOpen) return;
      searchOpen = !searchOpen;
      search = '';
    }
    if (event.key === 'Escape') {
      if (addModelOpen) {
        closeAddModel();
        return;
      }
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

  async function attach(event: Event) {
    const picker = event.currentTarget as HTMLInputElement;
    const file = picker.files?.[0];
    picker.value = '';
    if (!file || streaming) return;
    clearDataset();
    if (!/\.(csv|tsv)$/i.test(file.name)) {
      datasetError = 'Only structured CSV or TSV files are supported.';
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      datasetError = 'Dataset uploads are limited to 5 MiB.';
      return;
    }
    const abort = new AbortController();
    datasetInspectAbort = abort;
    datasetFile = file;
    inspectingDataset = true;
    try {
      const columns = await inspectDataset(file, abort.signal);
      if (!abort.signal.aborted) datasetColumns = columns;
    } catch (error) {
      if (!abort.signal.aborted) {
        datasetError = error instanceof Error ? error.message : String(error);
      }
    } finally {
      if (datasetInspectAbort === abort) {
        inspectingDataset = false;
        datasetInspectAbort = undefined;
      }
    }
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
    if (!lastUser || active.messages.at(-1)?.datasetRun) return;
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

<svelte:document onvisibilitychange={recheckVisibleAccount} />

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
                        </span>{#if searchStatus}<span
                            class="search-status"
                            role="status"
                          >
                            {searchStatus}
                          </span>{/if}{/if}{/if}
                    {#if message.sources?.length && message.content}<ol
                        class="message-sources"
                        aria-label="Sources"
                      >
                        {#each message.sources as source}<li>
                            <a
                              href={source.url}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              {source.title || source.url}
                            </a>
                          </li>{/each}
                      </ol>{/if}
                    {#if message.datasetRun === 'report'}<button
                        class="artifact-download"
                        onclick={() =>
                          download(
                            message.content,
                            'report.md',
                            'text/markdown;charset=utf-8',
                          )}
                      >
                        <Icon name="download" size={16} /> Download report
                      </button>{/if}
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
                        </button>{#if message.id === messages.at(-1)?.id && !message.datasetRun}<button
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
    accept=".csv,.tsv"
    bind:this={fileInput}
    onchange={attach}
    aria-label="Choose attachments"
  />

  {#if addModelOpen}
    <div
      class="modal-backdrop"
      role="presentation"
      onclick={(event) => {
        if (event.target === event.currentTarget) closeAddModel();
      }}
    >
      <div
        class="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Add model"
        tabindex="-1"
        use:focusDialog
      >
        <div class="modal-heading">
          <h2>Add model</h2>
          <button
            class="icon-button"
            aria-label="Close add model"
            onclick={closeAddModel}
          >
            <Icon name="close" />
          </button>
        </div>
        <p class="model-discovery-note">
          Only models installed on the configured Ollama server can be added.
        </p>
        {#if modelDiscovery.status === 'loading'}
          <p role="status">Looking for models…</p>
        {:else if modelDiscovery.status === 'error'}
          <p role="alert">Could not load models from the configured server.</p>
        {:else if modelDiscovery.status === 'ready'}
          {@const available = modelDiscovery.names.filter(
            (name) => !models.includes(name),
          )}
          {#if available.length}
            <div class="model-discovery-list">
              {#each available as name (name)}
                <button
                  aria-label={`Add ${name}`}
                  onclick={() => addModel(name)}
                >
                  <span>{name}</span><Icon name="plus" size={16} />
                </button>
              {/each}
            </div>
          {:else}
            <p role="status">No new models found on the configured server.</p>
          {/if}
        {/if}
        <button
          class="artifact-download"
          disabled={modelDiscovery.status === 'loading'}
          onclick={discoverModels}
        >
          <Icon name="refresh" size={16} /> Refresh models
        </button>
      </div>
    </div>
  {/if}

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
                <span aria-live="polite">{accountName}</span>
                <small>
                  {googleClientId
                    ? accountStatus[account.status]
                    : 'Google sign-in demo'}
                </small>
                {#if 'error' in account && account.error}
                  <small class="sign-in-error" role="alert">
                    {account.error}
                  </small>
                {/if}
              </span>
            </span>
            {#if !googleClientId}
              <button
                class="primary-button account-button"
                onclick={toggleDemoAccount}
              >
                {demoSignedIn ? 'Sign out' : 'Try demo sign-in'}
              </button>
            {:else if account.status === 'signed-in' || account.status === 'signing-out'}
              <button
                class="primary-button account-button"
                disabled={account.status === 'signing-out'}
                onclick={endSession}
              >
                Sign out
              </button>
            {:else if account.status === 'unavailable' || account.status === 'sign-in-failed'}
              <button
                class="primary-button account-button"
                onclick={refreshAccount}
              >
                Retry
              </button>
            {:else if account.status === 'guest'}
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
    {#if datasetFile}
      <div class="attachment-list">
        <div class="attachment">
          <Icon name="file" size={16} /><span>{datasetFile.name}</span>
          <button
            class="icon-button"
            aria-label={`Remove ${datasetFile.name}`}
            onclick={clearDataset}
          >
            <Icon name="close" size={13} />
          </button>
        </div>
      </div>
      {#if inspectingDataset}<p class="dataset-status" role="status">
          Reading table columns…
        </p>{/if}
      {#if datasetColumns}
        <div class="dataset-options">
          <label class="dataset-target">
            Target column (numeric)
            <select
              value={datasetTarget}
              onchange={(event) => {
                datasetTarget = event.currentTarget.value;
                datasetFeatures = datasetFeatures.filter(
                  (name) => name !== datasetTarget,
                );
              }}
            >
              <option value="">Choose a column</option>
              {#each datasetColumns.columns as name}<option value={name}>
                  {name}
                </option>{/each}
            </select>
          </label>
          <fieldset>
            <legend>
              Feature columns ({datasetFeatures.length}/{datasetColumns.max_features})
            </legend>
            <div class="dataset-features">
              {#each datasetColumns.columns as name}
                <label>
                  <input
                    type="checkbox"
                    value={name}
                    bind:group={datasetFeatures}
                    disabled={name === datasetTarget ||
                      (!datasetFeatures.includes(name) &&
                        datasetFeatures.length >= datasetColumns.max_features)}
                  />
                  <span>{name}</span>
                </label>
              {/each}
            </div>
          </fieldset>
        </div>
      {/if}
    {/if}
    {#if datasetError}<p class="dataset-status" role="alert">
        {datasetError}
      </p>{/if}
    <textarea
      bind:this={textarea}
      bind:value={input}
      onkeydown={inputKey}
      aria-label={datasetFile
        ? 'Prediction context (optional)'
        : 'Message Kett'}
      placeholder={datasetFile
        ? 'Prediction context (optional): e.g. after the second exam'
        : 'Message Kett'}
      rows="2"
      maxlength={datasetFile ? 500 : 16000}></textarea>
    <div class="composer-toolbar">
      <div class="composer-tools">
        <button
          class="attach-button icon-button"
          title="Upload a CSV or TSV dataset"
          aria-label="Upload dataset"
          disabled={streaming}
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
        <button
          class:enabled={webSearch}
          class="thinking-button"
          aria-pressed={webSearch}
          aria-label="Web search"
          title="Search the web before answering"
          onclick={() => {
            webSearch = !webSearch;
            notify(
              !webSearch
                ? 'Web search disabled'
                : model
                  ? 'Web search enabled'
                  : 'Web search enabled · Select a model to use it',
            );
          }}
        >
          <Icon name="search" size={16} /><span>
            Web search
          </span>{#if webSearch}<span class="thinking-dot"></span>{/if}
        </button>
      </div>
      <div class="composer-submit">
        <div class="model-select">
          <button
            class="model-button"
            bind:this={modelButton}
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
              <button
                class="model-add"
                aria-haspopup="dialog"
                onclick={openAddModel}
              >
                Add model <Icon name="plus" size={17} />
              </button>
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
            disabled={!canSend}
            aria-label={datasetFile ? 'Generate report' : 'Send message'}
            title={datasetFile
              ? 'Generate report · Enter'
              : 'Send message · Enter'}
            onclick={send}
          >
            <Icon name="arrow" size={19} stroke={2} />
          </button>{/if}
      </div>
    </div>
  </div>
  <div class="composer-hint">
    <span>
      {datasetFile
        ? 'Dataset analysis · CSV / TSV'
        : 'Local demo · No AI connected'}
    </span>
    <span>
      <kbd>Enter</kbd> to send <span class="hint-dot">·</span>
      <kbd>Shift + Enter</kbd> for a new line
    </span>
  </div>
{/snippet}
