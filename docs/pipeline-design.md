# コスト×精度パイプライン設計指針（多段 agent スキル/コマンド）

コスト（トークン・レイテンシ）と精度（偽陽性・偽陰性）を両立する多段 agent パイプラインを設計するときの共通指針。code-review / feature-dev / indie-issue-discover / failure-journal が独立に体現しているパターンを一般化したもの（元ネタ: Zenn「LLMエージェントのコスト×精度両立戦略：Clearwing に学ぶ設計原則」）。

新しい深掘り系スキル・コマンド・agent team を設計するときは、以下 10 原則のうち **どれを採用し・どれをあえて捨てたか** を SKILL.md に一言残す。全部入れる必要はない（対象規模に合わせる）。核心は「**弱いモデルの失敗モードをワークフローで囲い込む**」＝賢いモデル購買より先に「どこで絞り・どこで検証し・どこで止めるか」を設計すること。

| # | 原則 | 一言 | 正本 / 参考実装 |
|---|------|------|----------------|
| 1 | ファネル | 安価な絞り込み（diff/scope/grep/AST/トリアージ）を先頭に置き、高コスト検証は通過分にだけ適用 | `code-review/references/triage-guide.md` |
| 2 | 2 軸スコア化 | 結論には confidence(0-100) と severity を独立フィールドで付与し、報告閾値をマトリクスで決める | `code-review/references/scoring-guide.md` |
| 3 | 段階予算 | `${CLAUDE_EFFORT}` → (agent 数 / 反復回数 / 起票数) をマッピング。low は速度優先・high 以上で多重化 | `feature-dev/references/triage-guide.md` |
| 4 | モデルルーティング | 探索=弱モデル / 判断・検証・独立検証=強モデル / 統合・メタレビュー=別系統モデル（下表） | 本節の下表 |
| 5 | 暴走ガード | 予算上限・最大反復・同一 fingerprint 再試行抑制の三点セットを PoC 段階から装備 | `indie-workflow/skills/indie-issue-discover` |
| 6 | 証拠ラダー | 単発の指摘は蓄積し、閾値超で下流の高コスト処理や規約/hook に昇格させる | `failure-journal` |
| 7 | 敵対的独立検証 | 高リスク結論は別モデル・別コンテキストで反証。**発見者の推論を検証者に見せない**（迎合防止） | `code-review` 反証レイヤー |
| 8 | 外部オラクル + fail-closed | 型/テスト/コンパイル/実行の**機械判定**で客観検証し、LLM に投げる前に落とす。曖昧・エラー時は保守側（不可/保留）に倒す | — |
| 9 | 構造化受け渡し | agent 間は最小 JSON（識別子・file:line）のみ渡してコンテキスト膨張を防ぐ | Event Bus / Shared State 規約 |
| 10 | 確信度フィールド化 | 不確実な主張は「未検証」タグで明示し、フィルタで自動除外。断定で高 severity を作らない | `code-review/references/scoring-guide.md` |

## モデルルーティング規約（原則 4）

agent / サブタスクのロールに応じて既定モデルを出し分ける。「**後から変えにくい判断を伴う結論には強モデル、絞り込み探索には弱モデル**」が原則。自動プローブはせず人手のルーティング表でハードコードする。

| ロール | 既定モデル | 理由 |
|--------|-----------|------|
| 探索・収集・機械的サマリ（read-only fan-out。code-context / explorer 等） | `sonnet` | 事実収集は弱モデルで足り、体数を稼げる |
| 判断・検証・レビュー（load-bearing な結論。reviewer 等） | `opus` + effort 引き上げ | 誤判定コストが高い段は精度優先 |
| 敵対的独立検証（発見者と別コンテキストで反証。code-review 反証 / discover-verifier / design-review 反証） | `opus` | 検証は精度が命なので強モデル。独立性は「発見者の推論を渡さない」+ 別コンテキストで担保する（モデルを弱める必要はない） |
| 統合・メタレビュー・設計 blueprint（meta-reviewer / architect 等） | `opus` | load-bearing な統合・設計判断は強モデルで質を担保する |

- **`fable` は使用しない**（プロジェクト方針）。従来 fable が担っていた「別系統モデルで相関を切る」decorrelation は行わず、統合・メタレビュー・設計 blueprint も `opus` に寄せる。独立性が要る局面（meta-reviewer / 敵対的独立検証）は**別コンテキスト起動 + 発見者の推論を渡さない**ことで担保し、モデル多様性には依存しない。
- agent frontmatter か skill 本文で **明示指定**する（親からの継承任せにしない。指定漏れは `validate_plugin_quality.py` の warning で拾えるようにするのが望ましい）。
- 1 呼び出し内は単一モデル。ステージ間での切り替えは可。

## 外部オラクル + fail-closed（原則 8）の勘所

「正解を機械判定できる手段」を 1 つ持つかがパイプライン精度の上限を決める。**LLM レビューの手前に安いオラクルを差し込む**のが最も費用対効果が高い。

- コード領域: 型チェック（`tsc --noEmit` 等）・テスト・lint・ビルド・実行結果。**変更範囲・対象ファイルに絞って**実行する（全ビルド/全テストは重い）。
- 検出できない・実行不能なら結果を破棄せず「疑いのまま保留（backlog / 人手送り）」に倒す（fail-closed）。誤 OK 判定コストが高いドメインほど効く。
- 検証プラグイン（code-review 等）が未インストールなら品質ゲートは skip せず **fail-fast**（feature-dev Phase 6 が採用）。

## あえて入れない（このリポジトリでの判断）

- **70/25/5 の予算配分＋繰越**: Claude Code は直列トークン予算でなく並列 agent＋体数上限モデル。effort→体数マッピングで十分。繰越は管理コストに見合わない。
- **finding schema の全面統一**: 共通化はコア 3 点（severity 語彙 / confidence 0-100 / evidence 必須）に留め、報告マトリクスは scoring-guide.md を soft 参照。ドメイン粒度を壊さない。
- **暴走ガード・モデルルーティングの hook 強制**: effort やループ回数は LLM の文脈判断で決まり決定的検証できない。意思決定フロー②（`docs/rule-placement.md`）に従い CLAUDE.md 規約止まりが正解。
