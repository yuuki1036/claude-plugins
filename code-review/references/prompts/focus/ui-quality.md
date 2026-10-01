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

検出対象（UI 文言の変更で落ちた情報 / GitHub issue #272）:
- diff で UI の文言（ツールチップ・エラー・案内・ラベル・確認ダイアログ・翻訳ファイルの値）が書き換わったとき、`-` の旧文言と `+` の新文言を並べ、**旧文言にあって新文言から消えた情報**を列挙する（誰が・どの操作で・何が対象か・何が起きるか・どうすれば直るか）
- 残った文の**指示語・相対語**（上位・下位・この・その・それ・配下・前の・該当の等）が、その文だけで指す先が決まるかを確かめる。消えた文が指す先を決めていた場合、意味が曖昧になるか反転していないか
- 指摘するのは、消えた情報が**読み手の判断に要る**場合だけ。規約（文の数・長さ・型）に合わせた短縮そのものは正しい作業なので指摘しない。根拠に旧文言（`-` 行）を引用する

検出対象（モダン Web / Baseline — 詳細と confidence は modern-web-checklist.md を参照）:
- 自前実装 → ネイティブ API への置き換え余地（自前モーダル → `<dialog>`、自前ツールチップ → Popover API + Anchor Positioning、自前 JS アニメ → View Transitions、viewport メディアクエリ → Container queries 等）
- **Baseline ゲート違反**（Limited availability の CSS/JS 機能をフォールバックなしで本番経路に導入）= ブラウザ互換が壊れる事実指摘
- 不要になった polyfill / レガシー回避（対象 API が Baseline widely available 化済み）

判定基準:
- 明確な WCAG 違反（alt 欠落、フォームラベル不足など）: confidence >= 85
- セマンティック HTML 違反: confidence 70-85
- デザイン的な改善提案（タップ領域、状態フィードバック等）: confidence 60-75
- 文言の短縮で意味が反転・曖昧化した（旧文言を引用して、読み手が逆に取る読み方を示せる）: confidence 75-90
- **Baseline ゲート違反（互換が壊れる事実）: confidence 75-90 / MAJOR**
- ネイティブ API 化の任意改善（自前実装 → 標準 API）: `Optional:` prefix・confidence ≤ 60（modern-web-checklist.md のマッピング表に従う。動くコードを「モダンでない」だけで書き換えさせない）

新たに導入された UI 部分のみ報告。既存コードの UI 課題は対象外。a11y 検出とモダン Web 検出で同一箇所を二重指摘しない（棲み分けは modern-web-checklist.md「ui-quality との棲み分け」を参照）。

**severity 目安**:
- CRITICAL: アクセシビリティが完全に壊れる（キーボード操作不能、スクリーンリーダー未対応で機能不全）
- MAJOR: WCAG 違反、セマンティック HTML 違反、フォーカス管理欠落、Baseline ゲート違反（Limited 機能のフォールバックなし本番投入）、文言の短縮で意味が事実と逆に読める（読み手が誤った操作をする）
- MINOR: タップ領域・状態フィードバック等のデザイン改善提案、ネイティブ API 化の任意改善（`Optional:`）、文言から判断に要る情報が落ちて曖昧になった（逆には読めない）
```

