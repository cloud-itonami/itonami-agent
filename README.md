# itonami-agent

A Hermes-compatible agent written in kotoba (`.cljk` on kbb), with peer-to-peer
execution of agent turns. The agent core needs only the kbb engine; no JVM or
npm packages. Cron jobs written in Hy additionally need Python with Hy installed.

```
bin/itonami-agent -p hiraku-soudan -z "質問"            # one turn, like `hermes -p … -z`
bin/itonami-agent -p hiraku-kyozai cron run <job-id>    # a Hermes cron job, same files
bin/itonami-agent peer serve --port 7420                # run turns for trusted peers
bin/itonami-agent peer run -p hiraku-soudan -z "質問"   # run this turn on a peer
```

## Running where `env -S` is missing (guest VMs, busybox)

The launcher's shebang is `#!/usr/bin/env -S kbb --backend sci`, which needs
an `env` that understands `-S` (GNU coreutils, BSD). Busybox `env` does not
(measured 2026-10-19 in an Alpine aarch64 initramfs: `env: Usage: ...` and
nothing else). On such hosts invoke the same launcher through kbb directly --
it is equivalent, the launcher adds `src/` itself:

```
kbb --backend sci bin/itonami-agent -p <profile> -z "…"
```

Two more guest notes from the same run: profiles resolve under `ITONAMI_DIR`
(default `~/.itonami`) so set it when `HOME` is not where the profiles live;
and the toolset gate refuses to start when the selected Hermes tools exceed
the Kotoba implementation (`-t terminal,file,web` selects a supported set).

## Compatibility with Hermes Agent

itonami-agent is Hermes-compatible in FORMAT, not in STORE. It keeps its own
profiles and state under `ITONAMI_DIR` (default `~/.itonami/`): profiles at
`~/.itonami/profiles/<name>/`, run state and receipts under the same root.
The Hermes home (`~/.hermes/`) is a different store that itonami-agent never
writes to. The two never share a profile directory, a sessions DB, or a run
log — what they share is the file layout, so a profile directory copied
between the two stores is a valid profile on either side:

- `profile import <p>|--all [--from DIR] [--force]` copies a profile's
  DEFINITION from a Hermes home (`ITONAMI_HERMES_ROOT`, default `~/.hermes`)
  into the itonami store. The source is read-only.
- `profile export <p>|--all [--to DIR] [--force]` copies the other way. When
  the profile's cron scheduler is `:itonami`, the exported copy gets Hermes'
  `gateway.parked` marker so the Hermes gateway never double-ticks it.

Definition = `SOUL.md`, `profile.yaml`, `config.yaml`, `.env`,
`secrets.command`, `yakuwari.edn`, `itonami.edn`, `cron/jobs.json`,
`scripts/`, `skills/`. State and DBs never cross with it:
`sessions/`, `workspace/`, `memories/`, `logs/`, `.itonami/`,
`cron/output/`, `cron/usage_audit.jsonl`, `cron/ticker_*`,
`cron/itonami-runs.jsonl`. Each store keeps its own.

### Two CLIs, two inference rails

The same split applies to inference — the two CLIs never share a rail:

| | hermes agent CLI | itonami-agent CLI |
|---|---|---|
| profile store | `~/.hermes/profiles/` | `~/.itonami/profiles/` |
| 推論 rail | `config.yaml` `model:`（openrouter 等） | `itonami.edn` `:inference`（murakumo / mishima 等） |
| murakumo / mishima | **使わない** | **専用** |

A Hermes agent profile must not use murakumo/mishima — not in `config.yaml`,
not in a cron job's `model`/`provider` pin (the pin wins over config, so both
are banned). `itonami.edn :inference` is read only by itonami-agent; Hermes
skips the file entirely. `profile import`/`export` move a definition between
the two stores unchanged — the file format is the shared surface, the store
and the rail stay separate.

**One profile, one side** (com-junkawasaki/root ADR-2610222100, owner
2026-10-22: 「hermes と itonami をまず分離する。hermes は murakumo を使わないが、
itonami agent は murakumo を前提にする」). A profile with `itonami.edn` is an
itonami agent and runs on murakumo; one without is a Hermes agent and never
names murakumo or mishima. Reading one profile both ways (the additive
manifest) is retired; `import`/`export` are migration steps, not a mode. The
registry's `:agent/runtime` must agree with the profile.

The check is one pure Kotoba module, `kotoba/itonami/rail.kotoba`:
`profile-verdict` (registry runtime × has `itonami.edn` × rail) answers
`rail/ok`, `rail/hermes-on-murakumo`, `rail/hermes-with-itonami-manifest`,
`rail/itonami-without-manifest`, `rail/itonami-off-murakumo`,
`rail/itonami-without-rail` or `rail/unknown-runtime`; the caller asks
`hermes-provider-verdict` once per provider name a Hermes profile names
(`model`, `providers`, `fallback_providers`, each cron pin). Its gate builds it
with the pinned Amu selfhost root compiler (no Node.js, nbb, JVM or babashka):

```bash
AMU=../amu; G=$(mktemp -d)   # G must be under a path podman can mount
cp "$AMU/seed/bootstrap/aarch64-linux-static-root.elf" "$G/root.elf"
F=kotoba/itonami/rail.kotoba
end=$(grep -n 'test-profile\]))' $F | cut -d: -f1)
{ echo '(ns itonami-rail-gate (:export [main]))'
  tail -n +$((end+1)) $F
  cat <<'EOF'
(defn main [] :i64
  (+ (if (test-murakumo-rail) 1 0) (+ (if (test-runtime-for) 2 0)
  (+ (if (test-hermes) 4 0) (+ (if (test-itonami) 8 0)
  (if (test-profile) 16 0))))))
EOF
} > "$G/gate.kotoba"
podman run --rm --platform linux/arm64 --network none -e KEXE_CAP_RESOURCES_35="$G" \
  -v "$G:$G" -w "$G" docker.io/library/python:3.12-alpine sh -c \
  "./root.elf compile $G/gate.kotoba --target aarch64-linux --output $G/gate.elf --format static \
   && chmod +x gate.elf && KEXE_STRUCTURED_REPORT=1 ./gate.elf"
#   → {:status :ok :result 31 ...}      (31 = all five test-* true)
```

Measured 2026-10-22 with the root of amu `f5b11a08` (sha256 `8256bfd8…dc7`):
`:result 31`; a mutated `test-hermes` (mishima allowed) gives `27`. Receipt:
`docs/evidence/rail-selfhost-gate-20261022.edn`. The existing `.cljk`
`profile check` is unchanged and does not call this module yet.

| Hermes surface | itonami-agent |
|---|---|
| `SOUL.md`, `profile.yaml`, `config.yaml`, `.env`, `secrets.command` | read the same way. YAML reader is checked against PyYAML on all 1,954 host files: 0 differences |
| `model` / `providers` / `fallback_providers`, job pin disables fallback | same resolution order (`cron/scheduler.py`, `runtime_provider_custom.py`) |
| `agent.max_turns`, `agent.run_budget_seconds` (80 % wrap-up notice, hop timeout ≤ ½ remaining budget) | `agent.max_turns` follows Hermes' `resolve_turn_limit` (unset / `none` / `null` / `unlimited` / `infinite` / `infinity` / `inf` / `∞` / `0` / `-1` / bools / garbage = unlimited; ints and floats truncate; resolution order API value > `agent.max_turns` > root `max_turns` > `HERMES_MAX_ITERATIONS`), the case list mirroring Hermes' `tests/hermes_cli/test_resolve_turn_limit.py`; the 80 % wrap-up notice fires at the mark (`elapsed ≥ 0.8·budget`, `5·elapsed ≥ 4·budget` in whole milliseconds — exact equality fires, as in Hermes' `_maybe_inject_run_budget_wrapup`), once per run (latched on a successful append), as Hermes' `RUN_BUDGET_WRAPUP_NOTICE` verbatim appended (`\n\n` + notice) to the newest tool result, and the hop timeout is capped at half the budget left (min 60 s floor, never raised), recomputed per hop — Hermes' `chat_completion_helpers.cap_to_run_budget`; an explicit hop timeout (`models.<m>.timeout_seconds` / `providers.<p>.request_timeout_seconds`) wins untouched — plus up to 3 rounds over the chain with backoff when every hop failed transiently (429 / 5xx / transport) |
| tools `terminal process_manage read_file write_file patch search_files web_search web_extract skills_list skill_view skill_manage todo_list delegate_task cronjob_manage memory execute_code session_search ha_list_entities ha_get_state ha_list_services ha_call_service`; toolsets `terminal`, `file`, `web`, `search`, `skills`, `todo`, `memory`, `session_search`, `code_execution`, `homeassistant` | these names have Kotoba handlers and JSON-string results (incl. `manage_connections` slice 1: read-only connection surfaces — local MCP auth state and dapp rows, hosted connectors answer the named tool-gateway unavailability); some semantics remain partial. `terminal(background=true)` and `process_manage` provide background terminal processes, checkpointed to `processes.json` and restored on the next runtime touch (Hermes crash-recovery, `restore-checkpoint!`). `process_manage handoff` implements Hermes' `_handoff_process` / `transfer_ownership`: a running process a delegate child owns (`owner_task_id` = the child's `sub-…` id) moves to its live parent exactly once — `owner_task_id`, the container `task_id` (`session:<key>` / `default`, as `_resolve_container_task_id` resolves a non-container backend), `session_key` and `handoff_note` flip exactly as in Hermes and persist in the same checkpoint shape (recovery defaults `owner_task_id` to `task_id`, as `process_registry_checkpoint` does) — with the parent-gate, parent-owner, per-child cap (3), required `data` note, and not-owned/unknown refusals all answering Hermes' verbatim outcomes. Kotoba binds one task id per agent run (Hermes binds a fresh one per turn in `_bind_turn_identity`). Completion notices are pushed: `terminal(background=true, notify_on_complete=true)` arms Hermes' `_publish_finished` completion event (redacted command and output), `drain_notifications` routes it to the owning conversation between model turns (and as its own turn in `chat`) with Hermes' ownership proof (`session_key` equality; unkeyed events to the first drainer), the wait/log/poll dedup (`_completion_consumed` / `_poll_observed`), `sub-…`-owner suppression behind `delegation.surface_child_process_notifications`, and `format_process_notification`'s completion text verbatim (`handoff_note` rides as "Handed off to you by a subagent before it finished. Purpose: …"), batched by `ProcessNotificationBatch.render`. A delegated child's spawn stays armed and its result carries `subagent_note` verbatim. A child-owned completion names its provenance exactly as Hermes' `_delegation_attribution_line`: `get_subagent_attribution` resolves live and recently-finished children (`_active_subagents` plus a bounded FIFO of 200 retained stubs — `goal`, `delegation_id`) into `Started by subagent <id> of delegation <deleg>. Task: "<goal>"` (the goal is stripped, and over 120 characters truncates to 117 + `...`; a missing `delegation_id`/goal drops just that clause), the lookup key is `owner_task_id` (the container `task_id` may be `session:<key>` / `default`), and an aged-out registry entry falls back to `Started by subagent <id> (delegate_task).`. Kotoba stamps `delegation_id` once per `delegate_task` call in Hermes' live-transcript batch id shape (`deleg_` + 8 hex, `tools/delegation_live_log.create_live_transcripts`); every child of the batch shares it. `terminal(notify=[...])` / legacy
| tools `terminal process_manage read_file write_file patch search_files web_search web_extract skills_list skill_view skill_manage todo_list delegate_task cronjob_manage memory execute_code session_search ha_list_entities ha_get_state ha_list_services ha_call_service`; toolsets `terminal`, `file`, `web`, `search`, `skills`, `todo`, `memory`, `session_search`, `code_execution`, `homeassistant` | these names have Kotoba handlers and JSON-string results (incl. `text_to_speech` slice 1: OpenAI-compatible /audio/speech via `tts.provider`/`tts.model`, audio written to the profile workspace, unconfigured = named error); some semantics remain partial. `terminal(background=true)` and `process_manage` provide background terminal processes, checkpointed to `processes.json` and restored on the next runtime touch (Hermes crash-recovery, `restore-checkpoint!`). `process_manage handoff` implements Hermes' `_handoff_process` / `transfer_ownership`: a running process a delegate child owns (`owner_task_id` = the child's `sub-…` id) moves to its live parent exactly once — `owner_task_id`, the container `task_id` (`session:<key>` / `default`, as `_resolve_container_task_id` resolves a non-container backend), `session_key` and `handoff_note` flip exactly as in Hermes and persist in the same checkpoint shape (recovery defaults `owner_task_id` to `task_id`, as `process_registry_checkpoint` does) — with the parent-gate, parent-owner, per-child cap (3), required `data` note, and not-owned/unknown refusals all answering Hermes' verbatim outcomes. Kotoba binds one task id per agent run (Hermes binds a fresh one per turn in `_bind_turn_identity`). Completion notices are pushed: `terminal(background=true, notify_on_complete=true)` arms Hermes' `_publish_finished` completion event (redacted command and output), `drain_notifications` routes it to the owning conversation between model turns (and as its own turn in `chat`) with Hermes' ownership proof (`session_key` equality; unkeyed events to the first drainer), the wait/log/poll dedup (`_completion_consumed` / `_poll_observed`), `sub-…`-owner suppression behind `delegation.surface_child_process_notifications`, and `format_process_notification`'s completion text verbatim (`handoff_note` rides as "Handed off to you by a subagent before it finished. Purpose: …"), batched by `ProcessNotificationBatch.render`. A delegated child's spawn stays armed and its result carries `subagent_note` verbatim. A child-owned completion names its provenance exactly as Hermes' `_delegation_attribution_line`: `get_subagent_attribution` resolves live and recently-finished children (`_active_subagents` plus a bounded FIFO of 200 retained stubs — `goal`, `delegation_id`) into `Started by subagent <id> of delegation <deleg>. Task: "<goal>"` (the goal is stripped, and over 120 characters truncates to 117 + `...`; a missing `delegation_id`/goal drops just that clause), the lookup key is `owner_task_id` (the container `task_id` may be `session:<key>` / `default`), and an aged-out registry entry falls back to `Started by subagent <id> (delegate_task).`. Kotoba stamps `delegation_id` once per `delegate_task` call in Hermes' live-transcript batch id shape (`deleg_` + 8 hex, `tools/delegation_live_log.create_live_transcripts`); every child of the batch shares it. `terminal(notify=[...])` / legacy
`watch_patterns` arm watch-pattern events, and `terminal(heartbeat=N)` (min
60 s, implies `notify=true`) arms heartbeat events, exactly as `ProcessRegistry`'s
watch/heartbeat machinery: every output chunk is scanned (`watch_match` carries
the matched lines — 20 lines / 2 000 chars — plus the rate-limited `suppressed`
count), with per-session 15 s spacing (one strike per window; 3 consecutive
strikes or 8 lifetime deliveries disable watching with a `watch_disabled`
summary and promote the session to `notify_on_complete`) and a registry-wide
breaker (15 matches per 10 s; overflow emits `watch_overflow_tripped` /
`watch_overflow_released` summaries). Heartbeats queue a `heartbeat` tick
carrying the output since the last one (quiet ticks skipped, tail capped at
2 000 chars with `omitted`). The events format verbatim as
`format_process_notification`'s `watch_match` / `heartbeat` branches and reach
the conversation between model turns, one message per
`group_process_notifications` group (watches and heartbeats are batch
barriers). The one-shot linger is wired exactly as Hermes'
`continue_quiet_notify_completions` / `terminal.oneshot_completion_wait_seconds`:
a non-failed `-z` turn runs the notify-resume loop (owned completion texts
re-enter as follow-up turns — one per round, joined `\n\n` — under ONE shared
linger budget, ≤ `_MAX_QUIET_NOTIFY_ROUNDS` (8) rounds, stopping early on a
timed-out process, and a diagnostic-only wake running but never displacing the
printed answer under suppression), and any one-shot exit that skips the loop
lingers bounded (`wait_for_pending_completions`, `waited`/`completed`/
`timed_out` id lists, orphaned-pipe exits reconciled from the real child state)
for `notify_on_complete` children before the parent dies. The spawn result carries Hermes' `spawn_background_process` result notes and
effective arming (`hint` = `_SILENT_BACKGROUND_HINT` +
`_HOMEBREW_CI_POLLER_HINT`, `notify_unsupported` = `_ASYNC_UNSUPPORTED_NOTE`
on an async-unsupported turn — Hermes binds `async_delivery=False` for cron
job turns, so Kotoba's default cron executor runs its turns `:async-delivery?`
false — `watch_patterns_ignored`, `heartbeat_ignored`, `subagent_note`, and
the `heartbeat_seconds` / `watch_patterns` keys; a delegated child's spawn
stays armed exactly as Hermes while its result says so). The gateway completion
watcher's registration contract is wired exactly as Hermes
(`terminal_tool_background._register_completion_watcher` →
`run_notifications.arm_process_watcher`): a notify spawn with stamped routing
(`_stamp_gateway_routing` from `HERMES_SESSION_*`) sets `watcher_interval` 5 and
registers the descriptor (`session_id`, `check_interval` 5, `session_key`,
`platform`, `chat_id`/`user_id`/`user_name`/`thread_id`/`message_id`,
`notify_on_complete`, `parent_session_id`) — armed through the live runner's
`arm_process_watcher` hook, parked in `pending_watchers` when nothing serves,
and drained by the startup / post-turn batch detach (`run_startup` /
`run_turn_persistence`, atomic reassign). The checkpoint round-trips the
`watcher_*` / `watcher_interval` / `parent_session_id` fields and
`process_registry_checkpoint`-style recovery re-enqueues the descriptor
(`check_interval` = the stored interval). The watcher's delivery loop
(`_run_process_watcher`'s chat push / admission) is
`itonami.agent.watcher/run-process-watcher!`, verbatim control flow — the
silent `off` wait, the `all`-mode running updates, the agent-notify synthetic
completion with the launching-turn-busy concise receipt, the refused-injection
`jittered_backoff(…, jitter_ratio=0.0)` retry (8 attempts, then the
`completion_admission` recheck's committed break or the fall-back notice) and
the wait/log-consumed skip — its two egress calls riding the messaging gateway
adapter surface as the `:send!` / `:enqueue!` / `:admission-recheck` hooks;
the chat push is wired live — `itonami.agent.gateway` is Hermes'
`gateway/delivery.py` `DeliveryTransport` / `resolve_delivery_transport`
(a concrete native adapter always wins; Relay is eligible only when its
transport `fronts_platform` the logical platform; an explicitly disabled
native adapter never shadows an enabled Relay; the `PlatformConfig.enabled`
gate defaults False), `gateway/platforms/base.py`'s send surface (`send` /
`send_for_platform` / `fronts_platform` as the adapter fns),
`run_notifications._send_watcher_message` verbatim (`if adapter and chat_id`,
the `_non_conversational_metadata` merge — `non_conversational` on Discord
only — and `Watcher delivery error: %s` suppression) and `run.py
_gateway_platform_value` / `_non_conversational_metadata`, bound as the
loop's `:send!` by `gateway/send-hook`; the loop's `:enqueue!` /
`:admission-recheck` are bound live by `gateway/enqueue-hook` /
`gateway/admission-recheck-hook` over the same surface — the admission fan-in
is `_enqueue_process_completion_notification` /
`_flush_process_completion_batch` verbatim (the `should_surface_notification`
drop, the route-key batching over `_COMPLETION_BATCH_KEY_FIELDS` +
`parent_session_id` / `origin_session_id`, the 0.1 s coalescing window,
`_format_coalesced_process_completions`, `process_completion_display_text`'s
`_display_text`, the `_automation_identities` merge, the already-admitted
skip, `_record_coalesced_completion_siblings`, and waiter settlement — True /
None / False, `_cancel_process_completion_batch_tasks` settles retryable),
with `completion_admission` / `producer_identity` matching the admission rows
(`local_automation_v1` / `native_text_v1.automation`) of the entry's route
owner and the lost-ACK `committed` break. Kotoba `execute_code` runs one confined, stateless Python source string per call (no persistent kernel — state does not survive across calls) and serves the in-script `hermes_tools` RPC over Hermes' file transport: the generated `hermes_tools.py` stub (`generate_hermes_tools_module(transport="file")` byte-identical), `req_<seq:06d>`/`res_<seq:06d>` request files with the constant-time token check, the allow-list (`SANDBOX_ALLOWED_TOOLS` intersected with the run's advertised tools), the 50-call budget, terminal param stripping, the dispatch log, and `tool_errors_since` on the result (`tool_calls_made` / `tool_errors`), every in-script call dispatched through the run's own tool handlers. the import-failure hint rules (`_FAILURE_HINT_RULES`) map a failed script to ONE actionable recovery hint (bounded 4000-char scan, first match wins). Kotoba `session_search` supports bounded browse, FTS discovery, read, and scroll, plus Hermes' cross-profile lookup (`session_search_tool._resolve_profile_db` verbatim: `profile=` or the combined `<profile>/<id>` session_id value — the split `test_combined_value_autosplits` pins — open a named sibling profile's `state.db` read-only for every shape through `hermes_cli/profiles.py`'s `normalize_profile_name` / `validate_profile_name` / existence gates with the same error strings; a fully-prefixed `@session:<profile>/<id>` value hits the name gate exactly as Hermes' source does, and a bare id never scans other profiles — a miss answers `_read_scoped`'s hint) and Hermes' `detail` modes (`_hydrate_hit`: `adaptive` (default) fully hydrates only the top-ranked discovery hit with `get_anchored_view`'s window/bookends as bounded SQL (`messages_before` / `messages_after`, `anchor`, `_shape_message` caps), lower hits carry just the anchor message marked `detail: compact`; `full` hydrates every hit; bookends exclude compaction summaries). Discovery honours Hermes' `sort` (only `newest` / `oldest` count — trimmed, lower-cased, anything else falls back to rank-only — as `_FTS_ORDER_BY`'s temporal bias on top of rank), `after` / `before` (`_parse_iso_bound` verbatim: ISO date/datetime — date-only is midnight UTC, naive is UTC — or relative `7d` / `24h` / `2w`; an invalid bound raises the `invalid time bound` tool error in the discovery shape only) enforced in SQL on `sessions.started_at` (inclusive / exclusive, `_search_filter_clauses`) so LIMIT cannot be filled by out-of-window hits, and `exclude_session_ids` (`_normalize_exclude_session_ids`: string or list, deduped, cap 20) dropping the excluded ids and their lineage (`_excluded_lineage_roots` over `parent_session_id` roots) with backfill from Hermes' 300-row scan (`_DISCOVER_SCAN_LIMIT`) so an excluded hit never starves the limit. Title matching, lineage dedup, and `link` hints are not implemented. `hermes-cli`/`hermes-cron` retain Hermes' full core inventory and refuse to start when any selected tool is unsupported, rather than silently presenting a reduced bundle |
| `cron/jobs.json` (including `monitor_script` / `monitor_url`), 5-field cron / interval / once schedules | read and written in Hermes' format; Kotoba can create, list, and update monitor jobs, then evaluates the monitor before the agent turn |
| Pre-run script extensions `.sh`/`.bash`, `.cljk`, `.js`/`.mjs`, `.py`, `.hy` | extension dispatch; `.hy` runs through `hy.cmdline.hy_main` with the job/config-selected Python, which must have Hy installed |
| cron prompt: `_CRON_HINT`, `## Script Output` / `## Script Error` block, empty stdout and `{"wakeAgent": false}` skip, `[SILENT]`, `[CRON_FAILURE]` | identical text and semantics |
| `cron/output/<id>/<YYYY-MM-DD_HH-MM-SS>.md`, newest 50, mode 0600 | identical layout (adds `**Engine:**` / `**Peer:**` lines) |
| `usage_audit.jsonl`, `ticker_heartbeat`, `ticker_last_success` | written |
| `-p`, `-z` (stdout = final text, exit 1 + `… -z: reason` on stderr), `-m`, `--provider`, `-t`, `cron list/create/run/tick/runs/status`, `profile list/show`, `chat`, `gateway run`, `doctor`, `model`, `fallback`, `sessions [list]`, `sessions show`, `status`, `pause [reason]`, `resume`, `send --chat-id C [--platform P] [--thread-id T]` | same commands; `doctor` reports named findings and exits 1 when any (a profile that will not load — e.g. a malformed jobs.json — readiness issues, unset model, missing state.db, missing lane token envs for lanes that need one, paused). `model`/`fallback` are show-only for now (the effective resolution with the config layer it came from, chain order verbatim from `provider/chain`; the setter lands with config writing). `sessions list/show` read this profile's state.db read-only with session_search's visibility filters (resume lands with history re-entry). `cron create` also accepts `--no-agent`, `--monitor-script`, and `--monitor-url`. `pause`/`resume` are Hermes' emergency stop: one store-wide marker gates cron dispatch (run/tick and the gateway tick loop) and new `gateway serve` turns; one-shot `-z` is not a gateway turn and stays available, as in Hermes. While paused, inbound `gateway serve` updates are dropped (`:status :dropped :reason "paused"`) and the poll offset still advances — they are NOT replayed after `resume` |
| `cron/executions.db` | Kotoba writes Hermes-shaped claimed/running/completed/failed rows with ownership, timestamps, and delivery outcome. A later run marks attempts `unknown` only when the prior owner is provably gone; it does not retry them automatically. Handoff adoption matches Hermes: `mark-handoff-pending!` fences restart recovery while an external worker adopts a claim, `adopt-claimed!` is the single claimed-to-running adoption gate (ownership transfers exactly once), and recovery honours the 30s adoption grace |
| `cron incidents` / `cron incidents ack <id>` | Kotoba groups failures by Hermes-compatible job/error signature, resolves them after success, and records acknowledgements and delivery outcomes. The repeat-alert gate is wired (`cron.failure_repeat_alert_hours`, default 6h: an alerted signature withholds the per-run ping until the cooldown elapses; an acked signature is silent until the error text changes; 0 re-alerts every run) |
| configured MCP stdio and Streamable HTTP servers (plus the built-in `itonami_dapps` toolset, below) | discovered from `mcp_servers`, exposed as `mcp__server__tool`, and invoked with profile-scoped environment values and configured HTTP headers. Cached OAuth tokens can refresh with issuer binding and a Kotoba process lock; interactive OAuth login is implemented (`mcp login <server> [--device]`: PKCE over a loopback redirect, or the device grant for headless surfaces). MCP subprocesses are disabled on peer runs |
| browser navigation, snapshot, click, type, scroll, back, key press, image listing, screenshot vision, console | local Chrome through `agent-browser`; a Kotoba loopback proxy checks the allowlist and every DNS result for HTTP, HTTPS CONNECT, redirects, and subresources, pins the selected public IP, disables Chromium's implicit loopback proxy bypass, and closes the per-run session at loop end. Browser output is scrubbed for common credential forms. Raw CDP (`browser_cdp`) and dialog control (`browser_dialog`) run against a configured CDP endpoint (`browser.cdp_url` / `browser.cdp_endpoint` / `BROWSER_CDP_URL`): one CDP command per call over its WebSocket (target attach supported), credential-shaped strings redacted from results. The `browser_vault_*` tools run against a host-local encrypted store (`vault/vault.json.enc` + a 0600 key file; the CLI `vault add|list|remove` is the write path, as in Hermes): `browser_vault_list` returns handles and metadata only — passwords never enter the conversation — `browser_vault_fill` types the password into the page over CDP, `browser_vault_enter_code` mints the TOTP server-side (RFC 6238) when the login carries a seed and types it over CDP, `browser_vault_save_login`/`unlock` answer honestly when no interactive surface or external manager exists (the CLI is named as the write path). `browser_exec` runs Python through the Browser Use CLI engine (`python -m browser_harness.run`; interpreter from `browser.use_python` / `BROWSER_USE_PYTHON` / `ITONAMI_PYTHON`, else `python3`) and answers honestly when `browser_harness` is missing; the session and workspace persist across calls, output is credential-scrubbed. The cloud backend remains unsupported and readiness-blocked |
| `cron/notepad` (`cron notepad <job-id> set\|get\|delete\|list`) | per-job durable KV notepad in profile-local `cron/notepad.db`, same schema and caps as Hermes (16 KB/value, 128-char key, 64 KB/job; refused writes leave the store untouched). Prompt-injected per run — empty renders `''` so unused jobs keep a byte-identical prompt — and cleared when the job is removed. CLI write path only, as in Hermes |
| `cron/deliveries.db` (durable delivery handoff) | Hermes' `delivery_queue` contract: enqueue before the transport, a send claimed at most once, terminal rows fenced (never rewritten), payloads redacted and pruned to `delivery_tombstones` (bounded at 1,000). A claimer that dies mid-send is fenced `unknown` and never retried — losing a delivery beats duplicating a possibly-completed send — and `tick` surfaces it as an incident. `settle-queued-delivery!` writes a queued send's terminal outcome back onto the run that queued it (fenced on the execution id: the ledger's latest attempt for the job must still be that run, and a later run's status is never rewritten) and `drain-queued!` is the drain: each pending send is claimed at most once, delivered through its lane's adapter, and settled — `tick` drains before running due jobs. `ledger-outcome` maps queue status to the ledger (`unknown` -> `failed`) |
| `gateway serve [--platform telegram]` | the messaging surface (JUN-465): `getUpdates` long poll -> normalize -> intake guards -> chat to profile routing -> a turn on the owning profile -> the reply in the SENDER's chat (webhook-style sends refuse a chat they do not serve). One bot token per serve process (`delivery.telegram.token_env`, enforced at startup); thread replies carry `message_thread_id`; `--interval seconds` is the poll-error backoff (validated: 1s floor, 10min cap — never a hot retry loop) |
| `deliver` lanes (`local`, platform lanes, `bot-chat[:name]`, `all`) | Hermes' `_normalize_deliver_value` / `parse_bot_chat_deliver_token` contract and the `_classify_delivery_outcome` vocabulary (`delivered` / `failed` / `suppressed` / `suppressed_acked` / `not_configured` / `queued`). Every non-local lane resolves to a delivery adapter (a registered one — the messaging gateway's platform adapters plug into `delivery/register-adapter!` — or the job run's `:delivery-fn`); a lane with no adapter is `not_configured`, never a silent success. Built-in adapters resolve when configured (tokens from the env named by `delivery.<platform>.token_env`, targets from `delivery.<platform>` config): `telegram` (Bot API sendMessage), `slack` (chat.postMessage), `discord` (execute-webhook or bot channel message), `mattermost` (incoming webhook), `matrix` (m.room.message send). Other platforms are **not implemented**; Kotoba also keeps its detailed local run log in `cron/itonami-runs.jsonl` |

`delegate_task` carries Hermes' argument contract: `tasks` up to 10
(`delegation.max_concurrent_children`), `tasks[].goal/context/output_schema/
images`, and `action` spawn·list·steer·stop with `subagent_id`/`message`.
One-shot sessions join their foreground children and return `results` in the
call (as Hermes does without a later-result consumer); `output_schema` is
told to the child up front and validated with one bounded correction retry
(`schema_valid` / `schema_errors` beside the raw summary, which is never
discarded). Children cannot call `delegate_task`, `clarify`, `memory` or
cron tools. Live controls work like Hermes': `steer` queues the correction into the
child's next tool result mid-run, and `stop` ends the child early with an
`interrupted` completion carrying its partial output. Sessions without a
later-result consumer (CLI `-z`, cron) still join their children; a caller
that passes `:join-children? false` gets background children back as live
handles (`{"background": true, results: [...status "running"]}`) whose
finished summaries re-enter as a message between model turns. What remains
of Hermes' delegation surface: cross-run re-entry in chat sessions.

Home Assistant uses the profile's `HASS_URL` / `HASS_TOKEN` (default URL:
`http://homeassistant.local:8123`); redirects are refused and the service-call
domains that can execute commands or issue arbitrary HTTP requests are blocked.
`ha_call_service` requires approval. `skill_manage` has remaining
staged-review/curator differences from Hermes. These limitations must be closed
before claiming full agent parity or adopting profiles that depend on them.

The CLJK turn API accepts prior user/assistant history and per-request
instructions, in addition to the current prompt. Tool rows remain scoped to the
turn that produced them; only the user/assistant transcript is carried into the
next request, matching the current Kotoba Desktop gateway's normalized history.

`itonami-agent bridge` exposes this turn API to a local host over stdin/stdout:
one JSON request containing an explicit `tool_names` array, then JSONL event rows
and one terminal result row. It refuses any requested tool the Kotoba agent
does not implement; it never silently narrows a caller's requested tool set.

## itonami profile

`profile itonamify <p>|--all` adds `itonami.edn` (schema
`cloud.itonami.profile.v2`; v1 manifests stay valid) to a profile in the
itonami store. The manifest is additive: deleting itonami.edn returns the
profile to a plain Hermes-format profile, and `profile export` copies such a
profile back into a Hermes home as-is.

```clojure
{:itonami/schema "cloud.itonami.profile.v1"
 :profile/id "hiraku-soudan"
 :runtime   {:engine :itonami-agent :scheduler :hermes}   ; who ticks cron
 :placement {:mode :p2p :order [:peer :local] :peers :trusted :inference-rail :murakumo}
 :state     {:workspace :host-local :results :cid-receipts :secrets :never-leave-host}
 :bundle    {:cid "bafkrei…" :files 5 :skills []}          ; content address of the definition
 :capabilities [...]}                                       ; copied from yakuwari.edn, grants nothing
```

v2 adds where the profile sits in the organisation, projected from the agent
registry by `profile organize --registry <agent-registry.edn>`. The registry
is an index, not authority: `:authority` only points at `yakuwari.edn`.

```clojure
 :agent/kind :worker                      ; :steward :unit :role-bot :organism :worker
 :org/world :awai                         ; :etzhayyim :awai :kotoba :host
 :org/path [:etzhayyim :awai :hyakka]     ; governance line; a :host profile has none
 :org/github "network-awai"  :org/unit :hyakka  :invocation :resident
 :awai/business :hyakka                   ; when the profile works for an awai business
 :ids {:repo "network-awai/app-hyakka" :yakuwari/id "…"}
 :authority {:default-decision :approval-required :source :yakuwari :ref "yakuwari.edn"}
```

- `profile check <p>|--all [--summary]` validates the manifest
  (`itonami.agent.manifest/validate`, no dependencies) and reports drift: a
  bundle CID that no longer matches the files, a config provider other than
  the declared rail, a missing managed SOUL block. Read-only; exit 1 on
  errors. Capability decisions follow yakuwari's vocabulary
  (`:autonomous :voice-required :approval-required :blocked`); a legacy or
  unknown word is a warning, because yakuwari.edn, not itonami.edn, is where
  it is fixed.
- `profile refresh <p>|--all [--dry-run]` rewrites what is derived from the
  profile's own files: a stale bundle CID (peers verify the bundle against
  it, so a stale CID fails peer runs) and `:capabilities`, re-copied from
  `yakuwari.edn` when the profile has one.
- `itonamify --refresh` keeps the declared runtime, placement, rails,
  terminal/web policy and organisation keys.
- `profile did <p>|--all [--registry F] [--out F]` prints each profile's
  did:key (`itonami.agent.identity`). It is the same identity tree
  cloud-itonami-app uses for its Bots (`bot-identity`): ed25519 seed =
  SHA-256(fleet-seed || 0x00 || key-id), key-id = the profile id (or
  `<profile-id>#<epoch>` after the registry raises `:did/epoch`). The key is
  derived, never stored. The fleet seed's canonical copy is the kagi item
  `shared/agent-identity-seed`; it reaches the one command through
  `ITONAMI_AGENT_IDENTITY_SEED`, filled in a human session; without it the
  command refuses. `profile organize` projects the
  registry's `:did` into `:ids :did`.
- `profile soul <p>|--all --registry F --worlds F [--unit U] [--dry-run]`
  renders the generated SOUL blocks (`itonami.agent.soul`): **world** (the
  `:soul` lines of every world on the profile's `:org/path`, then
  `:soul/common`, from `manifest/worlds.edn`), **unit** (the registry entry)
  and **role** (a summary of `yakuwari.edn`, which stays the authority). They
  sit right after the workspace-locations block; together they stay under
  1500 characters (capability lists shrink to fit). The body — everything
  outside these blocks — is never changed: a profile whose body would change,
  or whose blocks would not fit, is refused. Every rewrite keeps a backup
  and a receipt under `~/.itonami/state/soul-blocks/<stamp>/`.

Exactly one scheduler ticks a profile:

- `profile readiness <p>|--all` checks active cron jobs for unsupported Kotoba
  tools, missing/unrefreshable OAuth caches, and non-local delivery lanes.
- `profile adopt <p>` sets `:scheduler :itonami` and writes Hermes'
  `gateway.parked` marker, so the Hermes gateway stops ticking it;
  `gateway run` then ticks it. `profile adopt --all --dry-run` previews a
  fleet-wide ownership change. Fleet adoption refuses the whole operation if
  any profile fails the Kotoba readiness check.
- `profile adopt --ready-only [--dry-run]` adopts every currently ready profile
  and reports blocked profiles individually. This supports staged fleet
  migration while preserving the all-or-nothing behavior of `--all`. Profiles
  owned by a scheduler other than Hermes or Kotoba are refused until that
  scheduler is explicitly retired.
- `profile release <p>` reverses both. `profile release --all --dry-run`
  previews a fleet rollback; `profile release --all` applies it.
- `profile refresh-bundle <p>` recomputes the CID after files change without
  replacing the rest of `itonami.edn` (including custom bundle directories and
  scheduler ownership).
- `profile hy-stage <p>|--all <artifact-dir> [--dry-run]` verifies the staged
  migration manifest and every source/payload hash before copying sibling `.hy`
  files into profile `scripts/`. It leaves `.py` sources and job references intact;
  Kotoba-owned bundle CIDs are refreshed after files are staged.
- `profile hy-migrate <p>|--all [--dry-run]` switches cron `script` and
  `monitor_script` references only when a sibling `.hy` file exists, the profile
  is readiness-clean, and Kotoba owns its scheduler with Hermes parked. Apply
  mode holds the Kotoba tick lock and updates only the job fields, preserving
  `.py` sources, job run state, and unknown `jobs.json` metadata.

Hy cron scripts use the first configured interpreter among the job's
`interpreter`, `cron.script_python`, `ITONAMI_PYTHON`, `HERMES_PYTHON`, then
`python3`. The fleet target is Hy 1.3.1, supported on Python 3.9 through 3.15.
The dispatcher inserts the script directory into `sys.path` and preserves
arguments after the script path, matching the `.py` job contract. When launched
by Kotoba Gateway, the scheduler uses `KOTOBA_HY_DEPS` when configured; otherwise
it discovers Hy and `funcparserlib` in the main environments under
`ITONAMI_HERMES_ROOT/installs` and adds those site-packages to the selected
Python's import path. It does not download or copy packages. Direct CLI runs
still require Hy in the selected interpreter or an explicit `KOTOBA_HY_DEPS`
path (multiple paths may be separated with the platform path separator).

## itonami dapps (`-t itonami_dapps`)

`itonami_dapps` is a built-in toolset for the itonami dapps that the
[Itonami Registry](https://github.com/cloud-itonami/itonami-registry) publishes
as stdio MCP servers. Selecting it starts them for that run; no profile file
changes.

```
bin/itonami-agent -p <profile> -t hermes-cli,itonami_dapps -z "…"
bin/itonami-agent dapps        # where each server resolves on this host (starts nothing)
```

| server | registry entry | tools |
|---|---|---|
| `mihari` | `mcp/mihari` (cloud-itonami/app-itonami-mihari) | `mcp__mihari__mihari_ingest_events`, `mcp__mihari__mihari_decide` — Sentry-compatible error grouping and triage rules |
| `dandori` | `mcp/dandori` (cloud-itonami/app-itonami-dandori) | `mcp__dandori__dandori_import`, `…_export`, `…_cycle_progress`, `…_check_estimate`, `…_sla_status` — Linear-compatible export conversion and planning checks |

How it behaves:

- The servers are added to the run's effective `mcp_servers` only. If the
  profile already defines a server with the same name, the profile's spec is
  used as written.
- A checkout resolves from the registry placeholder (`MIHARI_REPO`,
  `DANDORI_REPO`), then from this repository's west sibling
  (`../../cloud-itonami/app-itonami-<name>`). It is launched as
  `kbb <checkout>/bin/<name>-mcp`.
- Nothing is cloned or fetched. A checkout that does not resolve is reported
  under "MCP server issues" for that run, and its tools are absent. A
  placeholder that does not hold the launcher is an error; it does not fall
  through to another checkout.
- `no_mcp`, `agent.disabled_toolsets: [itonami_dapps]` (or a server name), and
  peer runs start none of them. Naming another server
  (`-t mcp-cloudflare,itonami_dapps`) keeps them.
- The tools are pure functions over the text passed to them. They make no
  network calls and store nothing. The first launch of a checkout still lets
  kbb resolve its pinned `kotoba-lang/text` git dependency.

The registry and source commits the toolset was written against are recorded
in `src/itonami/agent/dapps.cljk`. A newer checkout is used as found: the pin
is provenance, not an admission check.

## Peer-to-peer execution

Every node runs the same program. There is no coordinator.

```
requester (node A)                               peer (node B)
  itonami.edn :placement [:peer :local]
  discover: peers.edn + one gossip hop  ── GET /itonami/v1/peer ──▶  signed {did load rails profiles peers}
  pick: trusted, not full, holds CID first
  bundle = SOUL + config − host-local + jobs + scripts  (CIDv1 raw sha2-256)
  POST /itonami/v1/run  (signed envelope: profile cid prompt opts [files])  ──▶ verify sig, trust, ts, nonce
                                                    ◀── 202 {run_id} (signed)
                                                    `peer exec` child process:
                                                      verify bundle CID, materialize ~/.itonami/peer-runs/<cid>/
                                                      rebase A's home paths onto the copy
                                                      run the turn with B's own inference rail
                                                      (profile chain + murakumo), writes confined to the copy
  GET /itonami/v1/run/<id> every 3 s (signed)  ◀── 200 signed {final usage attempts writes result_sha256}
  verify B's signature and CID, apply workspace/ writes, record receipt in cron/itonami-runs.jsonl
```

- **Identity**: ed25519 per node (`~/.itonami/node/key.json`, 0600), named by
  `did:key:z6Mk…`. A murakumo fleet node advertises `MURAKUMO_NODE_DID`
  beside it.
- **Trust**: `~/.itonami/peers.edn`. Gossip learns URLs but never trust.
- **Secrets never cross**. The executing peer pays inference with its own
  rail (`~/.itonami/peer.env` or its environment); `murakumo` is put on the
  chain when the profile's `:inference-rail` is `:murakumo`.
- **`terminal` runs in an OS sandbox** (`itonami.agent.confine`): macOS
  Seatbelt (`sandbox-exec`) or Linux `bwrap`. Writes reach only the run's
  roots and a per-run `TMPDIR`; ssh/cloud/gpg keys, keychains, the node key
  and every `.env` / `peer.env` are unreadable (also to `read_file` and
  `search_files`); there is no network; the env is `PATH`/`HOME`/locale/`TERM`
  only. With no sandbox on the host the command
  is refused. A turn run for a peer always gets this policy: the bundle's
  `itonami.edn` cannot widen it. The remaining conditions of ADR-2609242300
  (tunnel, cross-node resume) are still open.

### Linux (bwrap) differs from macOS (Seatbelt)

bwrap matches paths, not patterns. Under it the whole home directory is an
empty tmpfs for every run, local ones too, and only the run's roots, the
profile home and the PATH toolchains are shown back; each `*.env`,
`*.env.*`, `secrets.command` and `auth.json` found under them (node_modules
and .git pruned) is masked with /dev/null. If that scan takes over 15 s the
command is refused. So a local run on Linux sees less of the home directory
than on macOS, and a dotenv outside the home directory (e.g. /srv/app/.env)
is not masked there. Verified on Linux 6.15 / bubblewrap 0.8.0 in a
container (2026-10-09): the same 193 assertions pass, and with the sandbox
bypassed 18 attack assertions fail.

## Terminal policy

Local runs read `:terminal` from the profile's `itonami.edn`:

```clojure
:terminal {:confinement :sandbox     ; default; :host = run unconfined (local only)
           :network true             ; outbound network (default: none)
           :env ["GITHUB_TOKEN"]     ; profile secrets passed to commands, by name
           :write ["~/notes"]}       ; extra write roots
```

A profile without `:terminal` gets the default: sandboxed, offline, no
secrets, writes confined to its terminal cwd.

`read_file` and `search_files` follow the same read rules: the secret stores
are refused before the file is even looked up (a symlink is judged by its
target), and `search_files` runs `rg` / `grep` / `find` inside the sandbox,
so a search over a broad path skips them. A turn run for a peer reads
nothing under the home directory except its own roots, the bundle it runs
from and the toolchains on `PATH`; its commands get the per-run `TMPDIR` as
`HOME`.

`web_extract` goes through `itonami.agent.webguard`: http(s) only, no
credentials in the URL, and every address the host resolves to must be
public -- loopback, private, link-local (cloud metadata), CGNAT (tailscale),
multicast and reserved ranges are refused, judged inside the socket's own
lookup so a DNS answer cannot change between check and connect. Redirects
are followed by hand (at most 5), each hop judged again; bodies are cut at
2 MB. To limit where a profile may fetch from at all:

```clojure
:web {:allow ["www.mhlw.go.jp" "*.go.jp"]}   ; exact names or *.suffix
```

A bundle can only narrow this, so a peer turn honours it. Every URL, fetched
or refused, is a line in `~/.itonami/logs/terminal-sandbox.jsonl`, with its
query string reduced to a length.

`web_search` uses the same fetch (so a profile with `:web :allow` must list
`html.duckduckgo.com` to search) and checks the query before it leaves the
host: queries over 256 chars, or carrying API keys / private keys / JWTs,
40+ char encoded blobs, e-mail addresses or phone numbers are refused. These
are pattern checks, not a guarantee. The audit line keeps the query's length
and a sha256 prefix, never its text.

### Decentralised inference (no third-party relay)

Every node brings its own inference rails and lends them to trusted peers.

```
any OpenAI client on node A (itonami-agent, Hermes)
  provider itonami-p2p  base_url http://127.0.0.1:7420/v1      (loopback only)
        │
        ├─ A's own rails  ~/.itonami/rails.edn   (llama-server, mlx_lm, Ollama,
        │                                         murakumo mishima-local-router over the mesh)
        └─ trusted peers  POST /itonami/v1/infer (signed envelope) ──▶ B's own rails only
                                                  ◀── signed response   (never forwarded onward)
```

- `peer rails detect` probes loopback for OpenAI-compatible servers and
  writes `rails.edn`; models too small for tool calling (≈1B and below) are
  marked `:agent? false` and used only when named exactly. `model: auto` picks
  the first agent-capable rail.
- `/peer` advertises `models` / `agent_models`, so gossip tells a node which
  peer can answer which model.
- For an itonami profile, hops whose base URL is a relay in
  `:inference :deny-hosts` (default `openrouter.ai`) are dropped from the
  chain; a profile without `itonami.edn` keeps its Hermes chain.
- **`itonami-p2p` is opt-in.** A profile gets it on its chain only when it
  names `:itonami-p2p` in `:inference :rails` or as `:placement
  :inference-rail`. New profiles use murakumo only (`:inference-rail
  :murakumo`, `:inference {:rails [:murakumo]}`); a turn run for a peer gets
  the requester's `:inference-rail`. `profile rail <p>|--all --to R
  [--dry-run]` repoints existing manifests (`murakumo`, `kotoba` or
  `itonami-p2p`).
- **Authority servers, used but not depended on.** kotoba
  (`api.kotoba.cloud`) and murakumo (`api.murakumo.cloud`) are the few
  authority servers of the plane (`:inference :authorities`). They keep their
  place on a profile's chain while healthy, but each sits behind a circuit
  breaker shared by the node (`~/.itonami/authority-health.json`): a failure
  parks the authority (402/401/403 → 30 min, 429 → 2 min, 5xx/transport → 5
  min) and later turns skip it at no cost while a hop behind it can still
  carry the turn; a success clears it. When the authority is the last rail
  (a murakumo-only chain) it is tried anyway, so a parked breaker never fails
  the turn by itself. `peer authorities` shows the breaker state.

### murakumo

murakumo today is hub-and-spoke: nodes poll `api.murakumo.cloud` for
inference jobs, and it has no generic agent-step job kind. itonami-agent
uses murakumo as the shared inference rail (`murakumo/free`, `mishima`) and
keeps agent execution on its own peer protocol. The
mesh path (`mishima-local-router` on a node, straight to fleet llama-servers
over tailscale) is used as a node-owned rail, without `api.murakumo.cloud`. Making agent turns a
murakumo job kind is a change on the murakumo side (`poll_worker.cljk`) and
not done here.

## Schedule

`kotoba/itonami/schedule.kotoba` computes when a cron job is next due, as one
pure Kotoba function (com-junkawasaki/root ADR-2610222120 decision 2; the
gateway becomes the trigger edge that only issues murakumo agent-step jobs).
`next-cron-ms`, `next-interval-ms`, `next-once-ms`, `due?` and `cron-problem`
keep `cron.cljk`'s semantics (5 fields, ranges, steps, lists, one day name, 7
= Sunday, Vixie day-of-month/day-of-week, strictly after, the 600000-step
guard) with two deliberate differences for a network of nodes: time is epoch
milliseconds plus an explicit UTC offset in minutes (so every node computes
the same instant; equal to the `.cljk` for a fixed-offset zone such as
Asia/Tokyo, +540), and a malformed expression is refused
(`schedule/bad-cron`) rather than read leniently. Gate (no Node.js, nbb, JVM
or babashka):

```bash
AMU=../amu; G=$(mktemp -d)   # G must be under a path podman can mount
cp "$AMU/seed/bootstrap/aarch64-linux-static-root.elf" "$G/root.elf"
F=kotoba/itonami/schedule.kotoba
end=$(grep -n 'test-other\]))' $F | cut -d: -f1)
{ echo '(ns itonami-schedule-gate (:export [main]))'
  tail -n +$((end+1)) $F
  cat <<'EOF'
(defn main [] :i64
  (+ (if (test-civil) 1 0) (+ (if (test-parse) 2 0)
  (+ (if (test-cron) 4 0) (if (test-other) 8 0)))))
EOF
} > "$G/gate.kotoba"
podman run --rm --platform linux/arm64 --network none -e KEXE_CAP_RESOURCES_35="$G" \
  -v "$G:$G" -w "$G" docker.io/library/python:3.12-alpine sh -c \
  "./root.elf compile $G/gate.kotoba --target aarch64-linux --output $G/gate.elf --format static \
   && chmod +x gate.elf && KEXE_STRUCTURED_REPORT=1 ./gate.elf"
#   → {:status :ok :result 15 ...}      (15 = all four test-* true)
```

Measured 2026-10-22 with the root of amu `f5b11a08` (sha256 `8256bfd8…dc7`):
`:result 15`; shifting the leap-day expectation by one minute gives `11`. The
expected instants were computed independently by a minute-by-minute brute
force. Receipt: `docs/evidence/schedule-selfhost-gate-20261022.edn`. The Node
gateway (`cron.cljk`) is unchanged and does not call this module.

## Self-organisation

`kotoba/itonami/self_org.kotoba` decides how an itonami bot keeps working on
a dandori board without a person in the loop (com-junkawasaki/root
ADR-2610222130; Linear JUN-310). The board rules (what may be taken, in what
order, who may move what) are dandori's (`cloud-itonami/app-itonami-dandori`
`kotoba/dandori/work.kotoba`), and a claim is a sahai lease
(`kotoba-lang/sahai` `kotoba/sahai/fence.kotoba`); this module holds the
bot's side:

- `wake-reason`: whether the trigger edge should issue an agent-step job for
  this bot now. `wake/go`, or `wake/stopped` (the stop switch wins over
  everything), `wake/lease-lapsed` (the organisation's lease was not renewed:
  fail closed), `wake/over-budget`, `wake/busy` (at its work-in-progress
  limit) and `wake/idle` (nothing takeable: no job, no cost).
- `next-after` / `next-state`: what follows a turn on a claimed issue.
  `next/complete` (done, with a receipt; state 4), `next/continue` (a step
  made, with a receipt; keep the claim; 3), `next/retry` (failed, under the
  attempt limit; 3) and `next/escalate` (blocked, an owner-only act, the
  attempt limit, or an unknown outcome: back to the steward; 2). A turn that
  says it finished or advanced but leaves no receipt counts as a failed
  attempt, so a bot cannot spin on an issue.
- `backoff-ms`: base * 2^(n-1) before retry n, at most the cap.
- `staffing-reason`: what the steward proposes to the governor. `staff/add`
  (takeable work and no worker, or more than high-per-worker per worker),
  `staff/retire` (nothing takeable and a worker idle at least
  retire-after-ms), `staff/hold`, or `staff/limit` (the day's change limit).

Gate (no Node.js, nbb, JVM or babashka; not in CI, which is stopped):

```bash
AMU=../amu; G=$(mktemp -d)   # G must be under a path podman can mount
cp "$AMU/seed/bootstrap/aarch64-linux-static-root.elf" "$G/root.elf"
F=kotoba/itonami/self_org.kotoba
end=$(grep -n 'test-staffing\]))' $F | cut -d: -f1)
{ echo '(ns itonami-self-org-gate (:export [main]))'
  tail -n +$((end+1)) $F
  cat <<'EOF'
(defn main [] :i64
  (+ (if (test-wake) 1 0) (+ (if (test-next) 2 0)
  (+ (if (test-backoff) 4 0) (if (test-staffing) 8 0)))))
EOF
} > "$G/gate.kotoba"
podman run --rm --platform linux/arm64 --network none -e KEXE_CAP_RESOURCES_35="$G" \
  -v "$G:$G" -w "$G" docker.io/library/python:3.12-alpine sh -c \
  "./root.elf compile $G/gate.kotoba --target aarch64-linux --output $G/gate.elf --format static \
   && chmod +x gate.elf && KEXE_STRUCTURED_REPORT=1 ./gate.elf"
#   → {:status :ok :result 15 ...}      (15 = all four test-* true)
```

Measured 2026-10-22 with the root of amu `f5b11a08` (sha256 `8256bfd8…dc7`):
`:result 15`. Counting a receipt-less "done" as complete gives `13`, and
ignoring the stop switch gives `14`. Receipt:
`docs/evidence/self-org-selfhost-gate-20261022.edn`. Nothing calls this module
yet: the cell route it is for needs agent-step jobs (JUN-289), a static image
that can reach the network (JUN-292) and a dandori board in yataverse
(JUN-296).

## Resident gateway

`~/Library/LaunchAgents/cloud.itonami.agent.gateway.plist` runs
`bin/itonami-agent gateway run --interval 60` (KeepAlive). Every minute it
ticks each adopted profile that has a due job — profiles independently, each
under its own `cron/.itonami-tick.lock`, secrets resolved only when a job is
due. Logs: `~/.itonami/logs/gateway.log`.

```
launchctl kickstart -k gui/$(id -u)/cloud.itonami.agent.gateway   # restart
launchctl bootout gui/$(id -u)/cloud.itonami.agent.gateway         # stop
```

## Fleet deployment

A node needs only `node`: the runtime is the nbb engine (`cli.js`, `lib/`,
`node_modules/import-meta-resolve`, ~19 MB) plus this repository, placed in
`~/.itonami/runtime/`. On the murakumo mishima nodes it runs as
`/Library/LaunchDaemons/cloud.itonami.agent.peer.plist` (`UserName` = the
node user, like `com.murakumo.mishima`), `node cli.js bin/itonami-agent peer
serve --port 7420 --url http://<tailscale-ip>:7420`; `peer rails detect`
finds the node's llama-server on `127.0.0.1:18094`. Trust is a full mesh in
each node's `~/.itonami/peers.edn`. `ITONAMI_PEER_PORT` moves the port (serve
and the `itonami-p2p` rail) on a node where 7420 is taken.

## System One Coding (kotoba-harness)

itonami-agent can assemble typed kotoba functions with
[kotoba-lang/kotoba-harness](https://github.com/kotoba-lang/kotoba-harness):
TypeSafe Jev chooses typed blocks one hole at a time (never source text), the
harness emits kotoba typed-subset source, and kotoba verifies each function
(`kotoba -M check`, then the module plus fixed exhaustive checks compiled to
wasm32-browser and run through `instantiateKotoba`). The search backtracks
outward when the policy reports that no candidate fits.

`system-one/loop.edn` encodes the run-loop rules of `src/itonami/agent/loop.cljk` — stop at `max_turns`, `budget_exhausted` when `elapsed > run_budget` (only for a positive budget: `pos?`, so zero or negative disables it), and the wrap-up notice at 80% of the budget (`5·elapsed ≥ 4·budget`) — as `turn-allowed`, `budget-exhausted`, `wrap-up` and `may-continue` (15 016 exhaustive cases, including non-positive budgets; checks use
independently written oracles). The harness commit is pinned in
`kotoba-harness.pin.edn` and fetched into
`${XDG_CACHE_HOME:-~/.cache}/kotoba-harness/<sha>` on first use (network),
outside this repository, and reused only while that checkout is the pinned
commit with a clean worktree (override with `KOTOBA_HARNESS_HOME`). The
launcher is a kbb program and runs the harness in-process.

```sh
bin/itonami-system-one validate   # no kotoba CLI, no model: shape, catalog, baseline splice
bin/itonami-system-one known      # kotoba verification of known-correct bodies
bin/itonami-system-one wrong      # negative control (rejected)
OPENROUTER_API_KEY=... bin/itonami-system-one jev
```

`known`/`wrong`/`jev` need a kotoba CLI that provides `-M check` and
`-M compile --target wasm32-browser`, and `KOTOBA_BROWSER_HOST` pointing at
amu's `runtime/browser-host.mjs`. `jev` spends OpenRouter credit (about a tenth
of a cent per run). Receipts land in `target/system-one/`.

## Tests

```
kbb --backend sci --classpath src:test run-tests.cljk
```
