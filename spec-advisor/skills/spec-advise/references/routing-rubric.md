# spec ルーティング rubric

開発タスクの説明から、実装着手前に書くべき設計・計画系成果物を判定する基準。
`spec-advise` skill と ambient rule（`rules/advisor-rule.md`）がこの表を参照する。

**SSoT の現状（重要）**: 同種の WHAT/HOW/WHY 判定は `linear-workflow` / `indie-workflow` の
issue-create（着手前 spec 選択）と `feature-dev`（Phase 1.3 / 4.5）にも**インラインで独立実装**が存在する。
本ファイルはそれらの唯一の正本ではなく、`spec-advisor` が担う「構造化入口を通らない raw chat のタスク」
向けの判定基準である。真の一元化には、他プラグインが本ファイルを `Read` 参照するか pre-commit で表セルの
一致を検証する束ね方が要る（単なるコピー増加を避ける）。現状は意図的に非統合（cross-plugin refactor は
linear/indie ミラー影響が大きく別タスク）。

## 5 軸モデル

| 軸 | 何を残すか | skill | 出力先 |
|---|---|---|---|
| **WHAT** | ユーザー可視な振る舞い・受け入れ条件 | `bdd-spec:create-spec` | `features/…/spec.md` |
| **HOW** | 技術方式の選定・代替案比較（面の設計） | `design-doc:design-doc` | `.claude/designs/` |
| **WHY** | 単一の重要な設計判断を理由ごと（点の記録） | `adr-keeper:adr` | `.claude/adr/` |
| **Issue 粒度** | 1 Issue の作業設計（9 セクション・決定/open の仕分け） | `issue-design` | Issue 本文 |
| **実装一気通貫** | 設計から実装まで進める意思が明確 | `/feature-dev`（command。skill ではない） | 8 phase フロー |

軸は排他ではない（後述の組み合わせを参照）。委譲手段は軸ごとに異なる: WHAT/HOW/WHY/Issue 粒度は
`Skill` tool で skill 起動、**実装のみ `/feature-dev` command の実行を案内**する（feature-dev は skill を持たない）。
Issue 粒度の `issue-design` は linear / indie が同名なので `linear-workflow:issue-design` / `indie-workflow:issue-design` と namespace を明示する。

## 判定フロー（ファネル: 先に「不要」を落とす）

1. **guard（over-suggestion 抑制）を最初に適用する。** 次のいずれかに該当したら **提案しない**（黙って実装へ進む — 提案しないことも正しい出力）:
   - bugfix / typo / 文言修正 / 設定値変更
   - 影響範囲が 1 ファイル〜数行に閉じる軽微な変更・軽微な refactor
   - 手順・方式に迷いがなく、書くより実装した方が速い規模
   - すでに spec / design doc / Issue 設計が存在し、それに沿うだけのタスク
2. guard を通過したら、下の signal 表で軸を判定する。
3. 複数該当したら組み合わせる（後述）。

このファネル順序が noise 抑制の要。**「該当なし＝黙る」を既定にし、確信を持てたときだけ提案する。**

## signal → 軸

| タスクのシグナル | 推奨軸 | skill |
|---|---|---|
| 新機能・仕様変更。ユーザー可視な振る舞い / 受け入れ条件 / エッジケースの網羅が中心 | WHAT | `bdd-spec:create-spec` |
| 技術方式の選定・ライブラリ/アーキテクチャ比較・複数 Issue やコンポーネントに波及・トレードオフが Issue 本文に収まらない | HOW | `design-doc:design-doc` |
| 単一の重要な決定（このライブラリを使う / この方針を採る）を、後から理由を辿れるよう残したい | WHY | `adr-keeper:adr` |
| 1 つの Issue の作業を 9 セクションで構造化し、決定と open を仕分けたい | Issue 粒度 | `issue-design` |
| 上記の設計を経て、そのまま実装まで一気に進める意思が明確 | 実装 | `feature-dev` |
| 原因調査・分析。結論が出れば方針が決まる | （調査中は不要） | 結論を残すなら `adr-keeper:adr` |

## 組み合わせの典型例

- 新機能で方式選定も要る → **bdd-spec（WHAT）→ design-doc（HOW）**。決定が 1 点に凝縮するなら design-doc の代わりに adr。
- 大きめの技術的負債の移行 → **design-doc（HOW）**。移行方針の 1 決定だけなら adr。
- 振る舞いは自明だが 1 ライブラリ選定だけ重い → **adr-keeper のみ**。
- 設計はもう固まっていて実装するだけ → guard に該当するので **advisor は沈黙**する（feature-dev や実装着手はユーザーの選択であって advisor の提案ではない）。

**feature-dev との二重化に注意**: 「実装まで一気通貫」の意思が明確なら **feature-dev 単独**を案内する。feature-dev は Phase 1.3 で bdd-spec、Phase 4.5 で design-doc を内部的に呼ぶため、WHAT/HOW を別途先に提案すると spec が二重生成されうる。WHAT/HOW を先に書くよう勧めるのは「実装前に仕様・方式だけ固めたい（まだ実装に入らない）」ケースに限る。

## 確信度と提示

- 確信度が高い（guard で明確に「不要」/ signal が 1 つに強く寄る）→ **質問せず 1 文の根拠を添えて提案、または沈黙**する。
- 迷う場合のみ **AskUserQuestion**:
  - question: 「着手前に {推奨} を書きますか？（{根拠 1 行}）」
  - header: `spec 選択`
  - options: 導入済みの軸のみを提示し、推奨を先頭に `(推奨)` を付す。**「不要（直接実装）」を必ず含める**。
- **提案は 1 回のみ。** 断られたら同一タスクで再提案しない（作業の流れを止めない）。

## dormant 判定（プラグイン独立）

- 各軸のコンポーネントは、グローバル + プロジェクトローカルの settings（`$HOME/.claude/settings.json`・`$CLAUDE_PROJECT_DIR/.claude/settings.json`・同 `settings.local.json`）を `grep -Eq '"<plugin>@[^"]*"[[:space:]]*:[[:space:]]*true'` で走査して**有効**を判定する（`bdd-spec` / `design-doc` / `adr-keeper` / `feature-dev`。`issue-design` は `linear-workflow` / `indie-workflow` のいずれか）。`": false"` の無効化-but-インストール済みは除外する（#74 の誤検知回避。形式差で拾えない時は沈黙側に倒す）。
- 推奨軸が無効/未導入なら、提案肢から外し、次点 or 「不要」にフォールバックする。
- 全て無効/未導入なら advisor は沈黙する（提案する先が無い）。

## effort 分岐

- **low / medium**: タスク説明のテキストのみで軸を判定し即提案（速度優先）。
- **high / xhigh / max**: 関連 Issue / コードを軽く読み、影響範囲・複数コンポーネント波及・既存 spec の有無を裏取りしてから判定する（over-suggestion と取りこぼしの両方の精度を上げる）。
