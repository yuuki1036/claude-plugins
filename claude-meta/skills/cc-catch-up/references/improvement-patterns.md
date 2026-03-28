# 改善パターン集: 機能 → プラグイン改善デシジョンツリー

CC Catch-Up の Phase 4（Gap 分析）で使用するデシジョンツリーと具体的な before/after パターン。

---

## デシジョンツリー

各プラグインコンポーネントに対して、以下の判定を順に適用する。

### DT-1: Hook 改善

```
プラグインに hooks/hooks.json がある？
├─ Yes → DT-1a: 既存フック改善
│   ├─ PreToolUse/PostToolUse がある？
│   │   ├─ `if` 条件なし → [適用推奨] if 条件で発火を絞り込み（スクリプト簡素化）
│   │   └─ スクリプトで入力チェックしている → [検討] updatedInput で入力書き換えが有効か？
│   ├─ SessionStart で依存チェックしている？
│   │   └─ `once: true` 未使用 → [適用推奨] once: true で1回だけ実行
│   ├─ Stop フックがある？
│   │   └─ ブロック不要な処理？ → [検討] async: true で非同期化
│   └─ PostCompact 未使用？
│       └─ コンテキストにルール/状態を注入している？ → [適用推奨] PostCompact で再注入
├─ No → DT-1b: 新規フック追加の検討
│   ├─ 外部依存がある？ → [検討] SessionStart で依存チェック
│   ├─ 設定ファイルを監視したい？ → [検討] FileChanged フック
│   ├─ セッション変数を保持したい？ → [検討] CLAUDE_ENV_FILE 活用
│   └─ タスク管理機能がある？ → [検討] TaskCreated/TaskCompleted フック
```

### DT-2: Agent 改善

```
プラグインに agents/ がある？
├─ Yes → 各エージェントについて:
│   ├─ maxTurns 未設定？ → [適用推奨] 暴走防止の安全弁追加
│   ├─ disallowedTools 未設定？
│   │   └─ 不要なツール（Write, Edit 等）がある？ → [検討] 明示的ブロック
│   ├─ effort 未設定？ → [適用推奨] タスク複雑度に応じた effort 設定
│   ├─ memory フィールド未使用？
│   │   └─ セッション間で学習すべき？ → [検討] memory スコープ設定
│   ├─ 外部 API を使う？
│   │   └─ mcpServers 未設定？ → [検討] エージェント固有 MCP 定義
│   └─ 他スキルに依存？ → [検討] skills フィールドでプリロード
├─ No → スキル内で Agent ツールを使っている？
│   └─ Yes → 複数スキルから呼ばれる？ → [検討] agents/ ディレクトリに抽出して再利用性向上
```

### DT-3: Skill 改善

```
プラグインに skills/ がある？
└─ Yes → 各スキルについて:
    ├─ effort 未設定？ → [適用推奨] 複雑度に応じた effort 設定
    ├─ paths 未設定？
    │   └─ 特定ファイルタイプに関連？ → [検討] paths で自動アクティベーション
    ├─ references/ で ${CLAUDE_PLUGIN_ROOT} 使用？
    │   └─ ${CLAUDE_SKILL_DIR} の方が適切？ → [検討] 変数の最適化
    ├─ 重い処理でメインコンテキストを消費？
    │   └─ context: fork 未使用？ → [検討] フォーク実行でコンテキスト保護
    └─ スキル実行中のみ有効なフックが欲しい？
        └─ hooks フィールド未使用？ → [検討] スキルスコープドフック
```

### DT-4: Manifest 改善

```
plugin.json を確認:
├─ userConfig 未使用？
│   └─ ユーザーがカスタマイズしたい設定がある？ → [検討] userConfig 追加
├─ agents フィールド未記載？
│   └─ agents/ ディレクトリがある？ → [適用推奨] agents フィールドに記載
├─ channels 未使用？
│   └─ リアルタイム通知が有効？ → [検討] channels 追加
└─ ${CLAUDE_PLUGIN_DATA} 未活用？
    └─ 永続データ保存が必要？ → [検討] PLUGIN_DATA でキャッシュ/状態管理
```

---

## Before/After パターン

### P-1: `if` 条件によるフック簡素化

**Before** (スクリプトでツール名を判定):
```json
{
  "hooks": {
    "PreToolUse": [{
      "type": "command",
      "command": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/check-push.sh"
    }]
  }
}
```
```bash
# check-push.sh
cat > /dev/null
TOOL_NAME=$(echo "$CLAUDE_TOOL_USE_TOOL_NAME" | tr -d '\n')
if [[ "$TOOL_NAME" != "Bash" ]]; then exit 0; fi
INPUT="$CLAUDE_TOOL_USE_INPUT"
if echo "$INPUT" | grep -q "git push"; then
  echo "..."
fi
```

**After** (if 条件で直接絞り込み):
```json
{
  "hooks": {
    "PreToolUse": [{
      "type": "command",
      "command": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/check-push.sh",
      "if": "Bash(git push*)"
    }]
  }
}
```
```bash
# check-push.sh（簡素化）
cat > /dev/null
echo "⚠️ push 前にセルフレビューを推奨"
```

### P-2: `once: true` で依存チェックを1回限定

**Before**:
```json
{
  "hooks": {
    "SessionStart": [{
      "type": "command",
      "command": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/check-deps.sh"
    }]
  }
}
```

**After**:
```json
{
  "hooks": {
    "SessionStart": [{
      "type": "command",
      "command": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/check-deps.sh",
      "once": true
    }]
  }
}
```

### P-3: `async: true` でノンブロッキング化

**Before** (Stop フックがセッション終了をブロック):
```json
{
  "hooks": {
    "Stop": [{
      "type": "command",
      "command": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session-review.sh"
    }]
  }
}
```

**After**:
```json
{
  "hooks": {
    "Stop": [{
      "type": "command",
      "command": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session-review.sh",
      "async": true
    }]
  }
}
```

### P-4: Agent `maxTurns` 追加

**Before**:
```yaml
---
name: doc-resolver
description: ドキュメント解決エージェント
model: opus
effort: high
tools: Read, Glob, Grep
---
```

**After**:
```yaml
---
name: doc-resolver
description: ドキュメント解決エージェント
model: opus
effort: high
maxTurns: 15
tools: Read, Glob, Grep
---
```

### P-5: `${CLAUDE_SKILL_DIR}` でパス参照最適化

**Before**:
```markdown
Read `${CLAUDE_PLUGIN_ROOT}/skills/my-skill/references/guide.md`
```

**After**:
```markdown
Read `${CLAUDE_SKILL_DIR}/references/guide.md`
```

### P-6: `userConfig` でユーザーカスタマイズ

**Before** (ハードコードされた設定):
```markdown
## 設定
コミットメッセージは日本語で記述する。
```

**After** (plugin.json):
```json
{
  "userConfig": {
    "commit_language": {
      "description": "コミットメッセージの言語 (ja/en)",
      "required": false,
      "default": "ja"
    }
  }
}
```
```markdown
## 設定
コミットメッセージは ${user_config.commit_language} で記述する。
```

### P-7: `${CLAUDE_PLUGIN_DATA}` で永続データ

**Before** (auto memory に依存):
```markdown
Write instinct data to `~/.claude/projects/.../memory/instincts.md`
```

**After**:
```markdown
Write instinct data to `${CLAUDE_PLUGIN_DATA}/instincts.json`
```

### P-8: `paths` で自動アクティベーション

**Before** (description のトリガーフレーズのみ):
```yaml
---
name: review
description: コードレビュースキル。トリガー: 「レビュー」
---
```

**After**:
```yaml
---
name: review
description: コードレビュースキル。トリガー: 「レビュー」
paths:
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.py"
---
```

### P-9: `context: fork` でコンテキスト保護

**Before** (重いスキルがメインコンテキストを消費):
```yaml
---
name: session-start
description: セッション開始スキル
effort: high
allowed-tools: Agent, Read, Glob, Grep, ...
---
```

**After**:
```yaml
---
name: session-start
description: セッション開始スキル
effort: high
context: fork
allowed-tools: Agent, Read, Glob, Grep, ...
---
```

### P-10: `FileChanged` で設定ファイル監視

**Before** (変更検知なし):
```json
{
  "hooks": {
    "SessionStart": [{ "type": "command", "command": "..." }]
  }
}
```

**After** (設定変更をリアルタイム検知):
```json
{
  "hooks": {
    "SessionStart": [{ "type": "command", "command": "..." }],
    "FileChanged": [{
      "type": "command",
      "command": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/on-config-change.sh",
      "matcher": ".claude/session-context.md"
    }]
  }
}
```

---

## 優先度判定ガイド

| 優先度 | 基準 | 例 |
|-------|------|-----|
| **High** | 安全性向上 or UX の明確な改善 | maxTurns（暴走防止）、if条件（不要発火の排除）、once（重複実行防止） |
| **Medium** | 機能強化 or 開発効率向上 | userConfig、PLUGIN_DATA、CLAUDE_SKILL_DIR |
| **Low** | 最適化 or 将来対応 | paths、context:fork、async、channels |
