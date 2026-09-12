---
id: 20260912-worktree-gc-skill
title: dev-workflow に worktree-gc skill を新設する（PC 横断の worktree 棚卸し・一括削除）
status: approved
phase: target
last-validated: 2026-09-12
supersedes: []
superseded-by: null
issue: https://github.com/yuuki1036/claude-plugins/issues/223
spec: null
adrs: [20260912142858]
tags: [dev-workflow, worktree, gc, skill-design]
---

# dev-workflow に worktree-gc skill を新設する（PC 横断の worktree 棚卸し・一括削除）

## TL;DR

散らばった git worktree を検出・分類・安全確認して一括削除する `worktree-gc` skill を dev-workflow に足す。判定は副作用のない `scan.sh` が JSON Lines で出し、削除は承認済みの行だけを受け取る `reap.sh` が行う（reap は判定を再実行しない）。既定は現リポのみ、`--all` で PC 横断。

## 背景 / 課題

- GitHub issue #223: next repo 24 件 + 他リポの review 残骸 18 件 + agent worktree 4 件 + 空 dir / temp を**手作業で**棚卸しして消した。手順は 6 段（検出 → 分類 → 安全確認 → 削除 → 付随掃除 → 承認）で毎回同じ
- 既存の `worktree-setup` / `worktree-teardown` は **1 worktree の作成・破棄**が対象。teardown は Step 1 で `GIT_DIR == GIT_COMMON` なら `exit 1`（main clone では実行不可）で、厳守ルールでも「現 worktree の env に書かれた port のみを対象にする」と定める。複数 worktree を横断する用途には前提が反転する（`dev-workflow/skills/worktree-teardown/SKILL.md`）
- `claude-meta:component-addition-advisor` のゲートは通過済み（2026-09-12）。既存拡張で解けない blocker は上の 2 点。新 skill として追加する
- review 用 worktree（`.claude/worktrees/` 配下）は code-review 締めフロー 5 が正常時に掃除するため、残るのは**レビューが途中で死んだ回**に限られる（`code-review/skills/review/SKILL.md:505-511`）

## ゴール / 非ゴール

- **ゴール**:
  - 現リポ（既定）または root 配下の全リポ（`--all`）の worktree を検出し、削除候補 / 保持を理由つきの表で提示する
  - 損失リスクのあるもの（未コミット・未マージ・生存プロセス・自分自身）は機械判定で保持側へ倒す
  - リポ単位の承認後、ネスト → 親の順で `git worktree remove` + `prune`、**marker のある行の DB drop**、空の親 dir の掃除を行う
  - `gh` / session 一覧が無い環境でもブランチの merged 判定で動く
- **非ゴール**:
  - プロセスの kill（生存プロセスがある worktree は保持し、PID を表示するだけ。理由: 誤 kill の被害が worktree 誤削除より大きく、teardown が既に「勝手に kill しない」を規範にしている）
  - port の解放追跡（マーカー消失後の port は逆算できない。理由: `port-allocation.md` の動的空き探索は記録を残さない）
  - **marker 無し行の DB drop**（design review F1。所有権を証明できないため。列挙 + 手動コマンド併記に留める）
  - **`agent-*` 孤児ブランチの `git branch -D`**（design review F6。既存 `code-review/scripts/cleanup-agent-worktrees.sh` が持つ責務。GC は worktree の remove までで、ブランチ掃除は code-review 側に委ねる。生成側の変更ではないので上の「生成側の変更」とは別）
  - 1 worktree の丁寧な破棄（`worktree-teardown` の領分。GC は teardown を置き換えない）
  - 他プラグイン（code-review）の worktree 生成側の変更

## 確定した前提

| # | 前提 | 出典 |
|---|---|---|
| 1 | worktree は 4 種 + prunable: **review**（`*/.claude/worktrees/*`、EnterWorktree 由来）/ **agent**（review 配下にネストした子。`nested_parent != null`）/ **dev**（`envs/.backend.env.worktree` or `.frontend.env.worktree` マーカー持ち）/ **other**（マーカー無し）/ **prunable**（dir が消えた残骸）。scan 出力の `kind` 値と一致させる（design review MINOR で 3 種→ここに統一） | `code-review/scripts/detect-dev-worktree.sh:43-46`、agent ネストの出典は `code-review/skills/review/SKILL.md:500-507`（design review で出典修正） |
| 2 | (1) の判別述語は code-review が持つが、プラグイン間依存禁止のため dev-workflow 側に再実装する | CLAUDE.md「プラグイン開発ルール」 |
| 3 | DB 名は `${BASE_DB}_$(sanitize_db_name WORKTREE_NAME)`。50 文字超は頭 20 文字 + hash6 に切り替わる。**逆算は marker 無し行の drop には使わない**（design review F1。`BASE_DB` は marker が正本で marker 無し行では取得できず、hash 形候補も構成不能。sanitize は非単射で所有権を証明できない）。逆算は「残っているかもしれない DB」の列挙にだけ使う | `dev-workflow/skills/worktree-setup/references/db-naming.md` |
| 4 | port は動的空き探索で割り当てられ、マーカー以外に記録が無い。マーカー消失後は逆算不能 | `worktree-setup/references/port-allocation.md` |
| 5 | `gh` は dev-workflow の `_requirements` で `required: true` 済み。session 一覧（`ccd_session_mgmt`）は desktop app が提供する host MCP で CLI には無い | `dev-workflow/.claude-plugin/plugin.json` |
| 6 | SKILL 本文に bash を書き下ろさず `scripts/` へ寄せる。テストは `.claude-plugin/scripts/tests/test_<plugin>_*.py` で CLI 境界越しに叩く。dev-workflow は現状 `scripts/` を持たない | CLAUDE.md リポジトリ構造 |
| 7 | 削除は不可逆なので「起動＝実行確定」例外の対象外。AskUserQuestion での承認が必須。走査系なので `${CLAUDE_EFFORT}` 分岐も必須 | CLAUDE.md プラグイン開発ルール |
| 8 | ユーザー確定（2026-09-12）: 既定は現リポ・`--all [root]` で横断 / 承認はリポ単位で 1 回 / DB は逆算して候補提示 → 承認後 drop / 構成は scan・reap の 2 段 | grill 回答 |
| 9 | 統合ブランチ経由で merge された PR は `ahead_of_main` が正でも安全（issue #223 の落とし穴） | issue #223 本文 |

## 採用案

### 全体フロー

```
/worktree-gc [--all [root]] [--dry-run]
  │
  ├─ Step 0  起動位置の確認（main clone / worktree 内どちらでも可。自分を含む worktree は self として保持）
  │
  ├─ Step 1  scan.sh [--all <root>] [--effort <lv>]  → stdout に JSON Lines（1 行 = 1 worktree、副作用なし）
  │
  ├─ Step 2  LLM が verdict=keep をそのまま、verdict=reap をリポ単位の表に整形
  │          （session 一覧が使える環境では、実行中 session に紐づく行を keep へ倒す）
  │
  ├─ Step 3  AskUserQuestion（リポごと）: 「削除 / 一部保持（行番号）/ このリポは skip」
  │
  ├─ Step 4  reap.sh < 承認行の JSON Lines
  │          ネスト → 親の順で remove（dirty 行は承認済みのときだけ --force）→ prune
  │          → db_guess が実 DB と一致した行だけ drop → 空の親 dir → worktree 由来 temp
  │
  └─ Step 5  レポート（OK / WARN / SKIP の件数。失敗行には手動コマンドを併記）
```

`--dry-run` は Step 1〜2 で止まる（表だけ出す）。

### scan.sh の出力（1 行 = 1 worktree）

| フィールド | 型 | 導出 |
|---|---|---|
| `repo` | path | `git rev-parse --git-common-dir` の親 |
| `path` / `branch` | path / string | `git worktree list --porcelain` |
| `kind` | `review` / `dev` / `agent` / `other` / `prunable` | 前提 1 の述語。`prunable` はディレクトリが消えた残骸 |
| `nested_parent` | path or null | `agent-*` の親 review worktree |
| `self` | bool | scan を起動した cwd を含む |
| `dirty` / `untracked` | bool | `git status --porcelain`（worktree 内で実行） |
| `ahead_of_main` | int | `git rev-list --count origin/main..<branch>` |
| `pr` | `{number, state}` or null | `gh pr list --head <branch> --state all`（gh 不在なら null） |
| `merged_into_main` | bool | `git branch --merged origin/main` に含まれる |
| `live_pids` | int[] | `lsof -d cwd` で path 配下を cwd にするプロセス |
| `marker` | `{db_name, ports[]}` or null | `envs/.backend.env.worktree` を読む |
| `db_guess` | string[] | **marker がある行のその `db_name` のみ**。marker 無し行は drop 対象にしない（下記 F1 修正）。逆算は列挙だけに使い、drop 候補には昇格させない |
| `verdict` | `reap` / `keep` | 下の分類規則 |
| `reasons` | string[] | verdict の根拠（表にそのまま出す） |

### 分類規則（scan 内で完結。reap は再判定しない）

安全ゲート（1 つでも真なら `keep`）:

1. `self`
2. **`primary`（`git rev-parse --git-dir` == `--git-common-dir`。メインの作業ツリー）** — `reasons: ["primary-worktree"]`。design review F2 で追加。`self` は cwd を含む 1 個しか除外しないため、`--all` 走査時や別 worktree からの起動時に各リポの primary が `kind=other` で reap に落ちるのを防ぐ
3. `dirty` または `untracked`
4. `live_pids` が空でない
5. `pr` が open
6. `pr` が null かつ `merged_into_main` が false
7. `pr` が null かつ `ahead_of_main` が正（gh 不在時の保守側フォールバック）

ゲートをすべて通過したら `reap`。`pr.state` が merged / closed なら **`ahead_of_main` が正でも reap**（前提 9）。kind 別の追加条件は無い（review / dev / other はすべて同じゲート）。`prunable` は無条件で `reap`（`git worktree prune` だけが走る）。分類できない行（git コマンドが失敗した等）は `keep` + `reasons: ["unclassified"]`。

### reap.sh の入力契約

- stdin に scan の出力行をそのまま渡す（LLM が行を**選ぶ**ことはあっても**書き換える**ことはない）
- **外部由来文字列（branch / path / db 名）は argv 渡し限定、`eval` / コマンド文字列組み立て禁止**（design review F5。branch 名は PR 作者が制御する外部入力で git ref 規則は `$` / バッククォート / `;` / `|` を禁じない。`detect-dev-worktree.sh:12-16,37-40` が同じ理由で `--pr` 数値のみ受け awk `-v` 文字列等価で比較している。scan.sh も同契約を継承する）
- `path` が `git worktree list` に実在しない行は SKIP + WARN（stale な承認を弾く）
- **削除直前に `live_pids` を再取得**し、非空なら SKIP + WARN（design review F4。scan → 承認 → reap の間に使い始めた worktree の became-live race を塞ぐ。ADR-20260912142858 の「判定を再実行しない」は verdict の再計算を禁じるものであり、liveness の TOCTOU 再チェックはこれと両立する — 消えた worktree の実在チェックと同じ「削除直前の安全確認」の枠）
- `verdict != reap` の行は拒否して exit 2（承認フローの迂回を機械的に塞ぐ）
- 順序: `nested_parent` を持つ行 → それ以外。同一 repo 内で `remove` を終えてから `prune`
- `dirty` の行は承認済みでも `--force` を付ける前に 1 行 WARN を出す（ログに残す）
- **DB drop は `db_guess`（＝ marker がある行の `db_name` のみ）を再度実 DB 列挙と照合し、一致した名前だけを drop**（design review F1）。**marker 無し行は drop しない** — sanitize は非単射（`feature-payment` / `feature_payment` / `Feature/Payment` がすべて `feature_payment` に潰れる）で、名前一致は DB の存在を示すだけで所有権を示さないため、別 worktree / 本番 DB を掴む経路になる。marker 無し行の逆算候補は「残っているかもしれない DB」として列挙し手動 drop コマンドを併記するに留める
- 付随掃除: worktree の親 dir が空なら `rmdir`、`path` 配下に残った `.stryker-tmp` 等の temp は remove で消えるので個別処理しない
- **`agent-*` 孤児ブランチの掃除**（design review F6）: review worktree（親）を reap すると、配下の agent worktree が detach で作った `agent-*` ブランチが孤児として残る。既存 `code-review/scripts/cleanup-agent-worktrees.sh` はこれを「どの worktree にも checkout されていない `agent-*` ブランチを `git branch -D`」で掃除している。**この掃除は既存スクリプトに委ねる**（プラグイン間依存禁止のため呼び出しはせず、非ゴールに「`agent-*` ブランチは code-review 側の cleanup が持つ」と責務境界を明記する。生成側の変更ではないので非ゴールと矛盾しない）

### `--all` の走査

- `find <root> -maxdepth 4 -name .git` で `.git` が**ファイル**（gitlink）のものを worktree、ディレクトリのものを main repo として拾う
- gitlink の `gitdir:` から main repo を解決し、main repo 単位に `git worktree list --porcelain` を 1 回だけ叩く（重複排除）
- **submodule / vendored リポの gitlink を除外する**（design review MINOR）。`git worktree list` に現れる worktree だけを対象とし、main repo 解決後にその一覧に含まれない gitlink（submodule 等）は候補にしない。無関係リポの worktree を候補表・DB 逆算に混ぜない
- `gh pr list --state all --limit 200` はリポごとに 1 回だけ叩き、branch → pr の辞書を作る（worktree ごとに叩かない）

### `${CLAUDE_EFFORT}` 適応

**分類ロジックは effort で分岐させない**（design review F3）。安全ゲートは全 effort 共通で、effort が変えるのは走査の広さと確認の深さだけ。

| effort | 走査の深さ |
|---|---|
| low / medium | `lsof` を省くときは `live_pids` を **unknown 扱いで保守的に keep**（mtime 代替はしない — mtime は生存プロセスと相関せず、稼働中 worktree を reap する経路になる）。対象が少数なら lsof のコストは小さいので、既定では省かず回してよい |
| high | 本文どおり（lsof + marker のある行の DB 照合） |
| xhigh / max | `--all` の `maxdepth` を 6 に広げる（走査範囲のみ拡張。非 worktree 残骸 dir の列挙は入れない — ゴール外で reap もしないため） |

### 変更対象ファイル

| ファイル | 変更 |
|---|---|
| `dev-workflow/skills/worktree-gc/SKILL.md` | 新規。Step 0〜5 の配線 + effort 分岐 + 「teardown との使い分け」節（blocker と fallback をここに記録） |
| `dev-workflow/skills/worktree-gc/references/classification.md` | 新規。分類規則・安全ゲート・reap 入力契約の正本 |
| `dev-workflow/scripts/worktree-gc/scan.sh` | 新規 |
| `dev-workflow/scripts/worktree-gc/reap.sh` | 新規 |
| `dev-workflow/scripts/lib/db-name.sh` | **F1 採用により縮小 or 不要**。marker のある行は `db_name` を直接読むため sanitize / hash 逆算が要らなくなった。逆算列挙（非 drop）にだけ使うなら小さく残す。open 1 を参照 |
| `dev-workflow/skills/worktree-teardown/SKILL.md` | 「複数 worktree の一括棚卸しは `worktree-gc`」の 1 行を「適用範囲」に追記。トリガーは変えない |
| `dev-workflow/README.md` / `CHANGELOG.md` / `.claude-plugin/plugin.json`（minor bump） | 追記 |
| `.claude-plugin/marketplace.json` / `INDEX.md` / `CLAUDE.md`（dev-workflow の skills 6 → 7） | 同期 |
| `.claude-plugin/scripts/tests/test_dev_workflow_worktree_gc.py` | 新規。使い捨てリポで worktree を複数作り scan の JSON を検証 / reap は stub `git` で exit 契約を検証 |
| `evals/cases/dev-workflow.yaml` | 「worktree 棚卸し」「worktree 一括削除」→ worktree-gc、「worktree 削除」→ worktree-teardown の分離ケース |

### トリガーフレーズ

`worktree-gc` は「worktree 棚卸し」「worktree 一括削除」「worktree GC」「残骸 worktree を掃除」「worktree gc」「/worktree-gc」。**単数の「worktree 削除」「worktree 破棄」は teardown に残す**（advisor 診断で 70% 重複の Red Flag が出た箇所）。

## 検討した代替案

| 観点 | 案 A: scan / reap 2 段（採用） | 案 B: 単一 `worktree-gc.sh --dry-run/--apply` | 案 C: スクリプト無し・SKILL 本文 bash |
|---|---|---|---|
| 承認の部分適用 | ◎ reap に渡す行を絞れる | △ `--exclude` の引数設計が要る | ○ LLM が手で選ぶ |
| 表示と削除の一致 | ○ reap は scan の出力行しか受けず再判定しない | ◎ 同一プロセス | ✕ 再実行のたびに揺れる |
| テスト | ◎ scan は使い捨てリポ、reap は stub git | ○ モード分岐でケースが倍増 | ✕ 不能 |
| 規約適合 | ◎ | ◎ | ✕（bash 書き下ろし禁止） |
| 変更量 | 中 | 小〜中 | 小（保守不能） |

- 案 B を採らない理由: リポ単位承認 + 一部保持を引数で表現すると、承認した内容と `--apply` が消す内容の対応をユーザーが目で追えなくなる
- 案 C を採らない理由: CLAUDE.md の構造規約に反し、テストできない

## 設計判断ログ

- [→ADR候補] 破壊的な一括操作の skill は「列挙（副作用なし・機械可読出力）」と「実行（承認済み行のみを入力に取り、判定を再実行しない）」を別プロセスに分ける。表に出したものだけが消える、を入力契約で担保する → **ADR-20260912142858 に切り出し済み**
- [local] 分類できない行は keep。誤って残す方が誤って消すより安い
- [local] `pr.state` が merged / closed なら `ahead_of_main` を無視する（統合ブランチ経由 merge の落とし穴。issue #223）
- [local] GC はプロセスを kill しない。生存プロセスがある行は keep にして PID を表示する
- [local] session 一覧は optional 信号で、keep 方向にしか使わない（無い環境で判定が変わらない）
- [local] review / dev / other で安全ゲートを変えない。kind は表示と DB 逆算の要否にだけ使う
- [local] `--all` の既定を on にしない。棚卸しは頻度の低い作業で、日常の起動は現リポで足りる
- [local] worktree 判別述語は code-review から複製せず dev-workflow 側に再実装する。同じ述語が 3 プラグインに散ったら分割単位を疑う（CLAUDE.md の backend 分岐規約と同じ扱い）
- [local] DB drop は marker のある行に限る（design review F1）。名前一致は所有権を証明しない（sanitize 非単射）。marker を DB 所有権の唯一の権威とし、teardown の「marker の DB_NAME を読む」規約と揃える
- [local] 安全ゲートは全 effort 共通（design review F3）。effort が変えるのは走査の広さと確認の深さだけで、削除の可否判定は変えない。mtime を生存プロセスの proxy に使わない（相関しない）
- [local] reap は削除直前に live_pids を再取得する（design review F4）。ADR-20260912142858 の「判定を再実行しない」は verdict の再計算の禁止であって、削除直前の安全再確認（実在・liveness）はこれと両立する
- [→ADR候補] 外部由来文字列（branch / path / DB 名）はスクリプトへ argv 渡し限定・`eval` 禁止（design review F5）。detect-dev-worktree.sh が明文化した脅威モデルを worktree を扱う全スクリプトの共通契約にする → 既存 ADR 化は保留（事例が detect-dev-worktree.sh と scan.sh の 2 件になったら切り出す）

## 未解決事項 (open)

1. **`sanitize_db_name` の要否**（design review F1 で縮小）: F1 採用で marker のある行は `db_name` を直読みするため、drop 経路に sanitize / hash 逆算は要らなくなった。逆算列挙（非 drop の「残っているかも」表示）を残すかどうかで決まる — (a) 逆算列挙も落とし db-name.sh を作らない — Pros: 実装最小・所有権問題の残滓ゼロ / Cons: marker 消失 DB の存在に気づけない (b) 逆算列挙だけ残し db-name.sh を小さく新設 — Pros: 気づける / Cons: lib 1 本増える。現時点では (a) が有力（#223 の実績は DB drop を伴わず、逆算列挙の実需が未確認）。確定タイミング: 実装着手時
2. **`--all` の root 既定**: (a) `$HOME/Projects` 固定 — Pros: 引数不要 / Cons: 利用者固有の値を plugin に埋める (b) `userConfig.worktree_gc_root`（既定 `$HOME`、`maxdepth 4`） — Pros: 規約どおり / Cons: 初回に設定が要る。現時点では (b) が有力（「プロジェクト固有の情報を含めない」規約）。確定タイミング: 実装時
3. **code-review 締めフロー 7 の案内文**: 残骸が複数見つかったとき「`/worktree-gc` で一括」を案内に足すか — (a) 足す（案内のみで依存にならない） (b) 足さない。現時点では (a) が有力。確定タイミング: dev-workflow リリース後、code-review 側の別コミットで
4. **DB エンジンの判別（open 1 で逆算列挙を残す場合のみ）**: F1 採用で marker のある行は engine を marker から取れるため、判別が要るのは open 1(b)（逆算列挙）を残したときだけ。その場合のみ — (a) main env の `DATABASE_URL` スキームから (b) 3 つ試す。現時点では open 1 が (a) 有力なので**この open ごと消える見込み**。確定タイミング: open 1 の確定と同時
5. **`--all` の submodule 除外の実装手段**（design review MINOR）: `git worktree list` に現れる worktree のみを対象にする方針は確定。実装で `find` の結果を worktree 一覧で filter するか、最初から各 main repo の `git worktree list` だけを信頼源にするか。現時点では後者が有力（`find` は main repo の発見にだけ使い、worktree 列挙は git に委ねる）。確定タイミング: scan.sh 実装時
6. **review 残骸（detached）が常に keep に倒れる**（実装後 self-review の related-observation / issue #223 の主目的に直結）: review worktree は `git checkout --detach` で作られ **branch が null**。安全ゲート 6（`pr` が null かつ merged false → keep）に必ず該当し、さらに親 review worktree はネスト agent dir を untracked として抱えて dirty keep になる。結果、MVP の scan は **review 残骸（issue #223 の 18 + 4 件）をほぼ全て keep** にし、掃除できない（安全側なのでデータ損失は無いが feature の有効性が出ない）。掃除するには — (a) review worktree は path から `.claude/worktrees/<name>` を取り、対応 PR が merged/closed なら reap（detached でも path から復元） — Pros: #223 の主目的が回る / Cons: review 命名規約への依存 (b) review worktree は「対象 PR が閉じている」を別経路（cleanup-agent-worktrees.sh の判定流用）で確かめる。現時点では (a) が有力。確定タイミング: MVP リリース後、review 残骸掃除を次段 issue で。**MVP では dev worktree（marker 持ち）の GC が主で、review 残骸は当面 code-review 締めフローと手動に委ねる**

## 実装ブリッジ (Implementation Bridge)

1. **実装着手の単位**（issue #223 を親に 3 コミット）:
   - `feat(dev-workflow): worktree-gc の scan / reap スクリプトとテストを追加`（scripts + lib + tests。SKILL より先に script を固める）
   - `feat(dev-workflow): worktree-gc skill を追加`（SKILL.md + references + teardown 追記 + README + CHANGELOG + bump + marketplace / INDEX / CLAUDE.md 同期 + evals ケース）
   - `docs(code-review): 締めフロー 7 の案内に worktree-gc を足す`（open 3 が (a) なら）
   - feature-dev で進める場合の起動引数: `/feature-dev dev-workflow に worktree-gc skill を追加する design=.claude/designs/20260912-worktree-gc-skill.md`
2. **検証方法**:
   - `python3 .claude-plugin/scripts/run-tests.py` が緑（scan: self / dirty / merged / review path / nested 順の 5 系統、reap: 非 reap 行の拒否 / 不在 path の SKIP / nested → 親の順）
   - 使い捨てリポで `--dry-run` を実測し、表の keep 理由が分類規則と一致する
   - `evals/runner.py --plugin dev-workflow` で teardown と gc のトリガー分離が pass^3
   - `/quality-check`（allowed-tools / トリガー / effort 分岐 / skill-hop）
3. **実装完了時の doc 更新**:
   - frontmatter を `phase: current` に、`last-validated` を更新
   - open 1〜4 の確定結果を「確定した前提」に移す
   - 分類規則が実装で変わったら本 doc を改訂、scan / reap の分割をやめたなら supersede
   - issue #223 を close し、本 doc のパスをコメントに残す

## 関連

- 関連 Issue: https://github.com/yuuki1036/claude-plugins/issues/223
- 関連 spec: なし
- 関連 ADR: `.claude/adr/20260912142858-enumerate-then-reap-split.md`（破壊的な一括操作は列挙と実行を別プロセスに分ける）
- 関連 design doc: なし
- 関連コード: `dev-workflow/skills/worktree-teardown/SKILL.md`、`dev-workflow/skills/worktree-setup/references/db-naming.md`、`code-review/scripts/detect-dev-worktree.sh`
