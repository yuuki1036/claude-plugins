---
id: 20260722164106
status: accepted
phase: current
last-validated: 2026-07-22
supersedes: []
superseded-by: null
append_only: true
tags: [architecture, plugin-design]
---

# ADR-20260722164106: 機能の対称性は別プラグインのミラーでなく同一プラグイン内の backend 分岐で表現する

## ステータス

accepted（2026-07-22）

## コンテキスト / 背景

linear-workflow / indie-workflow は同一のワークフローを 2 つのバックエンド（Linear MCP / ローカルファイル）向けに提供するため、別プラグインのミラーとして維持してきた。「プラグイン間依存禁止」の制約下でコードを共有できず、人手の対称反映 + 片方向同期スクリプト + drift 検証という 3 層の同期機構が必要になった。2026-07 の精査で、共有スキルの 52% が完全一致行の複製、linear 関連コミットの 69% が両側同時変更、そして人手反映の取りこぼし（機能の片側消失）が実際に発生していることが確認された。

## 決定

同一ワークフローの複数バックエンド対応は、プラグインを分けずに 1 プラグイン内の実行時分岐（backend 検出 + 条件付き Phase）で表現する。プラグイン間依存禁止の制約下で 2 プラグイン間に大量の複製が発生したら、それは分割単位の誤りを示すシグナルとして扱い、ミラー同期機構の増強ではなく統合を検討する。

## 影響 (Consequences)

- **良い影響**: 二重メンテの解消。ミラー対応表・同期スクリプト・drift CI・関連 Gotchas が機構ごと不要になる。機能追加が 1 箇所で完結する
- **悪い影響**: SKILL.md に backend 条件分岐が入り、単一バックエンド利用者にとって無関係な記述が混ざる。プラグインの責務が「1 プラグイン = 1 バックエンド」より広くなる
- **トレードオフ**: 「プラグインの単純さ（分岐なし）」と「保守の単純さ（複製なし）」を天秤にかけ、利用者が一人で両バックエンドを使い分ける実態から後者を採った

## 適用方法 (Enforcement)

機械強制は部分的に可能:

- ミラー規約の撤去自体が enforcement になる（validate_plugin_quality.py の MIRROR_SKILL_PAIRS / MIRROR_INTENTIONAL_*_ONLY、sync-linear-from-indie.sh、CI drift check を削除。「同期を検証する対象」を構造から消す）
- 将来の再発検知: 新規プラグイン追加時に既存プラグインとのスキル名・本文の高一致（例: 完全一致行 30% 超）を validate_plugin_quality.py で warning 化することは可能だが、誤検知リスクがあるため必要が顕在化するまで導入しない
- 残りは CLAUDE.md のプラグイン開発ルールへの記載（本 ADR への参照）で担保する

## 検討した代替案

- **完全片方向生成（linear を indie からの sed 生成物にする）**: 編集の二重化は解消するが、生成インフラ（SHARED/TRANSFORM 全域化）の保守が残り、sed で表現しきれない意味分岐が破綻点になるため不採用
- **共通 lib プラグイン化**: プラグイン間依存禁止の規約に正面から抵触するため不採用
- **現状維持（人手対称反映の徹底）**: 取りこぼしが既に実発生しており、規約と検証の増強では防げないことが実証済みのため不採用

## 関連

- 関連 ADR: なし
- 関連 Issue: なし
- 関連 design doc: [[20260722-issue-workflow-unification]]（この判断を切り出した元 design doc: .claude/designs/20260722-issue-workflow-unification.md）
- 関連 knowledge: なし
