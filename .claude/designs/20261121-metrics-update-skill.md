---
id: 20261121-metrics-update-skill
title: code-review metrics-update（計測の更新と issue へのコメント・起票の skill）
status: approved
phase: current
last-validated: 2026-11-28
supersedes: []
superseded-by: null
issue: "GitHub #480"
spec: null
adrs: []
tags: [code-review, metrics, skill]
---

# code-review metrics-update（計測の更新と issue へのコメント・起票の skill）

## TL;DR

計測ストアの集計 → 関連 issue へのコメント → 改善案の起票、という手作業を `code-review:metrics-update` にする。決定的な部分（前回からの差分・版や effort で割った比較表・`## 15` の更新条件・語彙落ちの特定）は新スクリプト `metrics-update.sh` に寄せ、issue の選び方・起票・ベースライン doc の書き換えの判断は SKILL.md の手順に残す。

## 背景 / 課題

この作業を 2026-10-16〜11-08 に 6 回手で回したが、手順も集計スクリプトも毎回その場で組み直していた（GitHub #480）。

- retro は区間・費用を effort や版の前後で割らないので、`## 15` の取り直し・前後比較・delta と full の比較・dispatch の欠測率・語彙落ちの特定を毎回 python で書き直し、フィルタ（世代・再レビューの除外・transcript の取り違えが直った版）が揃わなかった
- 前回いつ・どの版までを見たかが残らず、差分を毎回組み直した
- コメント先の issue の選び方がぶれた
- 公開先の本文の書き方で送信前のガードに 2 回止められた

## ゴール / 非ゴール

- **ゴール**: 1 回のコマンドで「見た範囲・前回からの差分・比較表・`## 15` の判定・語彙落ち」を出し、LLM の判断（コメント先・起票・ベースラインの書き換え）を固定の手順で回す
- **非ゴール**: `review-retro.sh` の出力契約の変更（publish 直後の 40 行・⚠️ のときだけ行動する）/ 計測ストア側の語彙の追加 / metrics-vocab の warning を hook に出すこと（#478）/ 原因の特定に要る transcript の読み方の手順（#480 の「ぶれた点」の最後の項。構造の正本は `code-review/references/orchestration-measurement.md` 側にあり、この skill の手順には入れない）

## 確定した前提

- 重複除去のキーは `(ts, plugin)`。サニタイズ済みの行と生の行は生の側を採る（`code-review/scripts/lib/event_dedup.py`）
- マシンは label で出し、生の hostname・repo のパスを出さない（`code-review/scripts/lib/machine_label.py`）
- 計測ストアの行は、語彙に無い値を落とした回に `payload.sanitize_drops`（keys / coverage / values の件数だけ）を持つ。生の行は各 repo の `.claude/events.jsonl` にある
- `## 15` の更新条件は「世代が変わったとき」か「xhigh 以上の review が 5 件たまったとき」。dispatch 由来の値は 2.130.6 以上に絞る（`code-review/references/orchestration-measurement.md ## 15`）
- 計測ストアの既定の場所は metrics-vocab 検査と同じ `REVIEW_METRICS_DIR`（既定 `~/.claude/review-metrics`）。ストアはプラグインから見て任意で、無い環境では手元の `events.jsonl` だけで回す
- 公開先への投稿は承認を取る（CLAUDE.md の「起動＝実行確定」の例外は外部送信を除く）
- 新 skill と新スクリプトにする（2026-11-21 決定。既存 skill 5 本はどれも単位が「1 回のレビュー / 1 PR」で重ならない）

## 採用案

### ファイル

| パス | 責務 |
|---|---|
| `code-review/commands/metrics-update.md` | router に載る description と、SKILL.md を Read させる 1 行 |
| `code-review/skills/metrics-update/SKILL.md` | 手順（Step と完了基準）・`${CLAUDE_EFFORT}` の分岐 |
| `code-review/skills/metrics-update/references/comment-template.md` | コメント・起票の本文の型、業務情報の置き換え表、貼る行の規則 |
| `code-review/scripts/metrics-update.sh` | 薄いラッパ。`report`（既定）・`retro`（同じ母集団で `review-retro.sh` を回す）・`workdir`（本文と `--json` を置く作業用 dir を毎回新しい名前の 0700 で作る。`mktemp -d`）。ログとストアの解決はここ |
| `code-review/scripts/lib/metrics_update.py` | 本体（状態・差分・比較表・`## 15` の判定・語彙落ち・出力） |
| `code-review/scripts/lib/payload_judge.py` | retro と共有する判定（世代・再レビュー・delta）と版マーカー・数値の読み方（GitHub #536 で追加） |
| `.claude-plugin/scripts/tests/test_code_review_metrics_update.py` | 回帰テスト（使い捨てのストア・状態ファイル・git リポジトリ） |
| `.claude-plugin/scripts/tests/test_code_review_payload_judge.py` | `payload_judge.py` の単体テスト（GitHub #536 で追加） |

### スクリプト

- 入力: 計測ストアの `events/*.jsonl`（既定の場所に無ければ飛ばす。明示して無ければ exit 2）と手元の `events.jsonl`（`review_event_logs` か `--logs`）
- 既定は読むだけ。`--record` のときだけ状態ファイル（既定 `~/.claude/code-review/metrics-update-state.json`、`--state` で差し替え）に日時・main の commit・ストアの件数・code-review の版・マシンごとに見た最新の `ts`（`last_ts_by_machine`）を書く。次回はそこからの差分（新しい回のマシン別・plugin 別・版別の件数、`code-review/` を触った commit）を出す。新しい回は**マシンごとの最新の `ts`** で切る（別のマシンの回は後から同期されるので、全体の最新の `ts` で切ると落とす）
- 比較表: 世代 × effort × size_tier × delta / full で、区間・トークン・報告件数・dispatch の欠測率の中央値と n。再レビューは除き、除いた件数を出す。`--split-version` でその版の前後に割る。dispatch とトークンは 2.130.6 以上に絞る
- `## 15` の判定: 節に機械可読の印（`<!-- METRICS-BASELINE: generation=... taken=... review_xhigh_need=<件数> -->`）を置き、`taken`（表に入れた最後の回の翌日）以降で世代の分かる直近 4 回に印の世代が 1 回も無いか（最新の 1 回では決めず、件数の多さでも、新しい世代の連続でも決めない）と、xhigh 以上の review の件数を判定する。件数 0 は xhigh の条件を消化済みの意味で、2026-11-21 時点の印は 0（2026-10-25 に xhigh 列を取り直したので、次は世代が変わったとき）
- 語彙落ち: `sanitize_drops` を持つストアの行を列挙し、手元に同じ `(ts, plugin)` の生の行があれば差（落ちたキーのパス・`other` になった値・`missing_coverage` の落ちた語）を出す。ストアが意図して落とすキー（`bin/sanitize.py` の `DENY_KEYS`）は印を付ける。手元表示のみ
- 判定関数（世代・再レビュー・delta）と版マーカー・数値の読み方は `lib/payload_judge.py` に置き、retro と同じものを import する（GitHub #536。当初は複製して parity テストで縛っていた）
- 終了コード: 0 正常（0 件・ストアなしでも `--json` は必ず JSON）/ 2 判定不能（引数の誤り・明示したパスが読めない・状態ファイルが壊れている・書き込み失敗・workdir で dir を作れない・未捕捉の例外）

### skill の手順

main の fetch とストアの pull・同期 → 作業用 dir（`metrics-update.sh workdir`。毎回新しい 0700 の dir）→ 集計（`--json`）→ 同じ母集団で retro → issue の選定（固定の `gh` 2 本: open の `[code-review]` / 前回の記録以降に close。候補は本文とコメントを読む）→ `## 15` の書き換えの判断 → コメント（本文はファイルに書く呼び出しと投稿の呼び出しを分け、置き換え表と retro の「集計」「マシン / 版」の 2 行を付け、投稿前に承認）→ 改善案があれば起票（同じ流れ）→ `--record` → 「見た範囲」のレポート。

## 検討した代替案

| 観点 | 案 A: 新 skill + 新スクリプト（採用） | 案 B: 新 skill + retro に引数を足す | 案 C: スクリプトだけ |
|------|------------|------|------|
| retro の出力契約 | 変えない | 引数ごとに別の出力形が増える | 変えない |
| 判断の手順の再現性 | skill に固定 | skill に固定 | 毎回組み直す |
| 常駐する context | description 1 本分 | description 1 本分 | なし |
| 規模 | 新ファイル 6 | retro（3,400 行）がさらに太る | 新ファイル 3 |

- 案 B を採らない理由: retro は publish 直後に毎回出す 40 行で、比較表・状態の記録は性質が違う
- 案 C を採らない理由: issue の選定・起票・ベースラインの書き換えの判断と、送信前の手順のぶれが #480 の原因そのもの

## 設計判断ログ

- [local] 状態ファイルは計測ストアにもリポジトリにも置かず、マシンの `~/.claude/code-review/` に置く（ストアは同期の対象で、リポジトリは public）
- [local] `## 15` の更新条件の入力は doc の機械可読の印から読む（doc が条件の正本であり続ける）
- [local] 判定関数は lib へ抽出せず複製し、parity テストで縛る（retro を変えない契約のため。抽出は別 issue の候補）
- [local] 判定関数と版マーカー・数値の読み方を `lib/payload_judge.py` へ抽出し、複製と parity テストをやめて lib の単体テストで見る（GitHub #536。2026-11-28 決定。retro の出力は変えない）
- [local] 計測ストアの同期（`bin/sync`）はスクリプトに入れず skill の手順に置く（スクリプトはネットワーク越しの push を持たない。書くのは `--record` の状態ファイルと `workdir` の一時 dir だけ）。確認を取らずに回す（送り先は利用者自身の private リポジトリで、追記だけの定常の同期）
- [local] 前回からの差分はマシンごとの最新の `ts` で切る（後から同期された別のマシンの回を落とさない）
- [local] `## 15` の世代の判定は、世代の分かる直近 4 回に印の世代が 1 回も無いかで決める（比べるために別のモデルで 1 回回しただけでは変わらないように。件数の多さで決めると旧世代の累計を新しい世代が上回るまで数百件ぶん遅れ、「新しい世代が 2 回続いた」で決めるとマシンごとに世代が違う時期に判定が行き来する）

## 未解決事項 (open)

- なし

## 実装ブリッジ (Implementation Bridge)

1. 実装着手の単位: GitHub #480 を 1 つの PR で実装する（feature-dev の流れの中で継続する）
2. 検証方法: `test_code_review_metrics_update.py`（0 件・dedup・状態の記録と差分・比較表の除外規則・`## 15` の印の 4 状態・語彙落ち・伏せ字）・`test_code_review_payload_judge.py`（retro と共有する判定。GitHub #536 で retro との突き合わせから置き換えた）と、使い捨てのストアでのスモーク
3. 実装完了時の doc 更新手順: frontmatter の `phase: target` → `current`、`last-validated` を更新。実装と乖離した箇所は追記する

## 関連

- 関連 Issue: GitHub #480（関連: #302 / #324 / #345 / #417 / #313 / #346 / #347）
- 関連 spec: なし
- 関連 ADR: なし
- 関連 design doc: なし
