# Awai growth team: Murakumo and Yataverse

Tracking: [AWAI-130](https://linear.app/kotobalabs/issue/AWAI-130),
[AWAI-128](https://linear.app/kotobalabs/issue/AWAI-128),
[AWAI-129](https://linear.app/kotobalabs/issue/AWAI-129),
[JUN-18](https://linear.app/kotobalabs/issue/JUN-18).
Date: 2026-10-31 JST.

GitHub redirected the source push from `kotoba-lang/itonami-agent` to
`cloud-itonami/itonami-agent`. The latter is the current repository owner.
The existing local checkout is preserved; new profile source IDs use the
current GitHub owner. Earlier Linear pointers to the former owner are historical.

These are Itonami profiles. The existing `hermes/profiles/` source directory
names the inherited file layout; these definitions belong only in the
Itonami store, never the Hermes store. The machine-readable roster is
[awai-growth-team.json](awai-growth-team.json). It is a source index, not a
registry registration, grant or scheduler.

| Profile suffix (`awai-growth-…`) | First responsibility | Handoff |
| --- | --- | --- |
| steward | Keep the demand, execution and accepted-outcome board | Next bounded job and evidence gap per role |
| marketing | Product-specific use cases and trial material | Qualified interest to sales |
| sales | Repeated task, evaluation scope, cost cap and acceptance | An actual work order to the product bot |
| murakumo-adoption | Inference/compute dapp evaluation | Accepted inference outcome and resource evidence |
| yataverse-adoption | Verified bytes dapp evaluation | CID readback and separate retention/restore evidence |
| node-operations | Useful-work baseline and shared-resource protection | Qualified supply and pressure/UNKNOWN observations |
| economy | Outcome-to-accounting reconciliation | Distinct service units, funding, payee and settlement state |

Each profile contains its first work order and an explicitly unqualified
product source inventory. Murakumo and Yataverse are the chosen product
targets. Their service roles do not make their public origins application
servers. Their browser releases, canonical broker builder provenance and
native service execution need independent qualification.

## Initial operating mode

The first phase is operator-supplied source snapshots and draft answers,
local placement, Murakumo/Mishima inference, no fallback providers, no MCP
servers and no scheduled jobs. The existing tool resolver subtracts the
profile's disabled toolsets, including the full Hermes CLI/API bundles.
Drafting policies name local review responsibilities but do not grant host
tools. No native host enforcement or live inference success is claimed.

The native entry must load the intended profile/SOUL/task and enforce its
model, data boundary, empty tool set, budget and output destination. The
current `turn` guest accepts a task string and renders notepad context; it
does not itself load these profiles. Passing it only a profile name would
silently lose their instructions. A verified profile-aware host is required.
Do not start the generic gateway or reuse another profile's credentials or
schedule to work around that requirement.

The source policy is `kotoba/itonami/awai_growth_policy.kotoba`. The
`yakuwari.edn` files and bundled `policy/yakuwari.edn` copies are native
generated compatibility outputs. Regenerate the policy with the Amu native
CLI, then update the manifest's copied capability vector and bundle CID:

```text
amu check kotoba/itonami/awai_growth_policy.kotoba
amu run kotoba/itonami/awai_growth_policy.kotoba > <private-output>/yakuwari.edn
```

`src/itonami/agent/profile.cljk` defines the current bundle byte contract.
The native profile checker/refresh entry remains unqualified. The one-off
developer reference measurements below are not an added build, CI, gate,
runtime or fallback path. Do not run the legacy profile CLI as an activation
step. Do not grant permissions merely because compatibility checks pass.

## Verification recorded in this change

The Amu macOS native CLI checked, compiled and ran the policy emitter.
Its exact emitted bytes are copied into all fourteen policy locations.
The seven profile definitions were compared against the owning legacy
profile reader and tool resolver as a dated, one-off developer oracle:
manifest validation, bundle CID/file count, copied policy, no jobs, and
no tools exposed even when broad toolsets are requested. Three mutation controls per profile detect a wrong provider, wrong CID and removed tool denylist. The first
measurement caught an off-by-one bundle file count; the corrected
definitions have eight bundle files and no reported drift.

This used the already installed kbb SCI-on-Node reference engine, Node
v26.0.0, and the existing `itonami-agent` source at
`4340340033efbfc79c63ee359bda6efdf85596f1`. No dependencies were downloaded.
Commands and results are retained under
`docs/evidence/awai-growth-20261031/`. They establish reference-format
compatibility only. Native profile parsing, tool enforcement, model
execution, live service availability and steady-state operation remain open.

## Owning-source discrepancies and activation blockers

* `AGENTS.md` / the README describe the `.cljk`/kbb entry, while
  `bin/itonami-agent:69–70` now selects native guests for a few routes and sends
  `profile`, `gateway` and other routes to `bin/itonami-agent-kbb`.
  That launcher (`bin/itonami-agent-kbb:7–9`) imports `nbb.classpath` and Node modules. The workspace's
  native-only runtime rule takes precedence; this team does not activate
  through that fallback.
* This checkout has neither `bin/kexe-loader` nor `bin/guests`. Native `turn`
  therefore has no default executable closure here. The one-shot guest also
  needs its pre-started `:llm/generate` host provider. A loader alone would
  not establish a profile-aware, authority-enforced live run.
* The unrelated existing `itonami-compat` manifest declares Murakumo, but its
  `config.yaml:2` selects OpenRouter. This conflicts with `AGENTS.md`'s Two
  CLIs rule. It was preserved and is not used as a deployment template.
* The observed Yataverse source is a Node CLI/MCP implementation. Its
  verified-byte behavior is useful source evidence, not qualification of
  a native or browser dapp. No replacement or route cutover occurs here.

Keep installed definitions, runtime activation, accepted user outcomes and
accounting/settlement as separate states. This change enables no cron,
external communication, publication, payment, storage mutation or fleet
reconfiguration.
