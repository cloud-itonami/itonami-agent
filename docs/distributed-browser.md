# Distributed browser — design (Hermes browser API on the itonami plane)

Status: design, not implemented. Owner ask (2026-10-17): keep the itonami
agent API fully Hermes-compatible while bot profiles stay distributed. Of
the two remaining gaps (messaging gateway adapters, browser tools) this one
is a **tool-API** gap — the browser tools are part of `_HERMES_CORE_TOOLS`,
so API compatibility names it directly; a gateway adapter is a gateway
surface, not the agent API. Browser first.

## Problem

Hermes' browser tools (`tools/browser_tool.py` and siblings) assume a
browser **on the turn's host**: `browser_navigate`, `browser_snapshot`,
`browser_click`, `browser_type`, `browser_scroll`, `browser_back`,
`browser_press`, `browser_get_images`, `browser_vision`, `browser_console`,
`browser_cdp`, `browser_dialog`, `browser_vault`, `browser_exec`. An itonami
bot profile is distributed: `itonami.edn :placement [:peer :local]` means a
turn runs on a trusted peer (the bundle travels by CID; the peer pays
inference with its own rail). Three failure classes follow:

1. **The executing node may have no browser at all** (a headless fleet node,
   a Linux box without one). The turn must fail honestly, not fake results.
2. **A peer turn must never drive the requester's own browser.** The
   requester's browser holds live logins and `browser_vault` credentials.
   The p2p contract already says secrets never cross; a browser is a secret
   store with a rendering engine attached.
3. **Browser state (cookies, logins, open tabs) is host-local state.** It
   must not enter a bundle, not sync between nodes, and not leak through a
   forwarded call — same rule as `sessions/` and `.itonami/` after the store
   split (profiles and DBs are separate things).

## Contract (API compatibility)

- The fourteen tool **names and argument shapes are copied from Hermes**
  (`tools/browser_tool*.py`), results are JSON strings like every other
  tool. A SOUL or skill written for Hermes calls them unchanged.
- A profile that has no browser surface advertises the tools as absent (the
  model never sees them) or answers an honest
  `{"error": "browser not available on this node"}` — never an invented
  snapshot. Absent beats wrong.
- `agent.disabled_toolsets` subtracts them as Hermes does.

## Design: browser as a placement capability

A browser is a **capability of a node**, declared in `itonami.edn` and
advertised in the signed peer info (the `/itonami/v1/peer` payload already
carries `{did load rails profiles peers}`; `browser` joins that set).

```clojure
:browser {:mode :local        ; :local | :none | :delegate
          :engine :chromium   ; what is actually installed, for the record
          :grant :owner-only} ; who may point turns at this browser
```

| mode | where a browser op executes | who holds the session |
|---|---|---|
| `:local` | the executing node's own browser | the executing node |
| `:delegate` | a single-op RPC on a trusted browser-capable peer (`POST /itonami/v1/browser`, signed envelope like `/itonami/v1/run`) | the browser node |
| `:none` | nowhere — the tools are not advertised | — |

- **Placement**: a turn whose profile enables browser toolsets prefers a
  peer that advertises `browser` (same pick rules as today: trusted, not
  full, holds CID first). A profile with `:browser {:mode :local}` never
  exports its browser to anyone else's turn.
- **`:delegate` is op-at-a-time, not session-at-a-time.** The requester
  never receives cookies, storage or a live page handle. Each call is one
  tool call in, one JSON result out (navigate/click/...), and the browser
  node keeps its own session across calls for ITS own turns only. This is
  the same shape as the delegation rule: children get summaries, not
  internals.
- **`browser_vault` is local-only in every mode.** A forwarded vault call is
  refused (`{"error": "browser_vault never leaves its host"}`). Credentials
  are exactly what the p2p "secrets never cross" rule protects.
- **`browser_cdp` / `browser_exec` bind to the node that owns the browser**
  (a CDP endpoint is the browser itself). In `:delegate` mode they are
  refused, not proxied — an escape hatch that proxies is an escape hatch
  that leaks.

## URL policy reuses webguard

`browser_navigate` (and dialog/press actions that can trigger navigation)
go through `itonami.agent.webguard` with the profile's `:web :allow`, on the
node that runs the browser. A peer turn keeps its own profile's policy — a
bundle cannot widen it (the same rule the terminal sandbox already has).
Private-address relaxation exists in Hermes' local-sidecar routing; here a
`:delegate` call to another node is never "local sidecar", so the strict
public-address check applies end to end.

## What crosses the wire in :delegate mode

```
turn (node A, :browser {:mode :delegate})
  one tool call  ── signed envelope (op, args, profile, ts, nonce) ──▶  browser node B
                                                                          run ONE browser op
                                                                          under B's web policy
                                                                          for A's declared :web :allow
  ◀── signed {result JSON, status}     (no cookies, no storage, no DOM beyond the tool's own result)
```

The result envelope is bounded the same way tool results are today (clip,
audit line per op in B's sandbox audit log). `browser_get_images` /
`browser_vision` return image bytes or paths like the local tool does; the
images are treated as tool output (cid-receipts state policy), not as
session state.

## Non-goals / open

- Not a shared browser profile across nodes (would break rule 3 by design).
- The browser-use backend (`browser_exec`) and cloud browsers
  (`browser_tool_cloud.py`) are separate placements — a cloud browser is a
  service endpoint and needs the operation-specific approval rules, so it
  is out of scope until then.
- `browser_dialog` handling on the browser node may require a human at that
  node; a peer turn must not be able to auto-accept a dialog (the
  approval-required default applies).
- Implementation order when this is built: (1) advertise `browser` in peer
  info + placement preference, (2) `:local` mode behind the existing tools
  dispatcher, (3) `:delegate` single-op RPC, (4) the refusals above as tests
  (a refused call must be byte-identical to an honest error, and must never
  fall back to a fake result).

## Why this before the gateway adapter

The compatibility goal names the **agent API**; the browser tools are in
`_HERMES_CORE_TOOLS` and are what turns actually need to do web work. A
messaging gateway adapter is a platform-connection surface: the distributed
question there is only "which node holds the platform connection" (one
ingress node per platform account; turns fan out via placement exactly as
today), which is smaller and better designed after this capability/placement
pattern exists.
