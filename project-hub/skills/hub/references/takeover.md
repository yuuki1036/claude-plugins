## takeover

このセッションを hub にする（前の hub のセッションを閉じた・開き直した）。ListAgents から自分の名前を取り、`hub.py takeover --project '<PJ>' --name '<名前>'`。config・journal・facts は触らない（自動で送った連絡の一覧の印と、別の PJ の印 `cross_seen_lines` / `cross_last_overlaps` も引き継ぐ）。出力の `mode_notice` は**必ずそのまま**伝え、`warning` は init の 4 と同じく伝える。続けて `status` を回す。
