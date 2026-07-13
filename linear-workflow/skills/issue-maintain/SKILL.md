---
name: issue-maintain
description: >
  Issue ファイルのセッション内容反映・品質整理・knowledge 切り出し・completed 管理。
  ローカル Issue ファイルのみ更新（Linear API は更新しない）。
  トリガー: 「/issue-maintain」「Issue整理」「Issue更新」「セッション終了前にIssue更新」
  引数: [Issue ID（省略時はブランチから抽出）]
effort: medium
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Bash
  - Skill
---

# Issue メンテナンス

## 概要

`.claude/linear/*/issues/` 内の issue ファイルを整理する。
目的は **次のセッションが素早くコンテキストを把握できる状態** にすること。

## コマンド

| コマンド | 動作 |
|----------|------|
| `/issue-maintain` | 現在のブランチに紐づく issue ファイルを整理 |
| `/issue-maintain TEAM-123` | 指定した issue ファイルを整理 |
| `/issue-maintain --all` | 全 issue ファイルを整理（in-progress + completed の削除判定） |

---

## セッションシグナルの取り込み（event bus subscribe）

`.claude/events.jsonl`（Event Bus ログ）から、対象 Issue に関連する `commit:created`（dev-workflow が publish）・`review:completed`（code-review が publish）を読み取り、Issue 本文に未反映の作業がないかを突き合わせる。Hook ではなく本スキル実行時の軽量読み出しとして行う（重い処理はしない）。

1. ログの存在確認: `.claude/events.jsonl` が無ければ本節をスキップ
2. 直近イベントの読み出し（Bash）:
   ```bash
   [ -f .claude/events.jsonl ] && tail -n 100 .claude/events.jsonl \
     | grep -E '"event":"(commit:created|review:completed)"' || true
   ```
3. 各イベントの payload を現在の Issue（ブランチ/セッションから特定済み）と突き合わせる。**payload に `issue_id` は含まれない**ため、payload の識別子から関連性を導出する:
   - `commit:created`（payload: `sha` / `type` / `files`〔件数〕）… `sha` が現在の Issue ブランチに含まれるか git で確認（例: `git branch --contains <sha>`、または現ブランチの `git log` に該当）。含まれ、かつ「変更ファイル」「更新履歴」へ未記載なら反映候補として提示
   - `review:completed`（payload: `pr` / 件数）… `pr`（PR 番号文字列、ローカルは `"local"`）が現在の Issue のブランチ/PR と一致するか照合。一致し、かつレビュー完了が更新履歴に未記録なら「レビュー済み」記録候補として提示（本文キーワード検出を補完する第二のシグナル源）
4. dedup: 更新履歴に既に該当 PR / commit / レビューが記録済みのイベントは再提示しない（Event Bus 規約の subscriber 責務）。payload に冪等性キーが無い場合は `ts` + event 名で重複排除する
5. 取り込んだシグナルは整理計画（処理フロー Step 10）に統合して提示する

> Event Bus 規約の詳細はリポジトリ CLAUDE.md「Event Bus 規約」を参照。publisher（dev-workflow / code-review）が既に publish しているイベントを subscribe する疎結合設計で、subscriber は publisher を意識しない。

---

## last_active の更新

整理実行時にフロントマターの `last_active` を今日の日付に更新する。`last_active` は dashboard の放置警告・context-agents の作業状態把握が参照する鮮度フィールドで、整理タイミングで書き換えないと死にフィールド化する。

```yaml
---
last_active: 2026-03-20
---
```

- `last_active` フィールドが存在しない場合は追加する（遡及修正は不要。次回整理時に付与すればよい）
- 日付形式は `YYYY-MM-DD`

---

## 整理対象

各セクションを走査し、以下の 4 分類で整理する:

- **削除してよいもの**: 完了済みサブタスクの詳細 / 不採用になったアプローチ / 解決済みの問題・疑問 / 重複した記載 / 一時的なデバッグメモ
- **残すもの**: 未完了タスク `[ ]` の詳細 / 採用した設計判断と理由 / スコープ外の記載 / 変更ファイル一覧 / 備考（副次的な発見）
- **圧縮するもの**: 完了済みサブタスクは詳細を削って1行サマリーにする
- **更新履歴の統合**: 同日に複数エントリがある場合、セッション単位にまとめる

判断基準の詳細と Before/After 例は以下を参照:
→ Read `${CLAUDE_SKILL_DIR}/references/cleanup-criteria.md`

---

## テンプレート準拠チェック

Issue ファイルがフロントマターの `type` に対応するテンプレートに準拠しているか確認する：

| type | 必須セクション |
|------|---------------|
| bugfix | 概要, 進捗, 変更ファイル, 更新履歴 |
| feature | 概要, 計画, 進捗, 変更ファイル, 更新履歴 |
| investigation | 概要, 調査結果, 根本原因, 提案, 関連ファイル, 更新履歴 |
| debt | 概要, 影響範囲, 放置リスク, 対応方針, 進捗, 変更ファイル, 更新履歴 |

**feature の推奨セクション**（省略可、必要に応じて追加）:
- 調査結果、スコープ外、備考

- 不足セクションがあれば追加を提案
- 空のままのセクションは「（なし）」と記載して残す（テンプレート構造を維持）

品質チェックの詳細は以下を参照:
→ Read `${CLAUDE_SKILL_DIR}/references/quality-checklist.md`

---

## knowledge/ への切り出し

整理中に汎用性のある知見を発見した場合、knowledge/ への切り出しまで実行する：

1. **破壊的変更パターンの検出（最優先）**: Issue 本文・進捗・更新履歴から以下キーワードを Grep ベースで走査する：
   - 「破壊的変更 / breaking change」「rename された / renamed to」「deprecated / 非推奨」
   - バージョン跨ぎ表記（例: `v\d+ ?→ ?v\d+`）「dead element / 空振り / lint は通るが」
   - 「衝突する / conflict with / 配列順序」「実機テストで判明 / ランタイムで発覚」
   - 検出時は通常の判断基準より優先して切り出しまで実行する（止めて確認しない）
   - 付与 tags は quality-checklist.md §5.1 の対応表から選ぶ
2. **候補の特定**: 特定の Issue に閉じない、再利用可能な知見を特定
   - アーキテクチャの分析結果
   - パフォーマンス調査の発見
   - ライブラリ・フレームワーク固有のノウハウ
   - ドメインロジックの仕様整理
3. **正確性の確認**: コードベースや関連 Issue と照合して内容が正しいか検証
4. **tags の付与**: 既存 knowledge の tags を確認（`knowledge/index.md` または Grep）し、語彙を揃えた上で 3〜7個の tags を決定
5. **切り出し実行**: `knowledge/{topic}.md` に格納し、元の Issue からはリンクで参照。フロントマターに `status`, `updated`（当日日付）, `tags` を付与
6. **切り出しの報告**: 切り出した内容と格納先は最終レポートに列挙する（承認待ちで止めない）
7. **index.md の更新**: 切り出し後、`knowledge/index.md` を更新する（後述）

knowledge の status フロントマターや切り出し時の照合ルール、tags 付与ルール、破壊的変更パターン検出キーワード一覧の詳細は quality-checklist.md を参照。

**既存 knowledge 編集時の注意:** frontmatter の `updated` を当日の日付に書き換える（鮮度判定に使用される）。

---

## knowledge/index.md の管理

knowledge ファイルの切り出し・更新・削除を行った際は、`knowledge/index.md` を必ず同期する。

フォーマットと更新ルール（新規/更新/削除時の行操作、概要の要約規則、concept のパス付き記載）の詳細:
→ Read `${CLAUDE_SKILL_DIR}/references/knowledge-guide.md`

---

## 概念ページへの波及（concept 統合）

source（個別知見）を切り出した後、複数の source を横断する知見が見えてきたら **概念ページ（concept）** に統合する。これが knowledge の価値の本体になる（個別知見の寄せ集めではなく、繋いで初めて見える構造を残す）。kind / wikilink の定義は `knowledge` スキルの SKILL.md を参照。

波及の判断（既存 concept への `[[ ]]` 追加 / 新規 concept 作成 / source のまま）と concept ページのテンプレート・frontmatter 仕様の詳細:
→ Read `${CLAUDE_SKILL_DIR}/references/knowledge-guide.md`

### 報告

concept の作成・更新も他の整理と同様、承認待ちで止めず実行し、内容と格納先は最終レポートに列挙する。波及で既存 concept を編集した場合は `updated` を当日日付に更新する。

---

## 未import knowledge の検知（横断 vault 反映促し）

knowledge/ 切り出しは本スキルの責務だが、切り出した知見を**横断 vault** に反映する `/import-knowledge` は手動トリガーで忘れやすい。切り出し直後の本スキル内で未import件数を検知して促すのが責務的に最も自然（切り出さない＝新規 import も無い、という論理も噛み合い、セッション開始 hook より発火位置が的確）。

feature-dev Phase 1.6（Vault Recall）と同じ **detect→skip パターン**に乗る。vault を持たないマシンでは静かに skip して後方互換を壊さない。

### Step 1: 検知 CLI の存在確認（外部依存の二段確認）

vault は本プラグイン外の外部資産。環境変数 `KNOWLEDGE_VAULT_ROOT` と検知スクリプトの**両方**が揃って初めて利用可能とみなす。

```bash
# vault 側の軽量 CLI（frontmatter 突合 + triage jsonl のみ・ベクトル検索なし。実測 0.4s）。
# vault の場所は環境変数 KNOWLEDGE_VAULT_ROOT で明示指定する（個人環境パスをハードコードしない）。
SCAN="$KNOWLEDGE_VAULT_ROOT/_shared/scripts/unimported_scan.py"
if [ -n "$KNOWLEDGE_VAULT_ROOT" ] && [ -f "$SCAN" ]; then
  UNIMPORTED_AVAILABLE=1
else
  UNIMPORTED_AVAILABLE=0
fi
```

- `UNIMPORTED_AVAILABLE=0` → 本節を **skip**（`KNOWLEDGE_VAULT_ROOT` 未設定 / スクリプト不在のいずれか）。notify も出さず静かに飛ばす（vault を持たない環境で常態的にノイズを出さないため）
- `UNIMPORTED_AVAILABLE=1` → 次の Step へ

### Step 2: 未import件数の取得

`--project` は vault 側で**巡回パスに対する部分文字列フィルタ**として使われる（`KNOWLEDGE_IMPORT_ROOTS`〔既定 `~/Projects`〕配下の `.claude/{indie,linear}/{slug}/{knowledge,concepts}` 絶対パスに対する部分一致）。cwd の開発プロジェクトに絞る用途なので、**現在のプロジェクトのディレクトリ名**（`basename "$PWD"`）を渡す。これで当該プロジェクト配下の全 slug の knowledge/concepts の fresh 件数が集計される（案件コードは端末に出さない）。`--count` で fresh 件数の整数だけを取得する。

```bash
N=$(python3 "$SCAN" --project "$(basename "$PWD")" --count 2>/dev/null || echo 0)
```

### Step 3: 促し

`N > 0` の場合のみ、最終レポートに 1 行で列挙する（AskUserQuestion では止めない。import 実行はユーザーがチャットで判断する）:

> 未import knowledge {N}件。`/import-knowledge` で vault 反映を推奨

`N = 0` または取得失敗（`echo 0` fallback）時は何も出さない（ノイズを出さない）。

---

## タスク完了時のフロー

Issue のタスクが全て完了した場合、以下を実行する：

1. **レビュー実施状況の確認（レビューガード）** — 詳細は次節「レビューガード」参照。未実施が疑われる場合は `/self-review` 起動を提案する
2. フロントマターの `status` を `completed` に更新
3. 別 Issue に引き継ぐ残タスクがあれば、フロントマターに `follow_up` を追加
   ```yaml
   follow_up:
     - TEAM-500           # Issue 起票済み
     - "xxx のバグ（未起票）"  # まだ Issue になっていない
   ```
4. 更新履歴に完了を記録
5. 汎用知見があれば `.claude/linear/{slug}/knowledge/` に切り出し
6. follow-up ファイルの棚卸し:
   - `.claude/linear/{slug}/follow-ups/*.md` を Glob で確認
   - `status: open` のファイルがあれば件数を通知:
     「open な follow-up が {N}件あります。`/follow-up list` で確認できます」
   - frontmatter の `follow_up` リストに未起票の文字列がある場合:
     「未起票の follow-up が {N}件あります。`/follow-up new` で記録できます」とレポートに列挙（自動記録はしない）

---

## レビューガード（完了マーク前の品質確認）

`/issue-maintain` で Issue を `completed` に遷移させる前、または完了サブタスクが 3 件以上ある時に、コードレビューが実施されたかを確認する。feature-dev 経由を通らず `/issue-maintain` だけで完了マークするケースで、レビュー素通りを防ぐ品質ガード。

- 検出ロジック（遷移条件・未実施シグナルのキーワード・investigation 例外）・警告フォーマット・注意事項の詳細:
  → Read `${CLAUDE_SKILL_DIR}/references/detection-guards.md`
- 起動＝実行確定のためガードで**止めない**。検出時も完了マークは実行し、最終レポートの冒頭で警告する（非ブロッキング）。ユーザーはレポートを見てからチャットで `/self-review` を起動できる

---

## completed ファイルのライフサイクル

completed / canceled の Issue ファイルは、メンテナンス完了後に**削除を提案**する。

### 削除の前提条件

1. テンプレート準拠チェックが完了していること
2. 圧縮（サブタスク詳細の1行化、デバッグメモ削除等）が完了していること
3. 汎用知見が knowledge/ に切り出し済みであること
4. projects doc の「関連 Issue」テーブルに以下が記録されていること:
   - Issue ID、担当者、ステータス（Done / Canceled）、PR リンク
5. canceled の場合、キャンセル理由が projects doc の備考に記録されていること

### 削除フロー

```
1. 上記前提条件を全て確認
2. 前提条件を満たすファイルは承認待ちせず削除する
3. 削除したファイル一覧を最終レポートに列挙する（git 管理下のため復元可能）
```

### linear-maintain からの自動呼び出し

`/linear-maintain` 実行時に completed が検知された場合、本スキルの処理フローが自動実行される。
手動で `/issue-maintain` を実行した場合も同じルールが適用される。

---

## スコープ外差分検出（follow-up 自動提示）

Issue ファイルの「スコープ外」「後続 Issue 候補」「やらないこと」セクションへの**前回コミット以降の追加行**を git diff で検出し、`/follow-up new` 候補として一括提示する。

- 検出ロジック（git log/diff の手順・抽出条件・スキップ条件）・報告フォーマット・注意事項の詳細:
  → Read `${CLAUDE_SKILL_DIR}/references/detection-guards.md`
- 検出が 1 件以上の場合のみ**最終レポートに列挙**する（AskUserQuestion で止めない。新規 follow-up ファイルの生成は副作用が大きいので自動化せず、ユーザーがチャットで判断する）

---

## writing-polish 連携（本文添削・必須）

整理した **Issue 本文** と **切り出した knowledge ページ** の両方を、writing-polish 連携（処理フロー Step 9.5）でファイル確定の直前に `Skill` tool で `writing-polish:writing-polish` を呼んで推敲する。`writing-polish` がインストールされていれば**必ず**実行する。未インストール時のみ skip（プラグイン独立性のため。後方互換）。

`Skill` 呼び出しのインストール判定（bash）・引数（`--embed --tone issue`）・結果反映時の構造保護（frontmatter / wikilink / 見出し階層は変更しない）・fallback の詳細手順:
→ Read `${CLAUDE_SKILL_DIR}/references/writing-polish-integration.md`

---

## 処理フロー

```
1. 対象 issue ファイルを読み込み
1.5 セッションシグナルの取り込み（events.jsonl から commit:created / review:completed を読み、対象 Issue と照合。未反映の commit / レビューを反映候補に）
2. テンプレート準拠チェック（セクション構成の確認）
3. 各セクションを走査し、整理対象を特定
4. 更新履歴のセッション単位統合を確認
5. 破壊的変更パターン検出（quality-checklist.md §5.1 のキーワードを Grep）
6. knowledge/ 切り出し候補を特定（5 の検出結果 + 通常基準。tags の語彙を既存 index.md と照合）
7. 概念ページ波及の判定（切り出し候補・更新 source の tags を既存 concept / source と照合し、新規 concept 作成 or 既存 concept への `[[ ]]` 追加を判断）
8. スコープ外差分検出（git diff で「スコープ外」「後続 Issue 候補」セクションの追加行を抽出）
9. タスク完了時フローの適用判定:
   - レビュー実施状況を確認（レビューガード節を参照）
   - 全タスク完了 → status 更新、follow_up 確認
9.5 writing-polish 連携（Issue 本文 + 切り出し knowledge の散文を推敲。frontmatter / wikilink / 見出し階層 / テンプレート構造は変更しない。「writing-polish 連携」節を参照）
10. 整理を承認待ちせず実行する（既存 knowledge / concept を編集した場合は frontmatter `updated` を当日日付に更新）
11. knowledge/ 切り出し・concept 波及があった場合、knowledge/index.md を更新（concept はパス付きで登録）
11.5 未import knowledge の検知（KNOWLEDGE_VAULT_ROOT + unimported_scan.py の二段 detect→skip。fresh 件数 N>0 なら `/import-knowledge` を最終レポートで促す。vault 不在時は静かに skip）
12. 更新履歴にメンテナンス内容を記録
13. 実行内容を最終レポートにまとめて報告:
    - 削除したもの（git 管理下のため復元可能）
    - 圧縮したもの
    - 統合した更新履歴
    - knowledge/ 切り出し（破壊的変更検出は 🔴 マーカー付きで先頭表示、tags を併記）
    - 概念ページ（concept）への波及（新規作成 / 既存 concept への `[[ ]]` 追加）
    - 未import knowledge 件数（vault 利用可 かつ N>0 の場合のみ。`/import-knowledge` を推奨）
    - スコープ外差分から検出した follow-up 候補（記録は未実行。ユーザーが判断）
    - レビュー未実施の警告（該当する場合。非ブロッキング）
    - 追加したテンプレート不足セクション
```

## 更新履歴への記録形式

```md
| YYYY-MM-DD | メンテナンス: 完了済み詳細を圧縮、xxx を knowledge/ に切り出し |
```

---

## 注意事項

- **情報を減らすのではなく、ノイズを減らす**
- 判断に迷う場合は残す（過剰な削除よりは冗長な方がマシ）
- knowledge/ 切り出し時は必ずコードベースとの照合を行う
- 起動＝実行確定。承認待ちで止まらず最後まで実行し、**実行後にレポートで報告**する（AskUserQuestion で問い直さない）
- Issue ファイルは git 管理下のため、不要な変更は git で復元できる
