## fact

hub が**自分で確かめた**事実だけを足す（ファイルを読んだ・コマンドを走らせた・一次ソースのページを見た）。出典は `path:line`・URL・コマンドとその出力の要点。

- 主張と出典は stdin の JSON で渡す（argv に載せない）。出典が config の repo の中のファイルなら `repo`（repo のパス）と `path`（repo の中の相対パス）も入れる。確かめた時点の base の SHA が残り、brief の前にそのファイルが変わったかを `facts` の `stale` で見られる:
  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hub.py" fact --project '<PJ>' <<'PROJECT_HUB_<8 桁の乱数>'
  {"claim": "<主張>", "source": "<出典>", "repo": "<repo のパス>", "path": "<相対パス>"}
  PROJECT_HUB_<8 桁の乱数>
  ```
- 訂正は `--supersedes <前の id>` を付けた新しい行で（消さない。置き換わった行はもう訂正できない）
- sub の主張を確かめずに控えるときは `--unchecked`（brief は引かない）。確かめたら出典を付けて `--supersedes` で確かめた行にする
