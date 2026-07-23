# Linear 固有の記法

Linear の Issue / プロジェクト description を書くときの記法。これは **Linear 固有** で、ローカル Markdown 管理（BACKEND=local）には適用しない。

> このファイルは BACKEND=linear のときのみ Read される（issue-design SKILL の Phase 3 参照）。

---

## collapsible セクション（`+++`）

依存・参考資料など補助情報を畳んで本文を読みやすく保つ。

```
+++ 依存・ブロッカー
- 先行: …
- 後続: …
+++
```

- `>>>` テキストショートカットを入力すると内部表現 `+++` に自動変換される
- **明示的な閉じ `+++` がないと折りたたみ範囲が後続まで広がる**ので、必ず閉じる
- 用途: 「依存・ブロッカー」「参考資料」など、常時表示しなくてよい補助セクションを畳む

参考: https://linear.app/changelog/2025-03-19-collapsible-sections

## Issue リンク（`<issue id>`）

Issue 間リンクは inline issue リンク記法を使う。

```
<issue id="UUID">TEAM-123</issue>
```

- Linear MCP は識別子（`TEAM-123`）から UUID を自動解決するため、識別子で書けば足りることが多い
- 依存・後続セクションで他 Issue を参照するときに使う（双方向依存を Issue リンクで繋ぐ）

## pros/cons のインライン圧縮

判断ポイント (open) の選択肢は、行を消費しないインライン形式で書く。

```
- (a) TTL ベース — Pros: 実装が単純 / Cons: 鮮度制御が粗い
- (b) イベント駆動 — Pros: 鮮度が高い / Cons: 実装コスト大
```

## redundancy 除去

同じことを違う言い方で複数箇所に書かない。Linear description は一望性が重要なので、重複を削ると可読性が上がる（経験上 50% 程度圧縮できることがある）。

---

参考: Linear Editor docs — https://linear.app/docs/editor
