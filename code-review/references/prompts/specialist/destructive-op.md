### specialist-destructive-op（破壊的操作の意図確認）

```
## 観点: 破壊的操作の意図確認専門レビュー

triage で検出された red-flag パターン（fs.unlink / fs.rm / rmSync / DROP TABLE / TRUNCATE / WHERE 句なし DELETE/UPDATE / .drop() 等）について、以下を厳密にチェックする:

1. **意図性の確認**: コミットメッセージ・PR 説明・コメントで「削除/破壊が意図された変更」と明示されているか
2. **対象範囲の検証**: 削除対象のパス・テーブル・コレクションが固定値か、動的に決まるか
   - 動的の場合、その変数の出所を追跡（ユーザー入力経由なら BLOCKER）
3. **冪等性・ロールバック性**: 一度実行したら戻せない操作か（migration の場合 down migration の存在を確認）
4. **環境ガード**: 本番環境で実行されないようガードされているか（NODE_ENV チェック、CI 限定実行等）
5. **既存データへの影響**: NOT NULL 制約追加・カラム削除等で既存データが破壊されないか

severity 目安:
- BLOCKER: WHERE 句なしの DELETE/UPDATE、本番 DB の破壊的 migration、動的パスでの fs 削除（入力検証なし）
- CRITICAL: 環境ガードなしの破壊的操作、ロールバック不能な migration
- MAJOR: ガードはあるが脆い、down migration が不完全
- MINOR: テスト環境専用の意図的破壊（コメント明示あり）

**重要**: migration 系は特に「疑わしい」段階で BLOCKER + 低 confidence で報告すること。復旧不能な代償が大きすぎる。
```

