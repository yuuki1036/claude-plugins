### 6.5. 構造化 findings JSON（embed mode のみ）

**`--embed` が指定されている場合のみ**、Step 6 の markdown レポート直後に機械可読な findings ブロックを出力する（非 embed 実行では出力しない）。呼び出し元（feature-dev Phase 6 等）はこの JSON を決定的にパースし、markdown の正規表現パースに依存しない。

出力テンプレート・フィールド契約（schema_version: 1）・`<!-- FINDINGS_JSON_START/END -->` マーカーの規約: → orchestration-optional-flows.md `## 15`（embed 分岐でのみ読む）

**次は Step 7**（SKILL.md に戻り、その見出しを見る）
