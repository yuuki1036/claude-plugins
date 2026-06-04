# modern-web-checklist（モダン Web 観点チェックリスト）

`ui-quality` reviewer Focus が参照するローカルチェックリスト。Chrome の **Modern Web Guidance**（Baseline ベースの「自前実装より HTML/CSS ネイティブ API を優先する」推奨）を、reviewer が diff から照合できる粒度に落としたもの。

出典: https://developer.chrome.com/docs/modern-web-guidance / Baseline: https://web.dev/baseline

> このファイルは外部公式 skill `web-design-guidelines` への dangling 参照を置き換える同梱 reference。`${CLAUDE_PLUGIN_ROOT}/references/modern-web-checklist.md` として参照する（他プラグインからは参照しない＝プラグイン間依存を作らない）。

---

## 大原則

**HTML/CSS のネイティブ API > JavaScript ワークアラウンド**。同じ UX をネイティブ機能で実現できるのに自前 JS で再実装している箇所を、より標準的・保守的・アクセシブルな選択肢に寄せる。

ただし **このチェックリストの指摘は大半が「任意改善」**である。reviewer-prompts.md の評価原則「好みではなく原則」と scoring-guide の confidence クランプに必ず従う:

- 動いているコードを「モダンでない」という理由だけで書き換えさせる指摘は **`Optional:` prefix・confidence ≤ 60**。
- confidence を上げてよいのは **事実根拠があるとき**に限る:
  - **Baseline ゲート違反**（後述）= ブラウザ互換の事実 → confidence 75-90 / `MAJOR`
  - 自前実装にアクセシビリティ欠陥が伴う（フォーカストラップ漏れ等）→ それは **ui-quality の a11y 観点（reviewer-prompts.md）側で指摘**し、こちらでは重複させない。

## ui-quality（a11y）との棲み分け

| 観点 | 担当 |
|---|---|
| aria / alt / コントラスト / セマンティック HTML / フォーカス管理 / キーボード操作 | **ui-quality 本体（reviewer-prompts.md）** |
| 「自前実装 → ネイティブ API」置き換え / Baseline ゲート / modern CSS・forms | **このチェックリスト** |

a11y 違反はこのファイルでは扱わない（重複指摘の禁止）。ネイティブ API 化が「結果的に a11y も改善する」場合は、Optional 改善の補足として一言添える程度に留める。

---

## レガシー → モダン マッピング（検出 → 推奨）

| diff で検出するパターン | モダン推奨 | confidence / prefix 目安 |
|---|---|---|
| 自前モーダル（`<div role="dialog">` + 手書きフォーカストラップ / 背景クリック閉じ） | ネイティブ `<dialog>` + `::backdrop`（light-dismiss 含む） | 任意改善 `Optional:` 50-60。ただし**フォーカストラップ欠陥があれば ui-quality 側で MAJOR** |
| 自前ツールチップ / ポップオーバー / ドロップダウン（位置を JS で算出） | Popover API（`popover` 属性）+ CSS Anchor Positioning | `Optional:` 50-60 |
| 自前 JS アニメ / 手動パララックス / ページ遷移アニメ | View Transitions API / CSS entry・exit アニメ | `Optional:` 45-55 |
| コンポーネント単位の出し分けを viewport メディアクエリで実装 | Container queries | `Optional:` 50-60 |
| grid の子で列線を手動合わせ | `subgrid` | `Optional:` 45-55 |
| 入力幅を JS で動的調整 | `field-sizing: content` | `Optional:` 50-60 |
| 即時バリデーション表示を手動制御 | `:user-invalid` 擬似クラス | `Optional:` 50-60 |
| メインスレッドの long task / `setTimeout(fn, 0)` で分割 | `scheduler.yield()` | `Optional:` 55-65（INP 実測があれば↑） |
| 画像の優先度未設定 / 手動 preload の濫用 | `fetchpriority` / speculative preloading | `Optional:` 50-60 |
| 色操作・グラデーションを hex/rgb/hsl で手計算 | `oklch`（知覚均等・広色域） | **好み度高 → `Optional:` ≤ 45**（強く推さない） |
| 過剰な polyfill / core-js import | 対象 API が Baseline widely available なら polyfill 削除を検討 | Baseline 確認後 `Optional:` 55-65 |

> マッピングは「diff に新規導入された UI」のみ対象。既存コードのレガシー実装をリファクタさせる指摘は出さない（reviewer-prompts.md「新規導入部分のみ報告」原則）。

---

## Baseline ゲート（confidence を上げてよい唯一の事実根拠）

**Baseline** = コアブラウザ 4 系統（Chrome / Edge / Firefox / Safari）のサポート状況を 3 段階で表す指標。

- **Limited availability**: 一部ブラウザのみ → 本番採用はリスク
- **Newly available**: 全コアブラウザ対応になった
- **Widely available**: newly になってから **30 か月経過**（互換を気にせず使える）

### ゲート判定（双方向）

1. **新しすぎる API の採用**: diff が Baseline **Newly availability 未満**（= Limited）の CSS/JS 機能を、フォールバックなしで本番経路に導入している → ブラウザ互換が壊れる事実指摘。**confidence 75-90 / `MAJOR`**。
2. **不要になった polyfill / レガシー回避**: 採用済みの回避策が、対象 API の Baseline widely available 化で不要になっている → 削除を提案。**confidence 55-65 / `Optional:`**。

判定にあたり、プロジェクトの目標 Baseline レベルが `CLAUDE.md` / `AGENTS.md` / Browserslist に明示されていればそれに従う。明示がなければ既定で **Widely available** を保守ラインとみなす。機能の Baseline ステータスが不確実な場合は **confidence を下げる**か、`context7` / MDN で確認してから指摘する（推測で MAJOR を出さない）。

---

## severity 目安

- `MAJOR`: Baseline ゲート違反（Limited 機能をフォールバックなしで本番投入）= 実ユーザーのブラウザで壊れる
- `MINOR` / `Optional:`: ネイティブ API 化の任意改善全般
- このチェックリスト由来の指摘で `CRITICAL` / `BLOCKER` は出さない（互換が壊れる Baseline ゲート違反でも上限 `MAJOR`）
