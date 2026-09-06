# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [0.3.7] - 2026-09-06

### Fixed

- **同名 command の本文に SKILL.md への Read 誘導を置いた**（GitHub issue #219）。command 名と skill 名が
  同名だと `Skill plugin:name` で呼んでも**注入されるのは command 本文**で、SKILL.md には到達しない
  （#206 の本文版）。本文が「X スキルを使って」だけだと model は記憶で手順を再現するか cache を
  `ls | head -1` で掴む — 実測（2026-09-06）では辞書順で旧版を掴み、publish まで丸ごと落ちた。
  `${CLAUDE_PLUGIN_ROOT}` が展開されていない場合の解決先（`installed_plugins.json` の `installPath`）も
  本文に書いた。`validate_plugin_quality.py` の `skill-hop-cmd` が error で強制する。対象: `living-spec` / `living-spec-maintain`

## [0.3.6] - 2026-09-05

### Fixed

- **`living-spec` と `living-spec-maintain` の境界を description に明示した**。eval
  `living-spec-trigger-status`（「収束率と残ってる open OQ を見せて」）が router に
  `living-spec-maintain` へ寄せられていた（#206 の前後比較で k=3 中 1〜2 回）。`status`
  サブコマンド（収束率 = 確定 ÷ 全項目 / open OQ の残数）は `living-spec` の責務なので、
  両側の description に**対比の 1 文**を足した — 「収束率や open OQ を見るのは living-spec
  の status / 壊れていないかの検証は maintain」。逐語トリガーも表示系の言い回し
  （「収束率を見せて」「open OQ を見せて」「残ってる OQ」「living spec の現在地」）を追加。
  同名ペアなので `commands/*.md` 側にも同じ内容を複製している（#206）

## [0.3.5] - 2026-09-05

### Fixed

- **同名 command の description に `トリガー:` を複製した**（GitHub issue #206）。command 名と skill 名が
  同名だと、スキル選択の一覧に載るのは `commands/*.md` の description だけで **`SKILL.md` 側は
  router に届かない**。`トリガー:` 必須の規約は SKILL.md にだけ掛かっていたので、字面は通るが
  ルーティングには効いていなかった。対象: `living-spec` / `living-spec-maintain`。
  - **移動ではなく複製**（SKILL.md 側は残す） — `check_router_trigger_drift` が SKILL.md の
    `トリガー:` を入力にしており、移動するとその機械ガードが沈黙する
  - 引用符なしの description に `トリガー:` を足すと YAML の `key: value` と解釈されて frontmatter が
    壊れるので、二重引用符で囲んだ（既存の書式に揃えた）
  - `validate_plugin_quality.py` が同名ペアの commands 側にも `トリガー:` 必須を error で強制する
    （`[trigger-cmd]`）

## [0.3.4] - 2026-08-28

### Fixed

- **doc と実装の乖離を掃引した**（GitHub issue #185）。旧 linear-workflow / indie-workflow の
  死んだ参照の張り替え、README が実装と食い違っていた記述（欠落していた表の行・設定キー・
  引数・エラー文言）の訂正が主な内容。挙動の変更は無い

## [0.3.3] - 2026-08-28

### Changed

- **`plugin.json` の description を 586 → 183 字に圧縮した**（GitHub issue #183 /
  設計 `.claude/designs/20260610-plugin-description-diet.md`）。description は「これは何の
  プラグインか」を伝える 1〜2 文だが、バージョンアップごとに機能詳細を積層してリリースノート化
  していた。落とした詳細は CHANGELOG / README / SKILL.md に既出で情報は失われない。
  あわせて `validate_plugin_quality.py` に 400 字の上限検査（非ブロッキング warning）を追加し、
  再発を機械強制に寄せた

## [0.3.2] - 2026-08-17

### Changed
- 削除された `linear-workflow` / `indie-workflow` への参照を `issue-workflow` に張り替えた（旧 2 プラグインは統合後継への移行完了に伴いリポジトリから削除）

## [0.3.1] - 2026-07-16

### Changed

- `living-spec` / `living-spec-maintain` skill の description を圧縮（常駐コンテキスト削減）。情報 move 除去の設計背景・段別 severity 内訳・design-doc/adr-keeper 責務分離の説明を SKILL.md 本文へ降ろし、what + サブコマンド列挙 + トリガーに絞った（eval pass^k=3 で非退行を確認。既存の近接スキル混同 3 件はダイエット前後で同一 fail ＝回帰なし）。

## [0.3.0] - 2026-07-15

### Added

- **`/living-spec-maintain` を実装**（#87）。living spec の整合と鮮度を 8 段のファネルで検証する
  - `commands/living-spec-maintain.md` / `skills/living-spec-maintain/SKILL.md`: 段 1-7 の機械判定（表スキーマ / 採番の重複・欠番 / OQ ⇔ Decision の双方向参照 / 外部 URL の死リンク / OQ の行内整合 / 確度ラベルの塩漬け / `last_updated` の整合）+ 段 8 の LLM 判断（現在地サマリのズレ）
  - `skills/living-spec-maintain/references/check-rules.md`: 段 1-8 の判定内容・severity・**修正方針**の正本
  - `--spec <slug>` / `--all` に対応
- **`${CLAUDE_EFFORT}` 実行時分岐**（深掘り系スキルの規約）: `low` / `medium` は段 1-7 のみ。`high` 以上で段 8 を追加。`low` の `--all` は最大 3 ファイルで打ち切る（打ち切り件数はレポートに明記）
- **doc-freshness 未導入時の縮退 warning**: fail-fast させず、レポート冒頭に「ファイル単位の鮮度と内部リンクの検証は行われません」と明示する（silent に不成立にしない）
- **検証を通過したときだけ `last-validated` を更新**する完了処理（承認つき）。`format-spec.md` 10 節の「maintain の実行＝内容を確認する行為とみなす」を機械化した

### Changed

- `skills/living-spec/SKILL.md`: `maintain` サブコマンドの扱いを「未実装」から `/living-spec-maintain` への案内に変更。即興実装しないガードは維持

### Notes

- **doc-freshness の縮退判定は enabled-only**（`grep -Eq '"doc-freshness@[^"]*"[[:space:]]*:[[:space:]]*true'` で global + project-local の 3 ファイルを走査）。キー存在だけを見る `grep -q '"doc-freshness@'` は使わない — `": false"`（インストール済みだが無効化）を導入済みと誤判定し、project-scoped 有効化を取りこぼす（spec-advisor が #74 の誤検知回避として同じ判定に揃えている）。**バージョンは検証できない**ので、有効時も「0.4.0 以降が必要。それ未満では走査されない」を必ず 1 行添える。宣言した下限を検証しないまま黙るのは、このプラグインが避けると宣言した silent 不成立そのもの
- **段 8 のゲートは「段 1-3 の Critical が 0 件」であって「段 1-7 を通過」ではない**。段 4-7 の Warning / Info は段 8 を止めない（段 6 の Warning は未定項目が 16 日で普通に出る）
- **完了処理の確認で「通過しました」と言わない**。Critical 0 でも Warning / Info は残りうるので、レポートの `判定: 要修正` と矛盾する。件数を明示し、`(Recommended)` も付けない（既定 effort では段 8 が skip され、機械が通したのは構造だけ）
- **段 1-3 で Critical が出たら段 8 に進まない**（ファネル）。壊れた表を LLM に読ませて意味を論じさせても無駄なため
- **fail-closed はパースにのみ適用する**。パース不能は「ファイルが壊れている」証拠なので Critical に倒すが、**段 4 のネットワーク不達は死リンクの証拠にならない**ので Info（未検証）に留める。ここを倒すとオフライン実行のたびに全リンクが指摘になる
- **段 2 の欠番は番号を詰めて直さない**。Critical が指しているのは「欠番という状態」ではなく「行が消えた事実」で、詰めると事実が見えなくなる。`git log -p` で元の ID のまま復元する
- **段 2 の既知の限界**: 欠番検出は 1..max の抜けを探すので、**max の ID を消した削除は原理的に検出できない**（残りが連続するため。実測で確認）。max を消すと次の採番が同じ ID を再利用する（6 節が禁じる操作）。削除された ID を参照する Decision があれば段 3 が拾うが、**どこからも参照されていない open な OQ を max で消した場合はファイル内の情報だけでは検出できない**。行の削除はそもそも 3 節・4 節が禁じており `oq` / `decision` は削除操作を持たない（W3）。段 2 は事後の網であって削除を防ぐ機構ではない。check-rules.md に検出境界の表を記載
- **`last-validated` は Critical が残っている状態では更新しない**（確認自体を出さない）。「内容を確認し問題ないと判断した日」の意味に反するため
- **契約（format-spec）と検知器（check-rules）を分離**した。契約を検知器側に書き写すと二重管理になり、片方だけ更新されて「検知器が古い契約を守らせる」状態になる
- コスト×精度 10 原則の採用/不採用を SKILL.md に明記（採用: #1 ファネル / #3 段階予算 / #8 外部オラクル + fail-closed。不採用: #2 2 軸スコア化（機械判定は confidence が常に 100）/ #4 #5 #7（agent fan-out なし）/ #6（failure-journal の責務））

## [0.2.0] - 2026-07-15

### Added

- **`oq` / `decision` / `spec` / `status` を実装**（#87）。living spec の中核である「採番・双方向参照・収束の可視化」が揃った
  - `oq <text>`: OQ 台帳に append。`OQ<max+1>` を機械採番、`status: open`、`since` を `date` で機械付与
  - `oq list [--all]`: 既定は open のみ表示（closed は台帳に残したまま、フィルタは表示だけの話）
  - `decision <text>`: Decision log に append（`D<max+1>`）し、関連 OQ を AskUserQuestion で選ばせて `closed` + `関連 D#` に更新。**書き込み後に Read で双方向参照を検証し、片方向ならその場で直す**（adr-keeper の supersede が新旧を Read で相互参照確認するのと同じ規律）
  - `spec <項目> <確度>`: 確度ラベルを更新し `since` を機械付与。確度が 3 値以外なら正規化せず倒す。項目が重複していたら更新せず倒す（2 節の一意性違反）
  - `status`: 収束率（確定 ÷ 全項目）+ open OQ 残数 + セッション再開導線
- `--spec <slug>` で対象ファイルを明示指定できる（省略時: 1 件なら自動 / 複数なら選択 / 0 件なら init を案内）
- SKILL.md に**書き込み前後の共通規律 W1-W5** を新設（日付は Bash / 採番はコメント除去後の max+1 / 削除しない / `last_updated` を更新 / 0 行の表への append）

### Changed

- `references/format-spec.md` に **0 節「対象ファイルの特定」** を追加。`.claude/living-specs/` はフラットで複数ファイルが並ぶため、どのファイルに対して実行するかを契約として明文化した（自動で推測せず、複数なら選ばせる）
- `references/format-spec.md` 2 節に **`項目` の一意性**を追加（`spec` が `項目` を更新キーにするため。重複すると更新先が非決定になる）
- `references/format-spec.md` 8 節に**セル内 `|` の扱い**を追加し、9 節の正規表現をエスケープ許容（`(?:[^|\\]|\\.)+?`）にした。従来は「`\|` にエスケープする」と指示しながら正規表現が `[^|]+?` で受けており、**指示に従っても従わなくても契約を満たす行が書けなかった**（`|` を含む OQ が一覧と収束率から黙って消える）。全角 `｜` への置換案は採らない（ユーザーが書いた問いの文字を機械が黙って変えることになるため）
- `references/format-spec.md` 9 節に **Decision の残り 5 bullet（`日付` / `確信度` / `根拠` / `出典` / `残`）の正規表現**を追加し、**段 1 の適用範囲をセクション別に分けた**。従来は「一致しない行は段 1 Critical」と規定しながら bullet のパターンが 2 本しか無く、4 節どおりの正しい Decision エントリが Critical と誤判定される契約になっていた
- allowed-tools に `Edit` を追加（表の in-place 更新のため）。採番・パースは Bash の `grep` パイプラインと Read で完結するので `Grep` ツールは宣言しない（最小性を保つ）

### Notes

- **採番の前に必ず HTML コメント区間を除去する**（9 節の前処理契約）。除去を省くと、テンプレや説明コメント内の記入例を実在 ID として数え、最初の決定が `D2` から始まる
- **OQ の reopen は許容しない**。close 後に再燃したら新しい OQ を起票して旧 OQ / D# を参照する（履歴を線形に保つ）
- **確度の逆行（確定 → 方向性(仮)）は警告しない**。決定が覆るのは正常な事象
- 整合・鮮度チェック（`/living-spec-maintain` の段 1-8）は未実装。即興実装しないガードを SKILL.md に残している

## [0.1.0] - 2026-07-15

### Added

- **初版リリース** (#87)。Issue 化前の設計収束ドキュメント (living spec) を運用する command + skill を実装
- `commands/living-spec.md`: `init [slug]` を実装。`oq` / `decision` / `spec` / `status` / `maintain` は分岐表に未実装として記載
- `skills/living-spec/SKILL.md`: 保存先確認 / サブコマンド判定 / init の引数解析（slug 命名規則・既存なら中止）/ scaffold 生成 / 完了報告
- `skills/living-spec/references/format-spec.md`: 表スキーマ・確度ラベル 3 値・採番規約・frontmatter の**正本**。maintain の段 1-3 が機械パースする入力契約
- `skills/living-spec/references/template.md`: living spec 本文テンプレ + frontmatter 雛形（7 セクション構成）

### Notes

- 設計は design doc `.claude/designs/20260715-living-spec-workflow.md` が確定仕様（status: approved）
- **第 1 引数は常にサブコマンドとして解釈し、既定のサブコマンドを持たない**（`/living-spec` 単独は usage）。slug は `init` の後ろにのみ置ける。サブコマンド名と slug 名を同じ名前空間に置くと、後からサブコマンドを追加するたびに、その語を slug に使っていた利用者の意味が変わるため（`/living-spec oq` が「slug=oq で作成」から「OQ を追加」に反転する）。Issue 追加時の破壊的変更を初版のうちに回避する
- **`format-spec.md` の 9 節は、正規表現を当てる前に HTML コメント区間を除去することを入力契約として要求する**。1 節がパース対象セクションでのコメントを許可しているため、前処理を省くとコメント内の記入例が採番・相互参照に拾われる（実在しない D1 を数えて最初の決定が D2 から始まる等）。テンプレ側でも行頭一致する記入例を書かないことで二重に防ぐ
- OQ 台帳と Decision log は**両方 append-only**。OQ は close しても行を消さず `status: closed` に更新して `関連 D#` を書く。情報の move を設計から除くことで消失を構造的に防ぎ、参照の不整合のみ maintain の事後検知に委ねる
- 日付は Bash `date +%Y-%m-%d` で取得（擬似日付を作らない規律は adr-keeper / design-doc と共通）
- frontmatter は doc-freshness と互換（`last-validated` / `phase`）。`append_only: true` は付けない（living spec は鮮度を測る対象そのもののため。ADR とは逆）
- Shared State 契約フィールドは持たない（規約の対象は複数プラグインが読み書きするファイルで、v0.1.0 の living spec に consumer がいないため）
- 鮮度 lint の委譲には **doc-freshness 0.4.0 以降**が必要（`.claude/living-specs/` の走査対象追加が 0.4.0 で入った）。それ未満では living spec が走査されず stale が検出されない。README の「既知の制約」を参照
