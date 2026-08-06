### ui-quality（UI 品質・アクセシビリティ分析）

UI / フロントエンド変更を検出した場合に起動する。

```
## 観点: UI 品質・アクセシビリティ分析

a11y / セマンティック HTML を検証し、加えて `${CLAUDE_PLUGIN_ROOT}/references/modern-web-checklist.md`（Chrome Modern Web Guidance を Baseline ベースで照合可能にした同梱チェックリスト）に準拠してモダン Web 観点も検証する。

検出対象（アクセシビリティ・セマンティクス）:
- アクセシビリティ違反（aria 属性の不足・誤用、alt 属性の欠落、コントラスト比、不適切な tabindex）
- セマンティック HTML 違反（button が必要な箇所での div onClick、見出しレベルのスキップ等）
- フォーカス管理（モーダル/ドロワーのフォーカストラップ・初期フォーカス）
- キーボード操作対応の欠落（onClick のみで onKeyDown 無し等）
- 状態フィードバック（loading / error / empty state）の欠落
- インタラクティブ要素の最低タップ領域（モバイル 44x44 px 相当）
- レスポンシブ崩れ・固定 px サイズの濫用
- 色のみに依存した情報伝達（色覚多様性配慮）

検出対象（モダン Web / Baseline — 詳細と confidence は modern-web-checklist.md を参照）:
- 自前実装 → ネイティブ API への置き換え余地（自前モーダル → `<dialog>`、自前ツールチップ → Popover API + Anchor Positioning、自前 JS アニメ → View Transitions、viewport メディアクエリ → Container queries 等）
- **Baseline ゲート違反**（Limited availability の CSS/JS 機能をフォールバックなしで本番経路に導入）= ブラウザ互換が壊れる事実指摘
- 不要になった polyfill / レガシー回避（対象 API が Baseline widely available 化済み）

判定基準:
- 明確な WCAG 違反（alt 欠落、フォームラベル不足など）: confidence >= 85
- セマンティック HTML 違反: confidence 70-85
- デザイン的な改善提案（タップ領域、状態フィードバック等）: confidence 60-75
- **Baseline ゲート違反（互換が壊れる事実）: confidence 75-90 / MAJOR**
- ネイティブ API 化の任意改善（自前実装 → 標準 API）: `Optional:` prefix・confidence ≤ 60（modern-web-checklist.md のマッピング表に従う。動くコードを「モダンでない」だけで書き換えさせない）

新たに導入された UI 部分のみ報告。既存コードの UI 課題は対象外。a11y 検出とモダン Web 検出で同一箇所を二重指摘しない（棲み分けは modern-web-checklist.md「ui-quality との棲み分け」を参照）。

**severity 目安**:
- CRITICAL: アクセシビリティが完全に壊れる（キーボード操作不能、スクリーンリーダー未対応で機能不全）
- MAJOR: WCAG 違反、セマンティック HTML 違反、フォーカス管理欠落、Baseline ゲート違反（Limited 機能のフォールバックなし本番投入）
- MINOR: タップ領域・状態フィードバック等のデザイン改善提案、ネイティブ API 化の任意改善（`Optional:`）
```

