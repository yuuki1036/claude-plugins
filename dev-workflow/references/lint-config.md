# PostToolUse lint チェーン設定

`post-format-lint.sh`（PostToolUse / Edit|Write|MultiEdit）は **opt-in**。`.claude/dev-workflow.json` に `lint.enabled: true` と言語別コマンドを定義したときだけ発火する。設定が無い・`enabled` が false のプロジェクトでは完全に dormant（既存挙動に影響なし）。

## 設計

- **3 段チェーン**: `fmt`（フォーマット自動修正）→ `lint`（lint 自動修正）→ `check`（残違反検出）
  - `fmt` / `lint` 段は黙って直す（出力は捨てる）
  - `check` 段で **残った違反だけ** を `decision:"block"` で Claude に返す
- **path guard 先行**: `node_modules` / `dist` / `build` / `.next` / `coverage` / `vendor` / `*.min.*` / lock 系は早期に除外（`hooks/lib/path-guard.sh`）
- **出力の context 節約**: check 出力は `head -20` + 総行数注記に丸める（`hooks/lib/json-block.sh::emit_block_json`）
- **errexit 隔離**: lint コマンドの非ゼロ終了で hook 自体が落ちないよう `set +e` 区間で実行

## 設定スキーマ（`.claude/dev-workflow.json`）

```json
{
  "lint": {
    "enabled": true,
    "languages": {
      "frontend": {
        "enabled": true,
        "extensions": ["ts", "tsx", "js", "jsx", "vue", "svelte", "css", "scss"],
        "fmt": "prettier --write",
        "lint": "eslint --fix",
        "check": "eslint"
      },
      "go": {
        "extensions": ["go"],
        "fmt": "gofmt -w",
        "lint": "golangci-lint run --fix",
        "check": "golangci-lint run"
      },
      "python": {
        "extensions": ["py"],
        "fmt": "ruff format",
        "lint": "ruff check --fix",
        "check": "ruff check"
      }
    }
  }
}
```

### フィールド

| キー | 必須 | 説明 |
|---|---|---|
| `lint.enabled` | yes | 全体の on/off。`false` または不在で dormant |
| `lint.languages.<key>` | yes | 任意の言語キー（`frontend` / `go` 等、名前は自由） |
| `.extensions` | yes | 対象拡張子（ドット無し小文字）。編集ファイルの拡張子がここに一致した言語を採用 |
| `.enabled` | no | 言語単位の on/off（既定 true）。言語別に無効化できる |
| `.fmt` | no | フォーマット自動修正コマンド。末尾にファイルパスが付与される |
| `.lint` | no | lint 自動修正コマンド。同上 |
| `.check` | no | 残違反検出コマンド。非ゼロ終了で block。同上 |

各コマンドは `eval "<cmd> \"<file>\""` で実行される（対象ファイル 1 件を引数に取る前提）。

## 注意・既知の制約

- **ファイル単位前提**: `eslint <file>` / `ruff check <file>` のようにファイル 1 件で動くツール向け。`golangci-lint run` のようにパッケージ単位で動くツールはファイルパス付与が効かない場合がある（その言語は `check` を空にして fmt/lint のみ運用するなど調整する）
- **timeout**: hooks.json で 30 秒。重い check はタイムアウトしうるので、必要なら check を CI 側に寄せて hook では fmt/lint のみにする
- **block の意味**: PostToolUse の block は編集を巻き戻さない。残違反を Claude に通知して次の修正を促すシグナルとして機能する
- **無効化**: 一時的に止めたいときは `lint.enabled` を false にするか、`.claude/dev-workflow.json` から `lint` ブロックを削除する
