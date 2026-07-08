---
id: 20260703-code-review-recall-high-risk-surface
title: code-review の high-risk surface における recall 補強（冷や読み skeptic + surface-aware 閾値）
status: accepted
phase: current
last-validated: 2026-07-08
supersedes: []
superseded-by: null
issue: null
spec: null
adrs: [20260703204045]
tags: [code-review, recall, false-negative, high-risk-surface, scoring, triage]
---

# code-review の high-risk surface における recall 補強（冷や読み skeptic + surface-aware 閾値）

## TL;DR

high-risk surface（DB 書込 / 金 / 認可、または PR 自己申告 D1-High）を含む変更に限り、事前所見と無関係に findings 非注入の独立 skeptic を 1 体起動し、報告閾値を surface-aware に緩める。precision の本丸（≤40 好みクランプ・高 severity 非削除・specialist 反証除外）は触らず、recall を surface 単位で非対称に補正する。

## 背景 / 課題

xhigh フルパイプライン（explorer 5 + reviewer 10 + 反証 3）で high-risk な DB 書込 PR を「Approve with nits」で通したが、別レビュー（Fable5 + Opus）が実バグ 2 件を検出した（発生源: 実レビューでの保存ロジック PR、GitHub issue #75）。

- **#1（CRITICAL 級）**: 空文字 `''` が `?? null`（null/undefined しか捕まえない）を素通りし numeric 列へ INSERT → 22P02 → 非 AppError → 500。空欄を含む draft 保存が常に失敗する。schema が `''` 許容 → domain が温存 → repository が生 INSERT → DB 拒否、という **層跨ぎの値フロー**。fleet 全員が同じ盲点を共有したため誰も検出しなかった。
- **#7**: エラー変換が共有の `withActionErrorHandler` / `errorMapping.ts` を迂回し SERVICE_UNAVAILABLE の error 級ログが消える。claude-md reviewer が `instanceof AppError` を見て「準拠＝問題なし」と積極 PASS し、迂回の帰結（観測性欠落）に接続できなかった。

根本原因は precision と recall の非対称にある。パイプラインの precision は健全（Fable の誤検出を正しく非検出化）だが、recall の最後の砦である meta-reviewer（Phase 5.6）が「フィルタ前に BLOCKER/CRITICAL がある時だけ起動」＝ fleet が severe を取りこぼした時こそ黙る逆循環になっている。scoring も全方向 precision 寄せで、high-risk surface に対する recall 補正が無い。

## ゴール / 非ゴール

- **ゴール**: high-risk surface に限定して recall を補正し、#1（層跨ぎ値フロー）・#7（帰結接続の欠落）を捕捉する。precision の本丸は保全する。
- **ゴール**: 既存の反証レイヤー（precision 側 = false-positive 潰し）と鏡像になる recall 側 = false-negative hunter を設計として対称に据える。
- **非ゴール**: reviewer を 1 体に統合しない（並列性・独立性・per-focus 較正を失うため）。「一頭」は explorer 値追跡 + 集約注入で近似する。
- **非ゴール**: 全 surface で閾値を緩めない（noise 爆発を避け、high-risk surface に限る）。
- **非ゴール**: 並行性 / MVCC を反証除外の specialist に載せない（MVCC 推論は誤りうる。反証を通して alert fatigue を防ぐ）。

## 確定した前提

- **meta-reviewer（Phase 5.6）は非独立**: `reviewer-prompts.md §6`。全 reviewer の指摘（フィルタ前）+ diff + explorer 結果を注入され「他に見落としは?」と問う係。model=fable。起動条件は「BLOCKER/CRITICAL あり **かつ** effort=xhigh/max」（`triage-guide.md §8`）。→ fleet 共通の盲点があると meta も引きずる（迎合リスク）。#1 のような fleet 全員が見落とす層跨ぎバグには構造的に弱い。
- **反証レイヤー（実装後 Phase 5.9 / 4.9。design 時は 5.8 / 4.8）は独立**: `triage-guide.md §9` / `reviewer-prompts.md §7`。指摘の主張のみ渡し reviewer 推論は渡さない。model=opus, effort=max。「偽陽性を独立に潰す」係。今回の skeptic はこの鏡像として設計する。
- **報告マトリクスは全方向 precision 寄せ**: `scoring-guide.md §報告マトリクス`。CRITICAL は confidence 80+、MAJOR は 95+ で報告。surface 別の可変は無い。
- **surface 検出の足場は「部分的」にしか無い**（design-review F2 で訂正）: red-flag pattern（`triage-guide.md §157`）は `DROP TABLE` / `TRUNCATE` / `DELETE FROM .* WHERE` など**破壊的操作のみ**が対象で、#1 の対象である通常の `INSERT` / `UPDATE`（DB 書込）は specialist 自動起動対象に**含まれない**。`INSERT`/`UPDATE` は performance 観点の起動条件（`triage-guide.md §108`）に文字列マッチとしてあるだけで surface 判定の足場ではない。「PR 自己申告 D1-High」の検出はコードベースに**存在しない**（grep で 0 件）。→ surface 判定は「既存の再利用で足りる」のではなく、**(1) performance 観点の INSERT/UPDATE 正規表現を surface 判定に転用 + (2) D1-High 検出を PR コンテキスト検出（`reviewer-prompts.md §2.5`）に新規追加**が要る。この新規実装コストを Tier1（Issue C）に織り込む。ADR-20260703155637 の Enforcement / 代替案却下理由も同じ前提に依拠しているため連動して見直す（open 参照）。
- **観点カバレッジ self-check は常時実行**（`review/SKILL.md` Step 直前・メインコンテキスト・Agent 不使用）。meta-reviewer の厳しいゲートを補うため既に severity 非依存で走る。skeptic はこれと別レイヤー（self-check は focus 漏れ検査、skeptic は独立再レビュー）。

## 採用案

案 B（cold-read skeptic 新設）を核に、Tier2/3 を下流の段階投入として配置する。

### アーキテクチャ（recall 側レイヤーの新設）

反証レイヤー（false-positive 潰し）の鏡像として、**「冷や読み skeptic レイヤー」**を meta-reviewer の後・反証レイヤーの前に挿入する。

> **Phase 番号は絶対値で固定しない**（design-review BLOCKER F1）。現行の Phase 5.7 / 4.7 は既に「観点カバレッジ・セルフチェック」が占有している（`review/SKILL.md:286` / `self-review/SKILL.md:249`）。前身 doc [[20260623-review-adversarial-verify-layer]] が確立した「絶対番号でなく相対位置で挿入点を定義する」規約に従い、skeptic の挿入位置は**「meta-reviewer の後・反証レイヤーの前」**とだけ規定する。具体的な Step 番号（self-check / skeptic / 反証レイヤーのリナンバリング）は実装時に SKILL.md ×2 を正本として確定する（Issue C）。

```
Phase 5.5 adaptive deepening (explorer 再)         … 既存
Phase 5.6 meta-reviewer        … 非独立・findings 注入・FN を足す（既存, ゲート変更）
Phase 5.7 観点カバレッジ self-check … 常時・メインコンテキスト（既存, 位置不変）
Phase 5.8 冷や読み skeptic     … 独立・findings 非注入・FN を足す（新設）★本設計
Phase 5.9 反証レイヤー          … 独立・主張のみ注入・FP を潰す（既存, design 時は 5.8）
Step 6    機械フィルタ（報告マトリクス, surface-aware 閾値）★本設計
```

（上図は実装後の確定番号。design 時は skeptic を Phase 5.x（未確定）、反証を 5.8 と表記していたが、実装時に skeptic=5.8 / 反証=5.9 へリナンバリングした（self-review 側も 4.8 / 4.9）。）

skeptic の作法（反証レイヤーと対称）:

| 項目 | meta-reviewer（既存） | 冷や読み skeptic（新設） | 反証レイヤー（既存） |
|---|---|---|---|
| 係 | false-negative 足す | false-negative 足す | false-positive 潰す |
| findings 注入 | 全注入（非独立） | **非注入（独立）** | 主張のみ |
| focus 分割 | 無し | **無し（generalist 一頭）** | 指摘単位 |
| 契約注入 | 通常 | **薄め（冷や読み）** | 通常 |
| model | fable | **opus**（独立検証は強モデル: ルーティング表） | opus |
| 起動ゲート | severe あり ∧ xhigh+ | **high-risk surface**（事前所見・severe 非依存） | 非対称ゾーン |

**独立性を「破り方」に変換する**（design-review F7）: 独立 model・別コンテキスト・findings 非注入だけでは、#1 の層跨ぎ値フローという盲点は model を変えても再現しうる（skeptic も同じ diff を薄い契約で読むため）。#1 を直撃する探索手順（敵対的入力逆算＝受理入力の端点を末端の永続層制約まで前進させる）は Tier2 に置くが、その**核だけを Tier1 skeptic テンプレート（reviewer-prompts.md の新設 skeptic focus）に内挿**し、独立性に「破り方」を持たせる。これにより Tier2 未投入でも Tier1 単体で #1 を捕捉できる。Tier2 の value-flow-trace explorer はこの探索を explorer 側に厚くする増分と位置づける。

### 起動ゲート（Tier1 #1）

`triage-guide.md §8` に skeptic フェーズ（挿入位置は前述の相対位置）を追記する。起動条件は meta-reviewer の「severe あり」ではなく **high-risk surface のとき**（事前所見・severity と無関係）:

- **surface 判定**: DB 書込（INSERT/UPDATE 含む）/ 金銭計算 / 認可・認証、または PR 自己申告 D1-High を含む。判定ロジックは F2 のとおり新規実装が要る（INSERT/UPDATE 正規表現の転用 + D1-High 検出の追加）。
- **effort 適応**: high（既定）でも high-risk surface なら起動 / low・medium はスキップ / xhigh・max は起動。今回のバグは xhigh で漏れたため xhigh の挙動を変える必要がある。※high 既定での常時起動コストは open で「初版 xhigh 起点・high は計測後に昇格」の fail-safe 案も残す。
- **上限（暴走ガード）**: **PR あたり skeptic 1 体・1 round のみ**（per-surface 起動ではない）。skeptic の指摘も通常の scoring・フィルタ対象。
- **失敗時挙動**（design-review F6・既存 5.6 に倣う）: skeptic が失敗/タイムアウトした場合は `missing_coverage` に `recall-skeptic: <failure reason>` を追記して best-effort 続行する。**起動条件（high-risk surface）を満たしたのに未実行だった事実はレポートに必ず出す**（silent 失敗で「守ったつもり」の偽の安心を防ぐ）。
- **userConfig**: `enable_recall_skeptic: false` で強制スキップ（既定 true）。計測前の暴走はこの config と effort での明示スキップで即時停止できる。

### surface-aware 報告閾値（Tier1 #2）

`scoring-guide.md §報告マトリクス` に surface 分岐を追記する。**high-risk surface に限り**:

- CRITICAL: confidence 80 → **70**
- MAJOR: confidence 95 → **85**
- BLOCKER / MINOR は変更なし。
- **効かせる箇所を一点に特定**（design-review F5）: surface-aware 閾値は `scoring-guide.md` の適用順序の**手順 7（報告マトリクスのフィルタ）でのみ**、surface フラグ付き指摘に緩和後の閾値を適用する。手順 2〜6（反証 verdict 反映＝高 severity 非削除 / 加減算 / `[unverified] min75` / `≤40 好みクランプ`）と Phase 5.9 の specialist 反証除外は**不変**。これら precision 機構は適用順序上バラバラの位置にあるため「全部の後段」と並置せず、緩和は手順 7 の一点に限定する。

### Tier2（プロンプト追記・新 agent 定義不要）

- **敵対的入力逆算**（`reviewer-prompts.md §3 bug-detection` に追記）: 受理入力の端点（`''` / 0 / null / 最大長 / 部分入力 draft）を列挙し各々を末端の DB 制約まで前進させる。#1 直撃。
- **value-flow-trace explorer**（`explorer-prompts.md` に新 focus）: 1 つの値が schema→domain→DB / FE→BE をどう通るかを追跡し、結論を bug reviewer 1 体に集約注入。reviewer は割ったまま「一頭」を近似する。
- **帰結接続の義務化**（`reviewer-prompts.md §3 claude-md-compliance / spec-compliance`）: 「パターンの有無」でなく「共有機構が実際に呼ばれるか / 無条件規約を満たすか」まで見る。#7 直撃。
- **要注意シグナル欄**（`explorer-prompts.md §出力フォーマット`）: explorer に判定禁止のまま suspicion を運ぶ欄を追加（観察・判定でない）。

### Tier3（安価・先行投入推奨）

- spec-compliance に「契約の前提を呼び出し側で実地検証せよ」を昇格（既存「整合性の罠」注記を focus プロンプトへ）。
- メッセージ時制 × 制御フロー照合、CRITICAL 以上に「発現シナリオ / テスト未検知理由」を必須化（自己較正が上がる）。

### 変更対象ファイル

| ファイル | 変更 | Tier |
|---|---|---|
| `code-review/references/triage-guide.md` | §8 に skeptic 起動ゲート + effort 適応表 + userConfig 小節を追記 / §9 反証レイヤーと対称化 / surface 判定ロジック（INSERT/UPDATE 転用・D1-High 追加） | 1 |
| `code-review/references/scoring-guide.md` | 報告マトリクス（適用順序 手順7）に surface-aware 閾値分岐 + userConfig 節 | 1 |
| `code-review/references/reviewer-prompts.md` | §7 隣に skeptic テンプレート新設（入力契約: diff + 最小 focus、findings/reviewer 推論非注入、敵対的入力逆算の核を内挿） / §2.5 に D1-High 検出追加 / §3 に敵対的入力逆算・帰結接続義務化 | 1,2 |
| `code-review/references/explorer-prompts.md` | value-flow-trace focus 追加 / 出力に要注意シグナル欄 | 2 |
| `code-review/skills/review/SKILL.md` | skeptic Phase の起動手順 + スキップ条件（effort/userConfig/surface 非該当）+ 失敗時 missing_coverage 追記 / self-check・反証のリナンバリング | 1 |
| `code-review/skills/self-review/SKILL.md` | 上記の self-review 側（4.x）対称追加 | 1 |
| `code-review/.claude-plugin/plugin.json` | userConfig に `enable_recall_skeptic`（既定 true）追加 + version bump + description | 1 |
| `.claude-plugin/marketplace.json` | plugin.json の version/description 同期（pre-commit validate-ssot.sh がブロック） | 1 |
| `code-review/CHANGELOG.md` | Added エントリ（version bump 必須） | 1 |

## 検討した代替案

| 観点 | 案 A: meta-reviewer ゲート拡張 | 案 B: cold-read skeptic 新設（採用） | 案 C: A + value-flow explorer 前倒し |
|------|------------|------|------|
| 機構 | meta-reviewer を「severe ∨ high-risk surface」に拡張 | 反証レイヤーの鏡像で独立 skeptic を新設（meta の後・反証の前） | A + Tier2 explorer を surface で必須起動 |
| 独立性 | ✕ 全 findings 注入（fleet 盲点を引きずる） | ◎ findings 非注入で独立 | △ meta は非独立、explorer で補う |
| #1 捕捉 | △ fleet 盲点だと meta も漏らす | ◎ 冷や読みで盲点を破る | ○ 値追跡で層跨ぎ可視化 |
| 変更量 | 最小（triage §8 のみ） | 中（triage + reviewer-prompts + SKILL ×2） | 大（+ explorer-prompts） |
| 設計の対称性 | 反証と非対称のまま | ◎ 反証レイヤーと鏡像 | △ 混在 |
| 段階投入 | Tier1 で完結 | Tier1→2→3 で綺麗に段階化 | Tier2 を Tier1 に前倒し（方針違反） |

- **案 A 却下**: 最小変更だが meta-reviewer は findings 注入で非独立。fleet 全員が同じ盲点（#1 の層跨ぎ値フロー）を持つ場合、meta も同じ盲点に引きずられ #1 を確実に捕まえられない。
- **案 C 却下**: 独立性は稼げるが Tier2 の value-flow explorer を Tier1 に前倒すことになり、issue 推奨の段階投入（Tier3→2→1）に反する。コストも最大。

## 設計判断ログ

- [local] recall 補強は meta-reviewer の再ゲート（案A）ではなく、findings 非注入の独立 skeptic 新設（案B）で行う。fleet 共通盲点を破るには独立性が要るため。
- [local] skeptic の挿入位置は**相対位置**（meta-reviewer の後・反証レイヤーの前）で定義し、絶対番号（5.7/4.7）を振らない。現行 5.7/4.7 は観点カバレッジ self-check が占有済みで、番号は SKILL.md を正本に実装時リナンバリング（design-review F1・前身 doc の規約準拠）。false-negative を足す係（meta / skeptic）→ false-positive を潰す係（反証）→ フィルタ、の順序を保つ。
- [local] skeptic の model は opus（探索=弱モデルではなく独立検証=強モデル。ルーティング表準拠。反証レイヤーと同格）。
- [local] 独立性（findings 非注入・別 model）だけでは fleet 共通盲点は破れない。Tier1 skeptic に敵対的入力逆算の核を内挿し「破り方」を持たせて初めて #1 を捕捉する（design-review F7）。
- [→ADR候補→ADR-20260703155637] high-risk surface に限り precision と recall を非対称に扱う（報告閾値を surface 単位で可変にする）。全 surface 一律緩和は noise を招くため surface-aware に限定するという判断は scoring 全体の設計哲学に効く。→ ADR-20260703155637 に切り出し済み。
- [local] surface 判定は既存足場を最大限流用しつつ、不足分（通常 INSERT/UPDATE・D1-High）は新規実装する。専用の重い detector は作らず performance 観点の正規表現転用 + PR コンテキスト検出への D1-High 追加で最小実装する（design-review F2 で「完全な再利用」から訂正）。
- [local] 投入順は Tier3（プロンプトのみ）→ Tier2 → Tier1。`review:completed` の adversarial_verify 集計で偽却下率を計測してから重い Tier1 へ。

## 実装状況 (2026-07-03 / code-review v2.32.0)

Tier3（v2.30.0）→ Tier2（v2.31.0）→ **Tier1（v2.32.0）** で 3 段すべて実装完了。Tier1 で以下を追加し、frontmatter を `phase: target → current` に更新した。

- **冷や読み skeptic ラウンド**（review=Phase 5.8 / self-review=Phase 4.8）: `reviewer-prompts.md` §8 テンプレート + `triage-guide.md` §8.5 起動ゲート + 両 SKILL.md に Phase 挿入。反証レイヤーは Phase 5.9 / 4.9 にリナンバリング（`references/` `skills/` の全番号参照を更新）。
- **surface-aware 報告閾値**: `scoring-guide.md` 報告マトリクスに subsection 追加 + 適用順序 手順 7 に分岐。
- **surface 判定**: `triage-guide.md` §8.5（INSERT/UPDATE 正規表現転用 + ORM 書込 API + reviewer フラグ保険）+ `reviewer-prompts.md` §2.5 に D1-High 検出。
- **F4 例外ゲート**: `triage-guide.md` §9 に surface 緩和帯（CRITICAL 70-79 / MAJOR 85-94）を high でも反証対象に含める例外を追加。
- **userConfig** `enable_recall_skeptic`（既定 true）追加 + version bump + marketplace 同期 + CHANGELOG。
- **ADR supersede**: ADR-20260703155637 → [ADR-20260703204045](../adr/20260703204045-surface-aware-report-threshold.md)（Enforcement を「新規実装で担保」に訂正、下記 open 参照）。

open の確定（実装時に採用した方向）:

- **surface 判定粒度**: (b)+(c) 併用（正規表現転用 + D1-High + reviewer `[surface:high-risk]` フラグ保険）で確定。
- **effort=high での skeptic 起動**: (ii) xhigh/max 起点の fail-safe で確定。high 昇格は `review:completed` 頻度計測後に検討（未計測）。
- **F4 吸収ギャップ**: (a) triage §9 の例外ゲートで確定。
- **ADR Enforcement 見直し**: supersede 実施済み。

残タスク:
- **回帰 fixture は作成済み**（2026-07-04）: `evals/fixtures/recall/` に合成 fixture 3 本（01=#1 層跨ぎ値フロー recall / 07=#7 帰結接続 recall / 90=副単位ゲート precision 対照群）+ `expected.yaml`（判定ルール: recall は k=3 中 2 回以上、precision は 0 回厳格）+ `setup.sh`（temp repo 構築 + surface 判定の決定的発火チェック）+ runbook README。setup 検証済み（01=HIT raw-sql+money / 07=MISS が正解 / 90=HIT money）。
- **k=3 本計測 完了（2026-07-08, v2.33.1, GitHub issue #76）**: `evals/reports/recall-20260708.md`。**01 PASS (3/3 CRITICAL 以上) / 07 PASS (3/3 BLOCKER) / 90 PASS (パターン合致 FP 0/3) → recall 回帰 PASS**。headless でも名前空間付き `/code-review:self-review` なら skill が起動する（スモークの不起動原因はコマンド名解決だった）。副次発見 2 点: (1) **skeptic silent skip** — surface HIT 6 run 中起動 1 run のみ、かつ未起動が missing_coverage に出ない遵守バグ（GitHub issue #85）。ただし skeptic 未起動でも 01 は全捕捉で、Tier2 だけで合成 fixture 級は足りる傍証（Tier1 縮小出口条件の材料）。(2) plan mode では review:completed が publish されず #77 の集計に寄与しない。
- high での skeptic 起動昇格判断: 前提だった `recall_skeptic` payload フィールド（surface / fired / skip_reason / findings_added）は **v2.33.0 で実装済み**（2026-07-05）。skip 時も正規表現 surface 判定を必ず記録する。昇格の判断基準と jq 集計手順は `triage-guide.md` §8.5「high 昇格の判断基準」に記載。あとは xhigh 運用で events を貯めて集計するだけ（データ蓄積待ち）。

## 未解決事項 (open)

- **surface 判定の実装粒度と偽陰性リスク**: (a) INSERT/UPDATE 正規表現の転用のみ / (b) それ + D1-High 検出の OR / (c) (b) + reviewer が surface フラグを返す 3 系統。現時点の方向性: **(b)**（新規実装は要るが reviewer 往復を増やさない）。ただし正規表現は **ORM 抽象経由の DB 書込（Prisma `.create()` 等、生 SQL 文字列を含まない）を取り逃す偽陰性**があり、surface 偽陰性＝recall 補強が丸ごと発火せず設計目的未達になる（#1 は生 INSERT だったので今回は拾えるが一般には危険）。方向性: (c) の「reviewer が surface フラグを返す」を偽陰性の保険として残す。確定タイミング: Tier1 実装の triage-guide 編集時（ADR-20260703155637 の「hook 昇格しない」判断と整合させる）。
- **effort=high での skeptic 起動コスト vs fail-safe**: high 既定で high-risk surface のたび opus skeptic 1 体が増える。方向性 2 案: (i) doc 本文どおり high で起動し `review:completed` で頻度計測、過剰なら high を外す / (ii) **初版は既存 5.6/5.8 と対称に xhigh/max 起点に揃え、high への拡大は計測後に昇格**（design-review MINOR: 「後で戻す」より「後で足す」が fail-safe）。バグは xhigh で漏れたため (ii) でも当面の再発は防げる。確定タイミング: Tier1 着手前に (i)/(ii) を決める。
- **surface-aware 閾値の high での吸収ギャップ**（design-review F4）: 緩和で新規報告化する **CRITICAL 70-79 / MAJOR 85-94 は effort=high では反証レイヤー(5.8) の対象ゾーン外**（5.8 は high で CRITICAL 80-94 のみ、MAJOR は xhigh/max のみ）。つまり「二段構えで吸収」は high では成立しない。方向性: (a) surface-aware で報告化するゾーンを high でも 5.8 対象に含める例外ゲートを triage §9 に追記 / (b) surface-aware 緩和自体を xhigh/max 限定にする。有力は (a)（recall を high で稼ぐ本設計の趣旨を保つ）。確定タイミング: Tier1 の scoring/triage 編集時。副作用計測は GitHub issue #61 の review:completed 集計基盤に相乗り。
- **Tier2 で足りる場合の Tier1 打ち切り条件**（design-review MINOR）: 投入順 Tier3→2→1 で、Tier2（explorer 強化 + プロンプト追記）適用後に #1/#7 の再現 fixture が捕捉できれば Tier1 skeptic レイヤーは不要と判定する出口条件を持つ。方向性: Issue B(Tier2) 完了時に fixture で捕捉率を測り、閾値超なら Issue C(Tier1) を縮小 or 打ち切り。確定タイミング: Issue B 完了時。
- **ADR-20260703155637 の Enforcement 見直し**（design-review F2 波及）: ADR の Enforcement / 代替案却下理由が「既存 red-flag 正規表現で surface を担保」に依拠しているが、F2 で INSERT/UPDATE・D1-High は新規実装が要ると判明。方向性: 本 doc 確定後に ADR を supersede して Enforcement を「performance 正規表現転用 + D1-High 新規検出」に更新。確定タイミング: 本 doc approved 後（ADR は append-only のため訂正は supersede で行う）。

## 実装ブリッジ (Implementation Bridge)

1. **実装着手の単位**（issue 推奨の投入順 Tier3→2→1 で 3 Issue に分解）:
   - `Issue A（Tier3・先行）`: spec-compliance の契約前提の実地検証昇格 + CRITICAL 以上に発現シナリオ/テスト未検知理由を必須化。編集: `reviewer-prompts.md`。プロンプトのみ・低リスク。
   - `Issue B（Tier2）`: 敵対的入力逆算（bug-detection）+ 帰結接続義務化（claude-md/spec）+ value-flow-trace explorer + 要注意シグナル欄。編集: `reviewer-prompts.md` / `explorer-prompts.md`。
   - `Issue C（Tier1）`: 冷や読み skeptic レイヤー（相対位置＝meta の後・反証の前、番号は実装時リナンバリング）新設 + surface-aware 報告閾値（手順7）+ surface 判定の新規実装（INSERT/UPDATE 転用・D1-High 追加）+ skeptic 失敗時 missing_coverage 追記。編集: 上記「変更対象ファイル」表の全 9 ファイル（`plugin.json` userConfig / `marketplace.json` 同期 / `CHANGELOG.md` を含む）。要 version bump。
   - **順序固定**（design-review F7）: `Issue B(Tier2)` を `Issue C(Tier1)` の前提として順序固定する。#1 直撃の敵対的入力逆算の核は Tier1 skeptic テンプレに内挿するが、value-flow-trace explorer の厚みは Tier2 が支える。Issue B 完了時に fixture で #1/#7 捕捉率を測り、Tier1 の要否・粒度を再判定する（open「Tier1 打ち切り条件」）。
   - feature-dev 起動する場合: `/feature-dev code-review recall 補強 Tier1 冷や読み skeptic + surface-aware 閾値`（Issue C を主対象に、Issue B 完了後）。
2. **検証方法**:
   - #1 / #7 を再現する最小 diff を fixture 化し、Tier1 適用後の self-review が CRITICAL（#1）と MAJOR 以上（#7）を報告することを確認（recall 回帰）。
   - precision 回帰: 既存の Fable 誤検出ケース（副単位ゲート等）が引き続き非検出になることを確認（surface-aware 緩和で誤検出が復活しないこと）。
   - `evals/runner.py` でトリガー回帰（skill 選択のデグレが無いこと）。
   - `/quality-check` で allowed-tools・safe-hook 同期・references 参照整合性。
3. **実装完了時の doc 更新手順**:
   - 各 Tier 完了ごとに本 doc の該当セクションに実装コミット/version を追記。
   - Tier1 まで完了で frontmatter `phase: target` → `current`、`last-validated` を更新。
   - 実装が方式ごと変わった場合（例: skeptic を別 Phase に置く判断に転換）は supersede。

## 関連

- 関連 Issue: [GitHub issue #75](https://github.com/yuuki1036/claude-plugins/issues/75)（high-risk コードでの実バグ見落とし）、[#61](https://github.com/yuuki1036/claude-plugins/issues/61)（review:completed 計測基盤）
- 関連 spec: null
- 関連 ADR: [ADR-20260703155637](../adr/20260703155637-surface-aware-report-threshold.md)（surface-aware 報告閾値。この doc の [→ADR候補] から切り出し）
- 関連 design doc: [[20260623-review-adversarial-verify-layer]]（precision 側 = false-positive 潰し。本 doc はその recall 側鏡像）、[[20260624-code-review-doc-substance-perspective]]（doc 観点・同じ triage/scoring を編集）
