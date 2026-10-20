# node+kbb prune 台帳 — itonami-agent CLI を kotoba/amu selfhost へ

目的: 実行経路から node + kbb（org-babashka-nbb / SCI-on-Node）を prune し、
kotoba / amu selfhost（amu-compile した native kexe）だけで動く形へ移す。
計画の筋は kexe-first（kagi ADR-0002）: 決定は pure kotoba guest に、effect は
host adapter / kexe wire providers に置く。tracked: Linear JUN-110 系。

## 計測 1: `amu check` 拒否インベントリ（2026-10-20, amu c3b1ef6a）

`amu check src/itonami/agent/<f> --source-path src` を 30 モジュール全数に実行。

| 拒否 | before | after (本 PR) | 内容 |
|---|---|---|---|
| `:read` leading-zero octal | 2 (p2p/cron) | 0 | `{:mode 0600}` → `384`（chmod 値同一） |
| `:read` reader dispatch | 1 (main) | 1 | `#?`/`#"`/`#(` 系。regex/anon の置換は個別 trench |
| `:project-link` 文字列 host import | 27 | 28 | `["node:crypto"]` 等 30 箇所 / 13 ファイル |
| `:project-link` require 未充足 | (同上) | (同上) | `clojure.string` ×30、`promesa.core` ×15 |

`required module clojure.string is missing from the explicit source paths` という
形（= **compat モジュールを `--source-path` で差し込めば通る**）なので、
require 面は shim で機械的に溶ける。文字列 import は「host adapter 境界」に
落とす設計判断（JUN-13 の方針どおり）。

構文面の残数（grep 計測）: `#"` regex 231 / `#(…)` anon 211 / `#js` 72。

## 計測 2: effect 半分の受け皿は kexe ABI に揃っている

amu `tools/kexe_loader.c` の provider 面（実測で列挙）:
`io_read` / `io_write` / `io_write_error` / `cli_args` / `env_read` /
`clock_text` / `hash_sha256` / `identity_verify` / `entropy_draw` /
`fs_app_data_*`（exists read write stat mtime chmod mkdir unlink rmdir rename
range_read fsync stat_nofollow owner make_temp_dir）/ `fs_browse` /
`process_spawn` / `net_broker`（listen/dial, wire 43/45）/ `gpu_compute`。

→ turn の effect 半分（profile 読取・provider hop・tool 実行・出力）に必要な
機構はすべてここにある。**残る壁は言語 subset（上表）と port 量だけ。**

## trench 順序（node+kbb が消えるまで）

1. read 面: octal → 済（PR #54）。main.cljk の reader dispatch は regex/anon
   の置換個別に潰す。
2. require 面: `clojure.string` / `promesa.core` の compat モジュールを
   amu `--source-path` 専用に供給（kbb の classpath には出さない — 両 CLI の
   分離は AGENTS.md の Two CLIs 表どおり）。→ **clojure.string 半分は 済**
   （下の計測 3）。promesa は effect 層の話なので trench 4 に送る。
3. `["node:…"]` import → host adapter 境界（kexe wire 呼び出し）へ置換。
4. effect 半分を guest に port → kexe の native CLI として起動、kbb launcher
   （`env -S kbb --backend sci`）を廃止。

## 計測 3: compat 導入後の拒否深さ（2026-10-20、32 モジュール）

計測コマンド: `amu check src/… --source-path src --source-path kotoba/compat`。
clojure.string は compat（`kotoba/compat/clojure/string.kotoba`）で解消し、
拒否は次の壁まで前進した:

| 次の壁 | 件数 | モジュール |
|---|---|---|
| `["node:…"]` 文字列 import | 16 | browser computer_use confine delivery_queue execution_ledger host identity mcp notepad oauth p2p platform_adapters soul tools vault webguard |
| `promesa.core` 未充足 | 9 | browser_cloud cron gateway homeassistant loop process provider quiet watcher |
| `cljs.reader` 未充足（**新**） | 2 | profile rails |
| `str/join` / `str/split` 未実装（**新**、fail-closed） | 3 | delivery manifest（join）/ yaml（split） |
| `:read` reader dispatch | 1 | main |
| `:subset`（link 抜け、swap! の atom cell 契約）（**新**） | 1 | browser_provider |

compat（`kotoba/compat/clojure/string.kotoba`）の内容と境界:
blank? trim trimr includes? starts-with? ends-with? lower-case upper-case
index-of replace replace-first（11 fn、test 6 件 = 18/18 が 3 target 緑）。
実測した境界はモジュール header に明記してある:

- ~~join / split / split-lines は未実装~~ → **container 境界は解決済み（計測 4）**。
  split は scalar API（`split-count` + `split-piece`）で吸収でき、string の
  コンテナは不要と実測。join は port 先で `string-concat` fold に置換。
- replace / replace-first は string パターンのみ（regex は read 壁）。
- lower/upper は ASCII テーブル参照で自前実装 — `string-fold-ascii` /
  `string-upper` は **compile は通るが runtime 未実装**（test runner が
  `unsupported KIR operation`）という罠を実測で回避。
- 文字列 escape は reader 非対応（`\t` 等）。docstring 内の `\"` も同じ理由で
  入れない（ns が clause count エラーに化ける）。

## 決定コア（kexe-first）の dispatch parity — 実測

`kotoba/agent_cli/route.kotoba` が `-main` の `(case (first pos) …)` と 1:1
（vault/mcp/gateway/unknown route code と `admit-gateway` を追加）。
host fact のまま残すもの: profile 名検証、`--oneshot` の route 乗っ取り。

- `amu check`: ok（effects #{}）
- `amu test`: 12/12（targets `:jvm-kir :js :wasm`）
- `amu compile --target aarch64-linux --jvm-free` → kexe →
  `extract-native`: route-code(offset 0, arity 2) / admit-turn(92, 5) /
  admit-gateway(164, 1)
- node 無し guest 実行証跡: `workspaces/hermes/itonami-aiueos-vm-boot/boot61.log`
  （QEMU virt arm64, initramfs に node なし）:
  ROUTE `7 1 2 3 4 5 6 8 9 10 0` / TURN `1 -1 -2 -3 -4 -5` / GATEWAY `1 -6`
  — 全数が test のオラクルと一致、qemu exit 0 で poweroff。

## 罠（実測）

- initramfs newc の padding は**アーカイブ先頭からの絶対 4 バイト境界合わせ**
  （header は 110 bytes なので相対 padding だと全 entry が 2 バイトずれ、
  kernel は `Initramfs unpacking failed: broken padding` で落ちる）。
- `kbb --backend sci run-tests.cljk` は `--classpath src:test` が要る。
  run-tests の baseline は `137 tests / 980 assertions / 5 failures`（uid 依存
  fixture 由来の既存 failure。本 branch で増減なし）。

## 計測 4: string container 境界の解決（2026-10-20、trench 2 の続き）

疑問: `str/join` / `str/split` は safe profile に string のコンテナが無いため
open wall だった。実測の結論 — **コンテナは不要**:

- `string-split-count` は **runtime 実行可**（`string-fold-ascii` /
  `string-upper` / `string-index-of-from` は compile 通るが
  `unsupported KIR operation` という罠には当たらなかった）。empty piece を
  数える = Clojure `str/split` と一致（`"a,,b"` `","` → 3、test で pin）。
- `split-piece(s, sep, k)` は `string-index-of`（実行可）+ `string-substring`
  の再帰で k 番目 piece を返せる。存在しない piece は `""`（fail-closed）。
  `string-index-of-from` が runtime 未実装なので、残余 suffix に
  `string-index-of` を掛ける形にした。
- `join` は入力コンテナが要るが、port 先の呼び出し側を `string-concat` の
  fold に書き換えれば消える（binary concat は実行可）。`split-lines` は
  改行 1 コードポイント区切りの split-count/piece で同じ形。

compat に `split-count` / `split-piece` / `test-split` を追加。
`amu check :ok true` / `amu test 21/21`（:jvm-kir :js :wasm）。

## 計測 5: cljs.reader の置換可否 → 置換可（2026-10-20）

cljs.reader 呼び出しは 3 箇所（p2p/profile/rails の `reader/read-string`、
いずれも EDN ファイル全体を map として読む形）。置換ルートを実測で確定:

- **`document-edn-read` は runtime 実行可**（`document-equal?` と組み合わせて
  3 target 緑）。EDN ファイル → `:document`。
- navigation 契約を実測で確定（test で pin 済み）:
  - map entry は **2 要素 vector [key value]**（`document-map-entry-at d i` →
    entry、`document-vector-at entry 0/1` → key/value。entry 自体が value では
    無い。`document-list-at` は list 専用で vector には `document-list-required`
    を出して拒む）
  - scalar は `document-*-value` → `[:option X]`、`option-value v default` で unwrap
- ヘルパ `kotoba/compat/itonami/edn_doc.kotoba`（ns `itonami.edn-doc`）を実装:
  `map-field`（key 名で fallback つき取得）/ `map-field-i64` /
  `map-field-string`。`amu check :ok true` / `amu test 6/6`（3 target、
  nested map と fallback を含む）。
- `cljs.reader` モジュール自体は shim しない: port 済み呼び出しは edn_doc の
  API を直接使う。**read-string の戻りである Clojure map は safe profile に
  無い**（これが cljs.reader 壁の正体）。壁カウントは呼び出し 3 件の port で
  消える。

## 計測 6: host adapter 境界（`["node:…"]` の置換）— 一巡完了（2026-10-20）

`["node:fs"]` 等の文字列 import 30 箇所の置換機構を実測で確定し、
end-to-end で通した。機構は 3 点セット:

1. ns の bounded 宣言: `(:capabilities #{:io/write :cli/args ...})`
   （名前付き keyword の set、上限 256。keyword で無いと
   `namespace-capabilities-shape` で拒否）
2. 呼び出し: `(typed-cap-call :ns/op request-type result-type request)`
   — 例: `(typed-cap-call :io/write :string :string s)`。
   参考実装は amu/seed/02-io.kotoba。
3. 付与: `amu check/compile --policy policy.edn`、policy は
   `{:allow #{[:cap/call :io/write]}}`（**catalog 名で書ける**。wire id は
   ABI の中だけで、人が書く数字ではない — capability_names.cljk が翻訳）。

正本: `kotoba-lang/lang/capability-catalog.edn`（名前 ↔ `:compiler-wire-id`
+ classification）。実測した wire id: hash/sha256=3, clock/now=7,
process/spawn=20, fs/app-data-bytes=35, io/write=37, cli/args=38,
io/write-error=39, io/read=41。ほか catalog に fs/app-data, fs/browse,
env/read, entropy/draw, identity/verify, gpu/compute 等。

node import との対応（port 時の置換表）:

| node import | capability |
|---|---|
| node:fs read/write | `:fs/app-data`（+ `:fs/app-data-bytes`） |
| node:crypto hash | `:hash/sha256` |
| node:os env | `:env/read` |
| node:child_process | `:process/spawn` |
| stdout / stderr | `:io/write` / `:io/write-error` |
| argv | `:cli/args` |
| node:http / node:net / node:dns | net broker（wire 43/45 listen/dial。catalog 名は要確認） |
| node:readline | `:io/read` |
| node:path | 純粋 port（capability 不要） |
| **node:sqlite** | **capability が無い** — execution_ledger / delivery_queue / notepad / tools の 4 件は `:fs/app-data` ベースの store への port か新 capability が必要（open） |

end-to-end 実測（boot62.log、guest VM、node 無し）:

    TEST_IO_GRANTED: CAP_WRITE_OK1     <- wire 37 がコンソールへ出力、return 1
    TEST_IO_DENIED:  KEXE_TRAP {:kind :signal :signal :SIGTRAP}

grants なしの同じ guest は **名前付き trap で fail-closed**。check :ok true
（effects / named-operations に名前が出る）、compile aarch64-linux kexe 成功。
例は `kotoba/compat/examples/host-adapter-io.kotoba` + 同 policy。

計測した制約: **`amu test` は capability guest を走らせられない**（internal
compiler error）。adapter 系の検証は kexe + kexe_loader / guest VM 経路で行う。

## 計測 7: promesa（effect 層）の置換設計（2026-10-20）

使用面（promesa.core を p と alias する 9 モジュール: browser_cloud cron
gateway homeassistant loop process provider quiet watcher）:

- 逐次合成 **110**: resolved 37 / let 30 / then 22 / catch 13 / rejected 5 / finally 3
- オーケストレーション **31**: loop 9 / recur 13 / delay 4 / all 3 / promise 2
- 別 alias の混入疑い 5 程度（run names-for discover call do）

置換設計（実測事実から）:

1. **kexe wire は同期**（provider: request → result）。guest 内に promise の
   基盤は無いし要らない。
2. **promise の値は result/option に写像**: `result-ok/result-err` は
   **:result-i64 のみ構築可**（`[:result :string :string]` の構築子は
   `expression type mismatch: expected result-i64` で実測拒否）。guest ABI は
   スカラー面なので、成功値は `:string`/`:document` の直接 return、失敗は
   `:result-i64` / `[:option …]`（`option-value` に default あり）で運ぶ。
3. **逐次 chain（let/then/catch/finally）は guest の直線的な typed-cap-call
   群へ平坦化** — cap 呼び出しは同期なので await 不要。ここが 110 箇所の行き先。
4. **オーケストレーション（loop/recur/delay/all/promise）は host/tender 側の
   責務**。watcher・background process 監視・provider retry などの継続ループは
   host が持ち、guest は 1 invocation = 1 有界ステップ（kexe-first の
   facts-as-i64 パターン）。ここが 31 箇所の行き先。
5. **stream/task は linear リソース**: `[:task [:stream :bytes]]` は
   `linear resources require move-aware parameters`（実測）。真の
   ストリーミングが必要ならこの面を使うが、CLI の port には不要
   （非同期は 4 の host 側に寄る）。

結論: promesa 壁の正体は「guest に非同期基盤が無い」ことではなく
「**非同期は host の責務**」という分担の明示。9 モジュールの port では
逐次 110 が直線コードに、orchestration 31 が host loop に移って壁が消える。

## 計測 8: node:sqlite の port 方針（2026-10-20）

### 使う面（実測）

node:sqlite は **リレーショナル store として運用されている**: WAL +
BEGIN IMMEDIATE/COMMIT/ROLLBACK、CREATE/ALTER（migration）、CREATE INDEX、
WHERE/ORDER BY/LIMIT の SQL。SQL 文字列の数: execution_ledger 32 /
delivery_queue 18 / notepad 8 / tools 121 = **計 179**。

### :fs/app-data の request プロトコル（seed/02-io.kotoba の実装から確定）

- EXISTS: `path + "EXISTS_SEP"` → 先頭バイト '1' で存在
- READ: `path` → ファイル内容
- RANGE: `path + "RANGE_SEP" + off + ":" + len`
- WRITE: `path + "WRITE_SEP" + content`（content に自 token を含む write は
  SIGILL で拒否。APPEND は `APPEND_SEP` 同様）
- バイト安全版: `:fs/app-data-bytes`（wire 35 kind 8、:bytes request）
- scope: `KEXE_CAP_RESOURCES_35=<colon 区切り path 群>`（loader が realpath
  で解決、解決できない entry は drop）。範囲外 path は **trap ではなく absent
  で返る**（confinement 契約、catalog 記載）。

### port 方針（2 つの生きた設計）

- **A. guest 側 journal store**: テーブルを append-only journal（WRITE/APPEND
  + RANGE 読取）に落とし、クエリは invocation ごとの有界スキャンへ。
  「1 invocation = 1 有界ステップ」原則に合う。179 SQL がスキャン/リプレイ
  コードに変わる（機械的だが大きい）。transaction は append + compaction
  （single-writer 前提）。
- **B. store サービス**: net broker（wire 43/45）越しに kotoba 製 store
  daemon へ RPC。transaction 語義は温存、C を増やさない。
  host=状態 / guest=計算という promesa 設計（計測 7）と同じ分担。
- 推奨: B を正とし A を小規模（notepad 8 文）で先行。tools の 121 文は
  クエリ帳が大きすぎるので置換ではなく縮小対象。

### 実測した open item: fs wire が aarch64 loader で SIGSYS（boot63/64.log）

guest で store 最小 primitive（WRITE→APPEND→READ、policy で
:fs/app-data/:io/write 付与、allow-csv `35,37`、
`KEXE_CAP_RESOURCES_35=/data`）を実行した結果:

    STORE_PROBE: PHASE:EXISTS1:KEXE_TRAP {:kind :signal :signal :SIGSYS}
    STORE_PROBE_DENIED (wire 35 なし): PHASE:EXISTS1:…SIGTRAP

- io 系（wire 37/38）は同じ guest で正常（CAP_WRITE_OK）。wire 35 は
  granted（ungranted は SIGTRAP で別症状）なのに、**:fs/app-data の最初の
  request で SIGSYS**（seccomp filter の syscall 不許可）。
- EXISTS という最小 op でも落ちるので、request path の解決
  （realpath / readlinkat / statx 系が filter 外と推定）が原因候補。
  confinement 契約は「範囲外は absent、trap しない」なので scope 拒否ではない。
- 影響: store 系 port の **guest VM 証跡**はこの loader gap の解消待ち。
  check/compile は緑（例: kotoba/compat/examples/store-probe.kotoba）。
- 次の一手: kexe_loader の seccomp filter の fs syscall 集合を実測照合し、
  不足 syscall の追加（amu repo への PR）か、実機（x86_64-linux の
  adopted loader）での再現確認。
