---
id: 20260831120000
status: accepted
phase: current
last-validated: 2026-08-31
supersedes: []
superseded-by: null
append_only: true
tags: [architecture, dev-workflow, ui-verify, mcp, dependency]
---

# ADR-20260831120000: ui-verify のブラウザ基盤は chrome-devtools MCP を維持する（Claude in Chrome / 内蔵 Browser pane を却下）

## ステータス

accepted（2026-08-31）

## コンテキスト / 背景

`dev-workflow:ui-verify` は v1.5.0 以来 chrome-devtools MCP を採用しているが、**採用を正当化する ADR / design doc は 1 件も無く**、既定が無記録のまま既成事実化していた。「Claude in Chrome の方が有用ではないか」という問いが出た時点で、比較の記録が無いため毎回ゼロから議論することになる。

現行の痛みは実在する:

- 同梱 MCP は `npx chrome-devtools-mcp@latest` で起動するため **node/npx が前提**。実際に npx を持たない機体で `plugin:dev-workflow:chrome-devtools (ENOENT)` として起動に失敗した
- `chrome-devtools-cheatsheet.md` は 279 行中 114 行（41%）が「認証突破ガイド」で、専用コミットで追加された。原因は「専用プロファイルの Chrome を新規起動するので普段のログイン状態を引き継がない」こと
- MCP 配管由来の不具合が CHANGELOG 上 3 ラウンド（tool 名が実名と不一致で 34 箇所修正 / `check_mcp` が同梱 `.mcp.json` を検知できず常時 WARN / user スコープ MCP を検知できず誤警告）

候補は 3 つある: chrome-devtools MCP（現行）/ Claude in Chrome（実 Chrome 拡張）/ 内蔵 Browser pane（`mcp__Claude_Browser__*`）。

## 決定

**chrome-devtools MCP を維持する。** 単一基盤を保ち、ハイブリッド構成も採らない。

## 理由

### 決定要因: fullPage スクリーンショットを任意パスへ保存できるのは chrome-devtools だけ

`snap` モードは `.claude/screenshots/{timestamp}/*.png` に保存し、`upload-screenshots.sh` が `cc-screenshots` ブランチへ上げて PR 本文に埋める。この鎖の起点が「パス指定でのファイル保存」なので、そこが欠けると PR 添付まで丸ごと死ぬ。

実体（`chrome-devtools-mcp` v1.7.0 の `build/src/tools/screenshot.js`）で確認:

- chrome-devtools: `filePath`（絶対パス or CWD 相対）+ `fullPage` の両方を持つ
- Claude in Chrome: `computer` は `save_to_disk: boolean` のみ。**パス指定引数が無く、fullPage 相当も無い**
- 内蔵 Browser pane: `computer` に `save_to_disk` も `filePath` も無い（**保存口が存在しない**）

ページ内 JS で自分の描画ピクセルは取れないため、Bash 側で回収する迂回も成立しない。

### Claude in Chrome は「プラグインが配布できない」

能力以前に配布の問題で落ちる。Claude in Chrome は**同梱プラグインとして配布できる MCP サーバーではない**（ホスト連携の `mcp__claude-in-chrome__*` ツールは実在するが、プラグインの `.mcp.json` から配布できる形では存在しない）:

- `~/.claude.json` の `mcpServers` に定義が無く、文字列 `claude-in-chrome` の出現も 0 回。ホスト側の専用キー（`cachedChromeExtensionInstalled` 等）で管理される
- tool 名に plugin 名前空間が無い（`mcp__claude-in-chrome__*`）。同梱 MCP なら `mcp__plugin_<plugin>_<server>__*` に展開される
- したがって `.mcp.json` で同梱配布できない
- `_requirements` の type enum は `mcp_server | cli_tool | plugin` の 3 つで `additionalProperties: false`。**ホスト組み込み機能を宣言する型が無い**。`mcp_server` として書くと `check_mcp` が到達できず**恒常 WARN** になり、「WARN が出たときだけ行動する」契約を壊す

さらに `resize_window` は description が「Resize the current browser window」と明記するとおり実ブラウザのウィンドウ自体をリサイズする（chrome-devtools / 内蔵 pane の `resize_page` / `resize_window` が viewport エミュレートなのと異なる）。Claude in Chrome はユーザーの実 Chrome を操作するため、`snap --viewports=` の 3 回や `tune` のループでユーザーの作業ウィンドウを奪う。

そして**取りたかった能力（認証フローを跨ぐ E2E）は既にスコープ外**で、`ui-verify/SKILL.md` の「E2E への昇格」節が `webapp-testing` へ委譲済み。取りたい能力がスコープ外・払うコストがスコープ内、という配置になっている。

### 内蔵 Browser pane は魅力的だが同じ 1 点で詰む

ゼロインストール（node も拡張も不要）、`resize_window` の `colorScheme` によるテーマ切り替え、`preview_start` / `preview_logs` による dev server の起動とサーバ側ビルドエラーの取得は、いずれも現行に無い利点。だが保存口が無いため `snap` の契約を満たせない。

### ハイブリッドも却下

「verify は pane、snap は chrome-devtools」は技術的には成立する（`pr-creator` の glob は `{snap,commit}-*` だけで `verify-*` を拾っていない）。しかし snap のために `.mcp.json` + node が残る以上、**pane 唯一の売りであるゼロインストールが消える**。残る利得は `preview_logs` だけで、tool 名・引数形・cheatsheet を 2 系統抱える対価にならない。加えて `validate_plugin_quality.py` に **MCP tool 名の実在検証が無い**（誤った名前は errors 0 で通る）ため 2 本目は静かに腐る。tool 名ドリフトが 34 箇所・3 ヶ月放置された実績がある。

### 認証の痛みは現行側で受けられる

`--autoConnect`（Chrome 144+）が v1.7.0 に実在し、`conflicts: ['isolated','executablePath']`。**パスを一切含まない**ので `${CLAUDE_PLUGIN_ROOT}` によるポータビリティ規約と衝突せず、同梱 `.mcp.json` に書ける。ただし繋ぐ先はユーザーの実プロファイルで Claude in Chrome と同じ privacy posture になり、`snap` の出力は public な raw URL になる経路を持つため、**既定にはせず cheatsheet の opt-in 手順に留める**。

## 影響

- 基盤は据え置き。ただし本 ADR と同時に、比較の過程で発見した破損を修理する（依存チェックの恒真・`wait_for` の誤用・`headless` 既定の誤記・`emulate` の allowed-tools 欠落）
- `_requirements` / `check-deps.sh` / `.mcp.json` の構成は変えない

## 却下した代替案

| 案 | 却下理由 |
|---|---|
| Claude in Chrome へ移行 | MCP サーバーとして存在せず配布・宣言・検出のいずれも不可。保存先も指定できない |
| 内蔵 Browser pane へ全面移行 | `computer` に保存口が無く snap → PR 添付が死ぬ |
| ハイブリッド（verify=pane / snap=cdt） | node 依存が残りゼロインストールの利点が消える。2 系統の tool 名が静かに腐る |
| `--autoConnect` を同梱既定にする | ユーザーの実プロファイルに繋ぐ。opt-in 手順としてのみ記載 |
| `--slim` でツール数を削る | 3 tool しか残らず `take_snapshot` / `click` / `fill` が消え、slim の screenshot は `filePath` を持たない |

## 再評価のトリガー

**`mcp__Claude_Browser__computer` に保存先パス指定が入った時。** その時点で「ゼロインストール + `colorScheme` + `preview_logs`」が snap の契約と両立し、**単一基盤のまま**乗り換えられる。多基盤にする理由はその場合も生じない。

## 未確認事項

- `@latest` が現在解決する版（npx 不在の機体では確認できない。npm キャッシュに 1.2.0 と 1.7.0 が同居しており、版ピンは別途検討）
- Claude in Chrome の `save_to_disk: true` の実保存先（description が無く、接続 0 で実測不能）
- 内蔵 pane が全ユーザー・全 CC 版で常在するか
