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

## 計測 9: kexe_loader の seccomp fs syscall 監査（2026-10-20、boot65-67.log）

計測 8 の SIGSYS を 4 変数の guest 実行で切り分けた（store-probe.raw、
allow-csv 35,37、KEXE_STRUCTURED_REPORT 付き）:

| scope grant | 結果 |
|---|---|
| `/data`（ディレクトリ = descendant grant） | 最初の fs call（EXISTS）で SIGSYS |
| `/` | fs 系は通るが exit で unhandled-child-signal（exit 123） |
| `KEXE_CAP_RESOURCES_34` のみ（fs_reads は true） | 同上（exit 123） |
| **`/data/store-probe.txt`（exact-file grant）** | **EXISTS → 1 / WRITE / APPEND まで成功**（guest の実 fs に `AAABB` が着地）。READ で SIGSYS |

### 特定した 2 つの gap（amu/tools/kexe_loader.c）

1. **`__NR_mmap` が seccomp allowlist に無い**（`__NR_munmap` と `__NR_brk` は
   ある）。fs READ provider は内容バッファを `malloc` するため、brk 領域を
   超えると musl が mmap を使い SIGSYS。exact grant で READ だけ落ち、
   WRITE/APPEND/EXISTS（malloc なし）が通ったのが一致する。
2. **descendant（ディレクトリ grant）の open 分支**（`open(O_PATH|O_DIRECTORY|
   O_NOFOLLOW)` + `openat2(dirfd, rest, RESOLVE_BENEATH)`）が最初の使用で
   SIGSYS。exact 分支（`openat2(AT_FDCWD, ...)`）は通る。filter は
   open/openat/openat2 を通しているので、分支内の別 syscall（containment
   証明の path 解決系）か、filter の arch/nr 突合の取りこぼし。
   （`/` grant で exit 123 の unhandled signal もこの系の残骸と推定。）

### 修復の選択肢（セキュリティ判断つき）

- A. allowlist に `mmap` を追加 — 1 行だが PROT_EXEC の mapping を guest に
  開く。BPF で引数制限（PROT_EXEC 除外）は可能だが複雑。
- B. **provider 側をヒープ不要に**（READ を static バッファ + pread の
  チャンク処理に、`kexe_append_buffer` と同じ形）— 「C を減らす」原則に沿い、
  sandbox を広げない。推奨。
- descendant 分支は open フラグ/containment の実測で syscall を特定してから
  同様に最小修復。

guest 証跡の状態: **WRITE/APPEND/EXISTS は node 無しで動くことが実証済み**
（exact grant、boot67、ファイル内容 `AAABB` を guest 自身の fs で確認）。
READ とディレクトリ grant は上記 gap 解消待ち。

## 計測 9 追記（2026-10-21）: gap 1 修正・guest 検証済み

amu PR #1422（`kexe_loader`: fs READ provider をヒープ排除し string pool へ
直接読取）で gap 1 を修正。guest 検証（boot68.log、exact-file grant）:

    PHASE:EXISTS1:ANS1:1PHASE:WRITE:PHASE:APPEND:PHASE:READ:STORE_READ:AAABB
    {:status :ok :result 1 ...}

**WRITE→APPEND→READ の store cycle が node 無しで完走**（guest の実 fs に
`AAABB` 着地も確認）。gap 2（descendant open 分支の SIGSYS）は未修・非
allocator 起因として切り分け済み（amu#1421 に記録）。amu PR は CI
（adopted-seed-native 他）が required なので checks 緑待ちで open。

## 計測 9 追記 2（2026-10-21）: gap 2 も修正 — 全 grant 形状で store cycle 完走

gap 2 の root cause を debug マーカー付き loader で実測（boot70）:
descendant 分支は `open(base, O_PATH|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC)`
**の中**で trap。musl の `open()` は O_CLOEXEC 指定時に
`fcntl(fd, F_SETFD, FD_CLOEXEC)` を追加実行し（musl src/fcntl/open.c）、
fcntl は allowlist 外（getdents64 のコメントと同じ意図の拒否）。
exact 分支が通ったのは openat2 を raw syscall で呼ぶため。
（計測罠: fprintf/stderr 自体が filter に当たる — musl stdio は writev で
flush するため。マーカーは write(2) で書くこと。）

修正（amu PR #1422 に追加）: O_CLOEXEC を付ける sandbox 内の open 2 箇所を
raw `syscall(SYS_openat, ...)` に置換。kernel が O_CLOEXEC を atomic に
設定するので意味は不変、allowlist は広げない。

boot71.log — **exact / directory 両 grant で store cycle が完走**
（EXISTS → 1 / WRITE / APPEND / READ('AAABB') / :result 1、guest の実 fs に
AAABB 着地）。verify-loader-fuzz: PASS_LOADER_SOURCE_BOUND_FUZZ
（floors [60 100 18]、floorsLowered false）。

## 計測 10: journal store スライス — node 無しで完走（2026-10-21、boot73.log）

計測 8 設計 A の最初のスライスを実装・実証:

- `kotoba/compat/itonami/journal_core.kotoba`（pure: entry 検証・piece
  走査・size 計算）+ `journal.kotoba`（effect: :fs/app-data の
  EXISTS/WRITE/APPEND/READ を 1 呼び出し 1 wire 関数に）。
- guest 実行（node 無し、KEXE_CAP_RESOURCES_35=/data）: 3 append →
  不正 entry（改行入り）拒否 → count 3 → 1 番目 "two" → 範囲外 "" →
  `JRESULT:two:3` / `:status :ok :result 1`。guest の実 fs に
  `one\ntwo\nthree` の journal が着地。
- テスト: journal_core 12/12（3 target）、check :ok true、**aarch64-linux
  native compile 成功**。

実測した 2 つの構文ゲート（計画に影響）:

1. **typed-cap-call は typed defn の return 位置のみ**（project mode）。
   let 束縛・呼び出し引数の位置は `named capability operation requires a
   typed result context` で拒否。→ wire 関数を「1 呼び出し = 1 関数」に。
2. **native target は `string-split-count` を qualify しない**（index-of /
   substring / concat / code-point-at / string=? / replace-all は全て
   native 可、個別コンパイルで実測）。さらに **リンクした graph の全関数を
   gate が走査する**ため、未使用でも compat の split-count が影を落とす。
   → journal_core は自己完結（count を string-index-of 再帰に）。
   clojure.string compat の split-count/split-lines は native 経路では
   使えない（wasm/js では可）。

## 計測 11: KV notepad port — node 無しで完走（2026-10-21、boot78.log）

node:sqlite port consumer 1（notepad.cljk の 8 SQL）を per-key ファイルの
KV store に載せ替え、guest VM で完走実証:

- `kotoba/compat/itonami/notepad_core.kotoba`（pure 12/12 緑: key/value 検証・
  entry codec・hex2 エンコード）+ `notepad.kotoba`（effect: key の sha256 を
  名にした per-key ファイル、set=WRITE upsert / get=READ+key 検証 /
  delete=UNLINK_SEP）。
- guest 実行（node 無し）: set v1 → upsert v2 → get = **v2** → missing = ""
  → 改行入り key 拒否 → delete → get = "" → `NRESULT:v2:1` /
  `:ok :result 1`。parity: upsert last-wins・cap 拒否は store 不変・
  fail-closed。**64KB/job total のみ open**（:fs/browse の有界スキャン要）。

実測した罠 2 件（boot77 triage で分離）:

1. **filename は NAME_MAX(255) 制約**: hash 答え（小文字 hex 64 文字、実測）を
   4 桁 hex で二重エンコードすると 270 文字になり、**WRITE が
   unhandled-child-signal で kill**（open の ENAMETOOLONG が trap に化ける）。
   hex2（2 桁/byte）で 133 文字に。
2. **KEXE_PAIRS の予算**: hex の再帰 concat が pair を消費（256 不足で
   :budget/cells trap）。65536 で解消。運用目安:
   KEXE_PAIRS=65536 KEXE_STRING_POOL=65536。

## 計測 12: delivery queue port — node 無しで完走（2026-10-21、boot80.log）

node:sqlite port consumer 2（delivery_queue.cljk の 18 SQL）。journal
（enqueue 順序）+ per-id state ファイル（notepad の hashed 命名を再利用）の
合成設計:

- `delivery_core.kotoba`（pure 6/6 緑: id 検証・state codec・status 0/1/2）+
  `delivery.kotoba`（effect: enqueue=INSERT OR IGNORE / claim-row は
  pending→delivering の一回きり flip / finish=terminal+error /
  claim-next=journal 順の最初の pending を claim）。
- guest 実行（node 無し）: enqueue ex1×2（2 回目は 0）/ ex2 / ex3 →
  claim-next **ex1** → **ex2** → finish ex1 terminal("boom") → status 2 /
  error "boom" → claim-next **ex3**（delivering の ex2 を飛ばす）→
  claim-next "" → claim-row(ex2) 0 → `DQRESULT:ex1:ex3:boom` /
  `:ok :result 1`。journal に enqueue 順 `ex1 ex2 ex3` が残る。
- 5-module graph（delivery+journal+notepad+cores）が aarch64-linux に
  native compile 成功。

parity notes（台帳記載）: terminal row の prune なし（re-enqueue は 0、
SQLite は tombstone 参照）/ get-status の tombstone fallback なし（-1）/
finished_at のみ省略。

運用値の追加実測: **KEXE_STRING_POOL は intern の蓄積で尽きる**
（65536 不足 → :budget/bytes trap、1MB で完走）。queue 系は
KEXE_STRING_POOL=1048576 が目安。

## 計測 13: execution ledger port — node 無しで完走（2026-10-21、boot81.log）

node:sqlite port consumer 3（execution_ledger.cljk の 32 SQL のうち
executions テーブル面）。per-execution state ファイル + per-job journal:

- `ledger_core.kotoba`（pure 6/6 緑: 4 フィールド row codec・status
  0 claimed/1 running/2 completed/3 failed・active 判定）+ `ledger.kotoba`
  （effect: **claim! 契約「job あたり active 1 つ」を journal 走査で強制** /
  mark-running / finish / active-count / row-count）。
- guest 実行（node 無し）: claim ex1 → 1、重複 claim → 0、active 中の
  claim(ex2) → 0、mark-running → 1、running 中の claim → 0、finish
  completed → 1、claim(ex2) → 1（空き）、finish failed("boom") → 1、
  active-count 0 / row-count 2 → `LGRESULT:2:0` / `:ok :result 1`。
- 6-module graph の native compile 成功。

parity notes: cron_incidents / handoff 遷移 / recover-interrupted /
finished_at は open（次スライス）。rows() は row-count のみ（render 版は
list 面が要る）。

運用値: 3 consumer とも string pool 1MB・pairs 65536 で安定。

## 計測 14: tools.cljk の store 面査定（2026-10-21）— 121 SQL の正体

node:sqlite port 最後の consumer（tools、121 SQL）の査定。正体は
**タスク/Kanban store**（tool 実装本体の一部として埋め込まれた DB）:

| テーブル | SQL | 内容 |
|---|---|---|
| tasks | 31（SELECT 19 / UPDATE 11 / INSERT 1） | status 遷移・claim_lock・assignee・current_run_id |
| task_events | 24（INSERT 15 / SELECT 9） | **append-only event log**（task_id, run_id, kind, payload） |
| task_links | 14（SELECT 12 / INSERT 2） | 親子グラフ（WITH RECURSIVE descendants あり） |
| task_runs | 10（UPDATE 6 / INSERT 2 / SELECT 2） | 実行レコード（ledger の executions と同形） |
| messages | 2 | セッション履歴（ROW_NUMBER window あり） |

グラフ/JOIN/window を含う SQL が **13 箇所**。

### port 設計（計測 8 設計 A の延長、既存 3 store の再利用で大半が埋まる）

- **task_events = journal そのもの**（append-only）→ journal store に直載。
  最も相性の良い面（24 SQL が journal append/read に還元）。
- **tasks（31）+ task_runs（10）= per-id state ファイル** — ledger /
  delivery と同形（status 遷移 + claim_lock は clock/now wire 7 で可）。
  既存パターンの再利用で 41 SQL 相当が埋まる。
- **task_links（14）= グラフ**。WITH RECURSIVE descendants は links の
  有界走査 + guest 自己再帰で表現可（O(links)、bounded step 原則）。
  形式: per-link state ファイル or links journal（親→子の隣接走査）。
- **messages（2）+ window（4）= per-session journal + scan**で代替可。

### 縮小効果の見積

- 121 SQL → guest 操作に読み替え（約 60 操作 + グラフ走査 2 系）。
- 13 箇所の再帰 CTE/JOIN/window は「スキャンへの読み替え」＝計算量は
  O(n) 化するが、queue/ledger の実測（1MB pool、bounded scan）で同形の
  走査は安定運用内。
- **削減で消えるもの**: SQL パーサ行き来・WAL/transaction 保全・index
  管理（guest は append + 全ファイル書換で同等の fail-closed を達成、
  3 store で実証済み）。残る固有作業は links グラフの 1 系のみ。

結論: tools の store 面は **port 可・既存 3 パターンの再利用で 8 割**、
新設計は task_links グラフのみ。次スライス: task_events journal 化
（最も自然な面から着手）。

## 計測 15: task_events journal 化 — node 無しで完走（2026-10-21、boot82.log）

計測 14 の port 設計第 1 スライス（tools の task_events、24 SQL）。

- **length-prefix エントリ** `<runlen>,<kindlen>,<plen>,<run><kind><payload>`
  — payload は改行を含むため行区切りを使わない（loader の実境界は
  `_SEP` token 規則のみ = 改行は問題外）。journal 位置 = event id。
- `tasks_core.kotoba`（pure 6/6 緑: 10 進 codec・entry encode/walk）+
  `tasks_events.kotoba`（effect: ev-append / ev-count / ev-last-by-kind
  = ORDER BY id DESC LIMIT 1 / ev-first-after = id > ? 走査 — 実測の
  query 形そのものの walk 化）。
- guest 実行（node 無し）: 3 append（payload "a\nb"）→ count **3** →
  last-by-kind("result") = **"a\nb"**（改行往復）→ created のみ → "" →
  after(id>1) = "a\nb" / after(id>2) = "" → `EVRESULT:3:3` /
  `:ok :result 1`。
- 7-module graph の native compile 成功。

実装上の罠（記録）: 空 entry で substring が OOB → field-at は
空/短小 entry を fail-closed で "" に。

## 計測 16: tasks テーブル port — node 無しで完走（2026-10-21、boot83.log）

計測 14 設計第 2 スライス（tools の tasks、31 SQL）。Kanban 状態機械:

- 状態語彙（UPDATE 面から実測）: 0 todo / 1 ready / 2 claimed / 3 running /
  4 blocked / 5 review / 6 done。row は 5 フィールド
  （status/assignee/claim_lock/current_run_id/result）。
- **SQLite の遷移は条件付き**（UPDATE ... WHERE status=...）→
  `task-transition` は **from 一致のときだけ flip**（generic な条件遷移で
  全 UPDATE 形を吸収）。claim は ready→claimed + assignee/lock、
  done は running→done + result。
- guest 実行（node 無し）: create 1 / 重複 0 / 0→1 遷移 1 / 不正 from 0 /
  claim(alice,L1) 1 / 二重 claim 0 / status 2 / assignee alice /
  2→3 遷移 1 / done("ok") 1 / result "ok" / 最終 status 6 →
  `TSRESULT:2:ok` / `:ok :result 1`。
- tasks_state 6/6 緑、8-module graph の native compile 成功。

parity notes: claim_expires / heartbeat / block_kind（時計・再発）は
open。row のフィールドに改行は入れない（journal_core piece 列のため —
改行を含む result は events の length-prefix codec 側で扱う）。

## 計測 17: task_links グラフ port — node 無しで完走（2026-10-21、boot84.log）

計測 14 設計第 3 スライス（tools の task_links、14 SQL）— 査定で
「唯一の新設計面」としたグラフ系。**忠実な UNION 去重を実現**:

- 設計: parent ごとの journal（child id の行）+ DFS の visited に
  **:string-index**（string-index-new/assoc/contains/count）。実測:
  string-index 群は **3 target で runtime 可・native compile 可**。
- `WITH RECURSIVE descendants ... UNION` の意味（重複 1 回）を
  DFS + visited で完全再現。相互再帰（dfs ↔ dfs-children）は
  subset で許容。
- guest 実行（node 無し）: diamond a→b, a→c, b→d, c→d の
  link-add 4 + 重複 add 0 → children 2 / child-at 1 = "c" /
  has(a,b) 1 / has(a,d) 0（直接辺なし）→
  **descendants(a) = 3（d を 1 回のみ）** / descendants(b) = 1 →
  `LKRESULT:3:1` / `:ok :result 1`。
- 9-module graph の native compile 成功。

これで node:sqlite port（計測 8）の store 面は **全テーブルの設計・実装・
guest 実証が揃った**（残: task_runs / messages = 既存パターンの薄い面と
incidents、および .cljk 側の呼び出し差し替え）。

## 計測 18: task_runs + messages port — node 無しで完走（2026-10-21、boot86.log）

計測 14 設計の薄い面 2 つを一括で:

- `runs.kotoba`（task_runs、10 SQL）: per-run state（tasks-state codec の
  列を流用: 0 status / 1 profile / 2 task / 3 outcome）+ from-conditional
  flip。UPDATE ... WHERE id 形を吸収。
- `messages.kotoba`（messages + ROW_NUMBER window）: per-session journal
  （**tasks-core の length-prefix codec を再利用** — content は改行を含む）+
  セッション title は state フィールド。window の OFFSET ページングは
  `msg-role-at` / `msg-content-at`（journal index = message id）に還元。
- guest 実行（node 無し）: run create 1 / 重複 0 / 0→1 flip 1 / 不正 from 0 /
  1→2 flip(outcome "done-ok") 1 / outcome 往復 ✓ / session create 1 /
  title "chat-1" / msg 2 append（content "a\nb"）/ count 2 / role-at 1 =
  "assistant" / content-at 1 = "a\nb" → `RMRESULT:done-ok:a\nb` /
  `:ok :result 1`。
- 11-module graph の native compile 成功。

実装罠（probe が検出）: run-set の outcome を field 4 に書いて field 3 を
読んでいた（列対応の不一致）→ probe の assertion が正確に捕捉。修正後
全緑。

これで **node:sqlite port（計測 8）の全テーブルが実装・guest 実証済み**:
notepad / delivery_queue / execution_ledger / task_events / tasks /
task_links / task_runs / messages。残: incidents（独立テーブル）と
.cljk 呼び出し差し替え本体。

## 計測 19: cron_incidents port — node 無しで完走（2026-10-21、boot87.log）

node:sqlite port（計測 8）**最後のテーブル**。状態機械は UPDATE 面から
実測: 0 open / 1 alerted / 2 closed / 3 resolved。ack は
`WHERE state != 'closed'` = from-conditional flip（tasks と同じ機構）、
upsert の repeat は recurrences フィールドの 10 進 bump
（tasks-core の dec codec 再用）。

- `incidents_core.kotoba`（pure 6/6 緑）+ `incidents.kotoba`（effect:
  inc-upsert create/repeat / inc-alert / inc-ack / inc-resolve-job =
  per-job journal を open/alerted だけ resolved に）。
- guest 実行（node 無し）: create 1 / repeat → recurrences **1** /
  alert 1 / 再 alert 0 / ack 1 / **再 ack 0**（WHERE state!='closed'）/
  closed 確認 / i2,i3 create / **resolve-job → 2**（closed の i1 は
  対象外）/ i2 = resolved → `ICRESULT:1:2` / `:ok :result 1`。
- 13-module graph の native compile 成功。

**node:sqlite port 完走**: notepad / delivery_queue / execution_ledger /
task_events / tasks / task_links / task_runs / messages / **incidents** の
全 9 テーブルが実装・guest 実証済み。残は .cljk 呼び出し差し替え本体
（store 面の障壁は解消済み）。

## 計測 20: notepad の list/render port — byte 一致 parity（2026-10-21、boot90.log）

.cljk 呼び出し差し替えの最初の consumer（notepad.cljk の list-notes /
render-notepad-section 面）:

- `notepad_render.kotoba`: browse リスト → **key ソート**（insertion sort +
  string-compare、SQL の ORDER BY key に対応）→ **prompt section を
  byte 一致**で生成（空 notepad は ""、prompt-cache 安全の契約を維持）。
- guest 実行（node 無し）: 3 keys（banana/apple/cherry と順不同で投入）→
  ソート済み listing（先頭 apple / 末尾 cherry）→ render **317 bytes =
  .cljk と byte 一致** → 空 store は "" → `RNRESULT:apple:317` /
  `:ok :result 1`。

### browse プロバイダの罠（boot88 で実測）と index 転換

`:fs/browse`（wire 34）の fs_browse_provider は **entries 構築に malloc を
使い、gap 1 と同じ SIGSYS**（musl malloc→mmap→seccomp）。対応として
listing を **key index journal**（notepad-set が追加、delete は compact
書換）に転換 — browse 非依存で完走。loader 側の browse heap-free 化は
amu の修正候補として記録（gap 1 と同じ runbook）。

実装罠（検証が捕捉）: render のヘッダ末尾の改行が 1 つ不足（316 vs 317）
→ probe の byte 一致 assert が検出し、修正で全緑。

## 計測 21: delivery の module parity 面 — node 無しで完走（2026-10-21、boot91.log）

.cljk 差し替え consumer 2（delivery_queue.cljk の残 parity 面）:

- 6 status 語彙（0 pending / 1 delivering / 2 delivered / 3 failed /
  4 unknown / 5 suppressed）に拡張。**fenced finish**（`WHERE status IN
  ('pending','delivering')` — terminal は二度と書換えない）と
  **recover-abandoned!**（delivering → unknown、再送しない安全側）を
  from-conditional flip で再現。
- **ledger-outcome の設計マッピングを parity**: delivered→delivered /
  suppressed→suppressed / failed→failed / **unknown→failed**（送達結果を
  伝えられない喪失は失敗として扱う、という意図的な非対称）。
- guest 実行（node 無し）: x1 delivered → outcome "delivered" /
  **fenced な再 finish → 0** / x2 claim → recover → unknown → outcome
  **"failed"** / 再 recover → 0 / x3 suppressed → "suppressed" →
  `DQ2RESULT:delivered:failed:suppressed` / `:ok :result 1`。
- delivery_core 9/9 緑（terminal/finish-from/outcome のテスト追加）、
  native compile 成功。

実装罠（この run で 2 回）: export ベクタの更新漏れ（fn 未定義エラーに
化ける）と、置換 anchor の不一致で edit が黙って適用されないケース →
**edit 後は必ず check で再読**する運用が効いた。

## 計測 22: execution_ledger の module parity 面 — node 無しで完走（2026-10-21、boot92.log）

.cljk 差し替え consumer 3（execution_ledger.cljk の残 parity 面）:

- **owner-fenced handoff**（mark-handoff-pending!: claimed かつ owner のみ）/
  **claimed→running の adoption gate**（adopt-claimed!）/
  **recover-interrupted!**（owner gone + adoption grace 外 → unknown に
  fenced、再送しない）— pid/grace など host facts は i64 フラグで渡す
  kexe-first パターン。recover の error 文言は .cljk と byte 一致。
- **failure-type の分類マップを parity**: substring マッチ（regex 不要）で
  rate_limit/timeout/auth/delivery/config/script/agent/unknown に分類
  （lower-ascii + includes?、7 カテゴリの優先順位も一致）。
- guest 実行（node 無し）: claim → handoff(owner-fenced) → adopt →
  set-outcome → finish completed / claim → **recover → unknown(4)**（再
  recover 0）/ claim → finish failed("provider timeout") →
  failure-type **"timeout"** → `LGMODRESULT:4:timeout` / `:ok :result 1`。
- ledger_core 9/9 緑（failure-type 全 8 ケース + handoff フィールド）、
  native compile 成功。

実装罠（テストが捕捉）: row-handoff のフィールド index が 1 つずれ
（5 フィールド codec で 4 が正）。加えて edit の anchor 不一致・export
漏れは link エラーになる運用教訓を再確認。
