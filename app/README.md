# Itonami — Tauri v3 desktop app (Android / Awai OS)

Itonami Desktop, modelled on the Hermes Agent desktop's chat-first layout: a
sidebar with **Sessions** and **Bots** (a drawer on phones), the conversation,
a composer and a status bar.

- **Bots**: the profiles bundled from `../itonami/profiles`, checked on the
  device by the Otehon `.cljc` core compiled to ClojureScript, with their
  routines (cron jobs) dry-run and shown per bot. On request, the Agent's own
  directory is loaded and merged ("on Agent" / "local only").
- **Conversation**: the owner's Agent conversation service
  (`network-awai/awai-os` `otehon/bot-chat`, `/v1/bot-chat/{bots,sessions,history,turn}`,
  Muse `muse-spark-1.3`). Every request goes through the canonical
  `kotoba-client-runtime.js` broker and asks the person first; denying sends
  nothing. Nothing is retried automatically. An unconfirmed send keeps its
  request id and offers **Check result**, which resends the same id so the
  Agent replays a finished turn instead of running it again.
- The Agent owns the history; the app keeps only what is on screen.
- **Worktrees**: a list of Git worktrees for the repositories the person curates,
  from a snapshot printed by `scripts/worktree-snapshot.clj` (it wraps
  `git worktree list --porcelain`). The snapshot is imported like the Autonomy
  files and kept in memory only; the app never runs `git` (no shell
  permission). Selecting a worktree shows its path, branch, HEAD and flags,
  and copies its path to the clipboard — a local operation only.
- **Items**: work items read from an `itonami.items.v1` JSON file the person
  imports (in the same in-memory pattern; the file can be an Orca
  orchestration export or written by hand). Statuses are **In progress** /
  **Waiting** / **Needs you** / **Done**, filterable, searchable; a Needs-you
  item shows its question and option labels for reading only — answering is
  not done from this view. Orca CLI is not required to display either view.
- The Rust side is a thin host (`awai_host_info` only).

- Automations (scheduled, event-waiting, PR watch) are intentionally not part of this app.
Tracking: [AWAI-3327](https://linear.app/kotobalabs/issue/AWAI-3327),
[AWAI-3355](https://linear.app/kotobalabs/issue/AWAI-3355).

**Path status.** This is the Otehon path (ADR 0026 D18, workspace Awai Otehon
rule): `.cljc`/CLJS for the shared domain, Tauri as a limited platform
adapter. Nothing on the Native route (`bin/`, `kotoba/`, the selfhost gates)
reads `app/`, and neither side falls back to the other.

## Layout

| path | role |
|---|---|
| `src/itonami/app/core.cljc` | pure view-model over `itonami.otehon.profile` (also runs on Babashka) |
| `src/itonami/app/chat.cljc` | request plans (same as Otehon `conversation/request-plan`, checked by `test/.../parity_test.clj`), response checks, transcript state |
| `src/itonami/app/worktrees.cljc` | worktrees snapshot validation/normalization (bb + CLJS) |
| `src/itonami/app/items.cljc` | items file validation/normalization (bb + CLJS) |
| `scripts/worktree-snapshot.clj` | `git worktree list --porcelain` → `itonami.worktrees-snapshot.v1` JSON |
| `src/itonami/app/main.cljs` | the desktop UI |
| `public/agent-client.js` | declares the five Agent operations and calls the broker; nothing else |
| `vendor/` | canonical `kotoba-client-runtime.js` / `kotoba-client-consent.css`, pinned by revision and SHA-256 in `PINS.json`; `npm run build` refuses a mismatch |
| `public/` | `index.html`, `style.css` |
| `scripts/bundle-profiles.mjs` | ships only `SOUL.md`, `config.yaml`, `profile.yaml`, `cron/jobs.json`, `itonami.edn`, `yakuwari.edn` per profile; refuses text that looks like a credential |
| `src-tauri/` | Tauri 3.0.0-alpha.6 host, Android project in `gen/android` (minSdk 35, target 37), macOS bundle (`app` + `dmg`, unsigned dev build) |
| `icon-src/icon.svg` | source of the launcher icons (`npx tauri icon`) |

## Build

Needs Node, the Clojure CLI (JDK 21), Rust with `aarch64-linux-android`, the
Android SDK and NDK 27.0.12077973.

```
npm ci
npm test             # ClojureScript tests on node
npm run test:bb      # the same tests on Babashka
npm run build        # dist/: index.html, style.css, app.js, profiles.json
ANDROID_HOME=… NDK_HOME=… npm run build:android      # arm64 debug APK
```

Tauri embeds `dist/` when the Rust crate compiles, and neither Cargo nor
Gradle notices a changed `dist/` by itself. After a UI change, run
`touch src-tauri/src/lib.rs` and remove `src-tauri/gen/android/app/build`
before `build:android`, then check that the APK's SHA-256 changed.

The APK lands in
`src-tauri/gen/android/app/build/outputs/apk/universal/debug/`. Install with
`adb install -r <apk>`.

## Build (macOS)

Needs Node, the Clojure CLI (JDK 21), Rust 1.95 (arm64 on Apple silicon) and
Xcode with its Command Line Tools. No signing identity, notary or
universal-target setup is involved in a development build:

```
npm ci
npm run build:mac   # npm run build + tauri build --no-sign
```

The unsigned `.app` lands in `src-tauri/target/release/bundle/macos/`.
`bundle.active` is on with `app` + `dmg` targets in `tauri.conf.json`, with
`bundle.macOS.minimumSystemVersion: 14.0` and `hardenedRuntime: true`. No
signing identity or entitlements are committed. Signing, notarization and a
universal (Intel + Apple silicon) build are separate claims and are not
verified here.

## Worktrees snapshot

```
bb scripts/worktree-snapshot.clj OUT.json REPO...
```

`REPO...` go to `git -C <repo> worktree list --porcelain`; each repository's
first non-bare worktree is its main one. OUT.json is an
`itonami.worktrees-snapshot.v1` file (paths, branches, HEAD ids and flags
only). It is private operational data: keep it out of the repository.

## Items file

An `itonami.items.v1` JSON file, imported in the Items tab:

```json
{"schema":"itonami.items.v1","items":[
  {"id":"IT-1","title":"Add worktrees view","status":"In progress","assignee":"junks","updated":"2026-11-25"},
  {"id":"IT-2","title":"Approve merge?","status":"Needs you",
   "ask":{"question":"Approve the PR?","options":[{"id":"yes","label":"Approve"},{"label":"Hold"}]}}
]}
```

`status` is one of `In progress`, `Waiting`, `Needs you`, `Done`; any other
status, or a missing `id`, is dropped (and counted as dropped on import).
`ask` is optional; a Needs-you item without a question shows that fact
instead of an empty box. Imported items live in memory only.

## Autonomy (Org tab)

Shows how far the bots get on their own by joining three files the person
imports. Files are read on the device and kept in memory only; nothing is
sent.

| file | from | read as |
|---|---|---|
| organization | the `awai.bot-fleet.v1` catalog Soshiki imports, or Soshiki's saved state | circles, roles, bots, each bot's schedule |
| board | a Dandori (or Linear) GraphQL issues export, `data.issues.nodes` | issues; a bot's issues are those assigned to it or named by its own receipts |
| activity | `itonami.autonomy-snapshot.v1` from `scripts/autonomy-snapshot.clj` | receipts per bot and per hour, last run, Linear issues |

```
bb -cp src scripts/autonomy-snapshot.clj OUT.json RECEIPT-DIR... -- OBSERVATION.json...
```

Developer-bot task directories (isolated clones holding `.agent-output/`)
become the same two files, so the unchanged view imports them:

```
bb -cp src scripts/dev-bot-snapshot.clj CATALOG.json SNAPSHOT.json ROOT... [-- ISSUE-MAP.json]
```

`ROOT...` are scanned recursively for directories holding `.agent-output/`;
nothing outside them is read. `ISSUE-MAP.json` is optional and maps Linear
issue keys to their project (a name string or `{"id" "name"}`); without it
there is one circle per task repository. Each circle gets one implementer
bot (run 1) plus the single `shinsa` review bot (runs 2+). Runs bind to
their task's issue only — never from log text; missing or malformed files
count as unknown, never as success; only `rc 0` counts as measured.
Finished runs file under their end time, in-progress runs under their start,
so the existing 24 h rule shows one as running only while its start is
recent. The snapshot also carries per-bot token usage (summed `run.usage`
events) and per-issue gate deliveries (action, PR URL, merge commit), which
older snapshots simply lack — they still import.

The snapshot holds bot ids, job ids, Linear issue ids, counts and times only,
but it is private operational data: keep it out of the repository.

States come from observations only:
- **Active**: a receipt within 24 h.
- **Stale**: receipts exist, but none within 24 h.
- **Scheduled**: a verified schedule with no receipt yet. A schedule alone is not evidence of a run.
- **Held**: no source schedule, or verification failed.

"Next" is the issue the bot would take under Dandori's work rules
(`take-reason` and the ordering in `before?`, ported from
`kotoba/dandori/work.kotoba`). An export carries no claims or blockers, so
none are assumed. When the newest observation is older than 24 h, a banner
says so and no bot is shown as active.

Not verified: the dev-bot running/usage/delivery facts on a real browser or
Android display — they are covered only by the reader-level tests (`npm
test`, `npm run test:bb`), not by opening the app on either surface.

## Reaching the Agent

The service origin is fixed: `https://21mbp.tail110d8b.ts.net:8443`, the
owner's tailnet (Tailscale serve, owner identity, origin allowlist including
`https://tauri.localhost`). The device must be on that tailnet with MagicDNS.
The CSP `connect-src` names only that origin besides the local IPC.

## Not covered yet
- Streaming replies, tool-call rows, attachments, voice, terminal, file
  browser, skills, memory graph and multi-window from the Hermes desktop.
- Loading a profile from the device's own store (`~/.itonami` equivalent).
- Physical Awai OS, signing, OTA and reboot persistence are separate claims.
