# ADR 0001 — Itonami Agent のピア API に Protobuf を導入する

- 状態: Protobuf を活用する方針は owner 指示（2026-11-25 JST）。初回の適用範囲と移行手順は提案。
- 追跡: [JUN-1452](https://linear.app/kotobalabs/issue/JUN-1452)。Native selfhost の関連: [AWAI-60](https://linear.app/kotobalabs/issue/AWAI-60)、[AWAI-131](https://linear.app/kotobalabs/issue/AWAI-131)。

## 現行契約

[`itonami-agent-p2p/1`](../../src/itonami/agent/p2p.cljk) は HTTP 上の JSON API。署名済みメッセージは `payload`（JSON 文字列）、`did`（`did:key`）、`sig`（base64）からなり、Ed25519 の署名対象は JSON 文字列の元の UTF-8 バイト列。既存の認可では信頼済み DID、時刻窓、nonce を確認し、操作によって取得対象 CID や run ID、要求者も確認する。このコードは [リポジトリの native selfhost 方針](../../AGENTS.md) 上、移植時の参照実装である。

## 最初の適用範囲

1. **ピア情報の取得から始める。** `GET /itonami/v1/peer` に、`Accept: application/protobuf` を明示したクライアント向けの Protobuf 表現を追加する。`.proto` は版付きの外側の envelope を定義し、元の署名済み `payload` を `bytes`、DID を `string`、Ed25519 署名を生の `bytes` で運ぶ。payload を JSON として解釈する前に、伝送されたバイト列の署名を照合する。ピア情報から見つけた DID は個別に信頼を設定するまでは discovery の情報として扱う。
2. HTTP の `Content-Type` でデコーダーを選ぶ。サーバーが複数表現を返す場合は `Vary: Accept` を送る。従来の要求には従来の JSON 表現を返す。新クライアントは discovery で旧ピアが JSON を返した場合に限り、その JSON を既存の署名検証経路で扱える。Protobuf のデコード失敗や署名・信頼検証の失敗から JSON へ切り替えない。
3. **型付き payload は別の版で追加する。** 互換性と native の適合確認後に、ピア情報の payload や結果通知などから用途別のメッセージ型を定義する。署名には、版・操作を束縛するドメインと、伝送する型付き payload の元バイト列を使う。受け手がデコード・再エンコードした結果を署名検証に使うと、言語やライブラリ間でバイト列が一致する保証がない。書き込みや実行を伴う API へ広げる際は、操作と宛先・対象リソースを署名で束縛し、通信エラー後の再送と表現変更で同じ操作を二重実行しない契約を別途定める。

## 互換性と実装条件

- フィールド番号を固定し、削除した番号と名前は `reserved` にする。互換変更は追加を基本とし、意味・型・署名規則を壊す変更には新しい版を割り当てる。受信時は envelope と payload のサイズ上限をデコード前に適用する。
- 初回は HTTP API の表現追加として扱う。MCP、loopback の OpenAI 互換 API、bundle CID、profile フォーマット、推論 rail はそれぞれ既存の契約に従う。ブラウザ側の外部操作が必要になった場合は [共有クライアントランタイム契約](https://github.com/kotoba-lang/kotoba/blob/main/lib/kotoba.wasmWebcomponent/docs/app-environment-contract.md) に従う。
- 実装は移植済みの Kotoba/Amu native peer route で検証する。既存 peer route の移植と native codec の選定・適合は実装の前提。外部処理系を native 実行の依存にせず、独立した相互運用試験の参照に使う。

## 受入条件

旧クライアントと新サーバー、新クライアントと旧サーバー、新クライアントと新サーバーの discovery を確認する。同じ署名済み JSON から両表現を作り、同じ DID と payload バイト列で検証できることを golden vector で確認する。壊れたフレーム、上限超過、署名改変、期限切れ、未承認の DID が信頼済みに昇格しないことを負例に含める。操作を伴うメッセージを移行する段階で、nonce 再利用、誤った操作・宛先、再送時の二重実行も検証する。

参考: [Protobuf MIME types](https://protobuf.dev/reference/protobuf/mime-types/)、[Proto3 のスキーマ互換性](https://protobuf.dev/programming-guides/proto3/#updating)、[Protobuf のシリアライズと正規化](https://protobuf.dev/programming-guides/serialization-not-canonical/)。
