### specialist-input-validation（信頼境界）

```
## 観点: 信頼境界（入力バリデーション）専門レビュー

triage で検出された red-flag パターン（JSON.parse(req.*) / parseInt(req.*) / RegExp(user_input) / 外部入力の直接利用）について、以下を厳密にチェックする:

1. **信頼境界の特定**: HTTP / CLI / メッセージキュー / ファイル読み込み等、信頼境界を越える地点を特定
2. **バリデーションの存在**: スキーマ（zod / joi / pydantic / json-schema）等で検証されているか
3. **型変換の安全性**: parseInt の NaN 取り扱い、JSON.parse の例外処理、Number(undefined) → NaN 等
4. **ReDoS リスク**: 動的に組み立てた正規表現 / ネストした量指定子（`(a+)+` 等）
5. **プロトタイプ汚染**: `Object.assign(obj, JSON.parse(input))` 等の危険なマージ

severity 目安:
- BLOCKER: パース失敗で認証バイパス、ReDoS で DoS 確実、プロトタイプ汚染で権限昇格
- CRITICAL: 検証なしで型不一致 → クラッシュ、NaN を ID として使用
- MAJOR: 検証あるが甘い、例外処理が雑
- MINOR: 命名・スタイル改善
```

