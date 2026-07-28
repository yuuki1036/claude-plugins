# evals

トリガーフレーズ → 期待スキル起動の回帰テストハーネス（waza 風 多層 grader 対応）。

## 概要

プラグインのスキルが意図したトリガーフレーズで起動するかを検証する。
`claude` CLI を headless モードで起動し、副作用なしにスキル選択のみを検証できるよう
プロンプトを変形して評価する。

スキル起動の正誤に加え、`text` (regex match) と `behavior` (latency / 出力長) の
grader を重ねられる。タグによる hold-out 機構と複数モデルの比較もサポート。

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
    tags: [smoke]
    graders:
      - type: text
        name: mentions_commit
        pattern: "コミット|commit"
      - type: behavior
        name: latency_budget
        max_latency_ms: 60000
```

| フィールド | 必須 | 説明 |
|-----------|------|------|
| `plugin` | ○ | 対象プラグイン名 |
| `id` | ○ | ケース識別子（ファイル内で一意） |
| `prompt` | ○ | ユーザー入力のシミュレーション |
| `expected_skill` | △ | 期待する呼び出し先（`plugin:skill` 形式）。inline list で `[a, b]` 列挙可。省略時は skill_invocation grader を使わない（text/behavior のみ評価） |
| `k` | - | pass^k の k（デフォルト 3）。連続 k 回成功で PASS |
| `tags` | - | タグ（hold-out フィルタに使用） |
| `graders` | - | 追加 grader（後述） |
| `wrapper` | - | `skill_json`（デフォルト）はスキル選択 JSON を要求するラッパーで包む。`none` は prompt をそのまま実行する（判定校正ケース用。`expected_skill` と併用不可） |

### Grader タイプ

`expected_skill` を指定すると `skill_invocation` grader が自動付与される。追加の grader は `graders:` リストで指定する。

#### text

応答 stdout を regex で検査する。

```yaml
graders:
  - type: text
    name: has_json_marker
    pattern: '\{"skill"\s*:'
    mode: must_match    # default。must_not_match で否定マッチ
```

#### behavior

応答時間や出力長の上限を検査する。

```yaml
graders:
  - type: behavior
    name: latency_budget
    max_latency_ms: 60000
    max_stdout_chars: 4000
```

`max_latency_ms` / `max_stdout_chars` はどちらか一方のみでも可。

### Tags（hold-out 機構）

過学習対策として、改訂サイクル中に参照するケースと最終確認用ケースを分離できる。

```yaml
- id: chore-ja
  prompt: 雑務的な作業をコミットして
  expected_skill: dev-workflow:git-commit-helper
  tags: [holdout]   # デフォルトで実行から除外される
```

`holdout` タグを持つケースは `--exclude-tag holdout`（デフォルト）で除外される。
最終確認時のみ `--only-tag holdout` で実行する。

## 使い方

```bash
# 全ケース実行（holdout は除外）
python3 evals/runner.py

# プラグイン絞り込み
python3 evals/runner.py --plugin dev-workflow

# スモーク（k=1）
python3 evals/runner.py --k 1

# レポートをファイル出力
python3 evals/runner.py --report evals/reports/latest.md

# dry-run（claude を呼ばず挙動確認）
python3 evals/runner.py --dry-run

# モデル間比較
python3 evals/runner.py --models claude-opus-5,claude-sonnet-5

# hold-out のみ（改訂後の最終確認）
python3 evals/runner.py --only-tag holdout

# 除外タグの追加
python3 evals/runner.py --exclude-tag holdout,slow
```

## 評価ロジック

1. ケースの `prompt` をラッパーで包み、Claude に「どのスキルを呼ぶか JSON で返せ（実行は禁止）」と指示する
2. `claude -p <wrapped> --output-format text --permission-mode plan [--model X]` を起動
3. 応答末尾の `{"skill": "..."}` を抽出 → `AttemptObservation` (skill, stdout, latency_ms) を構築
4. 全 grader を実行、すべて pass なら attempt 成功
5. k 回連続で attempt 成功なら case が PASS、途中失敗で早期終了

副作用を避けるためツールは実行させず、判断のみを問う設計。自然なスキル起動と
完全一致ではないが、description/トリガーフレーズ設計の回帰検出には十分。

`wrapper: none` のケースはラッパーを使わず prompt を直接実行し、text / behavior grader
のみで評価する。スキル選択ではなく「ルールに従った判定が正しく fire / no-fire するか」を
校正するケース（例: writing-polish カテゴリ7）に使う。

## レポート構造

- **Summary**: プラグイン × モデルのマトリクスで pass/total を表示
- **Model Comparison**: 複数モデル指定時にケース単位の PASS/FAIL を並列表示
- **Details**: モデル別・プラグイン別に attempt × grader の詳細を出力（latency / 失敗理由を含む）

## コスト

- ローカル実行（Max plan / subscription）: 通常セッションと同じ枠
- CI 実行: 現時点では非対応（API key 課金が発生するため）

詳細は `/knowledge` や `.claude/knowledge/` を参照。

## 依存

- Python 3.8+
- `claude` CLI（PATH 上）
- `pyyaml`（推奨。無い場合は内蔵の最小パーサで対応するが `graders` / ネスト構造は読めない）

## Gotchas（CLAUDE.md から移設）

- **eval のプロンプトにスラッシュコマンドを使わない**: `evals/runner.py` は headless の `claude -p` を呼ぶが、**headless はプラグインのコマンドを登録しない**ため `/living-spec` `/adr` `/design-doc` はいずれも `Unknown command` で必ず落ちる。**認証の有無とは無関係**（`claude auth status` が `loggedIn: true` でも再現するので、`Failed to authenticate` が同時に出ていても認証切れのせいだと誤診しないこと）。トリガーは自然言語のプロンプトで測る。`evals/cases/notebooklm-workflow.yaml` の `add-source-slash` がこの理由で恒常 fail している（未修正）
- **eval の fail はまず「プラグイン選択」と「skill id の綴り」を分けて読む**: モデルが実在しない skill id を綴る fail が一定率で出る（`adr-keeper:adr` を `adr-keeper:adr-keeper`、`notebook-source-adder` を `notebooklm-add-source`、`notebook-query-assistant` を `notebook-summarizer` 等）。プラグインの選択自体が正しいなら、それは harness 側の性質でスキル description の問題ではない。**expected に実在しない id を列挙して緑にしない**（eval が意味を失う）。誤発火の有無は「どのプラグインが選ばれたか」で判定する
- **eval の判定に k=1 の結果を使わない**: 上の id 捏造は**確率的**で、k=1 で落ちたケースが k=3 では通ることがある（notebooklm-workflow は k=1 で 3 件落ちたが k=3 では 1 件に減った）。`--k 1` は配線確認（ケースが読めるか・プラグインが解決するか）専用で、**恒常的に落ちる／description が悪い の根拠にはならない**。判定は既定の pass^k=3 で行う
