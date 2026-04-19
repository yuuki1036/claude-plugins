---
name: eval-runner
description: >
  プラグインのトリガーフレーズ → 期待スキル起動の回帰テストを実行する。
  evals/ 配下の YAML ケースを pass^k 基準で検証し、スキル選択のデグレを検出する。
  トリガー: 「eval実行」「evalランナー」「スキル回帰テスト」「トリガーフレーズ検証」「/eval-runner」
  引数: [--plugin NAME] [--case ID] [--k N] [--dry-run]
effort: medium
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

# Eval Runner スキル

## 概要

`evals/runner.py` を実行して、プラグインのスキル選択ロジックが期待通りに動くかを検証する。
トリガーフレーズや description を変更した後の回帰テストに使う。

## 前提

- カレントディレクトリが `claude-plugins` リポジトリのルートであること
- `claude` CLI が PATH 上にあること
- ローカル実行のみ対応（CI 非対応。Max plan / subscription の通常セッション枠を消費）

## ワークフロー

### 1. 対象範囲の確認

ユーザーの要求から以下を判定:

- 全ケース実行: 引数なし or 「全部」「全プラグイン」
- プラグイン絞り込み: プラグイン名が指定されている場合
- ケース絞り込み: ケース ID が指定されている場合
- スモーク: 「軽く」「スモーク」などの語 → `--k 1`

曖昧な場合は `AskUserQuestion` で確認する。

選択肢例:
- 全プラグインの k=3 回帰テスト（本番品質）
- 全プラグインの k=1 スモーク（速度優先）
- 特定プラグインのみ

### 2. 実行

```bash
# 基本
python3 evals/runner.py --report evals/reports/$(date +%Y%m%d-%H%M%S).md

# スモーク
python3 evals/runner.py --k 1 --report evals/reports/smoke.md

# プラグイン絞り込み
python3 evals/runner.py --plugin dev-workflow --report evals/reports/dev-workflow.md
```

大量ケースは時間がかかる（1ケース = k × 10-30s）。事前にユーザーに所要時間を伝える:

- k=3 × 全16ケース ≈ 8-20分
- k=1 × 全16ケース ≈ 3-7分

### 3. レポート確認

`evals/reports/<timestamp>.md` を Read で読み、サマリーテーブルの FAIL 件数を確認。

失敗ケースがあれば:
- どのプロンプトで失敗したか
- 実際にどのスキル（または null）が選ばれたか
- 期待とのギャップ

を抽出してユーザーに報告する。

### 4. 改善提案

FAIL が見つかったら以下を提案:

- **description のトリガーフレーズ追加**: プロンプトに近い言い回しをスキルの `description` の「トリガー:」節に追加
- **競合スキルの整理**: 複数スキルが似たトリガーを持っていないか `/quality-check` で確認
- **ケースの調整**: プロンプト自体が曖昧すぎる場合はケース側を見直す

## ケース追加

新しいプラグインやスキルを追加したら `evals/cases/{plugin}.yaml` にケースを足す。
プラグインあたり最低 1 ケース、主要スキルは代表トリガーで 1 ケースずつが目安。

```yaml
plugin: {plugin-name}
cases:
  - id: {unique-id}
    prompt: {自然な日本語のトリガーフレーズ}
    expected_skill: {plugin}:{skill-name}
    k: 3
```

### Gotcha: 同名の command + skill ペア

同じプラグイン内に `commands/foo.md` と `skills/bar/SKILL.md` の両方があり、
自然言語トリガーがどちらにも解釈されうる場合、Claude は **command 名で応答する
傾向が強い**（例: 「コミットして」→ `dev-workflow:commit` が返り、
`dev-workflow:git-commit-helper` ではない）。

実害はないので、ケース側で両方を許容する inline list 形式で書く:

```yaml
  - id: commit-ja
    prompt: コミットして
    expected_skill: [dev-workflow:git-commit-helper, dev-workflow:commit]
    k: 3
```

該当パターン:
- `dev-workflow:commit` ↔ `dev-workflow:git-commit-helper`
- `instinct-memory:learn` ↔ `instinct-memory:instinct-learning`
- `plugin-feedback:feedback` ↔ `plugin-feedback:feedback-issue`

## 注意事項

- **副作用なし**: runner はスキルを実際に実行しない。プロンプトを変形し「どのスキルを呼ぶか」を JSON で応答させるだけ
- **自然起動との差**: 測定値は「問われた時の Claude の判断」であり、通常会話での自動起動とは厳密には一致しない。MVP 指標として利用する
- **CI 非対応**: API key 課金が発生するため CI 実行は除外。手動実行のみ
- **k の設計**: pass^k は LLM の stochastic 挙動を織り込む指標。k=3 が標準、スモークで k=1
