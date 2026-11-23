## living-spec `<path|->`

PJ の living spec を結ぶ・外す。`hub.py set-living-spec --project '<PJ>' --path '<.claude/living-specs/<slug>.md のパス>'`（外すときは `--path -`）。結ぶと state.md に living spec のパスが出て、コンパクションの後も決定の置き場所が分かる。hub は自分の判断では living spec の決定を書かない（決定を書くのは `living-spec` skill で、lead が決めたときだけ。進捗はタイムラインへ聞かずに書く。どちらも `hub-living-spec` の決まり）
