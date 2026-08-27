---
id: 20260623-review-adversarial-verify-layer
title: review系スキルへの反証レイヤー（adversarial verification）導入
status: approved
phase: current
last-validated: 2026-08-28
supersedes: []
superseded-by: null
issue: null
spec: null
adrs: []
tags: [code-review, false-positive, adversarial-verify, scoring]
---

# review系スキルへの反証レイヤー（adversarial verification）導入

> 2026-06-23 design-review（minimal/clean/pragmatic/risk 4 視点）の findings を反映済み。主な変更: Phase 番号を相対位置で定義 / 二重計上の排他 / 高 severity 非削除の機械保証点を明示 / specialist 除外 / 反証軸を独立性に効くものへ絞り既存自己検算を再利用 / MAJOR drop の付録保全。
>
> **実装済み（code-review 2.26.0、phase: current）**: scoring-guide.md / reviewer-prompts.md `## 7` / triage-guide.md `## 9` / review SKILL Phase 5.8 / self-review SKILL Phase 4.8 / plugin.json userConfig + 両 payload。静的検証（validate-ssot / validate_plugin_quality / claude plugin validate）通過。残: 既知偽陽性 diff での runtime スモーク（高 severity 非削除の目視）と event bus 計測による verdict→delta チューニング（open 参照）。

## TL;DR

code-review の reviewer が出した指摘を、報告前に**独立コンテキストの**エージェントが反証する工程（review=Phase 5.8 / self-review=Phase 4.8）を追加する。reviewer 既存の自己検算で潰せない「独立読み直しでしか分からない偽陽性」だけを対象に、verdict を既存スコアリングへ流す。**高 severity は消さず係争注記**を機械保証し、偽陽性の減少と本物の見落とし防止を非対称に両立する。

## 背景 / 課題

review系スキル（`code-review:review` / `code-review:self-review`）の指摘は、人間が「これ本当？」と詰めると取り下げられることがある（= 偽陽性）。調査で構造的原因が判明した:

- **confidence は指摘を出した reviewer 自身の自己申告**（`scoring-guide.md:7`, `reviewer-prompts.md:60`）。出した本人が確信度を付けるため自己評価バイアスが乗る。
- **既存の自己検算は一部存在するが「独立性」が無い**。reviewer 共通指示には既に退行指摘の invariant 検算（`reviewer-prompts.md:96-107`）と事実主張のツール接地（`:109-127`、検証不能な主張は `[unverified]` で confidence ≤75 クランプ）がある。だがこれらは**指摘を出した本人が自分でやる**ため、最初に「バグだ」と判断したアンカリングから抜けにくい。
- 残りの検証機構はすべて「指摘を増やす方向」に偏る: 冗長ペア（angle 違い x2、`reviewer-prompts.md:703-727`）は両方「探す」係、meta-reviewer（fable、`SKILL.md:261-279`）は「見落とし観点」を足す係。
- 結果、パイプラインは false negative 対策に厚く、**別の目で偽陽性を独立に潰す半分が欠けている**。その欠けた半分を人間が手で詰めている。

→ 反証レイヤーの正味の追加価値は「**指摘を形成していない独立エージェントがアンカリングなしに読み直す**」点に限られる（design-review minimal 視点の指摘）。既存自己検算と重複する軸は再実装せず再利用する。

## ゴール / 非ゴール

- **ゴール**: reviewer が形成した指摘を独立コンテキストで反証し、偽陽性の prominence を下げる（取り下げを先回りして指摘に内蔵）。
- **ゴール**: 反証統合が**本物の高 severity 指摘を黙って消さない**ことを、プロンプトでなく **Phase 6 オーケストレーター手順の分岐で機械保証**する。
- **ゴール**: 既存の severity × confidence マトリクスと加減算機構に乗せ、footprint を最小化（新 agent 定義ファイルを足さない）。既存自己検算（invariant 検算 / `[unverified]` クランプ / severity 調整）を**再実装せず再利用**する。
- **非ゴール**: reviewer の既存自己検算で既に潰せる軸（`[unverified]` 相当・退行 severity 検算相当）を反証レイヤーで重複実装すること。
- **非ゴール**: security specialist 由来（injection / secret-handling / destructive-op）の BLOCKER を反証で係争中にすること（誤反証の代償が非対称に大きい）。
- **非ゴール**: `design-doc:design-review` への適用（あちらは evidence-first で偽陽性の痛みが小さい。code-review で効果計測後に判断）。
- **非ゴール**: 反証を全面的に決定的（非 LLM）検証へ置換すること（`pre-existing` と `intended` の鮮度のみ git で部分決定化）。

## 確定した前提

- **パイプライン Phase 番号は review と self-review で異なる**（design-review BLOCKER）:

  | 役割 | review/SKILL.md | self-review/SKILL.md |
  |---|---|---|
  | adaptive deepening | Phase 5.5 (`:238`) | Phase 4.5 (`:204`) |
  | meta-reviewer | Phase 5.6 (`:261`) | Phase 4.6 (`:225`) |
  | 観点カバレッジ self-check | Phase 5.7 (`:281`) | Phase 4.7 (`:244`) |
  | scoring | Phase 6 (`:292`) | Step 5 (`:255`) |
  | report | Phase 7 (`:316`) | Step 6 |
  | **反証レイヤー（新）** | **Phase 5.8** | **Phase 4.8** |

  本 doc では番号でなく**相対位置「観点カバレッジ self-check の後・scoring の前」**で挿入位置を定義する。
- 報告マトリクス（`scoring-guide.md:58-70`）: BLOCKER 60+ / CRITICAL 80+ / MAJOR・MINOR 95+ で報告。**不確実だが報告される非対称ゾーン**（BLOCKER 60-94 / CRITICAL 80-94）が偽陽性の温床。
- confidence 加減算はオーケストレーターが Phase 6（self-review は Step 6）で機械適用し reviewer 判断を介入させない（`scoring-guide.md:89-141`、適用順序 `:135-141`）。既存 severity 調整ルール（`:147-152`）は「scope:out/resolved で 1 段階下げ」「複数 reviewer BLOCKER は維持」「退行 invariant 検算済みは二重降格しない」を持つ。
- 既存の confidence 加算に「複数エージェント同一指摘 +15」(`scoring-guide.md:97`) が**既にある**。独立反証の confirm はこれと同根なので**二重計上を排他**する必要がある（design-review BLOCKER）。
- effort ゲートのスキップ条件本体: 5.5 は `review/SKILL.md:240-243`、5.6 は `:263-266`、effort 適応表は `triage-guide.md:278-293`（`SKILL.md:159-163` は reviewer 体数調整であってゲートではない＝旧 doc の誤参照を訂正）。meta-reviewer(5.6) は **xhigh/max のみ**、adaptive(5.5) は **high で起動**。
- explorer/reviewer は agent 定義ファイルでなく `*-prompts.md` を generic agent に注入して起動（`code-review/agents/` は存在しない＝Glob 0 件）。→ 反証も prompt テンプレ追加だけで実現可、新 agent 定義ファイル不要。
- specialist（injection/secret-handling/destructive-op）は「断定できなくても BLOCKER + 低 confidence で報告し人間判断を促す」前提（`reviewer-prompts.md:733,754,777,800`）。
- 計測基盤: `review:completed` を `.claude/events.jsonl` に publish 済み（payload は **flat 構造**、`review/SKILL.md:417-436` / `self-review/SKILL.md:314-331`、self-review は `pr:"local"` 固定）。新規フィールド追加は旧 subscriber に無害。
- 現行 version: `code-review/.claude-plugin/plugin.json` = 2.25.1（marketplace 同期済み）。新機能追加 → MINOR バンプ 2.26.0。

## 採用案

**案A': 反証=注記レイヤー（独立性に絞った軸 + severity 非対称の機械保証）。**

### アーキテクチャ

観点カバレッジ self-check の後・scoring の前に**反証レイヤー**を挿入（review=Phase 5.8 / self-review=Phase 4.8）。全指摘が出揃った状態で、報告ゾーンの指摘だけ独立反証する。

```
... → 観点カバレッジ self-check
    → 反証レイヤー（新規）
         ├─ 反証対象の選定（severity ゲート + specialist 除外 + 非対称ゾーン優先）
         ├─ pre-existing / intended鮮度 の git 決定判定（LLM 前に実行）
         ├─ 反証エージェント起動（指摘ごと、独立コンテキスト、reviewer 推論は非共有）
         └─ verdict 出力（confirmed / refuted / uncertain / severity-inflated）
    → scoring（verdict→delta を加減算に流す。高 severity は分岐で delta 抑止）
    → report（係争注記 + 取り下げ付録）
```

### 反証対象の選定（コスト制御・非対称ゾーン優先）

「詰めると取り下がる」のは**不確実だが報告される非対称ゾーン**なので、そこを狙い撃ちして既定パスのコストを抑える:

| effort | 反証対象 | 反証体数 |
|---|---|---|
| low / medium | スキップ（5.5/5.6 と同じ） | 0 |
| high（既定） | **非対称ゾーンのみ**（BLOCKER 60-94 / CRITICAL 80-94）。**specialist 由来を除外** | 指摘ごと 1 体 |
| xhigh / max | 上記 + BLOCKER/CRITICAL 95+ + MAJOR（specialist 除外は維持） | 指摘ごと 1 体 |

95+ の高確証指摘は取り下がりにくいので既定では対象外。specialist（injection/secret/destructive）は誤反証の代償が非対称なので全 effort で対象外。典型 PR で追加 1〜2 体（opus）。

### 反証エージェントの作法（独立性 + 両方向に証拠要求）

- finding の主張（file:line + 内容）だけ渡し、**reviewer の推論は渡さない**（アンカリング防止）。コードは自分で読み直す。
- **既存自己検算と重複する軸は反証レイヤーで再判定しない**。下表の「新規（独立性が効く）」軸に集中する:

| 軸 | 種別 | 判定手段 | 既存機構との関係 |
|---|---|---|---|
| unreachable | 新規 | LLM（独立にコード追跡） | reviewer 自己検算では抜けやすい |
| pre-validated | 新規 | LLM | 同上 |
| misread | 新規 | LLM（独立読み直し） | 独立性が本質的に効く |
| **pre-existing** | 新規 | **git（決定的）** | base 比較は本人もやらない |
| intended | 補強 | LLM + **git blame（コメント/テストの鮮度を機械確認）** | stale コメント誤認を git で補強 |
| unverified | **再利用** | — | 既存 `[unverified]` クランプに委譲、反証では新規判定しない |
| severity-inflated | **再利用** | — | 既存 severity 調整ルールに委譲（後述） |
| out-of-scope | **再利用** | — | 既存 `[scope:out]` に委譲 |

- **refute するには file:line の反証根拠が必須。「たぶん大丈夫」は refuted ではなく uncertain（軽い減点）。** confirm も同じくパス再現が必須。証拠なき同調・証拠なき却下を両方 uncertain に落とす（怠惰な却下で本物を殺さないための要）。
- `pre-existing` は LLM 前に `git show <base>:<file>` / `git blame` で機械判定。「base に元からあるが diff が周辺前提を変えて顕在化させた」ケースは refuted にしない。`intended` で却下する場合も、根拠コメント/テストが当該 diff で touch されているか git blame で diff より新しいかを判定材料に加える。

### 既存スコアリングへの統合（severity 非対称・機械保証・二重計上排他）

反証結果を Phase 6 の加減算に流す。ただし**「高 severity は消さない」を加減算の前段分岐で機械保証**する（design-review risk/clean BLOCKER の核）:

**適用順序への追加分岐**（`scoring-guide.md` の Step 6 適用順序 `:135-141` に挿入）:

```
verdict 反映ステップ（既存の加減算より前）:
  if verdict == refuted and severity ∈ {BLOCKER, CRITICAL}:
      delta を適用しない。本文に「⚠️ 反証メモ: <軸>（<根拠 file:line>）」を付与（= 係争中）。
      confidence / severity は据え置き。→ マトリクス境界を跨がない。
  elif verdict == refuted and severity ∈ {MAJOR, MINOR}:
      file:line 反証根拠ありが必須。confidence −40。ただし**却下理由を必ず付録にログ**（覆せる経路を保証）。
  elif verdict == confirmed:
      既存「複数エージェント同一指摘 +15」(scoring-guide.md:97) の発火源として扱う。
      反証 confirm と複数エージェント検出が同時成立しても +15 は一度だけ（二重計上排他）。
  elif verdict == uncertain:
      confidence −10 + 本文注記。単独では何も殺せない。
  severity-inflated:
      既存 severity 調整ルール（scoring-guide.md:147-152）の一項目として処理。
      退行 invariant 検算で既に 1 段下げ済みなら二重降格しない（既存の排他条件を流用）。
```

- 係争注記・反証メモは**オーケストレーターが機械付与する別系統**。reviewer 自己申告タグ（`[scope:out]` 等）と区別するため、`[...]` タグ語彙は増やさず**本文の「⚠️ 反証メモ:」表現**で表す（producer が記法から判別できる、design-review clean MAJOR）。
- max effort で BLOCKER をパネル運用する場合の集計規則（**初版は 1 体運用、パネルは open**）: refuted は過半数かつ全員 file:line 根拠提示時のみ成立、票割れ・棄権（uncertain 混在）は uncertain 扱いで delta 合算しない。

### 提示（軽く・保全を明示）

報告本体は変えない。サマリに 1 行追加 + 取り下げ/係争の付録:

```
反証で取り下げ/係争: 係争 M件（BLOCKER/CRITICAL、本文に反証メモ） / 取り下げ K件（MAJOR以下、付録に理由）
```

係争 BLOCKER/CRITICAL は消滅させず本文に反証メモ。**取り下げた MAJOR/MINOR も付録に file:line 付きで理由を残す**（誤却下を人間がその場で覆せる、design-review risk MAJOR）。

### 計測

`review:completed` payload に新規ネストフィールドを追加（flat な既存フィールドは変えない）:

```json
{ "adversarial_verify": { "confirmed": N, "refuted": N, "uncertain": N, "contested": N } }
```

**review / self-review 両 publisher を同時更新**して payload 規約の同一性を維持（self-review は `pr:"local"`）。後から「却下した指摘が実は本物だった」率を追跡し verdict→delta を調整。

### userConfig

`enable_adversarial_verify`（既定: high+ で true、`enable_meta_reviewer` と同型運用）。誤却下が多いと感じたら無効化できる。

### 変更対象ファイル

| ファイル | 変更内容 |
|---|---|
| `code-review/references/scoring-guide.md` | verdict 反映ステップ（高 severity 分岐 + MAJOR drop 付録 + confirm 二重計上排他 + severity-inflated 統合） |
| `code-review/references/reviewer-prompts.md` | `adversarial-verify` テンプレ追加（独立性軸 + 両方向証拠 + git 手順）。既存自己検算（`:96-127`）は変更せず前段として依存 |
| `code-review/references/triage-guide.md` | 反証レイヤーの effort ゲート（非対称ゾーン + specialist 除外） |
| `code-review/skills/review/SKILL.md` | Phase 5.8 + Phase 7 係争注記/付録 + payload |
| `code-review/skills/self-review/SKILL.md` | Phase 4.8 + report 反映 + payload + embed JSON に contested/refuted |
| `code-review/.claude-plugin/plugin.json` + CHANGELOG | 2.26.0 + userConfig 追記 |
| `.claude-plugin/marketplace.json` | version/description 同期 |
| ルート `CLAUDE.md` 一覧表 / `INDEX.md` | description 変更時に同期（`/quality-check` が検出） |

## 検討した代替案

| 観点 | 案A' 注記レイヤー（採用） | 案B ハードドロップ | 案C 独立 refuter agent | 案D reviewer 内セルフ反証のみ |
|------|------------------------|-------------------|----------------------|------------------------------|
| footprint | 小（prompt + phase + scoring 分岐） | 小 | 大（agents/ 新定義 + 専用フェーズ） | 最小（reviewer prompt のみ） |
| 偽陽性削減 | ○（独立性に絞る） | ○ | ○ | △（自己評価バイアス残） |
| 本物を殺すリスク | **低**（高 severity 分岐で機械保証） | **高**（BLOCKER を黙って drop） | 低〜中 | 低 |
| 独立性 | ○（別コンテキスト・推論非共有） | ○ | ◎ | ✗（出した本人が反証） |
| 既存自己検算との重複 | 回避（再利用） | 重複しうる | 重複しうる | n/a（既存そのもの） |

- **案B 不採用**: refuted −40 を severity 不問で適用すると本物の BLOCKER を弱い/誤った反証で報告圏外に落とす（採用案では高 severity 分岐で機械的に封鎖）。
- **案C 不採用**: explorer/reviewer が prompt 注入で動く以上、新 agent 定義は過剰。`component-addition-advisor` の退路確保原則に反する。
- **案D 不採用（ただし前提として依存）**: 「出した本人が反証」では自己評価バイアス＝根本原因が残り独立性が出ない。一方、案D が指す reviewer 自己検算（invariant 検算 / claim grounding）は **`reviewer-prompts.md:96-127` に既に実装済み**。採用案はこれを**前段の前提として再利用**し、重複する軸（unverified/severity-inflated/out-of-scope）を反証レイヤーで再実装しない。→ 案D は「新規施策」ではなく「既存資産への依存」として整理（design-review minimal の指摘を反映）。

## 設計判断ログ

- [→ADR候補] review系スキルの反証統合は**高 severity を削除せず注記する**ことを不変条件とし、プロンプトでなく**スコアリング手順の分岐で機械保証**する（false-negative を構造的に防ぐ。reviewer 系プラグイン全体の設計原則）。
- [→ADR候補] 自己申告 confidence を**独立エージェントの反証 verdict で補正**する。ただし既存自己検算（`reviewer-prompts.md:96-127`）で潰せる軸は再実装せず、反証は「独立性に効く軸」に限定する。
- [local] security specialist 由来の BLOCKER は反証対象から除外（誤反証の代償が非対称）。
- [local] 反証は非対称ゾーン（BLOCKER 60-94 / CRITICAL 80-94）優先。95+ は既定で対象外。
- [local] confirm は新規 delta を足さず既存「複数エージェント同一指摘 +15」の発火源として扱い、二重計上を排他。
- [local] 係争注記は `[...]` タグ語彙を増やさず本文「⚠️ 反証メモ:」で表現（機械付与と自己申告の producer 区別）。
- [local] verdict→delta の具体値（confirm: 既存+15流用 / refuted MAJOR以下 −40 / uncertain −10）は初期値、event bus 計測後に調整。
- [local] `pre-existing` と `intended` の鮮度のみ git で決定判定し LLM 反証の前段に置く。

## 未解決事項 (open)

> **2026-08-28 追記（GitHub issue #184）**: 実装から 2 ヶ月経ち、下の 4 項目は**決着済みと
> 据え置きが混在している**。doc 上で区別がつかず「全部未決」と読めてしまうので、現状を注記する。
>
> | 項目 | 現状 |
> |---|---|
> | 反証エージェントのモデル | **決着**（opus。`triage-dynamic-gates.md` の反証レイヤー節が正本） |
> | パネル（max で BLOCKER 3 体多数決） | **据え置き**。`design-notes/scoring-rationale.md` が「現行は全 effort で 1 指摘 1 verdict、パネルは event bus 計測後に拡張判断」と明記 |
> | verdict→delta の数値 | **決着**（実測に基づき確定。`design-notes/scoring-rationale.md` に 19 サンプル / 67 verdict の集計） |
> | design-review への展開 | **据え置き**（design-notes に言及なし＝着手されていない） |

- 反証エージェントのモデル: (a) opus — Pros: reviewer 同等の読解 / Cons: コスト高 (b) sonnet — Pros: 安い / Cons: uncertain 連発の恐れ。現時点 (a) opus が有力（反証は読解の質が直結）。確定タイミング: 実装後に uncertain 率を観測して判断。
- パネル（max で BLOCKER 3 体多数決）の要否: (a) 初版は全 effort で 1 体 — Pros: 単純・計測先行 / Cons: 1 体の誤却下耐性なし (b) max で 3 体パネル — Pros: 誤却下耐性 / Cons: 計測前は YAGNI。現時点 (a) が有力（1 体の uncertain 率すら未観測、design-review minimal/risk）。確定タイミング: event bus で 1 体の誤却下が観測された後。集計規則は採用案に既述。
- verdict→delta の数値: (a) 固定値スタート (b) 計測後チューニング。現時点 (a) で開始し `review:completed` の adversarial_verify が 20+ 件たまった時点で (b)。
- design-review への展開: (a) しない（code-review 専念） (b) 軽量版を後追い。現時点 (a) が有力（design-review は既に evidence-first）。確定タイミング: code-review 版の false-negative 率が許容範囲と確認後。

## 実装ブリッジ (Implementation Bridge)

1. **実装着手の単位**（Issue 分解案、依存順）:
   - Issue 1: `scoring-guide.md` に verdict 反映ステップを追記（高 severity 分岐 / MAJOR drop 付録 / confirm 二重計上排他 / severity-inflated 統合）。**他の土台、最初に確定すべき**
   - Issue 2: `reviewer-prompts.md` に `adversarial-verify` テンプレ追加（独立性軸・両方向証拠・pre-existing/intended の git 手順・specialist 除外）。既存 `:96-127` は触らない
   - Issue 3: `review/SKILL.md` に Phase 5.8 + Phase 7 係争注記/付録、`self-review/SKILL.md` に Phase 4.8 + report + embed JSON、`triage-guide.md` に effort ゲート（非対称ゾーン + specialist 除外）
   - Issue 4: `review:completed` payload に adversarial_verify 集計を**両 publisher 同時**追加
   - Issue 5: plugin.json 2.26.0 + userConfig + CHANGELOG + marketplace.json 同期 + CLAUDE.md 一覧/INDEX.md 同期確認
   - feature-dev 起動例: `/feature-dev code-review に反証レイヤーを追加（本 design doc 準拠）`
2. **検証方法**:
   - `evals/runner.py` でスキル選択の回帰なしを確認（トリガーフレーズ不変）。
   - 既知の偽陽性を含む diff で self-review を回し、**BLOCKER/CRITICAL が消えず係争注記が付く**ことを目視（高 severity 非削除の不変条件のスモークテスト）。specialist BLOCKER が反証対象外であることも確認。
   - `/quality-check` で marketplace 同期・allowed-tools 一致・safe-hook 同期・INDEX/CLAUDE.md 一覧同期を検証。
   - 実装着手前に `claude-meta:component-addition-advisor` で退路確保を正式判定（本 doc の minimal 視点で実施済みの分析を確認: 新 agent 不要・案D は既存資産で充足・反証は独立性軸のみ）。
3. **実装完了時の doc 更新手順**: frontmatter `phase: target → current`、`last-validated` 更新。verdict→delta を計測値で改訂したら本文 + `last-validated` 更新（方式不変なので改訂、supersede 不要）。

## 関連

- 関連 Issue: なし
- 関連 spec: なし
- 関連 ADR: `[→ADR候補]` 2 件（高 severity 非削除の機械保証 / 独立反証による confidence 補正）— adr-keeper 未切り出し
- 関連 design doc: なし
- 参照実装: `code-review/references/scoring-guide.md`（:58-70 マトリクス / :89-152 加減算・severity 調整）, `reviewer-prompts.md`（:60 confidence / :96-127 既存自己検算 / :703-727 angle / :733-800 specialist）, `triage-guide.md`（:278-293 effort 適応）, `skills/review/SKILL.md`（5.5-5.7/6/7）, `skills/self-review/SKILL.md`（4.5-4.7/Step5-6）
- review-metrics 集約: `review:completed` event（multi-machine gist 運用）
