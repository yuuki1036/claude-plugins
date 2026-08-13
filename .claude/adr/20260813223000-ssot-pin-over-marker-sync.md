---
id: 20260813223000
status: accepted
phase: current
last-validated: 2026-08-13
supersedes: []
superseded-by: null
append_only: true
tags: [architecture, doc-quality, validation]
---

# ADR-20260813223000: doc → doc の伝播関係は content-hash pin で機械検証し、一致比較（マーカー区間）では扱わない

## ステータス

accepted（2026-08-13）

## コンテキスト / 背景

code-review v2.63.0 のセルフレビューが初稿の欠陥 11 件を検出し、うち **6 件が「正本を書き換えたが複製先に伝播していない」型**だった（`references/reviewer-prompts.md` が旧設計のまま / `orchestration-dynamic-rounds.md` の 4 箇所が旧注入指示のまま / `skills/review/SKILL.md` の `## meta` 説明に新フィールドが無い、ほか）。doc がそのまま実行手順になるプラグインでは doc の consumer が別の doc であり、コード変更より伝播先が見えにくい。

既存の機械検証は `check_routing_axes_sync`（`ROUTING-AXES:START/END` マーカー区間の dedent 一致比較）だけで、保護対象は spec ルーティング 3 軸の 1 ブロックのみ。リポジトリの md 全体で「正本」に言及する行は 280（うち「正本は X」の形をとる宣言は 51、`正本:` / `〜が正本` 等を含む寛容集計で 165）あるが、いずれも機械検証されていない。

検討した 3 案:

1. **マーカー区間の汎用化** — routing-axes を N ブロックに拡張し byte-identical 比較する
2. **git co-change 検証** — 散文の「正本は X」をパースし、同一コミットで正本が変わったのに消費サイトが変わっていなければ pre-commit でブロック
3. **content-hash pin** — 消費サイトに `<!-- SSOT: <path>#<anchor> @<hash8> -->` を置き、正本の該当節のハッシュと突合する

## 決定

**3（content-hash pin）を採る。** 検証の意味論は「内容の一致」ではなく **「正本が変わったら消費サイトを確認して pin を打ち直す」という手順の強制**とする。

- 宣言: `<!-- SSOT: <repo ルート相対の md パス>#<見出し前方一致 anchor> @<hash8> -->`。anchor 省略でファイル全体
- 検証: `validate_plugin_quality.py` の `check_ssot_pins`（errors 扱い。pre-commit と CI の両方で掛かる）
- 打ち直し: `--update-ssot-pins`（**明示操作**。pre-commit では走らせない）
- 初期スコープは code-review のみ（15 pin）。効果を 1〜2 版で測ってから他プラグインへ広げる

## 検討した代替案

- **1（マーカー汎用化）**: 今回の 6 件は**どれも byte-identical 複製ではなく言い換え・要約**であり、一致比較では **1 件もカバーできない**。routing-axes のように「同一テキストであること自体が仕様」の関係は引き続き既存の仕組みで扱う（両者は併存する）
- **2（git co-change）**: 新規記入コストが 0 という利点はあるが、**コミットを分けると素通り**し、「消費サイトを触ったが別の箇所だった」も pass する。一度素通りした伝播漏れを後から再検出できない（状態を持たないため）

## 影響 (Consequences)

- **良い影響**: git 履歴に依存しないので、後から気づいても・CI でも・他マシンからでも検出できる。節単位なので正本の無関係な節を編集しても発火しない（実測で確認）。pin の一覧が消費サイト冒頭に集まるため、対応表そのものが doc として読める
- **悪い影響**: 消費サイトへの記入コストが要る。正本の節を編集するたびに「確認して打ち直す」1 手間が入る（これは意図した摩擦だが、無関係な編集でも掛かる）
- **トレードオフ**: `--update-ssot-pins` は確認の自己申告であり、中身を見ずに打ち直せば骨抜きになる。それでも「消費サイトのファイルを開かせる」強制力は残るため、pre-commit での自動更新だけは行わない
- **既知の制約**: **正本・消費サイトとも md のみ対応**。`scripts/lib/review-paths.sh` のような**スクリプトを正本とする関係は現状カバーしない**（全ファイルハッシュでは無関係な編集で発火しすぎるため、関数単位の切り出しが要る）。消費サイト側は `_iter_ssot_pins` が `rglob("*.md")` しか走査しないため、**非 md に pin を書くと警告なく無効化される**
- **既知の制約**: 節の区切りは**見出しレベル**で決まり anchor の番号階層では決まらないため、**`#8` は同レベルの `## 8.5` を含まない**。`8.5` を保護するには別 pin を打つ

## 適用方法 (Enforcement)

- **機械強制される**: `validate_plugin_quality.py` の `check_ssot_pins` が errors 扱いで pin と正本ハッシュを突合する。`.githooks/pre-commit` と `.github/workflows/validate.yml` の両方で走るため、ずれたままコミットできない
- **機械強制されない（人手に残る）**: **pin を打つこと自体**。新しい複製関係が生まれたときに宣言を追加するのは人間の判断で、宣言し忘れた関係は保護されない。`--update-ssot-pins` も「確認した」という自己申告であり、中身を見ずに打ち直せば骨抜きになる（だから pre-commit では自動実行しない）

## 関連

- 運用ルール: `CLAUDE.md` の Gotchas「正本 → 消費サイトの伝播漏れ（SSoT pin）」
- 併存する別機構（byte-identical 区間比較）の設計判断: `.claude/designs/20260708-spec-routing-ssot.md`
- 契機: code-review v2.63.0（GitHub issue #124）のセルフレビューで検出した欠陥 11 件の内訳（`code-review/CHANGELOG.md`）
