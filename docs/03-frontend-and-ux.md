# Frontend and user experience

## Technology

- **Build tool**: Vite 8 (`frontend/vite.config.js`).
- **UI library**: React 19 (`frontend/package.json`).
- **Styling**: Tailwind CSS v4 via `@tailwindcss/vite`, plus extensive custom CSS in `src/index.css` (design tokens like `--gem-bg`, sidebar layout, chat bubbles, markdown prose).
- **Icons**: `lucide-react`.
- **Markdown**: `react-markdown` with `remark-gfm` for assistant messages.

## Dev server and API proxy

`vite.config.js` proxies these paths to `http://localhost:8765`:

- `/chat`, `/health`, `/sessions`, `/voice`, `/skills`, `/skillbank`, `/greeting`, `/memory`, `/feedback`, `/schema`, `/profile`

The React app uses **`const API = ''`**, so in development all fetches are **same-origin** to Vite (e.g. `fetch('/chat')`), and Vite forwards them to the FastAPI backend.

**Production / static**: If you only open the backend URL and rely on `frontend/dist` being served by FastAPI, requests must target that **same origin** (no Vite proxy). The current `App.jsx` uses relative URLs, which is correct for that mode.

## Application shell (`App.jsx`)

State:

- `sessions`, `currentSession`, `messages`
- `isStreaming` and `streamRef` (AbortController pattern via `ReadableStreamDefaultReader.cancel` is not fully wired as abort; stop button cancels the reader).
- `sidebarOpen`, `health` (from `/health` every 8s)

Key behaviors:

- **New chat**: new UUID session id, clears messages.
- **Load session**: `GET /sessions/{id}/messages` → maps rows to message objects with `state: 'done'`.
- **Send message**: `POST /chat` with `{ query, session_id }`, reads SSE, parses `data:` JSON lines, updates assistant message incrementally.
- **Feedback**: `POST /feedback` with `{ query, response, rating }` where rating is `1` or `-1`.
- **Delete / clear**: `DELETE` on session or all sessions.

Health chip in the top bar shows Ollama availability (green/red).

## Components

### `Sidebar.jsx`

- Lists sessions with title and relative time.
- “New chat”, per-session delete, “Clear all history” with confirm.
- **Date field mismatch**: API returns `updated` from SQLite (`get_sessions`), but the component displays `s.updated_at || s.created_at`. Those keys are usually **undefined**, so relative times may **not show** as intended. Fix would be to use `s.updated` (and `s.created` if exposed — currently API does not return `created` separately; session row has `created` in DB but list query only selects `updated`).

### `ChatWindow.jsx`

- Empty state: welcome copy + **quick action** cards (system status, code review, deep recall, web research).
- Message list: user bubbles; assistant column with gem avatar, optional meta chips (many fields exist for **legacy** “power tier”, web search badges, GVU pushback, verification — the current backend stream **only** sends `state`, `token`, `done`, so most of those UI branches stay inactive).
- Strips `<thought>...</thought>` and `<think>...</think>` from model output before markdown render.
- **FeedbackRow**: thumbs up/down after completion.

### `InputBar.jsx`

- Auto-growing textarea; Enter sends, Shift+Enter newline; stop button while streaming.

### `AuraSphere.jsx`

- Canvas-based animated “presence” (tiers, listening, FFT for TTS, etc.).
- **Not mounted** anywhere in `App.jsx` in the current tree — likely leftover from a voice-heavy UI revision.

## HTML shell (`index.html`)

Title and meta reference J.A.R.V.I.S.; the page links `/jarvis-icon.png`, but **`frontend/public/`** in this tree only contains `favicon.svg` and `icons.svg` — the PNG may be missing (broken favicon in dev unless you add the asset or point to `favicon.svg`).

## Build scripts (`package.json`)

- `npm run dev` — development server (default port 5173).
- `npm run build` — output to `frontend/dist` for FastAPI static mount or any static host.
- `npm run lint` — ESLint.

## UX expectations vs backend v6

The welcome text says “adaptive power scaling, memory, and web research active.” In the checked backend:

- **Single model**, no tier switching in `llm.stream_chat`.
- **Web search** module exists but is **not invoked** from `/chat`.

So parts of the UI copy and quick prompts describe **aspirational or older** behavior. Aligning copy with the backend (or re-enabling search) would reduce user confusion.
