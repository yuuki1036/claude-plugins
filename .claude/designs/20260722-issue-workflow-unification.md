---
id: 20260722-issue-workflow-unification
title: linear/indie ワークフロープラグインの単一プラグイン統合（backend 分岐）
status: approved
phase: current
last-validated: 2026-07-23
supersedes: []
superseded-by: null
issue: null
spec: null
adrs: [20260722164106]
tags: [architecture, plugin-consolidation, linear-workflow, indie-workflow]
---

# linear/indie ワークフロープラグインの単一プラグイン統合（backend 分岐）

## TL;DR

linear-workflow / indie-workflow の 2 プラグイン体制を廃止し、新プラグイン `issue-workflow` に統合する。backend（local / linear）はデータディレクトリの存在で自動判定し、SKILL.md 内の条件分岐で差分を表現する。ミラー規約・片方向同期スクリプト・drift 検証は統合により機構ごと撤去する。

## 背景 / 課題

2026-07 のリポジトリ全体精査で、2 プラグイン体制の維持コストが実測された:

- 共有スキルペア 9 組は linear 側 3,036 行中 52%（1,572 行）が完全一致行の人手複製
- linear を触った 64 コミット中 69% が indie も同時変更（恒常的な二重メンテ）
- 機械同期（片方向 10 ファイル）の変換は sed 4 ルールのみ。差分の大半は意味的でなく語彙的
- 人手対称反映は現に破れている: linear 側「即クローズパターン検出」が references 分割時に脱落（CHANGELOG 1.34.0 に追加記録があるのに現行ファイルに不在）。detection-guards の細部 drift 3 箇所、放置 Issue 検知・scope_size 一式の未文書化非対称も検出
- 規約維持のメタコスト: MIRROR_SKILL_PAIRS / MIRROR_INTENTIONAL_* 対応表、sync-linear-from-indie.sh（153 行）、CI drift check、CLAUDE.md のミラー規約（約 30 行）+ Gotchas 複数項目

複製の根本原因は「プラグイン間依存禁止」の制約下で 2 つの成果物に分けたことにある。同一プラグイン内の分岐なら制約に抵触せず、複製も同期機構も不要になる。

## ゴール / 非ゴール

- **ゴール**: 二重メンテ（linear 関連コミットの 69% が両側同時変更）の解消と、ミラー検証機構の全撤去。機能は現状の和集合を維持する
- **非ゴール**: 機能追加・Phase 構成の改善（統合と混ぜると検証不能になるため。統合は挙動等価の移送に徹する）。ただし**意図的逸脱 2 点**を例外として明示管理する: ① indie 専用機能（discover / retrospective / scope_size hook）の両 backend 開放【grill で確定】、② check-deps.sh の backend ゲート新規実装（下記 hooks 統合）。いずれも CHANGELOG に挙動変更として明記する
- **非ゴール**: データディレクトリの統一（`.claude/indie` / `.claude/linear` の rename は移行コストに見合わない。既存パスを backend マーカーとして温存する。副次的利点として、code-review 等が行う `.claude/indie` / `.claude/linear` の dir スキャン連携が無改修で維持される）

## 確定した前提

grill で確定（コード調査 + ユーザー確認）:

1. **器**: 新プラグイン `issue-workflow` を新設（indie-workflow を母体にコピー）。version 1.0.0 から再出発【ユーザー確定】
2. **backend 判定**: データ dir の存在で自動判定。`.claude/indie/` → local、`.claude/linear/` → linear。設定ファイルは導入しない【ユーザー確定】
3. **命名**: prefix なし統一名（issue-create / start / maintain / discover / retrospective 等）。コマンドは `/issue-workflow:xxx` の namespace で衝突回避【ユーザー確定】
4. **機能ゲート**: indie 専用だった discover / retrospective / scope_size は初版から両 backend に開放（いずれもローカルファイル読取のみで Linear API 非依存であることをコードで確認済み）。これは linear backend にとって新規挙動であり、挙動等価移送に対する意図的逸脱 ① として非ゴール節で明示管理する【ユーザー確定】
5. **旧プラグイン**: deprecated 明記で短期併存 → 全マシン移行確認後に削除。ただし「併存」はマーケットプレイス掲載の併存であり、**同一マシンでの新旧同時 install は禁止**（移行手順 6 の順序制御を参照）【ユーザー確定 + design review で具体化】
6. linear MCP 依存は統合後 `required: false` に落とし、backend=linear 検出時のみ check-deps で警告する（現 linear-workflow は required: true。出典: linear-workflow/.claude-plugin/plugin.json）。この実現には check_mcp 関数の移植 + backend 条件分岐の**新規実装**が必要（indie 側 check-deps.sh に check_mcp は存在しない。出典: indie-workflow/hooks/scripts/check-deps.sh）
7. 固有機能の内訳（出典: diff -rq 実測）: linear 固有 = dashboard / linear-maintain / linear-sync agent / linear-syntax.md。indie 固有 = indie-issue-discover + discover-verifier agent / retrospective / check-scope-size hook
8. 両プラグインとも全マシンにインストール済み・enabled（出典: ~/.claude/settings.json）
9. scope_size の必須範囲は create 本文（feature のみ）とテンプレ・discover・hook・retrospective（全 type 前提）で矛盾している（精査で検出済み）。この修正は統合に**先行して** indie 側で独立に行い、統合時の等価移送の対照は修正後の状態とする（design review 反映: 移送の純度維持）

## 採用案

### アーキテクチャ

```
issue-workflow/
  .claude-plugin/plugin.json      # linear MCP は required: false
  skills/
    init/          # backend 選択（AskUserQuestion）→ 対応 dir 作成
    start/         # 旧 session-start / indie-start
    issue-create/  issue-design/  issue-maintain/
    follow-up/     knowledge/     knowledge-lint/  maintain/
    discover/      retrospective/               # 両 backend 開放
    dashboard/     linear-maintain/             # linear backend 専用（local 時は案内終了）
  agents/
    code-context.md  doc-resolver.md  discover-verifier.md
    linear-sync.md                               # linear backend 専用
  hooks/           # indie 側を母体に、パスパターンを .claude/(indie|linear)/ 両対応化
```

### backend 検出（全スキル共通の前段）

各スキルの Phase 0 相当に共通手順を置く:

1. **有効 backend の判定述語（SKILL と hook で共通）**: 「データ dir が存在し、かつ配下に 1 つ以上のプロジェクト slug dir を持つ」を有効とする。SKILL 側は Glob `.claude/indie/*/` `.claude/linear/*/`、hook 側も同一条件（`-d` + glob）で判定を揃える。init がプロジェクト slug dir を作成した時点を「backend 確定」とする（design review 反映: 述語不一致の解消）
2. indie のみ有効 → `BACKEND=local`, `DATA_DIR=.claude/indie`。linear のみ有効 → `BACKEND=linear`, `DATA_DIR=.claude/linear`
3. **両方とも有効（両方に slug dir がある）** → エラーとして停止し、片寄せを案内（現行の「排他警告」から昇格）。**片方が空 dir・残骸の場合は停止しない**: 警告を出しつつ有効側を採用して継続する（design review 反映: 残骸 dir 1 つで全機能停止する可用性回帰を防ぐ。判定述語 1 が「非空」を要求するため、`.gitkeep` や消し忘れの空 dir はそもそも有効 backend にならない）
4. どちらも無効 → init への誘導を表示して終了

以後の本文は `DATA_DIR` / `BACKEND` を使って記述する。sed 4 ルールで吸収されていた語彙差分（`.claude/indie` ↔ `.claude/linear` 等）はこの変数化で消える。

### 差分の表現方法

- **語彙差分（旧 sed 変換相当）**: `DATA_DIR` 変数化で吸収
- **linear 固有 Phase（Linear MCP 同期・linear-syntax 準拠等)**: SKILL.md 内に「BACKEND=linear のときのみ」の条件付き Phase として記述
- **linear 専用スキル（dashboard / linear-maintain）**: スキルとして残し、起動時に BACKEND=local なら「このスキルは Linear 連携プロジェクト専用」と案内して終了（dormant 検出と同型のガード）

### hooks 統合

- indie 側 6 hook を母体に、on-issue-change / on-knowledge-change / set-session-title のパスパターンを両 dir 対応化
- inject-rules は backend 検出後に knowledge index + 放置 Issue 検知を注入（放置 Issue 検知は linear にも開放 = 前提 4 と一貫）
- check-scope-size は両 backend 対応（scope_size の全 type 必須化は前提 9 のとおり統合前に indie 側で修正済みの状態を移送する）
- **check-deps.sh**: linear 側から check_mcp 関数を移植し、「backend=linear が有効なときのみ linear MCP を警告」の条件分岐を新規実装する（前提 6。意図的逸脱 ② として CHANGELOG 明記）

### 変更対象（統合の主目的）

**機構撤去**:

| 対象 | 場所 |
|---|---|
| sync-linear-from-indie.sh | .claude-plugin/scripts/ |
| MIRROR_SKILL_PAIRS / MIRROR_INTENTIONAL_*_ONLY / COMMAND_SKILL_ALIASES の indie/linear 行 | validate_plugin_quality.py |
| CI の drift check ステップ | .github/workflows/validate.yml |
| auto-quality-check.sh の sync --check 呼び出し | .claude-plugin/scripts/ |
| ミラー規約セクション + 関連 Gotchas | CLAUDE.md |
| routing-axes 消費サイト 2 箇所（linear/indie issue-create）→ 1 箇所（issue-workflow） | .claude-plugin/lib/routing-axes.md の同期表 |

**参照更新**（design review 反映: 網羅漏れの補完。CHANGELOG 等の履歴文書は更新しない）:

| 対象 | 内容 |
|---|---|
| .github/ISSUE_TEMPLATE/enhancement.yml / bug.yml | プラグイン選択肢の indie-workflow / linear-workflow → issue-workflow |
| .claude/skills/quality-check/SKILL.md | 15c ミラー対称性チェック節の削除、routing-axes 消費サイト一覧の更新 |
| docs/shared-state.md | producer 表の linear-workflow / indie-workflow → issue-workflow |
| docs/pipeline-design.md | 例示パス `indie-workflow/skills/indie-issue-discover` の更新 |
| failure-journal（log-failure / retro の SKILL.md、README） | `indie-workflow:retrospective` 名指し → `issue-workflow:retrospective` |
| code-review（orchestration-guide.md、review SKILL.md） | 「linear-workflow・indie-workflow 併用時」等の散文参照の更新（dir スキャン部分は dir 名温存により無改修） |
| CLAUDE.md | プラグイン一覧表（2 行 → 1 行）、Event Bus 規約表の publisher/subscriber 名 |
| INDEX.md / marketplace.json | 一覧の差し替え |

### 移行手順

0. **先行修正（統合前・独立コミット）**: scope_size の必須範囲矛盾を indie 側で修正する（前提 9。等価移送の対照を確定させる）
1. `issue-workflow/` を indie-workflow ベースで作成（命名統一 + backend 検出 Phase 追加）
2. linear 固有機能（dashboard / linear-maintain / linear-sync / linear-syntax.md / Linear 同期 Phase）を移植
3. hooks 統合（check-deps.sh の backend ゲート新規実装を含む）
4. eval 統合（linear 12 + indie 14 → 統合ケースに改廃）・marketplace.json 掲載・参照更新（上表）
5. 検証機構の撤去（上表）+ CLAUDE.md / INDEX.md 更新
6. 旧 2 プラグインの description に「deprecated: issue-workflow へ移行」を明記して最終バンプ
7. **各マシンで「旧 2 つを uninstall → issue-workflow を install」を連続実行する（新旧の同時 install を禁止する）**。理由: 新プラグインは indie 母体のため、同居すると SessionStart / FileChanged / PostToolUse hook が同一 `.claude/indie` に対して二重発火し、prefix なし統一名によりトリガーフレーズも衝突する（design review 反映）。plugin-manager の後発追加通知が導線
8. **全マシン移行の確認は機械化する**: 移行チェックリスト（マシン名を列挙した md）をリポジトリに置き、各マシンで移行実施時にチェックを入れてコミットする。全チェック後に旧 2 ディレクトリを削除（独立コミット）。**ロールバック**: 未移行マシンが後から見つかった場合は削除コミットを revert すれば marketplace 解決先が復活する。削除コミットは他の変更と混ぜない（design review 反映）

## 検討した代替案

| 観点 | 案 A: 新設 issue-workflow（採用） | 案 B: indie-workflow を母体に吸収 | 案 C: 統合せず完全片方向生成 |
|------|------|------|------|
| 名前と実態の一致 | ○ 名前が機能を表す | × 「indie」が Linear backend を含む | ○ 現状維持 |
| 移行作業 | 両プラグインの入替（一度きり） | linear 側のみ | 不要 |
| バージョニング | 1.0.0 再出発で解釈問題なし | スキル名維持なら non-breaking も可 | 影響なし |
| 二重メンテ税の解消 | ○ 完全解消 | ○ 完全解消 | △ 編集は解消、生成インフラ保守が残る |
| 固有機能の分岐表現 | ○ SKILL 内条件分岐 | ○ 同左 | × sed では表現しきれない箇所が出る |

- 案 B 不採用の理由: スキル名を維持すれば non-breaking にできる（当初の「どのみち MAJOR 破壊的変更」という評価は過大だった。design review 反映）。それでも不採用とするのは、「indie」というプラグイン名と indie- prefix のスキル名が Linear backend に恒久に残るため。移行コストは一度きりだが命名の misleading は恒久であり、利用者 1 人の今が最も安く直せるタイミングと判断した
- 案 C 不採用の理由: ユーザー視点の変更はゼロだが、SHARED/TRANSFORM 全域化という生成インフラの保守が残り、メタ層縮小という本来の目的を達成できない

## 設計判断ログ

- [→ADR候補] 機能の対称性が必要な場合、別プラグインのミラーではなく同一プラグイン内の backend 分岐で表現する（ミラー規約という機構自体を廃止する決定。プラグイン間依存禁止の制約下で複製が発生したら、それは分割単位の誤りを示すシグナルとして扱う）※ADR-20260722164106 に切り出し済み
- [local] backend は設定ファイルでなくデータ dir の存在で判定する（新しい状態ファイルを増やさない。既存プロジェクトの移行コストをゼロにする）
- [local] discover / retrospective / scope_size は両 backend に開放する（Linear API 非依存であることをコードで確認済み。ゲートを外すことで「意図的非対称リスト」という管理項目自体を消す）
- [local] 統合は挙動等価の移送を原則とし、意図的逸脱は非ゴール節に列挙した 2 点（indie 専用機能の開放 / check-deps の backend ゲート新規実装）に限定する。scope_size 矛盾修正は統合前の先行修正に分離し、逸脱に含めない（design review 反映）
- [local] 新旧プラグインの同一マシン併存を禁止し、マシン単位で uninstall → install を原子的に行う（同居時の hook 二重発火・トリガー衝突を構造的に回避する。design review 反映）
- [local] 両データ dir 同居のハードストップは「両方に slug dir がある」場合に限定し、空 dir・残骸では警告 + 継続とする（可用性の回帰を防ぐ。design review 反映）

## 未解決事項 (open)

1. **eval ケースの統合粒度**: (a) 26 ケースを機械的に改名移送 / (b) backend 使い分けフレーズが不要になった分を削って再設計。有力: (b) — 「Linear で」「ローカルで」の使い分けテストが不要になるため 20 ケース前後に減らせる見込み。確定タイミング: 移行手順 4 の着手時
2. **両 dir 同居（両方有効）時のエラー文言と復旧手順**: 片寄せの具体手順（どちらを正にするかの判断材料）をエラーに含めるか。有力: 含める（issue 件数と最終更新日を並べて提示）。確定タイミング: backend 検出の実装時
3. **linear-maintain の改名**: linear 固有スキルなので backend 名を含む現名維持が有力（「linear と同期する」機能の名前として正確）。対抗案は `sync`。確定タイミング: 移行手順 2 の着手時

## 実装ブリッジ (Implementation Bridge)

1. **実装着手の単位**（Issue 分解案、依存順）:
   0. `scope_size 必須範囲の矛盾修正（indie 側・統合前の先行独立コミット）`
   1. `issue-workflow スケルトン作成`（indie コピー + 命名統一 + backend 検出 Phase。この時点で quality-check が通ること）
   2. `linear 固有機能の移植`（dashboard / linear-maintain / linear-sync / Linear 同期 Phase / linear-syntax.md）
   3. `hooks 統合（check-deps backend ゲート新規実装を含む）`
   4. `eval 統合・marketplace 掲載・参照更新`
   5. `検証機構の撤去と CLAUDE.md / INDEX.md 更新`
   6. `旧 2 プラグイン deprecated 化`
   7. `全マシン移行（チェックリスト md 運用）→ 旧ディレクトリ削除`（6 の 1〜2 週間後、独立コミット・revert 可能）
   - または一気通貫: `/feature-dev issue-workflow 統合（linear/indie 廃止・backend 分岐） spec=.claude/designs/20260722-issue-workflow-unification.md`
2. **検証方法**:
   - `/quality-check` 全 pass（撤去した検証項目が error にならないこと含む）
   - eval pass^k=3（統合後トリガーフレーズで issue-workflow のスキルが選択されること）。**実行は旧 2 プラグインを uninstall 済みの状態で行う**（同居中は旧側への名前解決で flaky になるため。design review 反映）
   - 両 backend のスモーク: `.claude/indie` 持ちプロジェクトと `.claude/linear` 持ちプロジェクトで start / issue-create / issue-maintain を実走
   - 機能の和集合チェック: 精査で検出した linear 側欠落（即クローズパターン検出）が統合版に存在すること
3. **実装完了時の doc 更新手順**: frontmatter の `phase: target` → `current`、`last-validated` 更新。移行手順 8（旧削除）完了時に「関連」へ削除コミット hash を追記

## 関連

- 関連 Issue: なし（本 doc が起点。実装ブリッジの Issue 分解案から起票する）
- 移行チェックリスト: `docs/issue-workflow-migration.md`（手順 7〜8 の全マシン移行管理。実装は手順 0〜6 まで完了済み = 2026-07-23）
- 関連 spec: なし
- 関連 ADR: [[20260722164106-backend-branch-over-plugin-mirror]]（ミラー規約廃止の決定）
- 関連 design doc: [[20260708-spec-routing-ssot]]（routing-axes 消費サイトが 4→3 に減る影響あり）
- design review: 2026-07-22 実施（minimal / pragmatic / risk 3 視点 + 独立反証。MAJOR 6 / MINOR 3 を全件反映済み）
