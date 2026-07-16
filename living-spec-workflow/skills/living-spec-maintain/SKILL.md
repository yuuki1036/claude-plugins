---
name: living-spec-maintain
description: >
  living spec の整合と鮮度を 8 段のファネルで検証するスキル。表スキーマ・採番・OQ ⇔ Decision の双方向参照を機械判定し、死リンク・確度ラベルの塩漬けを検出する。通過したら last-validated を更新する。
  トリガー: 「living spec の整合チェック」「living spec を点検」「OQ と Decision の参照が合ってるか」
  「確度ラベルの塩漬けを検出」「living spec の鮮度チェック」「living spec lint」「/living-spec-maintain」
effort: medium
allowed-tools:
  - AskUserQuestion
  - Bash
  - Edit
  - Glob
  - Read
---

# Living Spec Maintain

`.claude/living-specs/<slug>.md` の整合と鮮度を検証するスキル。**検出に専念し、直すのは人**（機械的に直せるものだけ承認つきで直す）。

## いつ使う / いつ使わない

| 状況 | 使うスキル |
|------|-----------|
| living spec の整合・鮮度を点検したい | **living-spec-maintain**（本スキル） |
| living spec を作る・更新する（init / oq / decision / spec / status） | `living-spec` |
| ファイル単位の鮮度（`last-validated` / `phase` の stale）を横断で見たい | `doc-freshness:doc-freshness-check` |
| 実装コードをレビューしたい | `code-review:review` / `self-review` |

## 参照する規範（references）

- `${CLAUDE_SKILL_DIR}/references/check-rules.md` — 段 1-8 の判定内容・severity・修正方針の**正本**
- `${CLAUDE_PLUGIN_ROOT}/skills/living-spec/references/format-spec.md` — 表スキーマ・語彙・採番規約・パース正規表現の**入力契約**

> 契約（format-spec）と検知器（check-rules）を分けているのは、契約を検知器側に書き写すと二重管理になり、片方だけ更新されて「検知器が古い契約を守らせる」状態になるため。

## コスト×精度パイプライン設計（採用 / 不採用）

ルート CLAUDE.md「コスト×精度パイプライン設計指針」の 10 原則のうち:

**採用**
- **1（ファネル）**: 段 1-7 の機械判定を先頭に置き、段 8 の LLM 判断は通過分にだけ当てる。段 1-3 が 1 件でも出たらファイルが壊れているので段 8 に進まない（壊れた表の意味を論じさせても無駄）
- **3（段階予算）**: `${CLAUDE_EFFORT}` → 段 8 の実行有無と対象ファイル数
- **8（外部オラクル + fail-closed）**: 表パースが唯一のオラクル。パース不能なら Critical に倒す（「判定できなかった」を「問題なし」と報告しない）。ただし**段 4 のネットワーク不達には適用しない**（不達は死リンクの証拠にならない。オフラインで全リンクが Warning になる）

**不採用**
- **2（2 軸スコア化）**: 段 1-7 は機械判定で confidence が常に 100。段 8 も Info 固定。severity だけで報告閾値が決まるので、confidence をフィールドに持つ意味がない
- **4（モデルルーティング）/ 5（暴走ガード）/ 7（敵対的独立検証）**: agent の fan-out を持たず単一コンテキストで完結する。反復も起票もしない
- **6（証拠ラダー）**: 指摘の蓄積・昇格は failure-journal の責務

---

## Phase 0: 対象特定 + 縮退判定

1. **対象ファイルの特定**: `format-spec.md` の 0 節が正本。**Glob で `.claude/living-specs/*.md` を列挙**してから振り分ける:
   - `--spec <slug>` があれば `.claude/living-specs/<slug>.md`（Glob の結果に無ければ「`<slug>` が見つかりません」と報告して終了。勝手に作らない）
   - 無くて Glob の結果が 1 件なら自動選択
   - **複数件**なら AskUserQuestion で選択（自動で推測しない）
   - **0 件**なら「living spec がありません。`/living-spec init <slug>` で作成してください」と報告して終了
   - `--all` が指定された場合は Glob の結果**全件**を対象にする（`${CLAUDE_EFFORT}` 分岐は下記）
2. **doc-freshness の縮退判定**（未導入時に silent に不成立にしないため）。**enabled-only 判定**で、グローバル + プロジェクトローカルの settings を走査する:
   ```bash
   DOC_FRESHNESS=0
   for f in "$HOME/.claude/settings.json" "$CLAUDE_PROJECT_DIR/.claude/settings.json" "$CLAUDE_PROJECT_DIR/.claude/settings.local.json"; do
     grep -Eq '"doc-freshness@[^"]*"[[:space:]]*:[[:space:]]*true' "$f" 2>/dev/null && DOC_FRESHNESS=1
   done
   ```
   **キーの存在だけを見る `grep -q '"doc-freshness@'` は使わない**。settings.json は `"doc-freshness@<marketplace>": true|false` の形式で、キー存在判定は `": false"`（インストール済みだが無効化）も導入済みと誤判定する。project-scoped でのみ有効化した環境も取りこぼす（spec-advisor が #74 の誤検知回避として同じ判定に揃えている）。

   `DOC_FRESHNESS=0` なら**fail-fast させず**、レポートの冒頭に 1 行 warning を出す:
   ```
   ⚠️ doc-freshness が有効ではありません（未導入または無効化）。ファイル単位の鮮度（last-validated / phase の stale）と
      内部リンクの検証は行われません。living spec の整合チェック（段 1-7）は通常どおり実行します。
   ```
   `DOC_FRESHNESS=1` のときも、**バージョンは検証しない**ので次の 1 行を必ず添える:
   ```
   ℹ️ 鮮度 lint の委譲には doc-freshness 0.4.0 以降が必要です（.claude/living-specs/ の走査対象追加が 0.4.0 で入った）。
      それ未満では living spec が走査されません。`.claude/doc-freshness.json` に hookTargets を設定済みの場合も、
      配列に .claude/living-specs/ を追記しないと既定への追加が効きません。
   ```
   > **バージョン下限を宣言した以上、それを検証しないなら「検証していない」と明示する**。0.3.x がインストールされていると存在判定は通るが `.claude/living-specs/` は走査対象に入っておらず、利用者は「鮮度 lint に守られている」と誤認する。これは doc-freshness 自身が 0.1.0 で踏み 0.2.0 で修正した silent 不成立（委譲を宣言した側が守られていると思い込む）と同型で、本スキルが Phase 0 で「必ず明示する」と宣言している当のもの。

   失われるのはファイル単位の stale 検出だけで、living spec の中核価値は本スキル単体で成立する。**縮退していることは必ず明示する**（silent に不成立にしない）

### `${CLAUDE_EFFORT}` 分岐

| 実行時 effort = `${CLAUDE_EFFORT}` | 構成 |
|---|---|
| `low` / `medium` | 段 1-7 の機械判定のみ。段 8 は skip |
| `high` 以上 | 段 1-7 + **段 8（LLM 判断）** |
| `low` | `--all` 指定時も**最大 3 ファイル**まで（速度優先。打ち切った件数をレポートに明記する） |

skip した段は**レポートに理由つきで明記する**（「段 8: skip（effort=medium）」）。黙って落とさない。

---

## Phase 1: 前処理

`check-rules.md` の「前処理」が正本。**全段に先立って HTML コメント区間を除去する**:

```bash
perl -0777 -pe 's/<!--.*?-->//gs' "$F" > "$WORK"
```

除去を省くと、テンプレや説明コメント内の記入例を実在の行・ID として数え、段 2 と段 3 が偽陽性を出す。**以降の全段は除去後のテキストに対して判定する**。

frontmatter・セクション見出しの抽出に失敗したら、**その時点で段 1 の Critical**として報告し、以降の段に進まない（fail-closed）。

---

## Phase 2: 機械判定（段 1-7）

`check-rules.md` の各段の定義に従って判定する。判定は Bash（`perl` / `grep` / `jq` / `curl`）と Read で行う。**専用スクリプトは起こさない**（bdd-spec / doc-freshness と同方式）。

| 段 | 何を見るか | severity |
|---|---|---|
| 1 | 表スキーマ違反（`format-spec.md` 9 節の適用範囲に従う。セクション別に対象が違う） | Critical |
| 2 | 採番の重複・欠番 | Critical |
| 3 | OQ ⇔ Decision の双方向参照 | Critical |
| 4 | 「参照ソース」の外部 URL の死リンク（内部相対リンクは doc-freshness に委譲） | Warning |
| 5 | OQ の `status` と `関連 D#` の行内整合 | Warning |
| 6 | 確度ラベル stale（N は `.claude/doc-freshness.json` の `thresholds.target`、無ければ 15） | Warning |
| 7 | frontmatter `last_updated` がファイル内の最新日付より古い | Info |

**段 1-3 で Critical が 1 件でも出たら、段 8 に進まない**（ファネル）。段 4-7 は実行してよい（独立した観点で、まとめて直せるほうが手戻りが少ない）。

---

## Phase 3: LLM 判断（段 8）

**実行条件**: `${CLAUDE_EFFORT}` が `high` 以上 **かつ** 段 1-3 の Critical が 0 件。

「## 現在地サマリ」の記述が、仕様表の確度・open OQ・Decision log の実態と食い違っていないかを読んで判断する（詳細は `check-rules.md` の段 8）。

**断定できるズレだけを挙げる**。「もっと詳しく書けるのでは」のような好みは出さない（過剰指摘の抑制）。severity は Info 固定。

---

## Phase 4: レポート + 完了処理

### 4a. レポート

```
## living spec の点検結果: <slug>

<doc-freshness 未導入時はここに縮退 warning>

**判定**: <問題なし | 要修正>
**指摘件数**: Critical <n> 件 / Warning <n> 件 / Info <n> 件
**実行した段**: 1-7（機械判定）<+ 8（LLM 判断）>
**skip した段**: <あれば理由つきで。例: 段 8: skip（effort=medium）>

### Critical
1. [段 2][採番] OQ2 が欠番（OQ1, OQ3 は存在）
   → 行が削除された痕跡。git log -p で復元する。**採番し直して詰めない**（format-spec 6 節）

### Warning
2. [段 6][鮮度] 「権限モデル」が `未定` のまま 42 日（閾値 15 日）
   → /living-spec spec 権限モデル <確度> で見直すか、OQ に起票して論点を明示する

### Info
3. [段 7][frontmatter] last_updated が 2026-07-01 だが、ファイル内の最新 since は 2026-07-15
```

指摘が 0 件なら「問題なし」と報告する（**証拠を示す**: 実行した段と対象件数を出す。無言の PASS にしない）。

### 4b. `last-validated` の更新（完了処理）

**Critical が 0 件のときのみ** AskUserQuestion で確認する。**「通過しました」とは言わない** — この確認は Warning / Info が残っていても出るので、レポートの `判定: 要修正` と正面から矛盾する。件数を明示する:

- question: 「Critical はありません（Warning `<n>` 件 / Info `<n>` 件は残っています）。`last-validated` を今日に更新しますか？」
- header: 「last-validated」
- options:
  1. label: 「更新する」 / description: 「`last-validated` を `<TODAY>` に更新する。doc-freshness の stale 判定がリセットされる<段 8 を skip した場合は「。段 8（現在地サマリのズレ）は未検証」を追記>」
  2. label: 「更新しない」 / description: 「点検結果だけ受け取る。`last-validated` は据え置く」

> **`(Recommended)` を付けない**。`last-validated` は「人が内容を確認し問題ないと判断した日」で、判断するのは人。既定 effort（`medium`）では段 8（内容のズレを見る唯一の段）が skip されるので、機械が通したのは構造だけ。推奨を付けると「機械が OK と言った」に見える。

承認されたら `date +%Y-%m-%d` で取得した日付を frontmatter の `last-validated` に Edit する。

> **Critical が残っているときは更新しない**（この確認自体を出さない）。`last-validated` は `format-spec.md` 10 節の定義で「人が**内容を確認し問題ないと判断した日**」であり、契約違反が残った状態で更新するのは意味に反する。maintain の実行を「レビュー行為」とみなすのは、**通過した**ときだけ成立する。
>
> `last_updated`（機械フィールド）は触らない。段 7 が Info で整合を報告するだけで、直すかは人が決める。

---

## 処理フロー

```
1. Phase 0: 対象特定（--spec / 自動 / --all）+ doc-freshness 縮退判定 + ${CLAUDE_EFFORT} 分岐
2. Phase 1: 前処理（HTML コメント除去。失敗したら段 1 Critical で fail-closed）
3. Phase 2: 機械判定 段 1-7（段 1-3 に Critical が出たら段 8 に進まない）
4. Phase 3: 段 8 LLM 判断（high 以上 かつ Critical 0 件のときのみ）
5. Phase 4: レポート → Critical 0 件なら last-validated 更新を確認
```

---

## 注意事項

- **前処理を省かない**: HTML コメント除去は `format-spec.md` 9 節が要求する入力契約。省くと段 2・段 3 が偽陽性を出す
- **fail-closed はパースにのみ適用する**: パース不能は「ファイルが壊れている」証拠なので Critical に倒す。**ネットワーク不達（段 4）は死リンクの証拠にならない**ので Info（未検証）に留める。ここを Critical/Warning に倒すと、オフラインで回すたびに全リンクが指摘になる
- **欠番を詰めない**: 段 2 の Critical が指しているのは「欠番という状態」ではなく「行が消えた事実」。番号を詰めると事実が見えなくなる（`check-rules.md` 段 2）
- **契約は format-spec が正本**: 表スキーマ・語彙・採番規約を check-rules 側に書き写さない。食い違ったら format-spec が正
- **直すのは人**: 本スキルは検出に専念する。機械的に直せるのは `last-validated` の更新（承認つき）だけ。他は修正方針を示すに留める
- **skip した段は必ず明示する**: effort やユーザー指定で落とした段を黙って落とさない。「守ったつもり」の偽の安心を作らない
- **段 3 は事後の網**: 双方向参照は `/living-spec decision` が書き込み直後に自分で検証している。ここで出るのは手編集か decision の失敗の痕跡
