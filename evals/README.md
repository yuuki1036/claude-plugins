# evals

トリガーフレーズ → 期待スキル起動の回帰テストハーネス。

## 概要

プラグインのスキルが意図したトリガーフレーズで起動するかを検証する。
`claude` CLI を headless モードで起動し、副作用なしにスキル選択のみを検証できるよう
プロンプトを変形して評価する。

## 構成

```
evals/
├── cases/              # プラグインごとの YAML ケース
│   └── {plugin}.yaml
├── runner.py           # 実行ランナー（Python）
├── reports/            # レポート出力先（gitignore）
└── README.md
```

## ケースフォーマット

```yaml
plugin: dev-workflow
cases:
  - id: commit-ja
    prompt: コミットして
    expected_skill: dev-workflow:git-commit-helper
    k: 3
```

| フィールド | 説明 |
|-----------|------|
| `plugin` | 対象プラグイン名 |
| `id` | ケース識別子（ファイル内で一意） |
| `prompt` | ユーザー入力のシミュレーション |
| `expected_skill` | 期待する呼び出し先（`plugin:skill` 形式） |
| `k` | pass^k の k（デフォルト 3）。連続 k 回成功で PASS |

## 使い方

```bash
# 全ケース実行
python3 evals/runner.py

# プラグイン絞り込み
python3 evals/runner.py --plugin dev-workflow

# スモーク（k=1）
python3 evals/runner.py --k 1

# レポートをファイル出力
python3 evals/runner.py --report evals/reports/latest.md

# dry-run（claude を呼ばず挙動確認）
python3 evals/runner.py --dry-run
```

## 評価ロジック

1. ケースの `prompt` をラッパーで包み、Claude に「どのスキルを呼ぶか JSON で返せ（実行は禁止）」と指示する
2. `claude -p <wrapped> --output-format text --permission-mode plan` を起動
3. 応答末尾の `{"skill": "..."}` を抽出
4. `expected_skill` と一致するか判定（`plugin:skill` の suffix マッチ対応）
5. k 回連続で一致したら PASS、途中で失敗したら早期終了

副作用を避けるためツールは実行させず、判断のみを問う設計。自然なスキル起動と
完全一致ではないが、description/トリガーフレーズ設計の回帰検出には十分。

## コスト

- ローカル実行（Max plan / subscription）: 通常セッションと同じ枠
- CI 実行: 現時点では非対応（API key 課金が発生するため）

詳細は `/knowledge` や `.claude/knowledge/` を参照。

## 依存

- Python 3.8+
- `claude` CLI（PATH 上）
- `pyyaml`（任意、無い場合は内蔵の最小パーサで対応）
