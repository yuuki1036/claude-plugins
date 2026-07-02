---
name: design-review
description: >
  既存の design doc を複数視点（minimal / clean / pragmatic / risk）で静的レビューするスキル。
  doc の前提をコードベースと突き合わせて裏取りし、severity 付き findings を集約して
  doc への反映（open 追記・設計判断ログ追記・本文修正）まで行う。
  実装コードのレビューは code-review、doc の作成・supersede は design-doc スキルに任せる
  （このスキルは設計文書の事前レビューに専念する）。
  トリガー: 「設計レビュー」「設計書をレビュー」「design review」「design doc をレビュー」
  「設計案の穴を見つけて」「実装前にレビュー」「/design-review」
effort: medium
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Edit
  - AskUserQuestion
---

# Design Review

`.claude/designs/` の design doc を複数視点で静的レビューするスキル。**設計をやり直す場ではなく、問題・見落とし・より単純な代替の方向を根拠つきで挙げる場**。実装前の品質ゲートとして使う。

## いつ使う / いつ使わない

| 状況 | 使うスキル |
|------|-----------|
| design doc を実装着手前にレビューしたい | **design-review**（本スキル） |
| `status: draft` の doc を approved に上げる判断材料が欲しい | **design-review**（本スキル） |
| design doc を新規作成・改訂・supersede する | `design-doc` |
| 実装したコード（diff / PR）をレビューする | `code-review:review` / `self-review` |
| spec.md（BDD Scenario）の品質を評価する | 対象外（bdd-spec の将来 evaluate の領分） |

## 参照する規範（references）

- `${CLAUDE_SKILL_DIR}/references/review-perspectives.md` — 4 視点のチェックリストと effort 別構成（正本）

---

## Phase 0: 対象特定

1. 引数を解析する: `[doc-id] [--focus <視点>]`
2. 対象 doc の決定:
   - id 指定あり → `.claude/designs/*<id>*.md` を Glob。見つからなければ error として中止
   - 指定なし → `.claude/designs/*.md` を Glob し、`status: draft` または `approved` かつ `phase: target` の doc を候補に。1 件なら自動選択、複数なら AskUserQuestion で選択（最新を先頭 + `(Recommended)`）、0 件なら「レビュー対象の design doc がありません。/design-doc で作成してください」と案内して終了
3. `phase: superseded` の doc が指定された場合は「superseded doc はレビュー対象外」と伝えて中止

## Phase 1: 入力読み込み

1. 対象 doc を Read する（frontmatter 含む全文）
2. frontmatter の `spec:` / `issue:` / `adrs:` にパスがあれば Read する（reviewer へのコンテキスト）
3. doc の「採用案」「確定した前提」から関連コードのパス・パターンを抽出する（reviewer の裏取り対象ヒント）

## Phase 2: 視点トリアージ

`references/review-perspectives.md` の effort 別構成表に従う:

| 実行時 effort = `${CLAUDE_EFFORT}` | 構成 |
|---|---|
| `low` / `medium` | agent なし。メインコンテキストで minimal + risk を順次適用 |
| `high` | design-reviewer agent ×3 並列（minimal / pragmatic / risk） |
| `xhigh` / `max` | design-reviewer agent ×4 並列（全視点） |

- `--focus <視点>` 指定時は effort に関わらずその視点のみ
- agent 構成を 1 行でユーザーに表示してから実行する（例: 「effort=high: minimal / pragmatic / risk の 3 視点で並列レビューします」）

## Phase 3: レビュー実行

**agent 構成の場合**: 各 design-reviewer agent を **perspective mode** で並列起動する。プロンプトに以下を含める:

1. `Mode: perspective` を明示
2. 担当 Perspective 名 + `review-perspectives.md` から該当視点のチェックリスト全文
3. 対象 doc の全文
4. Phase 1 で集めたコンテキストパス（spec / ADR / Issue）
5. agent 定義の perspective mode の Output format に従って findings を返すこと

**メインコンテキストの場合**（low / medium）: 同じチェックリストと Output format を自分に適用し、minimal → risk の順で findings を作る。doc の前提のうち設計を左右するものは Grep / Read で裏取りする。

## Phase 4: findings 集約

1. 全視点の findings を回収する。agent が失敗した視点は「欠損視点」として明記する（黙って欠落させない）
2. **dedup**: 同一セクション・同根の指摘は 1 件に統合（視点名は併記）。複数視点が独立に同じ指摘を挙げた場合は confidence を引き上げてよい
3. **confidence フィルタ**: confidence < 50 の finding は MINOR に降格する（未検証・確信の薄い指摘を BLOCKER/MAJOR で提示しない＝過剰指摘の抑制）。ただし BLOCKER は消さず注記で残す（fail-closed: 重大リスクの見落としコスト > 偽陽性コスト）
4. severity（BLOCKER / MAJOR / MINOR）× セクションで整理し、レポートとして提示する:

```
## Design Review: <doc title>

視点: <実行した視点> / 欠損: <あれば>

| severity | conf | section | title | 視点 | 反証 |
|---|---|---|---|---|---|
| BLOCKER | 85 | 採用案 | ... | pragmatic | 支持 |

### 詳細
（finding ごとに evidence と suggestion）

### 裏取りされた前提
（Verified premises の集約）
```

（「反証」列は Phase 4.5 を実行した場合のみ。未実行なら列ごと省略する）

## Phase 4.5: 反証（敵対的独立検証・high 以上）

**Goal**: 集約後の findings（特に BLOCKER / MAJOR）を、レビュー視点とは別の独立 agent に**反証**させ、過剰指摘（偽陽性）を落とす。設計レビューは偽陽性コストが高い（ユーザーが不要な再設計に引きずられる）ため、Clearwing 原則 7（敵対的独立検証）を適用する。

**実行条件（effort 傾斜）**: `${CLAUDE_EFFORT}` が `high` 以上のときのみ実行。`low` / `medium` は skip（コスト優先）。BLOCKER / MAJOR の finding が 1 件も無ければ skip。

**手順**:

1. BLOCKER / MAJOR の finding を対象に、`Agent`（`design-reviewer`、`model: opus`）を **verification mode** で 1 体起動する。プロンプトに `Mode: verification` を明示し、**元 reviewer の suggestion / rationale は渡さず**、finding の `section` と `evidence`（file:line）と「この指摘は本当に妥当か？ 反論を組め」という中立な問いだけを渡す（アンカリング防止）。perspective は割り当てない。
2. agent は doc とコードを独立に読み直し、各 finding を verification mode の Output format（**支持 / 反証 / 保留** + basis）で返す（根拠は file:line か doc 引用）。
3. 判定を集約表の「反証」列に反映する:
   - **反証**（別 agent が明確に否定）→ その finding は severity を 1 段下げるか、レポートで「反証あり」と明示し Phase 5 の反映候補から外す
   - **保留 / 支持** → 据え置き
   - **BLOCKER は反証されても消さず**、「反証あり（要判断）」と注記して残す（fail-closed）

**暴走ガード**: 反証 agent は 1 体・1 ラウンドまで（多段化しない）。

## Phase 5: doc への反映

findings が 1 件以上ある場合、AskUserQuestion で反映方針を確認する（multiSelect）:

- question: 「どの finding を doc に反映しますか？」
- options: finding ごとに「<severity> <title>」（BLOCKER を先頭に）

採用された finding を性質別に doc へ Edit で反映する:

| finding の性質 | 反映先 |
|---|---|
| 設計変更が必要（採用案の修正） | 該当セクションを修正。大きな方式転換になるなら supersede を案内（design-doc スキルへ） |
| 未解決の論点が見つかった | 「未解決事項 (open)」に追記（選択肢 + 方向性 + 確定タイミングの形式で） |
| 判断の根拠補強 | 「設計判断ログ」に追記（マーカー付き） |
| 前提の裏取り結果 | 「確定した前提」に出典付きで追記 |

反映後、frontmatter の `last-validated` を更新する（`date +%Y-%m-%d`）。

> **Edit の対象は `.claude/designs/` 配下のみ**（design-doc スキルと同じ規律）。コードは修正しない。

## Phase 6: 完了報告

```
✅ design review 完了

📄 <doc path>
  findings: BLOCKER <n> / MAJOR <n> / MINOR <n>（反映済み <n> 件）

次のアクション:
- BLOCKER 0 件かつ主要 open 解消 → status: draft → approved への更新を検討
- 設計の方式転換が必要 → /design-doc supersede <id> <new-title>
- 実装に進む → 実装ブリッジの起動引数を使用
```

status 更新（draft → approved）はユーザーが判断する。BLOCKER が 0 件のとき提案してよいが、自動では変更しない。

---

## 処理フロー

```
1. Phase 0: 対象 doc 特定（id / 自動選択 / 0 件案内）
2. Phase 1: doc + 関連成果物（spec / ADR / Issue）読み込み
3. Phase 2: 視点トリアージ（${CLAUDE_EFFORT} / --focus）
4. Phase 3: レビュー実行（agent 並列 or メインコンテキスト）
5. Phase 4: findings 集約（dedup → confidence フィルタ → severity × セクション表）
6. Phase 4.5: 反証（high 以上・BLOCKER/MAJOR を独立 agent で敵対的検証）
7. Phase 5: 採用 finding を doc に反映 + last-validated 更新
8. Phase 6: 完了報告（approved 遷移の提案）
```

---

## 注意事項

- **レビューであって再設計ではない**: 代替設計の作成は design-doc スキル（とユーザー）の仕事。suggestion は方向を示すに留める
- **evidence-first**: 裏取りできない指摘は「未検証」と明記して MINOR に落とす（design-reviewer agent と同じ規律）
- **agent 失敗は明示**: 欠損視点を黙って欠落させない（code-review の欠損観点ルールと同思想）
- **status / phase を勝手に変えない**: 反映で変えるのは本文と `last-validated` のみ。status 遷移は提案に留める
