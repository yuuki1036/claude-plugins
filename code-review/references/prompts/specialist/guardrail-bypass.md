### specialist-guardrail-bypass（骨抜き検出）

```
## 観点: ガードレール骨抜き検出専門レビュー

triage で検出された lint / hook / static check 設定の変更について、以下を厳密にチェックする:

1. **削除・無効化**: linter rule の enable リストからの削除、pre-commit hook の空化、ESLint rule の `"off"` 化、Ruff の `select` 縮小
2. **severity 降格**: `error` → `warn`、`fail` → `pass`、`required: true` → `false`、`exit 2` → `exit 0`
3. **適用範囲縮小**: ignore パターン拡張、`paths-ignore` 追加、`exclude` リスト膨張、特定ディレクトリの除外
4. **ブロック判定反転**: hook の戻り値反転、`continue-on-error: true` 追加、test の skip 化
5. **迂回手段の追加**: `--no-verify` / `--no-gpg-sign` / `--ignore-errors` フラグ、`# noqa` / `// eslint-disable` の新規追加

判定原則:
- **追加・強化は OK** (新規 rule 追加 / severity 昇格 / 適用範囲拡大)
- **削除・無効化・縮小・反転は BLOCKER 固定**（commit body に「なぜ骨抜きが必要か」の justify が明示されていない限り）
- justify がある場合は CRITICAL に降格（人間レビューに委ねる）

severity 目安:
- BLOCKER: justify なき骨抜き変更（テストを通すために lint を緩めた疑い）
- CRITICAL: justify はあるが影響範囲が広い（ignore 拡大、複数 rule の一括無効化）
- MAJOR: コメント・ドキュメント側の弱体化（規約文書から「禁止」項目削除）
- MINOR: 純粋な構文整理（実質的な強度変更なし）

出力には必ず「設定変更前後の diff」と「弱体化された具体的 rule 名」を含めること。
```

