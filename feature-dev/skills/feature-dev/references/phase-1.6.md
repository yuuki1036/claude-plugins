## Phase 1.6: Vault Recall (knowledge vault retrieval handoff)

**Goal**: 過去プロジェクト横断の知見（落とし穴・設計判断・移行ノウハウ）を knowledge vault から recall し、Phase 4 architect に advisory 注入する。recall をモデルの文脈判断に委ねると省略されうるため、設計着手直前の必須ステップとして埋め込み「引き忘れ」を構造的に防ぐ。注入知見は advisory で、現コードベースのパターンと矛盾する場合は現コードベースを優先する。

vault は feature-dev 外の外部資源。取得経路を上から順に確かめ、使えるものを 1 つ使う。どれも無ければ skip する（後方互換）:

1. **MCP ツール `search_knowledge`**（server `knowledge-vault`。deferred なら ToolSearch で `select:mcp__knowledge-vault__search_knowledge` を読み込む）がこのセッションにある → `VAULT_VIA=mcp`
2. 無ければ `kvault` CLI と vault dir を確かめる:

```bash
# vault の場所は KNOWLEDGE_VAULT_ROOT で指定（個人環境パスをハードコードしない）。未設定なら skip。
if [ -n "$KNOWLEDGE_VAULT_ROOT" ] && command -v kvault >/dev/null 2>&1 && [ -d "$KNOWLEDGE_VAULT_ROOT" ]; then
  VAULT_VIA=cli
else
  VAULT_VIA=none
fi
```

- `VAULT_VIA=none` → **Phase 1.6 を skip して Phase 1.7 へ**。skip 理由を 1 行 notify（MCP ツール無し・CLI 未導入 / 未設定 / vault dir 不在）
- `VAULT_VIA=mcp|cli` → `${CLAUDE_PLUGIN_ROOT}/references/plugin-handoffs.md` の「Phase 1.6」を読み、その手順（キーワード列クエリ構築 → recall → 関連ありの結果だけを advisory 注入。関連判定は vault 側が行うので判定し直さない）に従う

**Output**: `VAULT_KNOWLEDGE=<関連知見の要約>` または `""`（未取得 / 関連なし / skip）。Phase 4 architect の "Vault Knowledge Injection" に渡す。

**次は Phase 1.7**（SKILL.md に戻り、その見出しの入口の条件を見る）
