# 軽量フロー（feature-dev を使わない一連のワークフロー）

Phase F7 で「軽量フロー」が選ばれたときに Read する。8 phase（explorer / architect / spec ゲート）は回さず、
実装 → 検証 → セルフレビュー → コミット → push → CI 確認 → Issue 更新の一連を最後まで通すことだけを保証する。

**対象**: 方針が既に決まっている・影響範囲が読めている変更（bugfix・小〜中規模の機能追加・リファクタ）。
設計判断が未確定・複数レイヤーにまたがる場合は feature-dev を勧め直してよい（1 回だけ。断られたらこのまま進む）。

## 前提: 委譲先プラグインの導入判定

他プラグインへの依存は禁止（dormant 設計）。冒頭で 1 回だけ判定し、以降の Step で分岐する:

```bash
DW=0; CR=0
grep -q '"dev-workflow@' "$HOME/.claude/settings.json" 2>/dev/null && DW=1
grep -q '"code-review@'  "$HOME/.claude/settings.json" 2>/dev/null && CR=1
```

## 手順

開始時に TodoWrite で以下 6 Step をタスク化し、進捗を追跡する（各 Step の完了条件を満たすまで次へ進まない）。

### Step 1: 実装

Issue ファイルの計画・タスクセクションに沿って実装する。計画が無ければ、着手前に変更方針を 2〜3 行で
ユーザーに示してから始める（黙って書き始めない）。スコープ外の変更を混ぜない。

### Step 2: 検証

プロジェクトの検証手段を特定して実行する。探索順: CLAUDE.md に書かれた検証コマンド → pre-commit hook
（`git config core.hooksPath` / `.git/hooks`）→ CI 定義（`.github/workflows/` 等）のジョブと同じコマンド。
いずれも無ければ変更に対応するテスト・lint を直接実行する。**赤のまま Step 3 へ進まない。**

### Step 3: セルフレビュー

- `CR=1`: `Skill` tool で `code-review:self-review` を起動する（引数は現在の base に合わせる）。
  指摘への対応は self-review 側の修正方針フローに従う
- `CR=0`: `git diff` を通読し、Issue のスコープ外変更・デバッグ残骸・コメントの言い残しを自分で点検する

### Step 4: コミット

- `DW=1`: `Skill` tool で `dev-workflow:commit` を起動する
- `DW=0`: 論理単位に分けて Conventional Commits 形式でコミットする

### Step 5: push + CI 確認

push し、CI があれば結果を確認する。**CI が緑になるまで完了と見なさない**（移植性・環境差はローカルで
検出できない）。赤なら修正して Step 2 から繰り返す。CI が無いプロジェクトでは push まで。
push しない運用（ローカルのみ・PR 前に溜める等）が明らかな場合は、その旨をユーザーに確認してスキップしてよい。

### Step 6: Issue 更新

進捗・完了を Issue ファイルへ反映する（`/issue-maintain` 委譲でも直接編集でもよい）。完了なら status を
completed へ遷移する（BACKEND=linear のときは Linear 側のステータス更新も案内する）。未完了で終える場合は
残タスクと次セッションの入口を Issue に書き残す。

## 報告

全 Step 完了時（または中断時）に、実施した Step / スキップした Step とその理由を 1 行ずつで報告する。
