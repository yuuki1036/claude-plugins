---
description: プラグインの改善要望・バグ報告を GitHub Issue として作成する
user_invocable: true
allowed-tools:
  - Bash
  - AskUserQuestion
---

プラグインへの改善要望・バグ報告を GitHub Issue として起票してください。

## 引数

`$ARGUMENTS` にプラグイン名や要望内容が含まれていればそれを使う。

## ワークフロー

### Phase 1: 認証チェック

`gh auth status` で GitHub CLI の認証状態を確認する。
未認証なら `gh auth login` の実行を案内して中止する。

### Phase 2: 対象プラグインの特定

1. `$ARGUMENTS` にプラグイン名が含まれていればそれを使う
2. 未指定なら、以下のプラグイン一覧から選択を促す:
   - instinct-memory
   - code-review
   - dev-workflow
   - claude-meta
   - linear-workflow
   - indie-workflow
   - plugin-manager
   - plugin-feedback

### Phase 3: 種別の特定

| label | 用途 |
|-------|------|
| enhancement | 機能追加・改善要望 |
| bug | バグ報告 |
| question | 質問・相談 |

- 会話コンテキストから自動判定できればそれを使う
- 判断に迷う場合はユーザーに確認する

### Phase 4: 内容のヒアリング

1. タイトルを決定する（簡潔に、50文字以内目安）
2. 詳細を決定する
3. 既にユーザーが説明している場合はそれを使い、重複して聞かない
4. 会話中に出てきた改善要望の場合、そのコンテキストを自動で要約する

### Phase 5: プレビューと承認

以下のフォーマットで Issue プレビューを提示し、ユーザーの承認を得る:

```
## Issue プレビュー

**リポジトリ**: yuuki1036/claude-plugins
**タイトル**: [{plugin-name}] {title}
**ラベル**: {label}

**本文**:
## 対象プラグイン
{plugin-name}

## 種別
{enhancement / bug / question}

## 説明
{詳細}

## 期待する動作
{改善後のイメージ（enhancement/bug の場合）}

## 現在の動作
{現状の動作（bug の場合）}

---
_このIssueは plugin-feedback により作成されました_
```

### Phase 6: Issue 作成

承認後、以下を実行:

```bash
gh issue create \
  --repo yuuki1036/claude-plugins \
  --title "[{plugin-name}] {title}" \
  --label "{label}" \
  --body "{body}"
```

- ラベルが存在しない場合は `--label` を省略する
- 作成された Issue URL を報告する

### Phase 7: 報告

```
Issue を作成しました: {URL}
```
