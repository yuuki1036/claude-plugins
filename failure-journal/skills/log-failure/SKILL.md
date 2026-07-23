---
name: log-failure
description: >
  再発しうる失敗を journal (JSON Lines) に append する。
  判断軸は「同じ状況で再発しうるか」の単一基準。tag は kebab-case 30 文字以内・固有名詞禁止・現象主体で抽象化。
  append-only（既存行の編集禁止）で valid JSON を保証し、append 後に failure:logged event を publish する。
  トリガー: 「失敗を記録」「log-failure」「再発しそうな失敗」「journal に追記」
  「また同じミスした」「failure journal」「/log-failure」
effort: medium
allowed-tools:
  - Read
  - Bash
---

# Log Failure

再発しうる失敗を journal (`.claude/failure-journal/journal.jsonl`) に append するスキル。責務は「セッション振り返り」ではなく「**再発する失敗パターンの記録**」。一過性のミスは記録しない。

詳細仕様は `references/` を参照:

- `references/journal-schema.md` — JSON Lines スキーマ定義 / append 手順 / tag 規約

---

## Phase 0: journal パス確認

1. journal パス: `.claude/failure-journal/journal.jsonl`
2. SessionStart hook が初期化済みのはずだが、念のため Bash で親ディレクトリの存在を確認し、無ければ `mkdir -p .claude/failure-journal` する
3. ファイルが無ければ空ファイルを用意（`: >`）

---

## Phase 1: 再発性判定（単一基準）

判断軸は **「同じ状況で再発しうるか」のみ**。これ以外の軸（重大度・恥ずかしさ・工数）では判定しない。

| 判定 | アクション |
|---|---|
| Yes（再発しうる） | append する（Phase 2 へ） |
| No（一過性・偶発） | **記録しない**（journal を汚さないため） |

迷ったら「同じ状況に再度遭遇したら同じ失敗を踏むか」を自問する。Yes なら記録、No なら破棄。

---

## Phase 2: tag 生成・検証

`tag` は集計の fingerprint。以下の規約をすべて満たすこと:

| 規約 | 内容 |
|---|---|
| 形式 | kebab-case（小文字 + ハイフン） |
| 長さ | 30 文字以内 |
| 固有名詞禁止 | ファイル名・関数名・Issue ID・人名など含めない |
| 現象主体 | 「何をしくじったか」を抽象化（例: `spec-skipped-without-rationale`） |

- 規約違反（長すぎ / 固有名詞混入 / camelCase 等）を検出したら、**AI が修正案を提示して rewrite を要求**する。ユーザーが指定した tag をそのまま使わない
- 既存 journal に類似 tag があれば（Read で確認）、表記揺れを避けるため既存 tag への寄せを提案する

詳細は `references/journal-schema.md`。

---

## Phase 3: append（Bash + jq）

valid JSON 保証 + append-only のため、必ず Bash + jq で追記する（手書き JSON 禁止）:

```bash
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
jq -nc \
  --arg ts "$ts" \
  --arg tag "$tag" \
  --arg ph "$phenomenon" \
  '{timestamp:$ts,tag:$tag,phenomenon:$ph,context:{}}' \
  >> .claude/failure-journal/journal.jsonl
```

- `>>` で append のみ。既存行は絶対に編集・削除しない
- `phenomenon` は現象の簡潔な説明（1〜2 文）。本文や長文ログは入れない
- `context` は将来拡張用の空オブジェクト（Phase 1 では `{}` 固定）

---

## Phase 4: event publish

Event Bus 規約に従い、publisher 責務として `failure:logged` を publish する。`safe-hook.sh` を source して `event_bus_publish` API を使う:

```bash
if source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh" 2>/dev/null; then
  SAFE_HOOK_NAME="failure-journal"
  event_bus_publish "failure:logged" "$(jq -nc --arg t "$tag" '{tag:$t}')"
fi
```

- payload は **tag のみ**（本文・現象説明は含めない）
- source 直後に `SAFE_HOOK_NAME="failure-journal"` を設定してから publish する。設定しないと `event_bus_publish` が `"plugin":"unknown"` を書き込む（`safe_hook_init` は stdin を cat してハングし得るので skill 内 Bash では呼ばない）
- source に失敗しても append 自体は成功扱いとする（event は best-effort）

---

## Phase 5: 完了報告

```
✅ failure をjournal に記録しました

tag: spec-skipped-without-rationale
現象: spec.md を生成せずに実装へ進んだ
→ .claude/failure-journal/journal.jsonl に append
→ event: failure:logged (tag のみ) を publish

3 回以上再発したら /retro で還流提案が出ます。
```

再発性が No と判断して記録しなかった場合は、その旨を理由付きで報告する。

---

## 処理フロー

```
1. Phase 0: journal パス確認（無ければ作成）
2. Phase 1: 再発性判定（「同じ状況で再発しうるか」の単一基準）
3. Phase 2: tag 生成・検証（規約違反なら rewrite 要求）
4. Phase 3: append（Bash + jq、append-only）
5. Phase 4: failure:logged event publish（tag のみ）
6. Phase 5: 完了報告
```

---

## 注意事項

- **単一基準で迷わせない**: 判断軸は「再発しうるか」のみ。重大度や工数では判定しない
- **append-only**: 既存行の編集・削除は禁止。修正したい場合も新規行を追記する
- **journal は retro 実行中のみ Read**: log-failure は append が主目的で、集計のために journal 全体を読む必要はない（fingerprint の AI 出力汚染を避ける）。Phase 0/2 での既存 tag 参照は表記揺れ防止の最小限に留める
- **event payload は最小**: tag のみ。本文を含めると Event Bus 規約（最小 JSON）違反になる
- **retrospective との責務分離**: 主観的なセッション振り返りは `issue-workflow:retrospective` の責務。本スキルは機械集計可能な fingerprint の記録に専念する
