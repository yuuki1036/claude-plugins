---
id: 20260916-code-review-review-guide-skill
title: code-review に review-guide skill を新設する（人間が PR を理解するための読み順ガイド）
status: approved
phase: target
last-validated: 2026-09-16
supersedes: []
superseded-by: null
issue: null
spec: null
adrs: []
tags: [code-review, skill-design, human-review, reading-order]
---

# code-review に review-guide skill を新設する（人間が PR を理解するための読み順ガイド）

## TL;DR

PR（または base 指定のローカル diff）を人間が読むための「読み順ガイド」をセッション内に出力する読み取り専用 skill。`triage-signals.sh` の分類とリスク信号で精読ファイルを上位 N 件に絞り、explorer（sonnet）が辿った呼び出し関係を「入口 → ロジック → 永続化 → テスト」のスレッド単位に並べ、各ファイルに「この PR で何をした / 難点 / 見る行 / レビュー観点」を付ける。ファイルは作らず、コメントも投稿しない。

## 背景 / 課題

- 主用途は**自分の PR を後から理解する**こと（マージ済み・時間が経った PR を読み直す）。副用途は他者 PR に `review` を回した後の学習
- 既存 4 skill はどれも「指摘を出す」（review / self-review）か「付いた指摘に応える」（review-triage）か「コメントを直す」（comment-polish）で、**人間が読む行為そのものを支援するものが無い**。`claude-meta:component-addition-advisor` の観点で既存拡張を検討したが、review の出力契約（severity 付き findings）と読み順ガイドの出力（説明文）は形が違い、review に `--guide` を足すと Phase 0〜反証の全機構が無駄に回る。新 skill が最小構成
- diff 全文を人間が上から読むのは非効率で、生成物・lockfile・機械的置換に時間を使ってしまう。**読まなくてよいものを理由付きで切る**のがガイドの価値の半分

## ゴール / 非ゴール

- **ゴール**:
  - PR 番号（既定）または `--base <ref>` のローカル diff を入力に、精読 N 件（既定 5、`--top N`）/ 流し読み / 不要 の 3 段に振り、不要には 1 行の理由を付ける
  - 精読ファイルをスレッド（変更が貫く 1 本の流れ）単位で実装順に並べ、各ファイルに 4 項目（この PR で何をした / 難点 / 見る行 `file:line` / レビュー観点）を付ける
  - PR 本文の主張と diff の突合（書いてあるが無い / 無いが入っている）
  - 変更した振る舞いごとのテスト対応表（ある / 無い）
  - PR に付いた既存コメント（review が投稿したものを含む）と、同一セッションに review レポートがあればその `🔁 報告閾値を割った指摘` を「人間の判断が効く箇所」として案内する。**無ければ単独で完結**
  - `${CLAUDE_EFFORT}` で agent 体数を変える（low / medium: agent なし、high: explorer 上限 2、xhigh / max: 上限 3）
- **非ゴール**:
  - ファイルへの永続化（ユーザー確定 2026-09-16: セッション出力のみ。必要なときに再実行する）
  - コメント投稿・PR 本文編集・コード修正（Edit / Write を持たない）
  - severity 付き指摘の生成（review の領分。ガイドの「レビュー観点」は「何を見るか」の問いであって判定ではない）
  - 全ファイルの解説（上位 N 件に絞る。残りは 1 行）
  - 反証レイヤー（説明文の誤りは `file:line` の根拠強制で抑える。独立検証を足すコストに見合わない）

## 確定した前提

| # | 前提 | 出典 |
|---|---|---|
| 1 | diff の取得と分類は `triage-signals.sh` が既に両入口を持つ: `--pr <N>`（`gh pr diff`）/ `--base <ref>`（base..HEAD + staged + unstaged）。出力の `## files` に core / doc / generated / lock 等の分類と行数、`## red-flags` `## surface` にリスク信号が出る | `code-review/scripts/triage-signals.sh:13-15`、Step 1 実測出力 |
| 2 | PR 本文・issue コメント・レビューサマリ・行コメント（返信チェーン付き）は `fetch-pr-context.sh <N> --save` で 1 ファイルに落ちる | `code-review/scripts/fetch-pr-context.sh:1-20` |
| 3 | **review は findings 本文を永続化しない**（`events.jsonl` は件数のみ）。後日の取り込み元は「review が PR に投稿したコメント」（前提 2 で取れる）に限られ、`🔁 報告閾値を割った指摘` は同一セッションのレポートが文脈に残っているときだけ使える | `code-review/references/orchestration-measurement.md` `## 16`、`scoring-guide.md:257` |
| 4 | explorer prompt は `explorer-common.md` + `explorer/<focus>.md` の 2 ファイル Read 方式。流れ追跡に使えるのは `function-flow.md`（分岐・データ変更・呼び出し先）と `dependency-trace.md`（import 元の列挙・呼び出し元）。explorer は判定せず事実収集に徹する | `code-review/references/explorer-prompts.md:16-30`、`prompts/explorer/` |
| 5 | 担当ぶんの diff は `diff-slice.sh <diff-file> '<path>'` で切り出す。パスはシングルクォート（信頼できない入力） | `explorer-common.md`「diff の取得」 |
| 6 | レビュー観点の判定表（観点 × diff 条件）は `triage-guide.md ## 3` が正本。ガイドの「レビュー観点」はこの表を diff シグナルで引いて添える（複製しない） | `code-review/references/triage-guide.md:110-134` |
| 7 | 同名 command + skill のペアでは router が見るのは `commands/*.md` の description。command 本文は SKILL.md を Read する 1 行を置く（`skill-hop-cmd` が error 強制） | ルート CLAUDE.md Gotchas（#206 / #219） |
| 8 | 深掘り系は `${CLAUDE_EFFORT}` 分岐必須。探索は `sonnet`、統合は `opus`。fan-out には体数上限を明示し、各 Agent call に `run_in_background: false` + 同一メッセージで一括発行 | ルート CLAUDE.md「プラグイン開発ルール」「コスト×精度」「Agent tool の background 既定」 |
| 9 | `gh` / `jq` / `python3` は code-review の `_requirements` 済み。新規依存は無い | `code-review/.claude-plugin/plugin.json` |
| 10 | ユーザー確定（2026-09-16）: 主用途は自分の PR の後日理解 / 副用途は他者 PR の review 後の学習 / 投稿なし / 全ファイル解説なし / **ファイル永続化なし（セッション出力のみ）** | 会話 |

## 採用案

### 全体フロー

```
/review-guide [PR番号 | --base <ref>] [--top N]
  │
  ├─ Step 0  入力確定: PR 番号（省略時は現ブランチの PR）→ triage-signals.sh --pr N
  │          --base 指定なら triage-signals.sh --base <ref>（PR 本文・コメントの Step は skip）
  │          → diff_file / files 分類 / red-flags / surface を得る（diff 全文は読まない）
  │
  ├─ Step 1  PR コンテキスト: fetch-pr-context.sh N --save → 本文・既存コメントを Read
  │          （--base モードでは無し。同一セッションに review レポートがあれば 🔁 付録を控える）
  │
  ├─ Step 2  重要度スコアと 3 段振り分け（メインコンテキスト・agent なし）
  │          score = 分類（core=3 / test=2 / doc=1 / generated・lock=0）
  │                + red-flags・surface の代表ファイルに +2（triage-signals の digest は
  │                  1 signal につき代表 1 ファイルしか出さないため、その代表にのみ加点する）
  │          分類だけで core(3) > test(2) > doc(1) が確定するので、シグナル加点が無くても
  │          core が上位に来る。同点は core 優先でタイブレークする（core を N 件目以降に落とさない）
  │          上位 N 件 = 精読 / 残りの core・test・doc = 流し読み / gen(生成物・lock)・rename・機械的置換 = 不要（理由 1 行）
  │
  ├─ Step 3  流れの把握（effort 分岐）
  │          low / medium: agent なし。diff-slice.sh で精読ファイルの hunk だけ読み、
  │                        import / 呼び出しの字面からスレッドを組む
  │          high:         explorer 上限 2（sonnet）。function-flow（精読ファイルの変更関数）と
  │                        dependency-trace（精読ファイルの被参照＝呼び出し元）を同一メッセージで一括発行
  │          xhigh / max:  explorer 上限 3（+ value-flow-trace で入口→永続化の値の流れ）
  │          explorer には diff_file のパスと担当ファイルだけ渡す（本文を転記しない）
  │
  ├─ Step 4  統合・執筆（メインコンテキスト = opus）
  │          スレッド構成 → 各精読ファイルの 4 項目（根拠 file:line 必須）
  │          → 主張 vs diff 突合 → テスト対応表 → 人間の判断が効く箇所
  │
  └─ Step 5  レポート出力（下の形式）。ファイルは書かない
```

### レポート形式

```
## 読み順ガイド: PR #<N> <title>（<core_files> files / <core_lines> lines / size_tier）

### まず全体
- この PR がやったこと（PR 本文 + diff から 2〜3 行。本文と diff の乖離があればここに ⚠️）
- スレッド一覧: ① <入口→…→永続化> ② … （精読ファイルがどのスレッドに属すか）

### 読まなくてよい（K 件）
- <path> — <理由 1 行: 生成物 / lockfile / rename のみ / 機械的置換（import 差し替え）>

### 流し読み（M 件）
- <path> — <何が変わったか 1 行>

### 精読（N 件・実装の流れ順）
1. <path>（スレッド ①・入口）
   この PR で: <何をしたか 2〜3 行>
   難点: <非自明な分岐・並行性・境界値・暗黙の前提。無ければ「特になし」>
   見る行: <file:line 〜 file:line> — <なぜここか>
   レビュー観点: <triage-guide の観点名 → この PR での具体的な問い>
2. …

### 主張 vs diff
- 本文の主張「…」→ diff で確認: <あり file:line / 見当たらない>
- diff にあるが本文に無い: <path> — <内容>

### テスト対応
| 変更した振る舞い | テスト | 場所 |
|---|---|---|
| … | あり / なし | file:line |

### 人間の判断が効く箇所（該当があるときだけ）
- 既存の行コメント（解決状態は不明。fetch-pr-context は isResolved を取得しない / design-review F6）: <file:line> — <要旨>
- review が閾値を割った指摘（同一セッションのみ）: <要旨> — <脱落理由>
```

### 変更対象ファイル

| ファイル | 内容 |
|---|---|
| `code-review/commands/review-guide.md` | 新規。description（トリガー: 「PR の読み方」「読み順」「PR を解説して」「このPR何やってる」「/review-guide」）+ SKILL.md を Read する 1 行 + 引数の説明 |
| `code-review/skills/review-guide/SKILL.md` | 新規。上のフロー。allowed-tools: Bash / Read / Grep / Glob / Agent（Edit / Write / Skill を持たない）。command と一致させる |
| `code-review/references/review-guide-format.md` | 新規。レポート形式の正本と 4 項目の書き方（「難点」に書くもの / 書かないもの、「見る行」の粒度）。SKILL.md は Step 4 でのみ Read |
| `code-review/CHANGELOG.md` / `.claude-plugin/plugin.json` / `marketplace.json` / `INDEX.md` / ルート `CLAUDE.md` の一覧 | 版と件数（commands 5 / skills 5） |
| `evals/cases/code-review.yaml` | トリガーフレーズの起動ケース + 逆方向（「レビューして」が review-guide に奪われない）ケース |

### コスト×精度パイプライン設計（SKILL.md に残す一言）

採用: **1**（ファネル: triage-signals の分類で精読を N 件に絞ってから agent を当てる）/ **3**（段階予算: effort → explorer 0 / 2 / 3 体）/ **4**（モデルルーティング: explorer sonnet・統合 opus）/ **5**（暴走ガード: 体数上限・精読 N の上限）/ **9**（構造化受け渡し: diff はパス渡し、explorer は事実のみ返す）。
捨てた: **2・10**（severity / confidence を付けない。判定ではなく説明）/ **6**（蓄積しない。永続化なし）/ **7**（反証なし。説明文の根拠を `file:line` で強制し、無い主張は書かない）/ **8**（機械層は不要。実行しない）。

## 検討した代替案

| 観点 | 案 A（採用）シグナル絞り込み → explorer 流れ追跡 → main 統合 | 案 B agent なし single-pass | 案 C ファイル単位 fan-out（1 ファイル 1 agent が解説） |
|---|---|---|---|
| 読み順の質 | 呼び出し関係を実際に辿るのでスレッドが正確 | 字面の import から推定。大きい PR で順序が崩れる | 各ファイルは詳しいが**横断の流れが消える**（ガイドの主目的と逆） |
| コスト | explorer 0〜3 体（effort 連動） | 最小 | 精読 N 体 + 統合。案 A の 2〜3 倍 |
| 既存資産の再利用 | triage-signals / explorer prompts / diff-slice をそのまま使う | triage-signals / diff-slice | reviewer 起動基盤に近いが出力契約が違い流用しにくい |
| 失敗モード | explorer が事実を取り違える → `file:line` 根拠で main が検算 | 大 PR で「読めていない」まま書く | agent 間で用語・粒度が揃わない |
| 採否 | **採用**。案 B は案 A の low / medium 分岐としてそのまま含める | 単独では大 PR に弱い | 横断の流れが主価値なので不採用 |

## 設計判断ログ

- [local] 出力はセッション内のみ。ファイルを書かない（ユーザー確定）。理由: 「後で理解する」は「後で再実行する」で足り、永続化は commit / gitignore / マシン間同期の判断を持ち込む
- [local] severity / confidence を付けない。レビュー観点は「この PR で何を見るか」の問いとして書く。理由: 判定を出すと review と役割が重なり、説明の信頼度と判定の信頼度が読み手の中で混ざる
- [local] 反証レイヤーを置かない代わりに、4 項目の各主張に `file:line` を必須にし、根拠を示せない主張は書かない（「難点: 特になし」を許す）。理由: 説明の誤りのコストは指摘の誤りより低く、独立検証の体数に見合わない
- [local] スコアは「分類 + red-flag/surface 代表加点」の 2 要素に絞る（初版）。理由: 精読 N の選抜は分類だけで core が上位に来る粗い判定で足り、fan-in（独自 Grep）や行数帯は重み付き合成を増やすだけで選抜をほぼ変えない。fan-in を独自実装すると triage-signals `## explorer-signals` が既に持つ誤カウント対策（3 文字未満の basename 除外・`-lwF` 固定文字列 word 一致・自己除外）を捨てることになり、common / 短い basename で過大カウントして選抜を歪める（design-review F1）。必要になったら triage-signals の `## explorer-signals` 出力を**再利用**して足す（独自 Grep は新設しない）
- [local] red-flag/surface は per-file に全展開できない。triage-signals の digest は 1 signal につき代表 1 ファイルしか出さないため（`## red-flags` / `## surface` の出力は `<key>\t<hit数>\t<代表根拠1ファイル>`）、加点は代表ファイルにのみ効かせ、全該当ファイルへ配れる前提で設計しない（design-review F2）。全展開が要るなら diff-slice で候補 core の hunk を先読みする段が要るが、初版では持たない
- [local] `🔁 報告閾値を割った指摘` は同一セッションに review レポートがあるときだけ使う。永続化を新設しない。理由: review 側の計測契約（events.jsonl は件数のみ）を変えずに済み、後日は PR コメント経由で同等の情報が取れる
- [local] `--base` モードでは PR 本文・コメント由来のセクション（主張 vs diff / 人間の判断が効く箇所）を「対象なし」と明記して省く。理由: silent skip と区別する（self-review の見出し規約と同じ）

## 未解決事項 (open)

- **精読 N の既定値**: (a) 5 — 1 回で読み切れる量。(b) size_tier 連動（small 3 / medium 5 / large 8）— 小 PR で全件精読になり「絞る」意味が薄れる。現時点の方向性: **(a) 5 固定 + `--top N`**。確定タイミング: 実装後 3 PR で使い、上限に当たる頻度を見て決める
- **スコアの 2 要素で選抜が不足するか**: 初版は分類 + red-flag/surface 代表加点のみ（fan-in・行数帯を落とした / design-review F1・F3）。精読すべきファイルが上位 N から漏れる回が出たら、triage-signals `## explorer-signals` の再利用で fan-in を足す。現時点の方向性: **2 要素で開始**。確定タイミング: 実装後 3 PR で、漏れ（後で「これは精読に入れるべきだった」と気づいた回）の頻度を見て決める

## 実装ブリッジ (Implementation Bridge)

1. 実装着手の単位: Issue 1 件で閉じる規模（新規 3 ファイル + 版更新 + evals）。起票時タイトル案: 「[code-review] review-guide: 人間が PR を理解するための読み順ガイド skill を追加」。feature-dev は使わず、issue-workflow:start の**軽量フロー**（実装 → 検証 → self-review → commit → push + CI → Issue 更新）で通す（本 doc が HOW を確定済みのため 8 phase は不要）
2. 検証方法:
   - 機械層: `bash .claude-plugin/scripts/machine-layer.sh`（allowed-tools ペア一致 / `skill-hop-cmd` / トリガー必須 / references 参照整合 / agent-sync warning）
   - evals: `python3 evals/runner.py --plugin code-review`（新トリガーの起動 + 「レビューして」「セルフレビュー」「レビューコメントを精査」が奪われない逆方向ケース。pass^k=3）
   - 実機: 本リポジトリの直近 PR 1 件と `--base 2ccab43`（本セッションの diff）で出力を目視。精読 N 件に core が入り generated が「不要」に落ちること、スレッドが入口から並ぶこと、各主張に `file:line` があることを確認
3. 実装完了時の doc 更新: frontmatter の `phase: target → current`、`last-validated` を更新。スコアの要素や N の既定が実装で変わっていたら「設計判断ログ」に追記。open 2 件は確定タイミングが来たら畳む

## 関連

- 関連 Issue: （起票前。実装ブリッジ 1 のタイトルで起票する）
- 関連 spec: なし
- 関連 ADR: なし（判断はすべて skill ローカル）
- 関連 design doc: `20260912-worktree-gc-skill.md`（新 skill 追加の先例。scan / reap 分離の判断過程を参考にした）
