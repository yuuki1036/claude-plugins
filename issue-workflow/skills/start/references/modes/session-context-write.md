<!-- 正本依存（SSoT pin）。このモードの本文が要約している正本。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: issue-workflow/skills/start/references/existing-work.md#2 @f8a4a7f8 -->

## セッションコンテキスト書き出し（Feature ブランチモード共通）

### Phase CTX: session-context.md 書き出し

Feature ブランチモードで Issue ファイルの読み込みに成功した場合に実行する。
ダッシュボードモード・Quick Pick モード・親 Issue 軽量サマリーモード、および Issue ファイルが存在しない場合はスキップする。
F2.5 の `WORK_STATE`（F7 で決め直した回は決め直した後の値）が `detached` / `closed` / `prunable` の回もスキップする（session-context を書かない）。
この Issue の作業が無い今のチェックアウトに `issue_id` を書くと、そこが detached HEAD の worktree なら、同じチェックアウトでの次の /start でここが session-context の候補（`current=1`）になって `fresh` に決まり、`detached` の歯止めが判定行の注記だけに弱まる（`closed` の status を戻した後・`prunable` を prune した後の /start も、作業のある候補より先にここへ決まる）。

1. 以下の情報を `.claude/session-context.md` に Write で書き出す:

```yaml
---
shared_state_type: session
producer: issue-workflow
consumers: [code-review, issue-workflow]
schema_version: 1
last_updated: {現在の ISO 8601 タイムスタンプ}
branch: {現在のブランチ名}
issue_id: {Issue ID}
---
```

> Shared State 規約（CLAUDE.md 参照）に従い、producer / consumers / schema_version / last_updated を付与する。consumer 側プラグインは frontmatter 不在のファイルも読めるが、新規書き出しは必ず付与する。

2. YAML frontmatter の後に以下のセクションを追記する:

```markdown
# セッションコンテキスト

## Issue サマリー
{Issue ファイルの frontmatter（title, status, type）と概要セクションの要約}

## 設計判断・スコープ外
{Issue ファイルから「設計判断」「スコープ外」「方針」「意図的」に関する記述を抽出}
{該当する記述がない場合はこのセクションを省略}

## 関連プロジェクト
{読み込んだプロジェクト doc の要約（プロジェクト名と概要のみ）}
```

3. このファイルは毎回上書きする（前回のセッションの内容は不要）

**注意:**
- `.claude/session-context.md` はセッション固有のファイルであり、git にコミットしない
- Write ツールで `.claude/session-context.md` に書き出す。Phase F2.5 か F7 で worktree に移した回は `{WORKTREE}/.claude/session-context.md`（絶対パス）に書く — 読む側（code-review・issue-band）は作業しているチェックアウトのものを見る
