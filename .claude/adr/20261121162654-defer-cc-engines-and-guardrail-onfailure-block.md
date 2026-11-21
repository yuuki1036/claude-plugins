---
id: 20261121162654
status: accepted
phase: current
last-validated: 2026-11-21
supersedes: []
superseded-by: null
append_only: true
tags: [cc-catch-up, harness-keeper, guardrail-protect, plugin-manifest, hooks]
---

# ADR-20261121162654: `engines["claude-code"]` と guardrail-protect の `onFailure: "block"` は今は使わない

## ステータス

accepted（2026-11-21）

## コンテキスト / 背景

2026-11-20 のキャッチアップ（CC 2.1.164〜2.1.328）で、プラグインに使えそうな機能として次の 2 つを検討した（#488）。

- `plugin.json` の `engines["claude-code"]`（CC 2.1.323）: 対応する CC の版の範囲を宣言し、範囲外のクライアントでは install / update / load しない
- hook の `onFailure: "block"`（command / http は CC 2.1.295、mcp_tool は 2.1.328）: hook が起動できない・timeout・exit 0 と 2 以外の終了コードのとき、action を通さずに止める（公式 docs の hooks「Exit code output」）

cc-catch-up の機能カタログ（`harness-keeper/skills/cc-catch-up/references/plugin-features.md`）はプラグインに同梱して配布するので、この repo だけの判断を置くと、他の repo で回したキャッチアップの提案まで抑えてしまう。そのため判断はこの ADR に残し、カタログには、どの repo にも当てはまる事実だけを書く。

## 決定

1. **`engines["claude-code"]` は今は使わない**。効くのは CC 2.1.323 以降のクライアントだけなので、それより低い下限（mods の要件 2.1.287 など）を書いても、今は何も変わらない
2. **guardrail-protect の PreToolUse に `onFailure: "block"` を付けない**。safe-hook は ERR trap で拾える内部エラーを exit 0 に倒すが、`set -u` の未定義変数は trap を通らずに exit 1 で終わる（`.claude-plugin/lib/safe-hook.sh:40` の `set -euo pipefail` / CLAUDE.md Gotchas / #138）。block を付けると、起動の失敗・timeout・未定義変数での異常終了のどれでも、guard の対象になる全ツール呼び出しが止まる。プラグインの更新で古い版のキャッシュが消えたときに、全 Bash が止まる恐れもある（未確認）

## 影響 (Consequences)

- guardrail-protect の hook が異常終了すると、今までどおり guard は黙って素通しになる（non-blocking error）。止める側に倒さない代わりに、この経路は残る
- 版の下限を manifest で宣言しないので、古い CC で新しい機能に依存したプラグインを読み込む余地は残る（今は該当なし）

## 適用方法 (Enforcement)

- cc-catch-up の Gap 分析（Phase 4）は、作業 repo の ADR と state file の `skippedFeatures` に載った見送りを照合し、下の「見直す条件」が満たされたかだけを判定する（`harness-keeper/skills/cc-catch-up/SKILL.md` の Phase 4）
- 機械的な強制は無い。`plugin.schema.json` が `additionalProperties: false` なので、`engines` を書くとスキーマ検証で止まる（使うと決めたら、スキーマにも足す）

## 検討した代替案

- **カタログに「見送った判断」の節を置く**: 却下。カタログは配布物なので、他の repo の提案まで抑えてしまう（#488 のセルフレビューで指摘）
- **state file の `skippedFeatures` と `notes` だけに残す**: 却下。state file は commit しないので、m1 と m2 で共有できない。また ID だけでは見直す条件を残せない

## 見直す条件

- `engines["claude-code"]`: CC 2.1.323 より新しい機能に依存するプラグインが出たとき
- `onFailure: "block"`: 起動の失敗と未定義変数での異常終了の両方で止まる影響を確かめ、guard が黙って素通しになる経路を塞ぐ価値の方が上回ると判断したとき

## 関連

- #488（cc-catch-up の機能カタログの更新）
- `harness-keeper/skills/cc-catch-up/references/plugin-features.md`（1.3 の `onFailure` の行・5 の `engines` の行）
