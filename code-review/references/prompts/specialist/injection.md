### specialist-injection（コード/コマンドインジェクション）

```
## 観点: コード/コマンドインジェクション専門レビュー

triage で検出された red-flag パターン（eval / new Function / child_process / exec / subprocess / shell=True 等）について、以下を厳密にチェックする:

1. **入力源の追跡**: 該当箇所に渡される文字列/引数の出所を Read / Grep で追跡
   - ユーザー入力（req.body / req.query / req.params / process.argv / 環境変数）が直接または間接的に流れていないか
   - 中間変換でサニタイズ・エスケープされているか
2. **代替手段の検討**: その API を使う必然性があるか（exec → execFile + 引数配列、eval → JSON.parse 等）
3. **コンテキスト判定**: テストコード・ビルドスクリプト・開発専用 CLI なら影響度が下がる（severity 下げ可）

severity 目安:
- BLOCKER: ユーザー入力が直接または検証なしで該当 API に流れる
- CRITICAL: 入力源が内部だが将来ユーザー入力経由になり得る、または検証が脆弱
- MAJOR: 内部限定・固定値だが該当 API を使う設計上の問題
- MINOR: 該当しない（specialist が MINOR を出す状況は稀）

**重要**: 完全に断定できない場合でも BLOCKER + confidence 60-79 で報告すること。人間判断を促す。
```

