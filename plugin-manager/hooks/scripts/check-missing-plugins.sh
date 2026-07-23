#!/usr/bin/env bash
# check-missing-plugins.sh
#
# 「ほぼ全部 install しているマーケットプレイス」に後から追加されたプラグインを
# 取りこぼさないようセッション開始時に軽く通知する。
#
# 監視対象の判定: marketplace ごとの install ratio が install_ratio_threshold
# 以上なら監視対象。一部しか install していない巨大 marketplace を通知爆発から守る。
#
# 設定（任意）: ~/.claude/plugin-manager/config.json
#   {
#     "notify_cooldown_days": 7,         // 同一プラグインの再通知最短間隔（既定 7）
#     "install_ratio_threshold": 0.8,    // 監視対象 marketplace の閾値（既定 0.8）
#     "ignore_plugins": [],              // 個別プラグイン無視リスト
#     "ignore_marketplaces": []          // marketplace ごと無視リスト
#   }
#
# 通知 state: ~/.claude/plugin-manager/state.json（自動生成）

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "plugin-manager:missing-plugins"

command -v jq >/dev/null 2>&1 || safe_hook_error Dependency "jq not installed"

PLUGINS_HOME="${HOME}/.claude/plugins"
MARKETPLACES_DIR="${PLUGINS_HOME}/marketplaces"
INSTALLED_FILE="${PLUGINS_HOME}/installed_plugins.json"
CONFIG_DIR="${HOME}/.claude/plugin-manager"
CONFIG_FILE="${CONFIG_DIR}/config.json"
STATE_FILE="${CONFIG_DIR}/state.json"

[ -d "$MARKETPLACES_DIR" ] || safe_hook_error NotFound "$MARKETPLACES_DIR"
[ -f "$INSTALLED_FILE" ] || safe_hook_error NotFound "$INSTALLED_FILE"

cooldown_days=7
install_ratio_threshold="0.8"
ignore_plugins_json="[]"
ignore_marketplaces_json="[]"
if [ -f "$CONFIG_FILE" ]; then
  cooldown_days=$(jq -r '.notify_cooldown_days // 7' "$CONFIG_FILE" 2>/dev/null || echo 7)
  install_ratio_threshold=$(jq -r '.install_ratio_threshold // 0.8' "$CONFIG_FILE" 2>/dev/null || echo "0.8")
  ignore_plugins_json=$(jq -c '.ignore_plugins // []' "$CONFIG_FILE" 2>/dev/null || echo "[]")
  ignore_marketplaces_json=$(jq -c '.ignore_marketplaces // []' "$CONFIG_FILE" 2>/dev/null || echo "[]")
fi

mkdir -p "$CONFIG_DIR" 2>/dev/null || true
[ -f "$STATE_FILE" ] || echo '{"last_notified":{}}' > "$STATE_FILE"

now_epoch=$(date -u "+%s")
now_iso=$(date -u "+%Y-%m-%dT%H:%M:%SZ")

installed_set=$(jq -r '.plugins // {} | keys[]' "$INSTALLED_FILE" 2>/dev/null | sort -u)

filtered=()
migrate_hints=()

shopt -s nullglob
for mp_json in "$MARKETPLACES_DIR"/*/.claude-plugin/marketplace.json; do
  mp_name=$(jq -r '.name // empty' "$mp_json" 2>/dev/null)
  [ -z "$mp_name" ] && continue

  ignore_mp=$(jq -nr --argjson ig "$ignore_marketplaces_json" --arg p "$mp_name" '$ig | map(. == $p) | any')
  [ "$ignore_mp" = "true" ] && continue

  # _superseded_by 付き（= deprecated）は提案から除外する（deprecated の新規 install を勧めない）
  mp_plugins_sorted=$(jq -r --arg mp "$mp_name" '.plugins[]? | select(._superseded_by | not) | .name // empty | "\(.)@\($mp)"' "$mp_json" 2>/dev/null | sort -u)
  [ -z "$mp_plugins_sorted" ] && continue

  # インストール済み deprecated の後継名を収集（後継の直接 install 提案は併存誘発なので update-all 移行に誘導する）
  mp_migr_succ=""
  while IFS=$'\t' read -r dep_id succ; do
    [ -z "$dep_id" ] && continue
    if printf '%s\n' "$installed_set" | grep -qxF "$dep_id"; then
      mp_migr_succ="${mp_migr_succ}${succ}
"
    fi
  done < <(jq -r --arg mp "$mp_name" '.plugins[]? | select(._superseded_by) | "\(.name)@\($mp)\t\(._superseded_by)"' "$mp_json" 2>/dev/null)

  mp_total=$(printf '%s\n' "$mp_plugins_sorted" | wc -l | tr -d ' ')
  mp_installed=$(comm -12 <(printf '%s\n' "$mp_plugins_sorted") <(printf '%s\n' "$installed_set") | wc -l | tr -d ' ')

  [ "$mp_installed" -eq 0 ] && continue
  [ "$mp_installed" -eq "$mp_total" ] && continue

  meets_threshold=$(jq -nr --argjson installed "$mp_installed" --argjson total "$mp_total" --arg threshold "$install_ratio_threshold" \
    '($installed / $total) >= ($threshold | tonumber)')
  [ "$meets_threshold" = "true" ] || continue

  while IFS= read -r plugin; do
    [ -z "$plugin" ] && continue

    in_ignore=$(jq -nr --argjson ig "$ignore_plugins_json" --arg p "$plugin" '$ig | map(. == $p) | any')
    [ "$in_ignore" = "true" ] && continue

    last=$(jq -r --arg p "$plugin" '.last_notified[$p] // ""' "$STATE_FILE" 2>/dev/null)
    if [ -n "$last" ]; then
      last_epoch=$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$last" "+%s" 2>/dev/null || date -u -d "$last" "+%s" 2>/dev/null || echo 0)
      if [ "$last_epoch" -gt 0 ]; then
        diff_days=$(( (now_epoch - last_epoch) / 86400 ))
        [ "$diff_days" -lt "$cooldown_days" ] && continue
      fi
    fi

    bare_name="${plugin%@*}"
    if [ -n "$mp_migr_succ" ] && printf '%s' "$mp_migr_succ" | grep -qxF "$bare_name"; then
      migrate_hints+=("$plugin")
      continue
    fi

    filtered+=("$plugin")
  done < <(comm -23 <(printf '%s\n' "$mp_plugins_sorted") <(printf '%s\n' "$installed_set"))
done

[ "${#filtered[@]}" -eq 0 ] && [ "${#migrate_hints[@]}" -eq 0 ] && exit 0

if [ "${#migrate_hints[@]}" -gt 0 ]; then
  safe_hook_emit "ℹ️  deprecated プラグインの後継が未インストールです。直接 install せず /update-all を実行してください（旧プラグインを uninstall してから後継を install する自動移行が走ります。併存は hook 二重発火・トリガー衝突の原因）:"
  for plugin in "${migrate_hints[@]}"; do
    safe_hook_emit "  - ${plugin}"
  done
  safe_hook_emit ""
fi

if [ "${#filtered[@]}" -gt 0 ]; then
  safe_hook_emit "ℹ️  marketplace に未インストールのプラグインがあります:"
  for plugin in "${filtered[@]}"; do
    safe_hook_emit "  - ${plugin}"
  done
  safe_hook_emit ""
  safe_hook_emit "  インストール: /plugin install <name>@<marketplace>"
fi
safe_hook_emit "  抑止: ~/.claude/plugin-manager/config.json (ignore_plugins / ignore_marketplaces / install_ratio_threshold)"

tmp_state=$(mktemp 2>/dev/null) || tmp_state="${STATE_FILE}.tmp"
# bash 3.2 の set -u は空配列の "${arr[@]}" 展開を unbound 扱いするため ${arr[@]+...} でガードする
plugins_json=$(printf '%s\n' ${filtered[@]+"${filtered[@]}"} ${migrate_hints[@]+"${migrate_hints[@]}"} | grep -v '^$' | jq -R . | jq -s .)
jq --arg now "$now_iso" --argjson plugins "$plugins_json" \
  '.last_notified = (.last_notified // {}) + ($plugins | map({key: ., value: $now}) | from_entries)' \
  "$STATE_FILE" > "$tmp_state" 2>/dev/null && mv "$tmp_state" "$STATE_FILE" || rm -f "$tmp_state"

exit 0
