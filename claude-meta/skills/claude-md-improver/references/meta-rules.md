# メタルール: ガードレール骨抜き禁止 + 静的検査優先

CLAUDE.md / AGENTS.md に含めると AI agent の暴走を構造的に防げるメタルール集。

## 1. ガードレール骨抜き禁止（必須セクション化）

CLAUDE.md に以下を `## ガードレール（骨抜き禁止）` セクションとして必須化する。

```markdown
## ガードレール（骨抜き禁止）

lint / hook / static check 設定は **追加・強化は可、削除・無効化・適用範囲縮小・ブロック判定反転は不可**。
設計上どうしても弱体化が必要な場合は commit body で justify を明示する。

### 不可とする変更パターン

- linter rule の enable リスト削除（例: `.golangci.yml` の `enable:` からの drop）
- pre-commit hook の空化 / skip
- severity 降格（`error` → `warn`、`fail` → `pass`）
- ignore pattern / paths-ignore の拡張
- hook 戻り値の反転 / `continue-on-error: true` の追加
- `--no-verify` / `--no-gpg-sign` / `# noqa` / `// eslint-disable` の新規導入

### 例外運用

骨抜きが必要な場合は commit body に以下 3 要素を必須記載:
1. なぜ既存ルールが今回の変更を阻害するか（具体的に）
2. 代替の検証手段（手動レビュー / 別 lint / テスト追加）
3. 復旧予定（恒久的な弱体化か、一時的か）
```

### なぜ必須化するか

AI agent は「テストを通すために lint rule を緩める」逃げ道を選びがち。明文化することで:

- reviewer agent が骨抜き diff を BLOCKER として検出できる
- hook 側 (例: `code-review` の `specialist-guardrail-bypass`) が機械的に検出できる
- 人間レビューでも「justify を見せて」と差し戻せる

## 2. 静的検査優先原則（CLAUDE.md 自己問い）

CLAUDE.md に長大な「○○禁止」リストがある場合、improver は「これは linter / ast-grep 化できないか？」を問い返す。

### 静的検査化できるパターン例

| CLAUDE.md の禁止項目 | 静的検査化手段 |
|---|---|
| `console.log を本番コードに含めない` | ESLint `no-console`, ast-grep rule |
| `any 型を使わない` | TypeScript `noImplicitAny`, `@typescript-eslint/no-explicit-any` |
| `Promise.all のループ内 await 禁止` | ESLint `@typescript-eslint/no-misused-promises` |
| `特定の関数を直接 import せず lib 経由で` | ESLint `no-restricted-imports` |
| `commit message は Conventional Commits 準拠` | commitlint + husky |
| `.env を編集禁止` | pre-commit hook + git attributes |

### 自己問いテンプレート

CLAUDE.md の「禁止」セクションを抽出した後、improver は以下を返す:

```
以下の禁止項目は静的検査化を検討してください（プロンプトより遵守率が高くなります）:

- [禁止項目1] → 候補ツール: <eslint rule | ast-grep | TS config | hook>
- [禁止項目2] → 候補ツール: <...>

CLAUDE.md には「なぜこのルールが存在するか」だけ残し、判定ロジックは静的検査側に移動することを推奨します。
```

### CLAUDE.md と静的検査の役割分担

- **CLAUDE.md**: Why（背景・意図・例外運用）
- **静的検査**: What/How（実際の判定ロジック・違反検出）

両方に同じルールを書くと乖離する。判定は 1 箇所、解説は CLAUDE.md に集約。
