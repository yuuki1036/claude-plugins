#### snap モード

スクリーンショット一括収集。**デフォルトは desktop 1 枚のみ**。複数 viewport が必要な PR タイプの場合のみ opt-in する。

**デフォルト viewport:** desktop 1440×900 のみ（1 枚）

**opt-in 引数:**

| 引数 | 撮影対象 |
|------|---------|
| なし（デフォルト） | desktop のみ |
| `--viewports=mobile,desktop` | 指定した viewport |
| `--viewports=mobile,tablet,desktop` | 3 viewport 全部 |
| `--viewports=light,dark` | テーマ切り替え（下の「テーマ撮影」参照） |

**プリセット viewport サイズ:**
- mobile: 375×812（iPhone 13 相当）
- tablet: 768×1024
- desktop: 1440×900

##### PR タイプ別ガイドライン

`pr-creator` / `git-commit-helper` から呼ばれた時、PR の性質に応じて以下を目安に viewport を選択する。撮影目的は「証跡」「レビュー補助」「レスポンシブ検証」のいずれかに分類できる。

| PR タイプ | 推奨枚数 | viewport |
|-----------|---------|---------|
| 検証 PR (probe / spike / stage1 / compat) | 0–1 | desktop のみ、または省略 |
| リファクタ（UI 変更なし） | 0 | — |
| UI 新機能 | 1–3 | desktop + 必要なら mobile |
| レイアウト / レスポンシブ変更 | 2–3 | desktop + mobile (+ tablet if breakpoint) |
| Theme / Token 変更 | 2 | light + dark |
| バグ修正（UI レンダリング） | 1–2 | 修正対象の viewport |

PR タイプ判定はブランチ名・コミットメッセージ・差分から推定する。判別不能な場合はユーザーに確認。

##### 手順
1. 出力ディレクトリ作成: `.claude/screenshots/snap-{timestamp}/`
2. 引数で指定された viewport（無ければ desktop のみ）について `resize_page` → `take_screenshot` → 保存
3. ユーザーが特定の state (hover, focus, open-modal等) を指定した場合、`hover` / `click` 後に追加撮影
4. 最後に保存済みファイル一覧を報告

##### テーマ撮影

`--viewports=light,dark` 指定時は viewport を desktop 固定にし、テーマを切り替えて 2 枚撮影する。

既定は `emulate` による `prefers-color-scheme` のエミュレート（プロジェクト非依存で決定的）:

```
mcp__plugin_dev-workflow_chrome-devtools__emulate(pageId: 1, colorScheme: "light")  # → light.png
mcp__plugin_dev-workflow_chrome-devtools__emulate(pageId: 1, colorScheme: "dark")   # → dark.png
mcp__plugin_dev-workflow_chrome-devtools__emulate(pageId: 1, colorScheme: "auto")   # 撮影後に解除
```

アプリが `prefers-color-scheme` ではなく自前のトグル（class / localStorage 等）でテーマを持つ場合は emulate が効かないため、その場合のみ UI 上のトグル操作に切り替える（どちらを使うかをユーザーに確認する）。
