# 三段防御（CLAUDE.md → skill → hook）

重要規約を **規範 → 推奨手順 → 機械強制** の 3 層で重複定義することで、AI agent の忘却・違反を構造的に防ぐパターン。

## 設計原則

| 層 | 役割 | 遵守率 | 例 |
|----|------|--------|-----|
| **CLAUDE.md（規範）** | Why を明示。背景・例外運用を記述 | ~80% | 「`--no-verify` は禁止」を本文に記載 |
| **Skill（推奨手順）** | What を提示。具体的なフロー・チェックリスト | ~90% | git-commit-helper skill 内で「コミット前に `--no-verify` を使わない」と明示 |
| **Hook（機械強制）** | How を実行。決定的に検出してブロック | **100%** | PreToolUse hook で `git commit --no-verify` を `exit 2` |

3 層に重複させる理由: AI が CLAUDE.md を読み落としても skill が補い、skill を忘れても hook が止める。**冗長性が信頼性を生む**。

## 判定マトリクス（improver の自己問い）

CLAUDE.md の重要規約に対して、improver は以下を問う:

```
あなたの CLAUDE.md の重要規約について、三段防御の充足度を確認してください:

| 規約 | CLAUDE.md | Skill | Hook |
|------|-----------|-------|------|
| --no-verify 禁止 | ✓ | ? | ? |
| .env 編集禁止 | ✓ | ? | ? |
| 直接 main コミット禁止 | ✓ | ? | ? |
| ...  | | | |

欠けている層について、以下を suggest します:
- Skill: 該当の skill が存在するか、なければ作成を提案
- Hook: PreToolUse / PostToolUse hook の実装を提案
```

## 三段防御を満たすパターン例

### 例 1: `--no-verify` 禁止

**CLAUDE.md（規範）:**
```markdown
## Git 運用ルール
- `git commit --no-verify` / `git commit -n` 禁止。pre-commit hook の検証は通すこと
- 設計上どうしても hook を skip する必要がある場合は commit body で justify
```

**Skill（dev-workflow/git-commit-helper）:**
```markdown
## 厳守ルール
- `--no-verify` / `-n` フラグを使わない
- hook が失敗した場合は原因を修正してから再 commit
```

**Hook（PreToolUse on Bash(git commit *)）:**
```bash
#!/usr/bin/env bash
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "no-verify-block"

cmd=$(jq -r '.tool_input.command' <<< "$(safe_hook_input)")
# heredoc / quoted string を剥がしてから検出
stripped=$(perl -0pe "s/<<'?(\w+)'?\n.*?\n\1//gs" <<< "$cmd" \
  | perl -pe "s/'[^']*'//g; s/\"[^\"]*\"//g")
if grep -qE '(^| )(-n|--no-verify)( |$)' <<< "$stripped"; then
  echo "Refusing to bypass git hooks (--no-verify is forbidden)" >&2
  exit 2
fi
```

### 例 2: ガードレール設定の保護

- **CLAUDE.md**: 「lint/hook 設定は追加・強化は可、削除は不可」を明記
- **Skill**: code-review の specialist-guardrail-bypass を起動条件付きで配置
- **Hook**: PreToolUse on `Edit|Write` で `.golangci.yml` 等の basename を `exit 2` でブロック

## どこまで三段化するか

全規約を三段化する必要はない。三段化の優先度:

| 規約の性質 | 三段化推奨度 |
|---|---|
| 違反コストが高い（データ損失・セキュリティ・本番障害） | **必須** |
| 違反が頻発（過去 2 回以上発生） | **必須** |
| 違反検出が決定的（grep / 型検査で書ける） | **必須** |
| 違反が稀・低影響 | CLAUDE.md のみで OK |
| 文脈依存（例外が多い） | CLAUDE.md + skill（hook 化困難） |

判断基準は CLAUDE.md の "ルール配置の意思決定（決定的 hook > LLM 判定）" を参照。

## アンチパターン

- **三層が乖離**: CLAUDE.md で禁止、skill で許容、hook なし → AI が混乱
- **hook だけで規範なし**: 機械的にブロックされるが「なぜ」が伝わらず、agent が回避策を探す
- **CLAUDE.md だけで強制なし**: 遵守率 ~80% に依存、見落としが事故化
