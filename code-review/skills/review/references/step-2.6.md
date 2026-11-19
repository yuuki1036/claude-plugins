### 2.6. Vault 照合（過去の指摘・落とし穴の retrieval / 任意・後方互換）

変更ファイルに関連する過去のレビュー指摘・落とし穴を vault から引き、Step 5 の reviewer に注入する（self-review Step 1.5 と同じ手順）。取得経路（MCP ツール `search_knowledge` → `kvault` → どちらも無ければ skip）・照合手順・注意事項 → orchestration-optional-flows.md `## 11`。**PR に投稿するコメントには vault の内容を引用しない**（vault は別プロジェクト由来の知見を含む）。`--emergency` では skip する（最小構成を保つ）。

**次は Step 3**（SKILL.md に戻り、その見出しを見る）
