---
name: discover
description: >
  プロジェクトを AI が多観点でスキャンし、取り組むべき課題（バグ・未実装機能・技術的負債）を発見して issue として自動起票する。優先度上位を起票し、残りは backlog に蓄積する。
  トリガー: 「課題を見つけて」「issue を自動で作って」「やることを洗い出して」「バグを探して起票」「タスク発掘」「何かやることない？」「課題発見」「/discover」
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
  - Bash
  - Skill
  - Agent
---

# discover — AI 主導の課題発見・自動起票

プロジェクトを多観点でスキャンし、**AI が「次に取り組むべき課題」を能動的に発見して issue を自動起票する**スキル。「何をやるか」を人間が考える負担を AI に移譲するのが目的。

## Phase 0: backend 検出（全スキル共通）

1. Glob で `.claude/indie/*/` と `.claude/linear/*/` を確認する。「dir が存在し、かつプロジェクト slug サブディレクトリを 1 つ以上持つ」場合のみ有効な backend とみなす（空 dir・残骸は無効）
2. `.claude/indie` のみ有効 → `BACKEND=local` / `DATA_DIR=.claude/indie`。`.claude/linear` のみ有効 → `BACKEND=linear` / `DATA_DIR=.claude/linear`。無効な残骸 dir がもう一方にある場合は警告を一言添えて継続する
3. **両方有効** → エラーとして停止する。両 dir の slug 一覧・issues 件数・最終更新日を並べて提示し、どちらを正とするか決めて他方を退避（rename）または削除する片寄せを案内する
4. **どちらも無効** → `/issue-workflow:init` の実行を案内して終了する

以後の `{DATA_DIR}` は検出したデータディレクトリ、`BACKEND` は判定結果を指す。

既存機能（`maintain` の放置/負債検出、`failure-journal` の再発パターン、`backlog`）は課題を**検出・列挙するが起票は手動**だった。このスキルはその「発見 → 起票」のラストワンマイルを自動化する。

## このスキルの役割と境界

| スキル | 責務 | このスキルとの違い |
|--------|------|-------------------|
| **discover**（本スキル） | AI がゼロから課題を発見し自動・一括起票 | — |
| issue-create | 人が起点の対話的な単発起票 | discover は自動・一括。**create のテンプレ/採番/推敲を再利用** |
| maintain | 既存 issue の整理・棚卸し | discover は**新規課題の創出**（既存の整理ではない） |
| follow-up | 人が開発中に思いついたメモの記録 | discover は **AI が発見**（方向が逆） |

## 設計原則（CLAUDE.md「起動＝実行確定」maintain 系に準拠）

ユーザーが起動した時点で「課題を発見して起票してほしい」意思は確定している。よって**止まらずスキャン → 自動起票 → 実行後レポート**まで進める。`AskUserQuestion` で取捨選択を問い直さない（ChatTool を奪う UX コストを避ける）。

暴走を防ぐ**三点セット**を必ず守る:

1. **起票上限 N**（既定 5・`${CLAUDE_EFFORT}` で可変）— 一度に大量の issue を作らない
2. **`status: backlog` で起票** — 自動生成は未着手扱い。放置検知（in-progress × 7日）の誤爆を防ぎ、着手判断を人に残す
3. **重複除外** — 既存 `issues/*.md` と `backlog.md` を照合し、同じ課題を再起票しない

加えて、**実行後に全件レポートで可視化**（何を・なぜ起票したか・evidence 付き）し、issue は git 管理下で復元可能。これにより無確認実行でも安全（CLAUDE.md 例外条項の前提を満たす）。

## ワークフロー

### Phase 0.5: 前提確認

```bash
ls -d {DATA_DIR}/*/ 2>/dev/null
```

backend 検出（冒頭の Phase 0）で確定した `{DATA_DIR}` の slug 一覧を取得する（Phase 1 の対象特定に使う）。

### Phase 1: 対象プロジェクト特定

- 引数で slug 指定があればそれを使う
- feature ブランチなら、ブランチ名から推定したプロジェクトに絞る
- プロジェクトが 1 つなら自動選択
- main ブランチで複数あり未指定なら、**直近アクティブな 1 プロジェクト**（issue の `last_active` 最新）を既定対象にし、レポートで「他プロジェクトも対象にするなら slug 指定」と案内する（全プロジェクト一括スキャンはコスト過大なので既定にしない）

### Phase 2: スキャン強度の決定（`${CLAUDE_EFFORT}` 適応）

| effort | 起票上限 N | スキャン方式 |
|--------|-----------|-------------|
| low / medium | 3 | 直列で主要観点（A・B・E）のみ（速度優先） |
| high | 5 | 観点 A〜E を `Agent`（Explore）で並列スキャン |
| xhigh / max | 8 | 観点 A〜E を並列スキャン + 各観点を深掘り |

### Phase 3: 多観点スキャン

対象プロジェクトのコードと管理ファイルを以下の観点でスキャンし、課題候補を抽出する。FE（フロントエンド）アプリのバグ・未実装機能を重視する。並列時は観点ごとに `Agent`（Explore）を起動して候補を集約する（各 Agent call に `run_in_background: false` を明示。CC 2.1.198 で既定が background になり、省略すると候補を待たずに進んで取りこぼす）。

> **モデルルーティング（Clearwing 原則 4）**: スキャン（候補列挙＝ランカー役）は安いモデルで足りるので、並列 `Agent` は `model: sonnet` を明示する。誤検知の最後の砦である Phase 4.5 の独立検証（深掘り役）は強モデルを使う。ルート CLAUDE.md「モデルルーティング規約」参照。

**観点 A — バグ・不具合の兆候（コード）**
- `TODO` / `FIXME` / `HACK` / `XXX` / `BUG` コメント（`grep -rn`）
- 握りつぶし: 空 `catch {}`、`catch (e) {}` で何もしない、`.catch(() => {})`
- 未処理の Promise / `await` 漏れ、`.then` のエラー未処理
- 型の逃げ: `@ts-ignore` / `@ts-expect-error` / `as any` の濫用
- 放置された `console.error` / `console.warn`
- FE: エラーバウンダリ欠落、フォーム未バリデーション

**観点 B — 未実装・スタブ**
- `throw new Error("not implemented")` 系、空関数本体
- `// TODO: implement`、`// 後で` 等の未完マーカー
- コメントアウトされた機能ブロック、`"Coming soon"` 等のプレースホルダ

**観点 C — FE 特有の改善余地（React / Next.js）**

> 対象が React/Next.js プロジェクトのとき、以下のチェック項目を適用する。
- アクセシビリティ: `alt` 無し `img`、`label` 無し `input`、`aria-*` 欠落
- パフォーマンス: 不要な再レンダリング兆候、`'use client'` の過剰付与、画像最適化漏れ（`next/image` 不使用）
- 巨大コンポーネント（目安 300 行超）、未使用 export / dead code

**観点 D — テスト欠落**
- `src/` 配下のモジュール/コンポーネントに対応するテストファイルが無いもの（重要パスを優先）

**観点 E — 既存シグナルの集約（再利用・重複実装しない）**
- `failure-journal` の再発失敗: `event_bus_tail "failure:logged" 200` で取得し、同一 tag が 3 回以上のものを課題化候補に（events.jsonl / failure-journal 無しなら graceful に skip）
- `backlog.md` の停滞項目: issue 化すべき粒度の項目
- 未昇格 follow-up: `follow-ups/*.md` で `status: open` のまま放置されているもの
- `knowledge/concepts/*.md` の「未解決の問い」セクションに残る論点

各候補を次の構造で保持する:

```
{ title, type(bugfix|feature|debt|investigation), description,
  evidence: ["path:line", ...], impact(high|medium|low),
  effort(small|medium|large), rationale,
  evidence_level(suspected|static-confirmed|verified) }
```

`evidence_level` は証拠強度（Clearwing の証拠ラダー）。スキャン直後は全候補 `suspected`（grep ヒット等の一次シグナルのみ）。Phase 4.5 の検証を通過すると `static-confirmed`（型/テスト/lint で機械裏取り）や `verified`（独立検証 agent が実在と判定）へ昇格する。ルート CLAUDE.md「コスト×精度パイプライン設計指針」参照。

### Phase 4: 正規化・重複排除・優先度付け

1. **既存 issue との重複除外（冪等性）**: `{DATA_DIR}/{slug}/issues/*.md` を Glob/Grep で確認し、同一ファイル対象・同一趣旨の候補を除外（issue-create Phase 5.4 のコードベース確認方式。3〜5 回の Glob/Grep に留める）。**evidence の `path:line` を冪等キーとして使い、既存 issue 本文に同じ `path:line` が含まれていればスキップする**（discover を再実行しても同じ課題を二重起票しないため）
2. **backlog 重複除外**: `backlog.md` に既出の項目を除外
3. **候補マージ**: 同一箇所を指す候補を 1 件に統合
4. **優先度スコア**: `impact 重み ÷ effort` を基本に、type 重み（bugfix・未実装 > debt > investigation）で調整
5. **分類**: 上位 N 件を「起票候補」、残りを「backlog 蓄積」に振り分け（起票は Phase 4.5 検証通過が前提）

候補が 0 件なら、その旨をレポートして終了（健全なら issue を捏造しない）。

### Phase 4.5: 独立検証（起票候補のみ・fail-closed）

**Goal**: 起票候補（上位 N 件）**だけ**を対象に、発見者とは別コンテキストで検証し、誤検知（存在しないバグ・意図的な実装・既に対処済みの箇所）を**起票前に**落とす。discover の唯一の構造的弱点は「発見者＝起票者の一気通貫」で「それっぽい嘘」を潰せないこと。ここを塞ぐのが Clearwing 原則 7（敵対的独立検証）+ 8（外部オラクル + fail-closed）。

**対象の限定（コスト暴走防止）**: 検証は**起票候補（上位 N 件）に限定**する。backlog 蓄積分は検証しない（傾斜予算配分。全候補を検証するとコスト爆発する）。effort による出し分け:

| effort | 検証対象 | 独立検証 agent |
|--------|---------|---------------|
| low / medium | 上位 1〜2 件のみ（外部オラクルは全候補、agent は上位のみ） | 省略可（オラクルのみで可） |
| high | 起票候補 N 件すべて | 各候補に 1 体 |
| xhigh / max | 起票候補 N 件すべて | 各候補に 1 体 + 曖昧判定は再検証 |

**Step 1: 外部オラクルによる裏取り（決定的・安い）**

対象プロジェクトに検証コマンドがあれば、候補 evidence の**対象ファイルに絞って**実行する（全ビルド/全テストは重いので避ける）。

```bash
ORACLE_TC=""; ORACLE_LINT=""
if [ -f package.json ]; then
  grep -q '"typecheck"' package.json && ORACLE_TC="npm run typecheck"
  grep -q '"lint"' package.json && ORACLE_LINT="npm run lint"
fi
[ -z "$ORACLE_TC" ] && [ -f tsconfig.json ] && command -v npx >/dev/null && ORACLE_TC="npx tsc --noEmit"
```

- 型/lint が候補の `path` を**赤で指摘**したら `evidence_level = static-confirmed` に昇格（バグの兆候が機械的に裏取りされた）。
- コマンド不在・実行不能なら昇格させず `suspected` のまま（fail-open は「検証手段が無い」ときだけ。捏造で昇格させない）。

**Step 2: 敵対的独立検証（agent・迎合防止）**

起票候補ごとに `Agent`（`discover-verifier`、`model: opus`、`run_in_background: false`）を起動する。**発見者の `rationale` は渡さない**（思い込み伝播を遮断）。渡すのは `evidence`（`path:line`）と `type` と中立な問いだけ。agent は自分でコードを読み直し、4 軸を YES/NO + 確信度(0-100) で返す:

- **REAL**: その箇所に実際に問題があるか（例: 空 catch が本当に握りつぶしか）
- **NOT-INTENDED**: 意図的な実装でないか（コメント・命名・設計から意図的と読めないか）
- **NOT-HANDLED**: 別の場所で既に対処・実装済みでないか（対応するハンドラ/テスト/バリデーションが他にないか）
- **IMPACTFUL**: 実利用パスに影響するか（dead code / 到達不能でないか）

**Step 3: 判定（fail-closed）**

- 4 軸すべて YES（確信度が閾値以上、目安 60+）→ `evidence_level = verified`。**起票する**。
- いずれかが NO、または確信度が低い → **起票しない**（`backlog.md` へ降格）。曖昧・agent 失敗時も起票せず backlog に倒す（誤起票コスト > 取りこぼしコスト）。
- 検証を省略した候補（low/medium で agent 未起動）は `suspected` のまま起票してよいが、本文の自動起票注記に「未検証」と明示する。

**暴走ガード**: 独立検証 agent は候補 1 件につき 1 体・1 ラウンドまで（多段化しない）。agent 内の探索は「対象ファイルの Read + 周辺 Grep 数回」に留める指示を渡す。

### Phase 5: 自動起票（起票候補のうち検証通過分）

各候補について、**1 件ずつ直列に**起票する（複数件をまとめて採番・書き込みしない）。

**採番ルール（ID 重複・上書き防止）**: 起票開始前に `issues/` 内の既存ファイル名から最大 ID 番号を求め、`counter.txt` の値と突き合わせて**大きい方を基点**にする（中断や他スキル併用で counter がずれていても壊れないための保険）。各候補は次の順で処理する:

1. `counter.txt` を Read し、その値を ID に採用（`{SLUG大文字}-{番号}`）
2. **先に `counter.txt` を +1 して Write（採番を確定）**。issue ファイル Write より前に確定することで、途中中断時に同じ番号が再採番されてファイルを上書きするのを防ぐ
3. type 別テンプレートを Read: `${CLAUDE_PLUGIN_ROOT}/skills/issue-create/references/` 配下の `{type}.md`（`bugfix.md` / `feature.md` / `investigation.md` / `debt.md`）
4. **frontmatter**（テンプレートに準拠。自動起票特有の差分に注意）:
   - `status: backlog` ← **必ず backlog**（自動起票は未着手。in-progress にしない）。`backlog` は正式 status 値で、`maintain` の status 表に「未着手・将来やる」として定義されている（`backlog.md` アイデア帳ファイルとは別物）。`start` ダッシュボードもこの status を集計する。in-progress にすると放置検知（in-progress × last_active 7日超）に誤爆するため避ける
   - `id` / `type` / `created`（今日）/ `last_active`（今日）
   - `scope_size`: **全 type で付与する**（bugfix/investigation/debt も省略しない。テンプレ同梱の既定値を下回らせず、`check-scope-size` のリアルタイム警告を有効に保つため）。effort から導出: `small→small / medium→medium / large→large`（bugfix の既定は small）
   - `pr: ""`
   - テンプレートの任意フィールド（`parent` / `related_knowledge` / `feature_dev_plan` 等）は空のまま残す
5. **本文**: テンプレート構造に沿って埋める
   - 「概要」/「Why」: 課題の背景と、なぜ取り組むべきか
   - 「調査結果」/「対応内容」: スキャンで分かった現状と対応の方向性（断定しすぎない）
   - 「完了条件」: 客観的に判定可能なチェック項目
   - 「参考資料」: **evidence を `path:line` で必ず残す**（人が裏取りできるように）。Phase 4.5 で `static-confirmed` / `verified` に昇格した候補は、その根拠（型/lint が赤 / 独立検証 agent の 4 軸判定）も 1 行添える
   - 本文冒頭に `> 🤖 このIssueは discover が自動起票しました（要レビュー・証拠強度: {evidence_level}）` の注記を 1 行入れる（`suspected` のまま起票した場合は「未検証」と明示）
   - AI が埋めきれない論点は「要確認」マーカーを残す（捏造しない）
   - 「進捗」は空のチェックリスト
6. issue ファイルを Write: `{DATA_DIR}/{slug}/issues/{ISSUE-ID}.md`（counter は step 2 で確定済みなので、ここでは触らない）

### Phase 5.5: writing-polish 推敲（dormant・インストール時は必須）

起票した各 issue の散文を推敲する（issue-create Phase 6.5 と同方式）。

1. 判定:
   ```bash
   if grep -q '"writing-polish@' "$HOME/.claude/settings.json" 2>/dev/null; then WRITING_POLISH=1; else WRITING_POLISH=0; fi
   ```
2. `WRITING_POLISH=1` なら `Skill` tool で `writing-polish:writing-polish` を `--embed --tone issue` で起動し、各 issue の散文部分を推敲。`POLISH_RESULT_START`〜`POLISH_RESULT_END` 間のみ抽出し、**frontmatter・見出し構造・evidence リンク・プレースホルダは変更しない**（構造を壊す結果は破棄）
3. `${CLAUDE_EFFORT}` が low / medium かつ起票数が多い場合は、推敲を起票上位のみに絞ってよい（コスト配慮。high 以上は全件）
4. fallback: 失敗時は warning を出し、推敲前の本文で確定（フローは止めない）

### Phase 6: backlog 蓄積（残り候補）

起票しなかった候補を `backlog.md` の「## 次にやりたい」に優先度付きで追記する（既出は除く）。捨てずに残すことで、次回の discover や `/maintain` で再評価できる。

- **追記先のフォールバック**: `## 次にやりたい` 見出しが無ければ作成する。`init` 由来の空プレースホルダ行（`-` 単独）が残っていれば除去してから追記する
- **`status: backlog` issue と `backlog.md` の使い分け**: **issue 化＝十分に具体化でき着手判断に値する課題**（上位 N 件）、**`backlog.md`＝まだ粒度が粗いアイデアの種**（残り候補）。同一課題が両方に重複しないことは Phase 4 の重複除外で担保する

### Phase 7: 実行後レポート

止めずにここまで実行した結果を一括報告する:

```md
## discover レポート（{slug}）

### 起票した Issue（{N} 件）
| ID | タイトル | type | scope | 優先度 | 証拠強度 | 根拠（evidence） |
|----|---------|------|-------|--------|---------|-----------------|
| MYAPP-7 | ... | bugfix | small | high | verified | src/api.ts:42 空 catch |

### 検証で起票見送り（{K} 件）
- {title} — 見送り理由（例: 独立検証で「意図的な実装」と判定 / 型チェック緑）→ backlog へ

### backlog に蓄積（{M} 件）
- {title}（{type}, {impact}）— {evidence}

### スキャン観点と検出数
- A バグ兆候: {x} / B 未実装: {x} / C FE改善: {x} / D テスト欠落: {x} / E 既存シグナル: {x}

### 次のアクション
- 着手するなら `/feature-dev {ISSUE-ID}` または `/start`（feature ブランチで）
- 起票内容は `status: backlog`。不要なら issue ファイルを削除（git 復元可）
```

## イベント連携

起票した issue ファイルは既存の FileChanged hook（`issues/*.md`）が検知するため、**追加のイベント publish は不要**（新イベントは作らない＝over-engineering 回避）。

## 注意事項

- **起動＝実行確定**: スキャン〜起票を確認で止めない。判断材料（evidence）はレポートに必ず添える
- **偽陽性は前提だが起票前に絞る**: 静的スキャンは誤検知しうる。起票候補は Phase 4.5 の独立検証（外部オラクル + 敵対的 agent）で裏取りし、通らなければ起票せず backlog に降格する（fail-closed）。加えて起票分も `status: backlog` + evidence 明示 + git 復元可能の三重で安全側に倒す。人はレポートを見て取捨選択できる
- **検証は起票候補に限定**: Phase 4.5 の検証は上位 N 件のみ。backlog 蓄積分まで検証するとコストが爆発する（傾斜予算配分）。発見（安いスキャン）と検証（高い深掘り）を段で分け、後者を通過分だけに集中させる
- **issue を捏造しない**: 候補 0 件ならそう報告する。健全なコードに無理やり課題を作らない
- **既存ロジックの再利用**: テンプレート・採番・推敲は issue-create を、再発失敗の集計は failure-journal の event を再利用する（重複実装しない）
