---
name: design-doc
description: >
  技術設計書 (design doc / RFC 相当) を実装に入らず作成・永続化するスキル。
  grill で前提を確定し、代替案のトレードオフ比較から採用案を `.claude/designs/` に保存する。
  実装ブリッジ (Implementation Bridge) セクション必須化と supersede 機械化で死に文書化を防ぐ。
  Issue 1 件の作業設計は issue-design、振る舞い仕様 (WHAT) は bdd-spec、単一決定の記録は adr-keeper、
  実装込みの開発は feature-dev に任せる（このスキルは HOW の設計とその永続化に専念する）。
  トリガー: 「設計書作って」「design doc」「技術設計書」「RFC 書きたい」「設計ドキュメント作成」
  「実装せず設計だけ詰めたい」「設計を文書化」「design doc supersede」「設計書一覧」「/design-doc」
effort: medium
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - Skill
  - AskUserQuestion
---

# Design Doc

技術設計書 (design doc) を **実装フェーズなし**で作成・永続化するスキル。代替案比較と設計判断を `.claude/designs/` に面で残し、ADR（点の決定記録）・spec.md（WHAT）・実装（feature-dev）への接続点を機械的に埋めさせる。

## いつ使う / いつ使わない

| 状況 | 使うスキル |
|------|-----------|
| タスクを跨ぐ技術設計（アーキテクチャ・データフロー・移行戦略）を文書化したい | **design-doc**（本スキル） |
| 既存 design doc の改訂・supersede・一覧 | **design-doc**（本スキル） |
| Issue 1 件の作業設計（9 セクション・決定/open の仕分け） | `indie-workflow:issue-design` |
| 振る舞い仕様（Feature/Scenario/Examples = WHAT）を書く | `bdd-spec:create-spec` |
| 単一の設計判断（WHY）だけを点で記録する | `adr-keeper:adr` |
| 設計から実装まで一気通貫で進める | `feature-dev` |

> 「決定 1 件だけ残したい」と分かったら adr-keeper に案内して終了する。逆に grill の途中で実装着手の意思が明確になったら、それまでの確定前提を提示して feature-dev への切替を案内する。

## 参照する規範（references）

- `${CLAUDE_SKILL_DIR}/references/template.md` — doc 本文テンプレ + frontmatter 雛形（プレースホルダ方式）
- `${CLAUDE_SKILL_DIR}/references/naming.md` — 配置パス・命名・改訂 vs supersede の判断基準
- `${CLAUDE_SKILL_DIR}/references/grill-protocol.md` — grill 3 原則（正本は feature-dev、byte-identical 複製）
- `${CLAUDE_SKILL_DIR}/references/section-guide.md` — 各セクションの書き方とアンチパターン

---

## Phase 0: 保存先確認 + サブコマンド判定

1. `.claude/designs/` の存在を確認（Glob または Bash の `test -d`）。不在なら作成:
   ```bash
   mkdir -p .claude/designs
   ```
   design doc は **committed 前提**（プロジェクトローカルに永続化）
2. 引数を解析してモードに振り分ける:

| サブコマンド / モード | 引数 | 遷移先 |
|---|---|---|
| `new`（または未指定） | `[title]` | Phase 1 |
| `list` | - | list フロー |
| `supersede` | `<old-id> <new-title>` | supersede フロー |
| `mode=export` | `title=... content=...`（下記 API 契約） | export フロー |

> export は他プラグイン連携用の**非対話 API** で、`mode=export` を正のキーとする（呼び出し元の feature-dev / issue-design は `mode=export` を渡す）。先頭語 `export`（`export title=...`）で来た場合も同じフローに振り分けて受理する（後方互換）。

---

## Phase 1: 入力収集（dormant 検出はここに集約）

設計の入力になる既存成果物を検出して Read する。**いずれも不在なら会話文脈のみで進む**（エラーにしない）。

1. **Issue ファイル**: `.claude/indie/*/issues/*.md` / `.claude/linear/*/issues/*.md` をテーマに関連するものに絞って Glob（プラグイン呼び出し不要のファイル直読み）。見つかれば frontmatter の `issue:` に相対パスを記録する
2. **BDD spec**: `features/**/spec.md` を Glob。テーマに合致する spec があれば **authoritative な WHAT** として Read し、`spec:` に記録する。Scenario の生成・編集は一切しない
   - spec が無く、振る舞い仕様が曖昧なテーマの場合、bdd-spec の存在を判定:
     ```bash
     if grep -q '"bdd-spec@' "$HOME/.claude/settings.json" 2>/dev/null; then BDD_SPEC=1; else BDD_SPEC=0; fi
     ```
     `BDD_SPEC=1` なら AskUserQuestion で「先に spec.md を作るか」確認し、作る場合は `bdd-spec:create-spec` を非対話引数（`role`/`want`/`why`）で呼ぶ。`BDD_SPEC=0` または「作らない」なら skip
3. **既存 design doc**: `.claude/designs/*.md` を Glob し、同テーマの doc がないか frontmatter の `title` / `tags` で確認。**同テーマの doc が存在する場合**は AskUserQuestion で確認:
   - question: 「同テーマの design doc が既にあります。どう扱いますか？」
   - header: 「既存 doc」
   - options:
     1. label: 「改訂 (Recommended)」 / description: 「既存 doc を Edit で更新（方式は維持したまま詳細化・追記。last-validated を更新）」
     2. label: 「supersede」 / description: 「方式転換。新 doc を作成し旧 doc を superseded に更新」
     3. label: 「別 doc として作成」 / description: 「スコープが別物。独立した doc を新規作成」
   - 改訂 vs supersede の判断基準は `references/naming.md` を提示する

---

## Phase 2: 軽量コードベース探索（read-only）

採用案の前提になる既存実装・制約を Grep / Glob / Read で把握する。

- 対象: 関連モジュールの構造、既存の類似パターン、依存ライブラリ、既存 ADR（`.claude/adr/*.md`）
- ここで判明した事実は Phase 4 の「確定した前提」の材料になる
- **agent は起動しない**。広範な探索（複数サブシステム横断）が必要なテーマと判明したら、feature-dev（explorer agent あり）への切替を案内する

---

## Phase 3: grill（前提と要求の確定）

`references/grill-protocol.md` を Read して適用する。

1. **自己解決（原則①）**: 設計を左右する問いのうち、コード・既存 ADR・spec.md・Issue で決着済みのものは自分で調べて「確定した前提」に移す（ユーザーに聞かない。黙って仮定もしない）
2. **1 問ずつ依存順（原則②）**: 残った問いを design tree の依存順に並べ、AskUserQuestion で 1 問ずつ確認する。回答のたびに残りの問いを再評価する
3. **推奨つき（原則③）**: 各質問の先頭 option に推奨案 + `(Recommended)` + 1 行理由を添える
4. **過剰質問を避ける**: 残 1〜2 問で方向が明確なら 1 回の提示にまとめる

---

## Phase 4: 設計案作成

1. 代替案を **2〜3 案**作り、トレードオフ比較表（変更量 / 複雑性 / 拡張性 / リスク等、テーマに合う軸）に整理する
2. 推奨案と理由を 1 行で明示する
3. AskUserQuestion で採用案を確定する（推奨案を先頭に `(Recommended)`）
4. 採用案について、アーキテクチャ・データフロー・変更対象ファイル・移行手順を具体化する

> 複数 agent による多視点比較は行わない（単一コンテキストの軽量版）。多視点が必要な規模なら feature-dev Phase 4 を案内する。

---

## Phase 5: doc 書き出し

1. **日付取得**（必ず Bash で取る。擬似日付を作らない）:
   ```bash
   date +%Y%m%d   # ファイル名・id 用
   date +%Y-%m-%d # last-validated 用
   ```
2. **kebab slug 生成**: タイトルから英語の要約 slug を作る（`references/naming.md`）。`.claude/designs/<YYYYMMDD>-<slug>.md` の衝突を Glob で確認し、衝突時は `-2` サフィックス
3. `references/template.md` を Read し、プレースホルダを置換して Write する
4. **実装ブリッジ (Implementation Bridge) は必ず埋める**（空欄禁止）:
   - 実装着手の単位（Issue 分解案、または `feature-dev <要約> spec=<path>` 形式のコピペ可能な起動引数）
   - 実装と doc の一致をどう検証するか
   - 実装完了時の doc 更新手順（`phase: target → current`）
   - 書けない場合は**書けない理由と確定タイミング**を残す（例: 「PoC 未了のため Issue 分解不能。確定タイミング: PoC 後」）
5. **writing-polish 連携（opt-in・dormant）**: 提示直前に判定:
   ```bash
   if grep -q '"writing-polish@' "$HOME/.claude/settings.json" 2>/dev/null; then WRITING_POLISH=1; else WRITING_POLISH=0; fi
   ```
   `WRITING_POLISH=1` なら `Skill` tool で `writing-polish:writing-polish` を `--embed --tone rfc` で呼び、散文部分のみ推敲する。**frontmatter・セクション構造・表・コードブロックは変更しない。構造を壊す結果は破棄して元案を使う**。失敗時は warning を出し推敲前の本文で続行
6. 本文をユーザーに提示し、承認を得てから Write する

> **Write / Edit の対象は原則 `.claude/designs/` 配下のみ**。このスキルはソースコード・設定ファイルを編集しない（設計専用の規律）。**例外**: Phase 6 の ADR 相互リンク追記時のみ、切り出した ADR ファイル（`.claude/adr/*.md`）の「関連」セクションの該当行を Edit してよい（doc ↔ ADR の相互参照を成立させるため）。それ以外の ADR 本文編集はしない。

---

## Phase 6: ADR 切り出し（adr-keeper dormant）

1. doc の「設計判断ログ」から `[→ADR候補]` マーカーの付いた判断を列挙する
2. adr-keeper の存在を判定:
   ```bash
   if grep -q '"adr-keeper@' "$HOME/.claude/settings.json" 2>/dev/null; then ADR_KEEPER=1; else ADR_KEEPER=0; fi
   ```
3. `ADR_KEEPER=1` かつ候補が 1 件以上 → AskUserQuestion で切り出す候補を確認（multiSelect）し、承認分を `Skill` tool で `adr-keeper:adr` の `new <title>` として作成する。作成した ADR の id を doc 側 frontmatter の `adrs:` に追記し、ADR 側「関連」にも doc パスを記録する（相互リンク）
4. `ADR_KEEPER=0` → 切り出しは skip。`[→ADR候補]` マーカーは doc に残す（後から adr-keeper 導入時に拾える）

---

## Phase 7: 完了報告

```
✅ design doc を作成しました

📄 .claude/designs/<YYYYMMDD>-<slug>.md
  status: draft / phase: target

次のアクション:
- 実装前のレビュー: /design-review <id>（複数視点の静的レビューで draft → approved の判断材料に）
- 実装に進む場合: /feature-dev <要約> spec=<spec パス（あれば）>
- 未解決事項 (open) の確定タイミング: <一覧>
- ADR 未切り出しの [→ADR候補]: <残があれば一覧>
- 実装完了時: phase を current に更新し、乖離があれば追記 or supersede
```

---

## list フロー

1. `.claude/designs/*.md` を Glob。0 件なら「design doc がまだありません」と報告して終了
2. 各ファイルの frontmatter を Read し、`id` / `title` / `status` / `phase` / `last-validated` を抽出
3. **id 降順**（新しい順）の表に整形して表示

---

## supersede フロー

方式転換時に旧 doc を新 doc で置き換える。「新規作成 + 旧 doc 更新 + 相互参照確認」を機械的に踏ませる（adr-keeper Phase 4 と同じ機構）。

1. **旧 doc 特定**: `.claude/designs/*<old-id>*.md` を Glob。見つからなければ error として中止
2. **最終確認（AskUserQuestion）**: supersede は旧 doc を superseded に落とす後戻りしにくい操作。誤った old-id 指定による別 doc の巻き込みを防ぐため、特定した旧 doc の id / title / 現 status を提示して実行可否を確認する（Phase 1 の既存 doc 検出時の確認と対称にする）:
   - question: 「design doc <old-id>「<title>」（現 status: <status>）を superseded にして新 doc で置き換えますか？」
   - header: 「supersede 確認」
   - options:
     1. label: 「supersede 実行 (Recommended)」 / description: 「旧 doc を superseded に更新し、新 doc を作成する」
     2. label: 「中止」 / description: 「何も変更しない（旧 doc はそのまま残す）」
   - 「中止」が選ばれたら一切変更せず終了する
3. **新 doc 作成**（Phase 1〜5 の通常フロー。軽量に済ませてよいが grill の自己解決と実装ブリッジは省略しない）。frontmatter の `supersedes` に `["<old-id>"]` を入れる
4. **旧 doc を Edit**（4 箇所）:
   - `status:` → `superseded`
   - `phase:` → `superseded`
   - `superseded-by:` → `<new-id>`
   - `last-validated:` → 本日（`date +%Y-%m-%d`）
5. **両方を Read で確認**: 新 doc の `supersedes` と旧 doc の `superseded-by` が相互参照になっていることを検証
6. 旧 doc は**削除しない**（append-only 原則: 履歴として残し status / phase のみ更新）

> 改訂（同一方式のまま詳細化・追記）なら supersede せず既存 doc を Edit して `last-validated` を更新する。境界は `references/naming.md`。

---

## export フロー（API 安定保証・他プラグイン連携用）

他プラグイン（feature-dev 等）からの `Skill design-doc:design-doc` 呼び出しを安定 API として扱う。grill / 設計フェーズを全 skip し、doc 化のみ実行する。

| 引数キー | 必須 | 説明 |
|---|---|---|
| `mode=export` | yes | export モード指定 |
| `title` | yes | doc タイトル（原文ママ） |
| `content` | yes | 採用案 + 代替案比較を含む本文（呼び出し元が整形済み） |
| `issue` | no | 関連 Issue の相対パス / ID（frontmatter に転記） |
| `spec` | no | spec.md の相対パス（frontmatter に転記） |
| `status` | no | 既定 `draft` |

1. 必須引数が欠けていれば error を返して中止（AskUserQuestion にフォールバックしない。呼び出し元の fallback に委ねる）
2. Phase 5 の手順（日付取得 → slug → template 置換 → Write）で書き出す。`content` をテンプレの該当セクションにマッピングし、マッピングできない部分は「採用案」に置く
3. **実装ブリッジが content に含まれない場合**: 「呼び出し元ワークフロー内で実装に継続するため省略」と自動記入する
4. **引数が全て埋まっていれば AskUserQuestion を一切発火しない**（writing-polish / adr-keeper 連携も skip）
5. 書き出したファイルパスを報告して終了（呼び出し元がパスを利用する）

---

## 処理フロー

```
1. Phase 0: .claude/designs/ 確認 + サブコマンド判定（new / list / supersede / export）
2. Phase 1: 入力収集（Issue / spec.md / 既存 doc の検出。既存 doc あれば改訂/supersede/別doc を確認）
3. Phase 2: read-only コードベース探索（既存パターン・制約・ADR の把握）
4. Phase 3: grill（自己解決 → 依存順 1 問ずつ・推奨つき）
5. Phase 4: 代替案 2〜3 + トレードオフ比較表 → 採用案確定
6. Phase 5: template 置換 → 実装ブリッジ必須 → writing-polish（dormant）→ 承認 → Write
7. Phase 6: [→ADR候補] を adr-keeper へ切り出し（dormant）
8. Phase 7: 完了報告
```

---

## 注意事項

- **日付は必ず Bash で取得**: `date +%Y%m%d` / `date +%Y-%m-%d` を実行する。擬似日付を作らない
- **実装ブリッジ必須**: design doc の死に方は「書いたが実装に接続されず腐る」。実装への接続情報と完了時の phase 遷移手順を必ず残す（書けない場合は理由 + 確定タイミング）
- **コードを編集しない**: Write / Edit の対象は原則 `.claude/designs/` 配下のみ。実装は feature-dev の領分。唯一の例外は Phase 6 の ADR 相互リンク追記（`.claude/adr/*.md` の「関連」該当行のみ Edit）
- **doc-freshness との住み分け**: 本スキルは作成・命名・supersede 整合のみ担当。鮮度 lint は doc-freshness が `.claude/designs/` を走査して担う。frontmatter（`last-validated` / `phase`）は doc-freshness 互換
- **status と phase は別次元**: `status` は合意状態（draft → approved → superseded）、`phase` はライフサイクル（target = 未実装 → current = 実装済 → superseded）。設計中の塩漬けは `phase: target` の stale 閾値（15 日）で doc-freshness が検出する
- **grill-protocol.md は複製**: 正本は feature-dev の `references/grill-protocol.md`。プラグイン間依存禁止のため byte-identical に複製している（safe-hook.sh と同じ運用）。正本が更新されたら同期する
