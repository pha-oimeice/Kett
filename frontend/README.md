# Kett frontend

The chat workspace uses **Svelte 5, TypeScript, and Vite**. The FastAPI backend handles Ollama requests, web search, file analysis, and Google sign-in.

## Run locally

Use Node.js 22 or later. From `frontend/`:

```bash
npm ci
npm run dev
```

Open the address printed by Vite, normally `http://localhost:5173`. Use `python start.py` from the repository root to start the frontend and backend together.

```bash
npm run check    # Check Svelte and TypeScript
npm test         # Run Playwright browser tests
npm run build    # Build to dist/
npm run preview  # Preview the production build
npm run format   # Format the source files
```

If Chromium is missing, install it before running Playwright:

```bash
npx playwright install chromium
```

## Workspace features

- Create, switch, search, and delete conversations from the collapsible sidebar. Use `Cmd/Ctrl + K` to search and `Esc` to close a dialog.
- Press `Enter` to send or `Shift + Enter` for a new line. Pressing Enter during input method composition does not send the message.
- Select a chat model from the configured Ollama server. Upload an attachment and ask a tool-capable model about it; supported files and report options are listed in the [project README](../README.md#student-performance-analysis).
- Stop replies, regenerate ordinary chat responses, copy text, or like a response. Read sanitized Markdown and download generated reports or a conversation export.
- Organize conversations into local projects and switch between light and dark themes. Conversation history and workspace preferences live in browser storage.

Without a selected model, text chat uses the English preset replies in `src/lib/demo.ts`. The **Thinking mode** control is a visual demo, and the downloadable sample HTML is built in. Attachment chat requires a selected model.

## Google sign-in

Without a client ID, **Workspace settings** shows **Try demo sign-in**. This does not contact Google or create a backend session. See the [project README](../README.md#enable-google-sign-in-locally-optional) for configuration.

With Google sign-in enabled, the frontend sends the ID token to the backend for verification without saving the token or profile in browser storage. Settings checks `/api/auth/me`: a `401` indicates a signed-out session, while a failed check can be retried. **Sign out** revokes the Kett session without signing the user out of Google.

Tabs on the same origin notify each other about session changes without sending profile data or tokens. Since tabs share the sign-in challenge cookie, start Google sign-in in only one tab at a time.

The default Playwright run covers demo sign-in when no client ID is configured. To exercise the configured sign-in UI with mocked Google SDK and backend responses:

```bash
GOOGLE_CLIENT_ID=test.apps.googleusercontent.com npm test -- tests/account.spec.ts
```

## Source layout

```text
src/
├── App.svelte        # Workspace layout and interaction
├── app.css           # Themes, typography, and responsive styles
├── main.ts           # Application entry point
└── lib/
    ├── Icon.svelte   # SVG icons
    ├── demo.ts       # Conversation types and built-in examples
    ├── google-auth.ts # Google sign-in and backend session client
    └── ollama.ts     # Model discovery and streamed chat client
tests/
├── account.spec.ts   # Sign-in and session UI
├── typography.spec.ts # Typography and responsive layout
└── workspace.spec.ts # Chat and workspace behavior
```
