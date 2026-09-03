# chat-vue Template Research — nuxt-ui-templates/chat-vue

**Date:** 2026-09-03  
**Source:** https://github.com/nuxt-ui-templates/chat-vue (Vue AI Chatbot Template — Nuxt UI + Vite + Nitro)  
**Scope:** What to steal for `chat-rag-agent` chat UI — keep same visual, refactor to template’s approach, add creative features that fit RAG.

---

## 1. How this was researched (primary sources)

Fetched directly from GitHub `main` via `api.github.com` + `raw.githubusercontent.com` (not blogs):

- `README.md` — features, setup, AI Gateway, auth, blob storage [@raw/README](https://raw.githubusercontent.com/nuxt-ui-templates/chat-vue/main/README.md) via crawl
- `package.json` — deps: `@ai-sdk/vue`, `@nuxt/ui`, `@comark/vue`, `drizzle-orm`, `nitro`, `ofetch` [@raw/package.json](https://raw.githubusercontent.com/nuxt-ui-templates/chat-vue/main/package.json)
- `src/App.vue` — `useColorMode` + `UApp` + `RouterView` [@raw/App.vue](https://raw.githubusercontent.com/nuxt-ui-templates/chat-vue/main/src/App.vue)
- `src/composables/useChats.ts` — `createSharedComposable`, `groups` by date (Today/Yesterday/Last week/Last month/Older), `fetchChats/updateChat/removeChat` via `$fetch('/api/chats')` [@raw/useChats.ts](https://raw.githubusercontent.com/nuxt-ui-templates/chat-vue/main/src/composables/useChats.ts)
- `src/composables/useChatActions.ts` — `renameChat`/`deleteChat` with `overlay.create(ModalRename/ModalConfirm)`, `useCsrf`, `useChats` [@raw/useChatActions.ts](https://raw.githubusercontent.com/nuxt-ui-templates/chat-vue/main/src/composables/useChatActions.ts)
- `src/pages/index.vue` — greeting by hour + `user.name`, `UChatPrompt` + `ModelSelect`, `quickChats` buttons, `createChat` via `POST /api/chats` then `router.push(/chat/:id)` [@raw/pages/index.vue](https://raw.githubusercontent.com/nuxt-ui-templates/chat-vue/main/src/pages/index.vue)
- `src/components/UserMenu.vue` — theme + primary/neutral color picker, `useColorMode`, `useAppConfig`, `UDropdownMenu` with `clearSession` [@raw/UserMenu.vue](https://raw.githubusercontent.com/nuxt-ui-templates/chat-vue/main/src/components/UserMenu.vue)
- `src/components/chat/*` — `ChatTitle.vue`, `ChatVisibility.vue`, `Comark.ts`, `Indicator.vue`, `SourceLink.vue`, `message/*`, `tool/*` [@api/chat components](https://api.github.com/repos/nuxt-ui-templates/chat-vue/contents/src/components/chat)
- `src/components/{ModelSelect,Navbar,ModalConfirm,ModalRename}.vue` [@api/components](https://api.github.com/repos/nuxt-ui-templates/chat-vue/contents/src/components)

All claims below cite these.

---

## 2. Template at a glance

| Property | Value |
|----------|-------|
| Stack | Vite 8 + Vue 3.5 + Nuxt UI 4.11 + Nitro 3 + Drizzle ORM 0.45 + SQLite/Turso |
| AI | Vercel AI SDK `ai@7` + `@ai-sdk/vue@4` (`useChat`), Vercel AI Gateway (Claude/Gemini/GPT-5 via one key) |
| Markdown | `@comark/vue@0.6` (streaming code highlight, same lib we already use `Comark`) |
| Auth | Nitro httpOnly cookies + GitHub OAuth (optional), `useUserSession` composable |
| History | `server/utils/drizzle` — `chats`, `messages` tables, `GET /api/chats` lists, `POST /api/chats` creates |
| Layout | `UDashboardPanel` + collapsible sidebar (`UDashboardSidebar`), `Navbar`, `UContainer` |

**Features (README):** streaming + thinking/reasoning, multi-model (Claude/Gemini/GPT via Gateway), web search tools, charts/weather tool UI, GitHub OAuth, SQLite history, file uploads (drag&drop, Blob, requires auth), Comark streaming highlight, light/dark, command palette, keyboard shortcuts.

---

## 3. Architecture we can steal (keep same UI, refactor code)

### 3.1 Composables > Pinia for global UI state

- `useChats = createSharedComposable(() => { chats, fetchChats, groups })` — **shared singleton without Pinia**, auto-cached across pages. `groups` computed does **date bucketing** (`isToday/isYesterday/subMonths`) into Today/Yesterday/Last week/Last month/± monthYear. Our `stores/chat.ts:groupByDate` does similar but with raw `day=86400000` math — switch to `date-fns` like template for correctness.
- `useChatActions` — encapsulates **overlay modals** (`ModalRename`/`ModalConfirm`) + `$fetch` + `toast` + `router.push` on delete. Our `ChatSidebar` does inline `prompt()`/`confirm()` — replace with overlay modals.
- `useUserSession` — wraps Nitro session; we have `stores/auth.ts` (JWT localStorage). Keep ours but add `clearSession` pattern and `computed user` like template.
- `useCsrf` / `useModels` — CSRF header for POST, model list for `ModelSelect`. We use JWT header, not CSRF, but can add `useModels` to fetch `GET /api/settings/models`.

### 3.2 Components

- **`UChatPrompt` + `UChatPromptSubmit` + `ModelSelect`** — template’s `pages/index.vue` uses `UChatPrompt v-model="input" :status="loading?'streaming':'ready'"` with `ModelSelect` in footer slot. Our `ChatComposer.vue` is custom `<textarea>` + buttons — replace with `UChatPrompt` for a11y, streaming state, view-transition.
- **`ChatTitle.vue`** — inline edit title with `UInput` + save/cancel. Our `ChatSidebar` rename uses `prompt()` — upgrade to `ChatTitle` or `ModalRename`.
- **`Indicator.vue`** — thinking/reasoning dots while `status==='streaming'`. We show `USkeleton` — swap to `Indicator` for parity.
- **`SourceLink.vue` / `message/*` / `tool/*`** — rich tool rendering (charts, weather, web search). We have ad-hoc `sources` accordion — extract to `SourceLink` + `tool` registry.
- **`UserMenu.vue`** — template’s is **rich**: primary/neutral chip pickers + Appearance Light/Dark + Templates/docs links + Log out. Our `ChatSidebar` footer is minimal avatar + `UDropdownMenu` with light/dark — upgrade to template’s chip pickers (creative addition).
- **`Navbar.vue`** — top bar with model select + new chat. Our `pages/index.vue` header is minimal — add `Navbar` for consistency.
- **`ModalConfirm` / `ModalRename`** — overlay-based, not `window.confirm`. Add.

### 3.3 Pages

- **`src/pages/index.vue` (home)** — **greeting** (`Good morning/afternoon/evening, {firstName}`) + `UChatPrompt` + `quickChats` (7 pills: “Why use Nuxt UI?”, “Weather in Bordeaux?”, etc.) that call `createChat(label)`. Our `pages/index.vue` shows `ChatEmpty` when no messages — add **greeting + quick prompts** (RAG-tailored: “Summarize my docs”, “List all documents”, “What is …?”).
- **`src/pages/chat/[id].vue`** — chat thread with `useChat` (Vercel AI SDK) streaming, `Comark` per message, tool invocations. Our thread is in `pages/index.vue` itself (no `/chat/:id` route). Keep single-page but extract thread logic to composable like template, or add `/chat/:id` route for deep-linking.
- **`UDashboardPanel`** layout — template uses `UDashboardPanel id="home" :ui="{ body:'p-0 sm:p-0' }"` with `UContainer flex flex-col justify-center`. Our layout is custom `h-screen flex` — migrate to `UDashboardPanel` for consistent Nuxt UI.

### 3.4 Server / Data

- Template: `POST /api/chats {input}` creates chat, `GET /api/chats` lists with `title/createdAt`. We have `POST /api/chat/query` + `GET /api/chat/sessions/:id` + `chat_sessions` table. Pattern to borrow: **create chat on first prompt** (`POST /api/chats`) then `router.push(/chat/:id)` — we already create session lazily; align to template’s explicit create.

---

## 4. What to adapt vs skip (RAG scope)

| Template feature | Adapt for RAG? | How |
|------------------|----------------|-----|
| `useChats` grouping + shared composable | **Adapt** | Replace `stores/chat.ts:groupByDate` with `date-fns` bucketing, keep Pinia or add `composables/useChats.ts` as shared (choose one source of truth) |
| `UChatPrompt` + `ModelSelect` | **Adapt** | Swap `ChatComposer` for `UChatPrompt`, wire `ModelSelect` to `GET /api/settings/models` (already exists) |
| Greeting + quickChats | **Adapt (creative)** | Add time-based greeting + 4–6 RAG quick prompts (“Summarize uploaded docs”, “How many documents?”, “Search …”) that call `chatStore.sendMessage` |
| `ChatTitle` / `ModalRename` / `ModalConfirm` | **Adapt** | Replace `prompt()`/`confirm()` in `ChatSidebar` with overlay modals |
| `Indicator` (thinking) | **Adapt** | Use while `chatStore.loading && !streamingText` |
| `UserMenu` rich theme picker | **Adapt (creative)** | Keep current UI but add primary/neutral chip pickers like template (already have `UserMenu.vue` admin — extend user) |
| `SourceLink` + `tool` registry | **Adapt** | Extract `sources` accordion into `SourceLink` component, prepare for future tool calls (RAG has `search_documents` tool) |
| `Navbar` | **Adapt** | Add to `pages/index.vue` header (model select + new chat) |
| Command palette (`Cmd+K`) + keyboard shortcuts | **Adapt (creative)** | Add `UCommandPalette` for “New chat / Go to doc / Toggle theme” — fits RAG power users |
| File uploads drag&drop | **Skip for now** | Template requires auth + Blob; RAG uploads are admin-only at `/admin/documents` — don’t duplicate in user chat |
| GitHub OAuth httpOnly cookies | **Skip** | We use JWT localStorage (`auth_token`); keep it |
| Drizzle + Turso | **Skip** | We use SQLAlchemy + `app.db` unified; keep `create_db_and_tables` |
| Vercel AI SDK `useChat` | **Skip** | We use `fetch` SSE + `pydantic-ai`; keep `streamChat` but align status handling to template (`status === 'streaming'`) |

---

## 5. Refactor plan — keep same UI, use template’s approach

**Goal:** No visual regression — same colors, spacing, `Comark` markdown, sidebar width — but code reads like `chat-vue`.

1. **Composables layer** — create `frontend/src/composables/useChats.ts` (shared, date-fns groups) and `frontend/src/composables/useChatActions.ts` (rename/delete with `UOverlay` modals). Keep `stores/chat.ts` as transport (SSE) or migrate transport into composable — pick one.
2. **Components** — add `frontend/src/components/chat/ChatTitle.vue`, `Indicator.vue`, `SourceLink.vue`, `ModelSelect.vue` (wrap existing `stores/settings.ts:models`), migrate `ChatComposer` → `UChatPrompt` in `pages/index.vue`.
3. **Home polish** — in `pages/index.vue`, when `!messages.length`, show greeting (`useAuthStore` first name) + `UChatPrompt` + quick prompts row (RAG-flavored) like template’s `UContainer` + `quickChats` pills.
4. **Sidebar** — in `ChatSidebar.vue`, use `useChats.groups` for sections (“Today” etc.), `useChatActions` for rename/delete, `UserMenu` with `Indicator` and theme chips.
5. **Creative adds** — `UCommandPalette` (`Ctrl+K`) for “New chat / Search docs / Toggle theme”, `Navbar` model switcher, `Comark` `streaming` prop already done.
6. **Keep UI same:** Tailwind 4 + `@nuxt/ui` tokens, `Comark` streaming, `UAvatar` bot, sources accordion — only structure changes.

---

## 6. References

- Template README + features: crawl `https://github.com/nuxt-ui-templates/chat-vue` (commit 151, private false, stars 97)
- Package deps: https://raw.githubusercontent.com/nuxt-ui-templates/chat-vue/main/package.json
- App shell: https://raw.githubusercontent.com/nuxt-ui-templates/chat-vue/main/src/App.vue
- Composables: https://raw.githubusercontent.com/nuxt-ui-templates/chat-vue/main/src/composables/useChats.ts, `useChatActions.ts`
- Home: https://raw.githubusercontent.com/nuxt-ui-templates/chat-vue/main/src/pages/index.vue
- UserMenu: https://raw.githubusercontent.com/nuxt-ui-templates/chat-vue/main/src/components/UserMenu.vue
- Chat components index: https://api.github.com/repos/nuxt-ui-templates/chat-vue/contents/src/components/chat
- Our RAG: `frontend/src/pages/index.vue`, `frontend/src/components/ChatSidebar.vue`, `frontend/src/stores/chat.ts`, `frontend/src/api/index.ts`, `frontend/src/components/ChatComposer.vue`
