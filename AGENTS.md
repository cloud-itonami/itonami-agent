# itonami-agent

- kbb only (`kbb --backend sci`). No new .sh, no JVM, no npm deps (root AGENTS.md).
- Do not add an `nbb.edn` with empty `:deps` — the kbb deps door then fails with
  "The uberjar task needs a classpath". The launcher adds `src/` itself.
- Hermes compatibility is the contract: change a file format only together with
  the Hermes code that reads it, and keep `run-tests.cljk` green.

## Two CLIs — 分離の正本（hermes agent CLI / itonami agent CLI）

`hermes` と `itonami-agent` は **同じ profile フォーマットを共有する別物**。
store・状態・推論 rail を混ぜない:

| | hermes agent CLI | itonami-agent CLI |
|---|---|---|
| 実体 | Hermes Agent（Python, upstream） | 本 repo（kbb / .cljk） |
| profile store | `~/.hermes/profiles/<name>/` | `~/.itonami/profiles/<name>/`（`ITONAMI_DIR`） |
| 状態 / DB | `~/.hermes/` 配下（sessions・executions.db 等） | `~/.itonami/` 配下（runs・receipts 等） |
| 推論 | config.yaml `model:` — openrouter 等 | itonami.edn `:inference` — murakumo（mishima 等） |
| murakumo / mishima | **使わない** | **専用** |
| 移動 | `profile export`（itonami store → Hermes） | `profile import`（Hermes → itonami store） |

- **Hermes agent profile に murakumo / mishima を使わない** — config.yaml の
  `model:` でも、cron job の `model` / `provider` pin でも（job の pin が
  config より優先で拾われるため、両方を禁じる）。
- **itonami.edn の `:inference` は itonami-agent CLI 専用。** Hermes は
  itonami.edn を読まない（読み飛ばすだけ）。逆に itonami-agent の推論は
  `:inference` の rails のみ（`:deny-hosts` に openrouter）。
- フォーマット互換（両 CLI が読むファイル）を変えるときは README の互換表と
  この表を同時に更新する。
