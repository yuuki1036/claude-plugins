# Journal Schema

failure-journal の永続フォーマット定義。

## 保存先

- パス: `.claude/failure-journal/journal.jsonl`
- 形式: JSON Lines（1 行 = 1 イベント）
- 書き込み: **append-only**（既存行の編集・削除を禁止）
- 永続性: **gitignore 推奨**（fingerprint を AI の出力に汚染させないため、commit せずローカルに留める。README 参照）

## スキーマ

各行は次の構造の単一 JSON オブジェクト:

```json
{"timestamp":"2026-05-29T12:00:00Z","tag":"spec-skipped-without-rationale","phenomenon":"spec.md を生成せず実装へ進んだ","context":{}}
```

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `timestamp` | string (ISO8601 UTC) | yes | `date -u +%Y-%m-%dT%H:%M:%SZ` で生成 |
| `tag` | string | yes | 集計の fingerprint。下記 tag 規約に準拠 |
| `phenomenon` | string | yes | 失敗現象の簡潔な説明（1〜2 文。長文ログ禁止）|
| `context` | object | yes | 将来拡張用。Phase 1 では `{}` 固定 |

## tag 規約

| 規約 | 内容 | 違反例 → 修正例 |
|---|---|---|
| kebab-case | 小文字 + ハイフン区切り | `SpecSkipped` → `spec-skipped` |
| 30 文字以内 | 長い場合は抽象化して短縮 | `spec-md-was-skipped-without-any-rationale` → `spec-skipped-without-rationale` |
| 固有名詞禁止 | ファイル名・関数名・Issue ID・人名を含めない | `foo-ts-type-error` → `type-error-untracked` |
| 現象主体 | 「何をしくじったか」を抽象化 | `forgot` → `version-bump-omitted` |

> tag は「同じ失敗を別の機会に踏んだとき、同一の tag に collapse できる」ことが目的。具体的すぎると集計で別 tag に散り、抽象的すぎると無関係な失敗が混ざる。現象の「型」を表す粒度を狙う。

## append 手順（正準）

```bash
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
jq -nc \
  --arg ts "$ts" \
  --arg tag "$tag" \
  --arg ph "$phenomenon" \
  '{timestamp:$ts,tag:$tag,phenomenon:$ph,context:{}}' \
  >> .claude/failure-journal/journal.jsonl
```

- `jq -nc` で null input から compact な 1 行 JSON を生成（valid JSON を保証）
- `>>` で末尾追記のみ。`>` （上書き）は禁止
- 文字列は `--arg` 経由で渡す（クオート・改行のエスケープを jq に任せる）

## event publish

append 成功後、`failure:logged` event を publish する（payload は tag のみ）:

```bash
if source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh" 2>/dev/null; then
  SAFE_HOOK_NAME="failure-journal"
  event_bus_publish "failure:logged" "$(jq -nc --arg t "$tag" '{tag:$t}')"
fi
```

> `SAFE_HOOK_NAME` を設定せずに `event_bus_publish` すると `"plugin":"unknown"` が書かれる。source 直後に必ず `SAFE_HOOK_NAME="failure-journal"` を設定する（`safe_hook_init` は stdin を cat するので skill 内 Bash では呼ばない）。
