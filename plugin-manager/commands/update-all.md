---
description: 自作プラグインを最新版に一括アップデートする（--all で全プラグイン対象）
user_invocable: true
argument-hint: "[--all]"
allowed-tools:
  - Bash
  - SendMessage
---

<!-- 手順の正本はこのファイル。mods が有効な環境では hooks/update-all.ts が同じ手順をモデルを呼ばずに実行する（ここには届かない）。手順を変えたら両方を直す -->

インストール済みプラグインを一括更新してください。

引数 `$ARGUMENTS`:
- 引数なし（デフォルト）: **自作プラグインのみ**更新
- `--all`: インストール済みの全プラグインを更新

## 手順

### Phase 0: 更新対象スコープの判定

`claude plugin list` を実行する（この出力は Phase 1 / Phase 2 でも再利用する）。

1. 出力から plugin-manager 自身の識別子 `plugin-manager@<marketplace>` を探し、`@` 以降を **「自作マーケットプレイス名」** として記録する（このコマンドが属するマーケットプレイス = 自作の出所とみなす。特定の名前をハードコードしない）。
2. 引数 `$ARGUMENTS` を確認する:
   - `--all` を含む → インストール済みの全プラグインを対象（従来挙動）
   - 含まない（デフォルト）→ 自作マーケットプレイスに属するプラグインのみを対象
3. 以降の全 Phase は、ここで絞り込んだ **対象プラグイン** に対してのみ実行する。
4. 対象スコープを冒頭で一言報告する（例: `自作プラグイン（@yuuki1036-claude-plugins）7件を対象に更新します。全件対象にする場合は /update-all --all`）。

### Phase 1: マーケットプレイスキャッシュの最新化

Phase 0 で記録した対象プラグインの `name@marketplace` から、マーケットプレイス名（`@` 以降の部分）を抽出する。
重複を除いた各マーケットプレイスに対して以下を順番に実行する:

マーケットプレイスのカタログをリモートから再取得する:

```bash
claude plugin marketplace update <marketplace-name>
```

**`~/.claude/plugins/cache/` は消さない**（GitHub issue #271）。`${CLAUDE_PLUGIN_ROOT}` は版ごとのディレクトリ（`cache/<marketplace>/<plugin>/<version>/`）を指し、実行中のセッションは起動時に読んだ旧版のパスを使い続ける。CLI は更新・アンインストールのとき旧版に `.orphaned_at` を付けて **14 日後に自分で消す**ので、その間は実行中のセッションが壊れない（公式: Plugin loading reference「Cleanup of previous versions」）。以前はここで marketplace のキャッシュを丸ごと `rm -rf` しており、並行セッションの skill が手順の途中で `No such file or directory` になっていた。新しい版は別ディレクトリに入るので、旧版が残っていても install の反映は妨げない。反映されなかった回は Phase 4 で検知する

### Phase 2: 対象プラグイン一覧とバージョンの記録

Phase 0 で実行した `claude plugin list` の出力を再利用し、Phase 0 で絞り込んだ **対象プラグイン** の以下の情報を記録する:

- `name@marketplace` 形式の識別子
- 現在のバージョン（Before バージョンとして保持する）

> `claude plugin list` の出力例:
> ```
> name@marketplace (v1.2.0)
>   Description: ...
>   Scope: user
> ```

### Phase 2.5: deprecated プラグインの自動移行（auto-migrate）

marketplace が後継プラグインを宣言している deprecated プラグインを検出し、更新の代わりに移行する。

1. **opt-out 確認**: `~/.claude/plugin-manager/config.json` の `auto_migrate` が `false` なら本 Phase をスキップし、検出結果だけ Phase 5 で「移行候補（auto_migrate=false のためスキップ）」として報告する（既定は有効）。
2. **検出**: Phase 1 で最新化した各マーケットプレイスの `~/.claude/plugins/marketplaces/<mp-name>/.claude-plugin/marketplace.json` を読み、Phase 2 の対象プラグインのうち **エントリに `_superseded_by` を持つもの**を抽出する:

```bash
jq -r '.plugins[] | select(._superseded_by) | "\(.name)	\(._superseded_by)"' "$MP_JSON"
```

3. **後継ごとにグループ化して移行を原子的に実行する**（同一後継を持つ deprecated 群は、後継の hook・トリガーと衝突するため「全部 uninstall → 後継を 1 回 install」の順序を厳守。片方だけ uninstall した中間状態で止めない）:
   1. グループ内の deprecated プラグインを全て uninstall する（Phase 3-1 と同じフォールバック chain を使う）
   2. 後継 `<successor>@<marketplace>` が未インストールなら install する（既にインストール済みなら uninstall のみで完了 = 併存状態の解消）
   3. **ロールバック**: 後継の install に失敗した場合、直前に uninstall した deprecated 群を元のバージョンで再 install し、エラーとして報告する（プラグインが 1 つも無い状態で放置しない）
4. 移行したプラグインは Phase 3 の更新対象から除外する。
5. 移行結果（deprecated 群 → 後継、uninstall/install の成否）を Phase 5 の報告に渡す。

> 例: deprecated なプラグインが `_superseded_by: "<後継>"` を宣言していれば、それがインストール済みのマシンでは update-all 実行時に自動で後継へ移行される（旧 linear-workflow / indie-workflow → issue-workflow がこの経路で移行された）。

### Phase 3: 各プラグインの再インストール

CLI の競合を避けるため順次実行（並列不可）。
各プラグインに対して以下を実行する:

#### 3-1. アンインストール（フォールバック付き）

以下の順で試行し、いずれかが成功したら 3-2 に進む:

1. `claude plugin uninstall <name@marketplace>`
2. 失敗した場合: `claude plugin uninstall <name@marketplace> --scope user`
3. 失敗した場合: `claude plugin uninstall <name@marketplace> --scope project`
4. すべて失敗した場合: `~/.claude/plugins/installed_plugins.json` を読み込み、該当プラグインのエントリを JSON から削除して書き戻す（手動削除フォールバック）

#### 3-2. インストール

```bash
claude plugin install <name@marketplace>
```

- install が失敗した場合はエラーとして記録し、次のプラグインに進む

### Phase 4: 更新後バージョンの取得

`claude plugin list` を実行し、各プラグインの更新後バージョン（After）を取得する。

**反映の確認**: After を、Phase 1 で再取得した marketplace の `marketplace.json`（Phase 2.5 と同じ `~/.claude/plugins/marketplaces/<mp-name>/.claude-plugin/marketplace.json`）にある版と突き合わせる。一致しない（marketplace の方が新しい）プラグインは「反映されていない」として Phase 5 の表の結果欄に `未反映（marketplace: <版>）` と出し、手動の対処（`claude plugin update <name@marketplace>` を実行して再確認）を添える。**キャッシュを消して直そうとしない**（実行中のセッションが参照している版を消すことになる / #271）

```bash
jq -r --arg n "<plugin-name>" '.plugins[] | select(.name == $n) | .version // empty' "$MP_JSON"
```

### Phase 4.5: 更新内容の取得

Phase 4 で「更新済み」と判定されたプラグイン（Before ≠ After）に対して、CHANGELOG.md から更新内容を抽出する。

1. キャッシュ内の CHANGELOG.md を読み込む:

```bash
cat ~/.claude/plugins/cache/<marketplace-name>/<plugin-name>/<After-version>/CHANGELOG.md
```

2. CHANGELOG.md から Before バージョンより新しいエントリを抽出する:
   - 見出しの版が Before より新しく After 以下の節（`## [<版>]` から次の版の見出しの直前まで）を、ファイルの並びのまま取得する。`## [<After-version>]` の見出しが無ければ「CHANGELOG なし」と同じに扱う
   - 並び順ではなく版で比べる。backport を時系列の位置に挟んだ CHANGELOG では、`## [<Before-version>]` の見出しより下にも新しい節がある（GitHub #464）
   - `Unreleased` など semver でない見出しの節は含めない。Before か After が semver でなければ、`## [<After-version>]` から `## [<Before-version>]` の直前までを並び順で取得する
   - Before と After の間に複数バージョンがある場合は全て含める
   - `### Added` / `### Fixed` / `### Changed` 等のサブセクションをそのまま保持

3. CHANGELOG.md が存在しない場合や読み取りに失敗した場合は「CHANGELOG なし」として記録する

### Phase 4.7: 未インストールの自作プラグイン検出

自作マーケットプレイスに登録済みだが未インストールのプラグインを検出する（後から追加された自作プラグインの取りこぼし防止）。デフォルトスコープ・`--all` のどちらでも、検出対象は **Phase 0 で記録した自作マーケットプレイス** に限定する（他マーケットプレイスは対象外）。

1. Phase 0 で記録した自作マーケットプレイス名に対応する `marketplace.json` を特定し、登録済み全プラグインの `name@marketplace` 一覧を取得する。
2. インストール済み一覧（`installed_plugins.json` の keys）と突き合わせ、差分（＝登録済みだが未インストール）を抽出する。
3. SessionStart hook と挙動を揃えるため、`~/.claude/plugin-manager/config.json` の `ignore_plugins` / `ignore_marketplaces` を尊重して除外する（cooldown / install_ratio 閾値は update-all では適用しない＝明示実行なので毎回検出する）。
4. **`_superseded_by` を持つ（= deprecated な）未インストールプラグインは提案から除外する**（deprecated の新規 install を勧めない）。

```bash
MP_NAME="<Phase 0 で記録した自作マーケットプレイス名>"

# 真実の marketplace.json は marketplaces/ 配下（cache/ ではない）
MP_JSON=""
for f in ~/.claude/plugins/marketplaces/*/.claude-plugin/marketplace.json; do
  [ "$(jq -r '.name // empty' "$f" 2>/dev/null)" = "$MP_NAME" ] && MP_JSON="$f" && break
done

INSTALLED_FILE=~/.claude/plugins/installed_plugins.json
CONFIG_FILE=~/.claude/plugin-manager/config.json

if [ -n "$MP_JSON" ] && [ -f "$INSTALLED_FILE" ]; then
  ignore_plugins_json='[]'; ignore_marketplaces_json='[]'
  if [ -f "$CONFIG_FILE" ]; then
    ignore_plugins_json=$(jq -c '.ignore_plugins // []' "$CONFIG_FILE" 2>/dev/null || echo '[]')
    ignore_marketplaces_json=$(jq -c '.ignore_marketplaces // []' "$CONFIG_FILE" 2>/dev/null || echo '[]')
  fi
  if [ "$(jq -nr --argjson ig "$ignore_marketplaces_json" --arg p "$MP_NAME" '$ig|map(.==$p)|any')" != "true" ]; then
    registered=$(jq -r --arg mp "$MP_NAME" '.plugins[]? | select(._superseded_by | not) | .name // empty | "\(.)@\($mp)"' "$MP_JSON" 2>/dev/null | sort -u)
    installed=$(jq -r '.plugins // {} | keys[]' "$INSTALLED_FILE" 2>/dev/null | sort -u)
    comm -23 <(printf '%s\n' "$registered") <(printf '%s\n' "$installed") | while IFS= read -r p; do
      [ -z "$p" ] && continue
      [ "$(jq -nr --argjson ig "$ignore_plugins_json" --arg p "$p" '$ig|map(.==$p)|any')" = "true" ] && continue
      echo "$p"
    done
  fi
fi
```

4. 抽出結果（未インストールの `name@marketplace` 一覧）を Phase 5 の報告に渡す。`marketplace.json` が見つからない場合は検出をスキップする（警告のみ・更新処理は止めない）。

### Phase 4.8: hub 系セッションへの読み直し依頼

Phase 4 で **自作マーケットプレイスの project-hub（`project-hub@<Phase 0 の自作マーケットプレイス名>`）が「更新済み」になった回だけ**行う（それ以外の更新では何もせず、Phase 5 にこの節を出さない。2026-11-18 決定）。hub 系のセッション（project-hub の hub のように、ほかのセッションを束ねる常設のセッション）は、更新前に読んだ SKILL.md と同梱スクリプトの手順で動き続けるからである（GitHub issue #460）。`--all` で入る別マーケットプレイスの同名プラグインは、hub が使う project-hub ではないので数えない。ほかのプラグインの skill の更新は、各セッションの stale-skill hook が次の発言で知らせる。

1. **宛先を集める**: project-hub のデータの置き場所（`$PROJECT_HUB_DIR`。無ければ `${CLAUDE_CONFIG_DIR:-~/.claude}/project-hub`）の `<PJ>/` ごとに `config.json` と `hub.json` を読み、`config.json` の `status` が `active` の PJ の `hub.json` から `session_id`・`host_session_id`・`name` を取る。`session_id` が同じものは 1 件にまとめる（1 つの会話が複数の PJ を兼ねることがある）。置き場所が無ければ何もせず（project-hub が入っていない環境でも止めない）、ファイルを読めない PJ は飛ばす。glob ではなく `find` で列挙する（zsh は一致の無い glob をエラーにする）

```bash
HUB_DIR="${PROJECT_HUB_DIR:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/project-hub}"
echo "self	${CLAUDE_CODE_SESSION_ID:-}	${CLAUDE_CODE_HOST_SESSION_ID:-}"
find "$HUB_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | while IFS= read -r d; do
  [ "$(jq -r '.status // empty' "$d/config.json" 2>/dev/null)" = active ] || continue
  jq -r --arg p "$(basename "$d")" '[$p, .session_id // "", .host_session_id // "", .name // ""] | @tsv' "$d/hub.json" 2>/dev/null
done
```

2. **送る**: 宛先ごとに SendMessage で次の本文を送る（`<Before>` / `<After>` は project-hub の版、`<installPath>` は Phase 4 の After の版のディレクトリ）。宛先は `host_session_id`（会話の ID。開き直しても改名しても変わらない）で、空か届かなければ `name` で送り直す（名前は重なると宛先が決まらないので後に回す）。mod（`hooks/update-all.ts`）は `$.session.send` が CLI の会話 ID も宛先に取れるので、この前に `session_id` を試す。宛先がこのセッション自身（hub の会話で `/update-all` を打った回。手順 1 の `self` の行の ID と、宛先の `session_id` か `host_session_id` が一致する）なら送らず、「このセッション自身」と報告する:

```
[plugin-manager] update-all で project-hub が <Before> → <After> に更新された。次の発言から、project-hub の skill は新しい版の SKILL.md を Read し直してから使う。
新しい版: <installPath>/skills/<skill>/SKILL.md（同梱の scripts/ も同じ版を使う）
返事は不要。
```

3. 送った宛先と、送らなかった宛先と理由（届かなかった・hub 系のセッションが無い）を Phase 5 に渡す

### Phase 5: 結果の報告

以下のフォーマットで報告する:

```
## プラグイン更新結果

| プラグイン | Before | After | 結果 |
|-----------|--------|-------|------|
| name@marketplace | 1.0.0 | 1.1.0 | 更新済み |
| name@marketplace | 1.0.0 | 1.0.0 | 変更なし |
| name@marketplace | 1.0.0 | - | エラー |
| name@marketplace | 1.0.0 | 1.0.0 | 未反映（marketplace: 1.1.0） |

### 移行（deprecated → 後継）

- <deprecated-plugin> → <後継> へ移行しました（uninstall → install）
- 反映には Claude Code の再起動が必要です

### 更新内容

#### name (1.0.0 → 1.1.0)
- Added: 新機能の説明
- Fixed: バグ修正の説明

### 未インストールの自作プラグイン

自作マーケットプレイスに登録済みだが未インストールのプラグインがあります（`update-all` は更新専用のため自動導入はしません）:

- name@marketplace
- name@marketplace

導入する場合:

    claude plugin install <name>@<marketplace>

抑止: ~/.claude/plugin-manager/config.json の ignore_plugins / ignore_marketplaces

### hub 系セッションへの読み直し依頼

- 送った: <hub の名前>（<PJ>, <PJ>）
- 送らなかった: <hub の名前>（<PJ>） — <理由>

反映にはClaude Codeの再起動が必要です。
動いているセッションには、そのセッションで使った skill が更新されていれば、次の発言で読み直す SKILL.md のパスを知らせる。
```

結果の判定ルール:
- Before と After のバージョンが異なる → **更新済み**
- Before と After のバージョンが同じ → **変更なし**
- install に失敗した → **エラー**（After は `-` と表示）

「移行」セクションは Phase 2.5 で移行（または移行候補の検出）が 1 件以上ある場合のみ表示する。
「更新内容」セクションは更新済みプラグインが1つ以上ある場合のみ表示する。
全プラグインが「変更なし」の場合はこのセクションを省略する。
末尾の「動いているセッションには、…」の行も、更新済みが 1 つ以上ある場合のみ表示する（再起動しないで動き続けるセッションには、plugin-manager の stale-skill hook が次の発言で読み直す SKILL.md を知らせる）。

「hub 系セッションへの読み直し依頼」セクションは Phase 4.8 を行った回（project-hub が更新済み）だけ表示する。宛先が 0 件なら「送らなかった: hub 系のセッションが無い（project-hub のデータに active な PJ が無い）」の 1 行を出す。

「未インストールの自作プラグイン」セクションは Phase 4.7 で検出が1件以上ある場合のみ表示する。0件の場合は省略する（更新のみが成果物）。
