# Diátaxis Framework: CLAUDE.md 構造診断レンズ

CLAUDE.md の品質スコアとは独立した**補助観点**。文書タイプの混在や役割不明瞭を検出し、構造改善の提案根拠として使う。スコアには加算しない（既存採点の安定性を維持するため）。

参照元: <https://diataxis.fr/> — 技術文書を 4 つの目的別タイプに分類するフレームワーク。

## 4 つの文書タイプ

| タイプ | 読者の動機 | 性格 | 主語 |
|--------|----------|------|------|
| **Tutorial** | 学びたい（初学） | Learning-oriented / 手取り足取り | "Let's together..." |
| **How-to Guide** | やりたい（達成） | Goal-oriented / レシピ | "To do X, do Y" |
| **Reference** | 知りたい（事実） | Information-oriented / 事典 | "X is Y" |
| **Explanation** | 理解したい（背景） | Understanding-oriented / 解説 | "X exists because..." |

混在が問題になる典型例:
- リファレンス表の中に How-to の手順が紛れ込む → どちらの目的でも読みづらい
- Gotchas が単なる事実列挙（Reference）になっていて、なぜ起きるかの背景（Explanation）が欠落
- セットアップ手順（How-to）が「コマンド一覧」表（Reference）に押し込まれてコンテキストが消えている

## CLAUDE.md セクション ↔ Diátaxis タイプ マッピング

ありがちな CLAUDE.md セクションを Diátaxis 軸で分類する。**混在しているセクションは分割候補**。

| セクション | 主タイプ | 補助タイプ | 混在しがちな失敗例 |
|-----------|---------|----------|------------------|
| Commands 表 | Reference | — | 表セル内に「先に X を実行してから」等の How-to が混入 |
| Architecture / ディレクトリ図 | Reference | Explanation | 図だけで「なぜこの構造か」がない（背景欠落） |
| Quick Start / Setup | How-to | — | 表形式で順序が消える |
| Gotchas | Explanation | Reference | 「事実列挙のみ」になり why が無い → 再発防止に弱い |
| Code Style / 規約 | Reference | Explanation | 「なぜそうするか」のないルール列は人が守らない |
| Workflow / 作業手順 | How-to | — | 概念説明（Explanation）が混じって長尺化 |
| Skill Coordination | How-to | Reference | タスク→skill 対応表は基本 How-to（"X するときは Y を使う"） |
| バージョニング規約 / 規定 | Reference | Explanation | MAJOR/MINOR の判定基準は Reference、なぜ semver かは Explanation |

**判定の原則:** 1 セクション 1 タイプを基本とし、補助タイプは 1 段落以内に収める。3 タイプ以上が混在しているセクションは**分割を提案**。

## 診断チェックリスト（Phase 2 補助観点）

スコアには加算せず、Quality Report の「Structural Observations」欄に診断結果として記載する。

- [ ] **タイプ混在**: 1 セクション内で 3 タイプ以上が混在しているか
- [ ] **Why の欠落**: Gotchas / 規約セクションが Reference だけになっていないか（Explanation が無いと再発防止にならない）
- [ ] **手順の喪失**: Setup / Workflow が Reference 形式（表）に押し込まれて順序が消えていないか
- [ ] **Tutorial 過剰**: CLAUDE.md は Claude 向けで Tutorial はほぼ不要。学習導入が長文なら削減候補
- [ ] **Explanation の偏在**: 「なぜ」が CLAUDE.md 全体に薄く撒かれているか、特定セクションに集中しているか（後者の方が読みやすい）

## 提案フォーマット（Quality Report に組み込む）

```markdown
#### Structural Observations (Diátaxis lens)

**Type mix:**
- `## Commands`: Reference (clean)
- `## Gotchas`: Reference + Explanation (well balanced)
- `## Workflow`: How-to + Explanation + Reference (混在 — 分割候補)

**Recommendations:**
- `## Workflow` を `## Workflow (How-to)` と `## Design Decisions (Explanation)` に分割する案
- `## Gotchas` の各項目に "Why:" 1 行を足すと再発防止度が上がる
- `## Setup` を表 → 番号付き手順に戻す（順序が意味を持つため）
```

**注意:** Diátaxis は**診断レンズ**であって規則ではない。プロジェクト固有の判断を上書きしない。「混在 = 悪」と断定せず、「分割した方が読みやすくなる可能性」として提示する。

## CLAUDE.md における Diátaxis の使いどころと限界

**使いどころ:**
- 巨大化した CLAUDE.md（300 行超）の構造改善方針を決めるとき
- 「Gotchas が増えすぎて読みづらい」と感じたときの分割軸
- skill / agent / hook の役割文書（references/）の整理

**限界:**
- 小規模 CLAUDE.md（〜100 行）には適用しない方が良い（フレームワークの方が重い）
- Reference と Explanation の境界は曖昧（厳格に分けない）
- Tutorial は CLAUDE.md にほぼ不要（読者は Claude であり初学者ではない）

## 既存品質スコアとの関係

| 既存スコア項目 | Diátaxis が補強する観点 |
|--------------|---------------------|
| Non-Obvious Patterns (15pt) | Gotchas に Explanation（Why）があるか |
| Conciseness (15pt) | タイプ混在による冗長化を検出 |
| Actionability (10pt) | How-to が Reference 形式に潰れていないか |
| Skill Coordination (15pt) | タスク→skill 表は How-to として書けているか |

Diátaxis レンズで「混在」「Why 欠落」「順序喪失」を見つけた場合、それは既存スコア項目の減点理由として活用できる。逆に Diátaxis スコアという独立採点項目は**作らない**（再配点リスク回避）。
