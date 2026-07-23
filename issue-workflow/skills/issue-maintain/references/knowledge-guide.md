# knowledge 管理ガイド（index.md 同期・concept 波及）

knowledge/index.md の同期フォーマット・更新ルールと、概念ページ（concept）への波及の判断・テンプレートの詳細。

## knowledge/index.md の管理

### フォーマット

```markdown
# Knowledge Index

| ファイル | tags | status | 概要 |
|---------|------|--------|------|
| api-patterns.md | api, rest, pagination | verified | REST API のページネーションパターン |
| cache-strategy.md | cache, redis, ttl | planned | キャッシュ戦略の設計案 |
```

### 更新ルール

1. knowledge ファイルの新規作成時: 行を追加
2. knowledge ファイルの更新時: 該当行の tags・status・概要を更新
3. knowledge ファイルの削除時: 該当行を削除
4. 概要はファイルの最初の見出し直後の1文を使用する（30文字以内に要約）
5. index.md 自体は knowledge ファイルとしてカウントしない
6. concept（`knowledge/concepts/*.md`）はファイル列をパス付き（`concepts/{slug}.md`）で記載する

## 概念ページへの波及（concept 統合）

### 波及の判断

切り出した／更新した source の tags・トピックを既存 knowledge と照合し、次を判定する:

1. **既存 concept に該当あり**（`knowledge/concepts/*.md` に関連する概念ページがある）:
   - その concept の「関連ソース」に `[[新しい source]]` を追加する
   - 「横断的知見」を読み返し、新しい source で補強・修正できる点があれば追記する（矛盾を見つけたら明記する）
   - concept の frontmatter `updated` を当日日付に更新する
2. **新規 concept の候補**（同じテーマを扱う source が 2 件以上あり、まだ概念ページが無い）:
   - 新規 concept ページの作成を提案する（下記テンプレート）
3. **該当なし**（単発の知見）:
   - source のままにする（無理に concept 化しない）

### concept ページのテンプレート

`knowledge/concepts/{concept-slug}.md` に作成する:

```markdown
---
kind: concept
source: {統合元 Issue ID（複数可）}
status: verified | planned
verified: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [...]
---

# {概念名}

## 概要
{この概念が何か。1〜2 文}

## 横断的知見
{複数 source を跨いで見えてくる構造・共通パターン・矛盾。concept の核}

## 未解決の問い
{この概念について残っている疑問・検証したい点}

## 関連ソース
- [[source-a]] — {このソースから得た観点}
- [[source-b]] — {このソースから得た観点}
```

- 「横断的知見」が薄い（単一 source の要約に留まる）なら concept にせず source のままにする
- 関連ソースは `[[name]]`（拡張子なし basename）で参照する
- concept も index.md に登録する（ファイル列は `concepts/{slug}.md`）
- frontmatter は source と同じく `kind` / `source` / `status` / `verified`（verified 時のみ）/ `updated` / `tags`。`kind: concept` を足すのが source との差分
