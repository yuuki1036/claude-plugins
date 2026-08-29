# Journal Schema

failure-journal の永続フォーマット定義。

## 保存先

- パス: `.claude/failure-journal/journal.jsonl`
- 形式: JSON Lines（1 行 = 1 イベント）
- 書き込み: **append-only**（既存行の編集・削除を禁止）
- 永続性: **gitignore 推奨**（fingerprint を AI の出力に汚染させないため、commit せずローカルに留める。README 参照）

## candidates.jsonl（自己申告の候補置き場）

journal の手前に置くステージングファイル。SessionStart 注入ルール（`rules/self-report-rule.md`）により、Claude が自己訂正した瞬間に 1 行 append する。`/retro` Phase 0.5 が承認レビューで journal に昇格する。

- パス: `.claude/failure-journal/candidates.jsonl`
- スキーマ: `{"ts":"<ISO8601 UTC>","summary":"<何をどう間違えたか 1 行>","verdict":null}`
  - `verdict` は起票時 `null`。`/retro` のレビュー後に `"accepted"` / `"rejected"` が書き戻される（再浮上防止）
  - `summary` は自由文。固有名詞可（tag 化・抽象化は retro のレビューで行う）
- journal との違い: append-only ではない（verdict の書き戻しのみ許可。行削除・summary 書き換えは禁止）
- Read 制約は journal と同じ（**retro 実行中のみ Read**。append はいつでもよい）

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

## umbrella tag の分割（retro で閾値を超え続けるとき）

**同一 tag が還流のたびに別の機構を出してくるなら、それは 1 つの失敗型ではなく複数を束ねている。**
分割せずに還流を重ねても、対策は毎回「今回の 1 件」にしか当たらず、閾値だけが鳴り続ける。

判定の目安（retro の Phase 4 で使う）:

- 閾値を超えた tag の内訳を書き出したとき、**還流先が 2 つ以上に割れる**（hook / 規約 / skill）
- 既に還流した対策が、**次の発生を止めていない**（発生が対策より後で、かつ別の機構）

分割するときは**新しい発生から新 tag を使い、既存 journal は書き換えない**（append-only）。
過去ぶんは umbrella のまま残るので、集計は「umbrella + 新 tag の合計」で読む。

### 実例: `claimed-fact-without-source`（全期間 17 件・窓内 9 件で最多）

内訳が 4 機構に割れ、還流先もばらけた:

| サブ tag | 機構 | 還流先 |
|---|---|---|
| `stale-record-read-as-current` | 記録（title / コミットメッセージ / 過去コメント）から現在値を断定 | 規約（CLAUDE.md） |
| `cited-passage-not-verified` | 引用先に該当記述が実在するか確認しない | hook（guardrail-protect） |
| `mechanism-asserted-unread` | 正本のコードを読まずに機構・原因を断定 | 規約 |
| `unassigned-id-written-as-fixed` | 未確定の識別子（issue 番号・版・ハッシュ）を確定として書く | 規約 |

**`unassigned-id-written-as-fixed` は存在検査では止まらない**（実測: 起票前に書いた issue 番号が
実在する別の issue を指しており、存在検査を通ってしまう）。`vNEXT` プレースホルダと同じく
**書く側の手順**で消す型。

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
