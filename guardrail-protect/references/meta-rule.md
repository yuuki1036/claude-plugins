# メタルール: ガードレール骨抜き禁止

このプラグインが守ろうとしている本質的なルール。

## 本文

> lint / hook / static check 設定は **追加・強化は可、削除・無効化・適用範囲縮小・ブロック判定反転は不可**。
> 設計上どうしても弱体化が必要な場合は commit body で justify を明示する。

## 不可とする変更パターン

| パターン | 例 |
|----------|-----|
| ルール削除 | `.golangci.yml` の `enable:` リストから linter を drop |
| 無効化 | ESLint rule を `"off"` に変更、`disable_*: true` |
| severity 降格 | `error` → `warn`、`fail` → `pass` |
| 適用範囲縮小 | ignore pattern 拡張、`paths-ignore` 追加、`exclude` 拡大 |
| ブロック判定反転 | hook 戻り値の反転、`continue-on-error: true` の追加 |
| 迂回手段の追加 | `--no-verify` / `--no-gpg-sign` / `--ignore-errors` フラグ、`# noqa` / `// eslint-disable` の新規導入 |

## 例外運用（commit body での justify）

骨抜きが必要な場合は commit body に以下 3 要素を必須記載:

1. **なぜ既存ルールが今回の変更を阻害するか**: 具体的に。「lint が通らないから」だけでは不十分
2. **代替の検証手段**: 手動レビュー / 別 lint / テスト追加 / 静的解析の別ルート
3. **復旧予定**: 恒久的な弱体化なら ADR を別途起票。一時的なら復旧予定の commit / issue を指定

### justify の例

```
fix(eslint): disable no-explicit-any for legacy adapter

Why: legacy/* 配下は外部 SDK の型定義が不完全で、any を排除すると
adapter 自体が型として表現できない。

Verification: 該当 adapter は integration test で外部 API 応答の
スキーマ検証を行う。型エラーで防げない領域を runtime test で補う。

Recovery: 外部 SDK の型定義が v3.0 で改善予定。upstream 修正が
入り次第、再度 strict 化する（追跡 issue: #234）。
```

## なぜこのメタルールが必要か

AI agent は「テストを通すために lint rule を緩める」「hook がうるさいから --no-verify する」逃げ道を選びがち。明文化 + hook 強制の二段構えで:

- AI が骨抜き diff を生成した場合、code-review の `specialist-guardrail-bypass` で検出される
- `git commit --no-verify` は PreToolUse hook で即座にブロックされる
- 保護対象 lint 設定の編集は PreToolUse hook で即座にブロックされる
- 人間レビューでも「justify を見せて」と差し戻せる

## 関連

- 三段防御パターン: `claude-meta/skills/claude-md-improver/references/three-tier-defense.md`
- code-review の specialist-guardrail-bypass: `code-review/references/reviewer-prompts.md` §5
- CLAUDE.md のルール配置の意思決定: リポジトリルートの CLAUDE.md §「ルール配置の意思決定」
