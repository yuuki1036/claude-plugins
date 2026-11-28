---
name: living-spec
description: >
  Issue 化前の「設計収束ドキュメント」(living spec) を作成・運用するスキル。OQ (Open Questions) 台帳と Decision log を append-only の表で持ち、確度ラベル（確定 / 方向性(仮) / 未定）で未確定を抱えたまま収束を追跡する。init / oq / decision / spec / timeline / status を提供する。**収束率や open OQ の残数を見る（status）のもこちら**（整合・鮮度の検証は living-spec-maintain）。
  トリガー: 「living spec」「リビングスペック」「living spec 作る」「OQ 台帳」「Open Questions 台帳」
  「OQ 追加」「Decision log」「決定を記録して OQ を閉じる」「確度ラベル」「収束率」「収束率を見せて」
  「open OQ を見せて」「残ってる OQ」「living spec の現在地」「living spec status」
  「Issue 化前に未確定を詰めたい」「設計を収束させたい」「/living-spec」
effort: medium
allowed-tools:
  - AskUserQuestion
  - Bash
  - Edit
  - Glob
  - Read
  - Write
---

<!-- 正本依存（SSoT pin）。本ファイルは format-spec.md の、続く pin の節を言い換えている。正本の節が変わったら、その節を言い換えている箇所を確認して pin を打ち直す（`--update-ssot-pins` は repo 全体を一括で打ち直す） -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#0 @74e61f65 -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#1 @650fbc07 -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#2 @b8e511ac -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#3 @d620c24e -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#4 @0375a0e6 -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#5 @74977fc6 -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#6 @afdfb988 -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#7 @e4e38744 -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#9 @3d83e7f4 -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#10 @fe9a7606 -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#11 @c405084f -->

# Living Spec

Issue 化する前段の「設計収束ドキュメント」(living spec) を `.claude/living-specs/<slug>.md` で運用するスキル。**未確定を抱えていることが正常状態**の文書を、採番・書式・相互参照を機械化しながら「仮 → 確定」へ収束させる。

> **サブコマンドの本文は、サブコマンドごとのファイルにある**（`skills/living-spec/references/subcommands/<サブコマンド>.md`）。この SKILL.md に残すのは、いつ使うか・参照する規範・どのサブコマンドでも通る Phase 0・書き込みの規律（共通手順の W1〜W5）・maintain の案内・処理フロー・注意事項と、各 Phase の見出しと Read の行だけ（init の Phase 2・3 は init のファイルの中にある）。Phase 0 で決まった Phase の見出しに来たら、Read の行が指すファイルを最初に読む。見出しだけを見て、本文を読まずに進めない（1 本のままだと Read 1 回で読み切れず、後ろの Phase を読まないまま進めうる / GitHub issue #447）。本文がほかのサブコマンドの節を引くとき（Phase 5・7 が使う Phase 6 冒頭の「凍結の判定」「壊れた宣言」、6a の報告が引く Phase 7 の収束率の数え方など）は、その Phase の見出しの Read の行のファイルも読んでから従う。本文の W1〜W5 は、この SKILL.md の「共通手順」の節を指す。サブコマンドのファイルの中の `${CLAUDE_PLUGIN_ROOT}` は、この SKILL.md を Read したパスのプラグインのルートに読み替える

## いつ使う / いつ使わない

| 状況 | 使うスキル |
|------|-----------|
| Issue 化する前に、未確定を抱えたまま設計を収束させたい | **living-spec**（本スキル） |
| 代替案を比較して採用案を確定し、スナップショットとして残したい | `design-doc:design-doc` |
| 単一の設計判断（WHY）を点で記録したい | `adr-keeper:adr` |
| Issue 1 件の作業設計（9 セクション） | `issue-workflow:issue-design` |
| 設計から実装まで一気通貫で進める | `feature-dev` |

**使い分けの軸は「何セッションかかるか」**。未確定が 1 セッションの grill（数問で、互いの依存が浅い）で片付くなら living spec は要らない — `design-doc` か `feature-dev` の grill で足りる。複数セッションに跨って決めていくときに使う。

living spec は**決める場所で、実装はしない**。実装に手を付けたくなったら今の phase の到達点に着いた合図なので、確定した塊を Issue 化するか `feature-dev` に渡す。**到達点は phase ごとに持ち**、着いたら `spec --phase-advance` で次の phase へ進む。実行に入ったあとも閉じずに使い続ける — 実装中に覆った確定の項目は新しい Decision で上書きし（関連 Issue を辿る）、後の phase へ回す項目は先送りにする（`format-spec.md` 2.2 節 / GitHub issue #320）。全 phase を終えたら閉じる。

> living spec で確度が `確定` に寄った塊ができたら、それを Issue 化する。living spec 側からプラグインは呼ばない（疎結合）。ユーザーが `/issue-create`（issue-workflow）に手で渡す。

## 参照する規範（references）

- `${CLAUDE_SKILL_DIR}/references/format-spec.md` — 表スキーマ・確度ラベル・採番規約・frontmatter の**正本**
- `${CLAUDE_SKILL_DIR}/references/template.md` — scaffold テンプレ（プレースホルダ方式）

---

## Phase 0: 保存先確認 + サブコマンド判定

1. `.claude/living-specs/` の存在を Glob で確認。不在なら Bash で作成（**`--spec` にファイルのパスが渡された回は、この確認も作成もしない**。`format-spec.md` 0 節。hub が別の repo の living spec を指したとき、cwd にディレクトリを作らない）:
   ```bash
   mkdir -p .claude/living-specs
   ```
   living spec は **committed 前提**（プロジェクトローカルに永続化）。Decision log を履歴として残す設計なので gitignore しない
2. **第 1 引数は常にサブコマンドとして解釈する**。既知の語彙に一致しなければ slug とみなさず、usage を報告して終了する:

| サブコマンド | 引数 | 遷移先 |
|---|---|---|
| `init` | `[slug]` | Phase 1 |
| `oq` | `<text> [--spec <slug>]` | Phase 4 |
| `oq list` | `[--all] [--spec <slug>]` | Phase 4 |
| `decision` | `<text> [--spec <slug>]` | Phase 5 |
| `spec` | `<項目> <確度> [--spec <slug>]` / `<項目> --phase <P<n>\|先送り\|-> [D<n>]` / `<項目> --issue <ID,…\|->` / `--upgrade` / `--phase-advance D<n>` / `--freeze D<n>` / `--unfreeze [D<n>]` | Phase 6 |
| `status` | `[--spec <slug>]` | Phase 7 |
| `timeline` | `<text> [--date <YYYY-MM-DD>] [--source <出典>] [--spec <slug>]` | Phase 8 |
| `maintain` | - | 案内のみ（整合・鮮度チェックは `/living-spec-maintain` の領分） |

3. 上記以外の入力の扱い:

| 入力 | 挙動 |
|---|---|
| 引数なし | usage（サブコマンド一覧）を報告して終了。**既定のサブコマンドを持たない** |
| 未知の第 1 引数（例: `/living-spec my-project`） | 「`my-project` は不明なサブコマンドです。利用可能: `init` / `oq` / `decision` / `spec` / `timeline` / `status`」と報告して終了 |

4. **`init` 以外は対象ファイルを特定する**（`format-spec.md` の 0 節が正本）: `--spec <slug>` があればそれ（`--spec <パス>` ならそのファイル）/ 無くて 1 件なら自動 / 複数なら AskUserQuestion で選択 / 0 件なら init を案内して終了。**自動で推測しない**（意図しないファイルを書き換える事故のほうが重い）

> **slug は `init` の後ろにしか置けない。** サブコマンド名と slug 名を同じ名前空間に置くと、後からサブコマンドを追加するたびに、その語を slug に使っていた利用者の意味が変わる（例: `/living-spec oq` が「slug=oq で作成」から「OQ を追加」に反転する）。第 1 引数を常にサブコマンドとして解釈し未知語を弾くことで、Issue 追加時の破壊的変更をまとめて回避する。同じ理由で**既定のサブコマンドを持たない**（`/living-spec` 単独は usage）。typo（`stats` 等）が無確認でファイルを作る事故も同時に塞がる。

---

## Phase 1: init — 引数解析と slug / タイトルの確定

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/living-spec/references/subcommands/init.md` を Read する（手順・分岐はそのファイルにある。見出しだけで進めない）。

---

## 共通手順: 書き込み前後の規律（Phase 4-6・8 が従う）

`oq` / `decision` / `spec` / `timeline` はいずれもファイルを更新する。**すべてこの規律に従う**。

### W1. 日付は Bash で取る

```bash
date +%Y-%m-%d
```

擬似日付を作らない。`since` / `日付` / `last_updated` はすべてこの値を使う。

### W2. 採番は「コメント除去 → 数値の最大 + 1」

`format-spec.md` の 6 節・9 節が正本。**必ず HTML コメント区間を除去してから**既存 ID を数える（コメント内の記入例を拾うと、実在しない ID を数えて採番がずれる）。

```bash
# OQ の max（コメント除去 → OQ 行の ID 列だけを取る）
perl -0777 -pe 's/<!--.*?-->//gs' "$F" | grep -oE '^\| *OQ([0-9]+) *\|' | grep -oE '[0-9]+' | sort -n | tail -1
# D の max
perl -0777 -pe 's/<!--.*?-->//gs' "$F" | grep -oE '^### D([0-9]+): ' | grep -oE '[0-9]+' | sort -n | tail -1
```

出力が空なら 0 件 → `OQ1` / `D1` から始める。**欠番は埋めない。ID は再利用しない**（6 節）。

### W3. 削除しない

Edit は **append と in-place 更新のみ**。行の削除を含む編集をしない（仕様表の行削除だけは項目の撤回として許容。2 節）。この規律があるので、Edit が部分適用で止まっても情報は消えない。

frontmatter の凍結の 2 行（`spec_table` / `spec_table_frozen_by`）は対象外で、`spec --unfreeze` が消す（2.1 節・10 節。有効な宣言の解除では経緯が Decision log に残る。壊れた宣言の除去は書き損じの修正で、残す経緯が無い）。

### W4. 書き込んだら `last_updated` を更新する

frontmatter の `last_updated` を W1 の日付に Edit する。**`last-validated` は触らない**（人が maintain を回したときに更新するフィールド。10 節）。

### W5. 0 行の表への最初の append

`init` 直後の表はヘッダ行 + 区切り行だけ。最初の行は**区切り行の直後**に足す。

---

## Phase 4: oq — OQ 台帳への追加 / 一覧

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/living-spec/references/subcommands/oq.md` を Read する（手順・分岐はそのファイルにある。見出しだけで進めない）。

---

## Phase 5: decision — Decision log への append と関連 OQ の close

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/living-spec/references/subcommands/decision.md` を Read する（手順・分岐はそのファイルにある。見出しだけで進めない）。

---

## Phase 6: spec — 仕様表の確度更新 / 凍結

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/living-spec/references/subcommands/spec.md` を Read する（手順・分岐はそのファイルにある。見出しだけで進めない）。

---

## Phase 7: status — 進捗ビュー

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/living-spec/references/subcommands/status.md` を Read する（手順・分岐はそのファイルにある。見出しだけで進めない）。

---

## Phase 8: timeline — タイムラインへの 1 項目の append

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/living-spec/references/subcommands/timeline.md` を Read する（手順・分岐はそのファイルにある。見出しだけで進めない）。

---

## maintain の案内

`maintain` が指定されたら、次を報告して終了する（このコマンドでは提供しない）:

```
整合・鮮度チェックは別コマンドです: /living-spec-maintain

段 1-7 の機械判定（表スキーマ / 採番 / 双方向参照 / 死リンク / 確度の塩漬け）と、
段 8 の LLM 判断（現在地サマリのズレ）を実行します。
```

> **このスキルで検証ロジックを即興実装しない**。maintain の段 1-8 は `format-spec.md` の全規約を機械判定する設計で、場当たりの検証は「通ったから正しい」という誤った安心を生む。`living-spec-maintain` スキルに委ねる。

---

## 処理フロー

```
1. Phase 0: .claude/living-specs/ 確認（無ければ mkdir）+ サブコマンド判定 + 対象ファイル特定
2. Phase 1: init → slug 命名規則の検証・タイトル確定・既存なら中止
3. Phase 2: date 取得 → 衝突確認 → template 置換 → Write
4. Phase 3: init の完了報告
5. Phase 4: oq → 採番（コメント除去 → max+1）→ append / oq list は読むだけ
6. Phase 5: decision → 採番（その番号を壊れた凍結の宣言が指していたら止める）→ 関連 OQ と覆す確定の項目を選ばせる → 同じ対象を決めた既存の Decision を探して見直すかを選ばせる → append（覆した項目の関連 Issue を報告） → OQ を close → 双方向参照を Read で検証
7. Phase 6: spec → 凍結中なら拒否 → 確度の 3 値検証 → 項目で引き当て（重複は倒す）→ 確度と since を更新
   / --freeze・--unfreeze → D# の実在と順序を確かめて frontmatter の凍結の 2 行を書く・消す（壊れた宣言は --unfreeze が D# なしで消す）
   / --upgrade → 旧 4 列の表を 6 列に / --phase-advance → D# を確かめて current_phase を進める
   / <項目> --phase・--issue → 先送りになる変更は D# を確かめて phase・関連 Issue を更新
8. Phase 7: status → 収束率（先送りを除く）・phase ごとの収束率・先送りの件数・open OQ 残数を集計（読むだけ）
9. Phase 8: timeline → 1 行・日付の検証 → 「## タイムライン」の末尾に `- <日付> <text>（出典: …）` を append（決定の文なら decision へ案内）
```

---

## 注意事項

- **日付は必ず Bash で取得**: `date +%Y-%m-%d` を実行する。擬似日付を作らない（adr-keeper / design-doc と同じ規律）
- **format-spec.md が正本**: 表スキーマ・語彙・採番規約が SKILL.md 本文と食い違ったら format-spec.md が正。書式が揺れると maintain の段 1-3 の機械パースが壊れる
- **採番の前に必ず HTML コメントを除去する**（W2）: 除去を省くと、テンプレや説明コメント内の記入例を実在する ID として数え、採番がずれる（`D1` を数えて最初の決定が `D2` から始まる等）。`format-spec.md` 9 節が前処理として要求している契約
- **削除しない**（W3）: OQ 台帳と Decision log から行・エントリを消さない。close は `status` の書き換えで表現する。この規律があるので Edit が部分適用で止まっても情報は消えない
- **双方向参照は decision がその場で閉じる**（Phase 5.6）: 書き込み後に Read で検証し、片方向なら即座に直す。maintain の事後検知に回さない
- **既存ファイルには触らない**: init は scaffold 専用。既存の living spec を上書き・改訂しない
- **doc-freshness との住み分け**: ファイル単位の鮮度（`last-validated` / `phase` の stale 判定）と frontmatter スキーマ検証は doc-freshness が担う。living-spec 側は表スキーマ・採番・相互参照・確度ラベルの `since` stale（doc-freshness では測れないセクション粒度）を担当する
- **doc-freshness 未導入時も動く**: 失われるのはファイル単位の stale 検出だけで、living spec の中核価値（OQ・Decision・収束の可視化）は単体で成立する。fail-fast させない
- **鮮度 lint の委譲には doc-freshness 0.4.0 以降が必要**: `.claude/living-specs/` の走査対象への追加は 0.4.0 で入った。それ未満では living spec が走査されず stale が検出されない（README 参照）
