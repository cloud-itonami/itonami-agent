# Verification — 2026-11-18 (AWAI-3327)

Source, browser, Android VM and physical acceptance are separate claims.

- **Tests.** `npm test` (ClojureScript 1.12.42 on Node 26.0.0): 4 tests, 9 assertions, 0 failures. `npm run test:bb` (Babashka) on the same `.cljc` tests: 4 tests, 9 assertions, 0 failures.
- **Parity with the Otehon CLI.** Error/warning counts shown by the app equal `otehon/bin/itonami-otehon bb check itonami/profiles/<p>` for `awai-op-approver` (1/0), `itonami-compat` (4/1) and `awai-banking-ops` (0/0). Other profiles were not compared one by one.
- **Browser.** `dist/` served from 127.0.0.1: 14 profiles, 12 usable; at 375px wide the page does not scroll horizontally (scrollWidth 375). The job table scrolls inside its card.
- **Android build.** Tauri 3.0.0-alpha.6, minSdk 35 / target 37, NDK 27.0.12077973, `--debug --apk --target aarch64`. Debug APK 29.6 MB (first build). Final APK SHA-256 `b29af6e498179b5c4736f684be6a6f6ca7fe0ccd4af4005f92ac855ffa8ff666` (debug build, not reproducible-checked).
- **Defect found and fixed.** The first APK rendered blank: `cljs.main -c` injected the browser-REPL preload, which tried to frame `http://localhost:9000/` and was refused by the CSP. `:browser-repl false` in `build.edn` removed it (`localhost:9000` occurrences in `dist/app.js`: 0).
- **Android VM.** A dedicated API 35 arm64 `default` image AVD (`ro.build.version.sdk` = 35): install `Success`, `cloud.itonami.agent/.MainActivity` resumed, DOM read over the WebView DevTools socket: `https://tauri.localhost/`, 14 cards, summary `14 profiles · 12 usable`, no error text, scrollWidth 412 = innerWidth 412. Screenshot: `preview-android.png`. Another session installed and foregrounded its own app on the same emulator during the run; it did not change this app's result.
- **Open.** Physical Awai OS, signing, OTA, reboot persistence, TalkBack and user acceptance are not verified. Live turns/inference are not part of the app.

# Verification — 2026-11-18, Itonami Desktop (AWAI-3355)

- **Tests.** ClojureScript: 10 tests, 43 assertions, 0 failures. Babashka: 11 tests, 52 assertions, 0 failures, including `parity_test.clj`: nine inputs, refusals included, give the same path and body from `itonami.app.chat/plan` and Otehon `conversation/request-plan`. The chat tests include negative controls: bad bot or session ids, `default` as a request id, blank or 8193-character text, an untitled or 121-character session title, and replies that were not read back or that name a different request, bot or provider.
- **Broker.** `vendor/` holds kotoba-lang/kotoba `18b8698c475c` `kotoba-client-runtime.js` (`de5e684e…fac6`) and `kotoba-client-consent.css` (`eb1caab0…b086`). `npm run build` checks both digests. KOTOBA-159, the independent review of this source, was still in progress.
- **Browser (127.0.0.1).** Sending opened the canonical consent dialog for send-message, which named the endpoint, route and data categories. After Deny the transcript was empty, the draft was restored and the request log had no `ts.net` request. Desktop width 1280: sidebar and bot detail with 2 routines, no overflow.
- **Android (API 35 arm64, own AVD).** APK `7f5c3ba9…7fbd5` (45.3 MB debug). Install and launch succeeded: 17 bundled bots, no overflow at 412 px, drawer hidden when closed.
  - The emulator cannot use MagicDNS, so its `/system/etc/hosts` maps the service name to the tailnet IP (writable-system AVD). This Mac's own DNS also returns public IPs for that name; that is not changed here.
  - With "Allow once" (pressed by a trusted tap):
    - list-bots returned 797 bots ("on Agent").
    - read-history for `hiraku-soudan` returned an empty default session.
    - list-sessions returned no sessions besides the default.
    - read-history for `awai-banking-ops` returned 404, because that bot is not in the Agent catalog. The app now says so.
  - A denied send: no message was sent, the draft was restored, and the notice said "Not sent".
- **Live send (owner approved, 2026-11-18 02:22Z).** One message to `hiraku-soudan`, default session, from the same emulator and APK, after "Allow once" in the send-message dialog. The reply arrived in 14 s and passed every reply check (same request, bot and session; provider `meta`; model `muse-spark-1.3`; `store.owner` `itonami-agent` with readback). A fresh read-history after reopening the session returned the same two messages from the Agent. Screenshot: `preview-android-chat.png`.
- **Not verified.** Session creation (a write). Also not verified: a physical Awai OS device on the tailnet, signing, OTA and TalkBack.
- **Interference.** During this run another session's ADB forward reused local port 9334 for its own emulator. CDP moved to port 47391 and every reading above is from this app's WebView.

# Verification — 2026-11-18, Autonomy view (AWAI-3447)

- **Tests.** ClojureScript: 15 tests, 85 assertions. Babashka: 16 tests, 94 assertions. Both 0 failures.
  - Negative controls: a stale receipt is not Active; a schedule is not a run; without the receipt the same bot has no board work; a completed issue is not takeable; unknown files and shapes are refused.
  - The Dandori `take-reason` cases follow the rules documented in `work.kotoba`.
- **Real data, local and not committed.**
  - Organization: the AWAI-2795 distributed catalog (899 bots, 762 circles).
  - Activity: a snapshot of 1,177 receipts (586 bots, 48 hours, newest observation 2026-11-13T12:15Z).
  - Board: the 583 Linear issues those receipts name, in Dandori's GraphQL export format (`orca linear list-issues`, all 583 in state started).
- **Browser, 1280 px.**
  - Fleet view: 899 registered, 842 with a verified schedule, 584 ran at least once, 0 active (24 h), board 583 started.
  - The stale banner shows. Each card shows its Linear issue and "Next … (take/resume)". No horizontal overflow.
- **Android (API 35 arm64 emulator).** The three files were pushed to Download and imported with the system picker (multi-select). Circle `cloud-itonami/ao-bot-fleet` shows 9 / 9 / 2 / 0 scoped to the circle, and its cards. Screenshot: `preview-android-autonomy.png`. APK `3910d9ed…1f1b`.
- **Found while verifying.**
  - Three APK builds re-packaged old web assets: Cargo and Gradle did not notice the changed `dist/`, and one web build had actually failed. The README now gives the clean-rebuild steps, and the reported APK is the one built after them.
- **Finding about the bots.** No receipt or observation newer than 2026-11-13 12:15Z was found on AwaiVol. As far as these records show, the bots have not been running on their own since then.

# Verification — 2026-11-25, Worktrees view, Items view, macOS build

- **Tests.** `npm test` (ClojureScript on Node 26): 31 tests, 208 assertions, 0 failures. `npm run test:bb` (Babashka): 32 tests, 217 assertions, 0 failures, including the new `worktrees_test` and `items_test` (reader-level, with negative controls: a blank path, an unknown item status and a missing id are refused, a blank ask question is not shown).
- **Worktrees/Items data path.**
  - `bb scripts/worktree-snapshot.clj /tmp/wt.json .` prints `2 worktrees from 1 repos` for this checkout (main + `com-junkawasaki/itonami-desktop-mac`).
  - In a browser tab at 1280 px: importing `/tmp/wt.json` shows both rows (Main `/ worktree), selecting the second shows path/branch/HEAD/flags; "Copy path" copies to the clipboard; "Refresh" re-reports the count. Importing `/tmp/items.json` (4 items) shows all rows grouped by the status filter chips, and the Needs-you item shows its question and the two options as a read-only box ("Answers are not sent from this view"). `document.documentElement.scrollWidth` = `window.innerWidth` = 1280 on every screen — no horizontal overflow. Screenshots: exports under `/tmp/it1280-*.png` (not committed).
- **macOS dev build (unsigned).** Tauri 3.0.0-alpha.6, Rust 1.95.0 (aarch64-apple-darwin), Xcode 26.6, `tauri build --no-sign` (also via `npm run build:mac`): 0 errors, 2 bundles —
  - `src-tauri/target/release/bundle/macos/Itonami.app` (9.26 MiB, ad-hoc signature, no Developer identity, no notarization)
  - `src-tauri/target/release/bundle/dmg/Itonami_0.1.0_aarch64.dmg` (3.35 MiB)
  `bundle.active: true`, targets `app` + `dmg`, `bundle.macOS.minimumSystemVersion: 14.0`, `hardenedRuntime: true`; no identity or entitlements committed. The `.app` was `open`ed and its window titled "Itonami" appeared, then the process was quit.
- **Chat/Bots unchanged.** The broker consent flow, Deny behaviour, no-retry, Check result replay, CSP and vendor pinning are untouched by this change (no file in `public/agent-client.js`, `vendor/`, or the chat path was modified).
- **Not verified.** Signing, notarization, universal (Intel) build, physical device acceptance, and the new views on Android.
