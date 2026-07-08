## 設計・計画の spec ルーティング（spec-advisor）

新しい開発タスクの説明を受けたら、**実装に着手する前に**、それが設計・計画系の成果物を先に書くべきタスクかを判断し、該当すれば 1 文の根拠を添えて提案すること。判断軸は WHAT=`bdd-spec` / HOW=`design-doc` / WHY=`adr-keeper` / Issue 粒度=`issue-design` / 実装一気通貫=`feature-dev`。

- 迷ったら `spec-advise` skill を起動して分類させる（正本は `spec-advisor` の routing-rubric）。
- **過剰提案の抑制**: bugfix・typo・設定変更・軽微な refactor・影響範囲が数行に閉じるタスク・既存 spec に沿うだけのタスクには提案しない（書くより実装した方が速い規模には黙る）。
- **提案は 1 回のみ。** 断られたら同一タスクで再提案しない。
- 未導入の設計プラグインは提案肢に出さない（dormant）。
