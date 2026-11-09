// scripts/scope-size.py と hooks/issue-band-lib.ts（mod）の数え方・超過判定を突き合わせる共有 fixture（GitHub issue #425）。
// 期待値は手で書く（どちらの実装からも生成しない）。mods/issue-workflow/tests/issue-band.test.ts が import し、
// test_issue_workflow_scope_size.py が `export default ` の後ろを JSON として読む（mod は .json を import できない）。
// そのため `export default ` の後ろは JSON として正しい形のまま保つ（末尾カンマ・コメントを入れない）
export default {
 "cases": [
  {
   "name": "上限ちょうどは超えない",
   "text": "---\nid: ISS-1\nscope_size: small\n---\n# ISS-1: t\n\n## 進捗\n- [ ] a\n- [ ] b\n- [x] c\n",
   "total": 3,
   "done": 1,
   "over": false
  },
  {
   "name": "上限を 1 超えたら超過",
   "text": "---\nid: ISS-1\nscope_size: small\n---\n# ISS-1: t\n\n## 進捗\n- [ ] a\n- [ ] b\n- [ ] c\n- [X] d\n",
   "total": 4,
   "done": 1,
   "over": true
  },
  {
   "name": "medium の境界",
   "text": "---\nid: ISS-1\nscope_size: medium\n---\n# ISS-1: t\n\n## 進捗\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n",
   "total": 8,
   "done": 0,
   "over": true
  },
  {
   "name": "進捗を優先し完了条件と足さない",
   "text": "---\nid: ISS-1\nscope_size: small\n---\n# ISS-1: t\n\n## 進捗\n- [ ] a\n- [ ] b\n\n## 完了条件\n- [ ] a\n- [ ] b\n- [ ] c\n",
   "total": 2,
   "done": 0,
   "over": false
  },
  {
   "name": "進捗が空なら完了条件を数える",
   "text": "---\nid: ISS-1\nscope_size: small\n---\n# ISS-1: t\n\n## 進捗\n\n未記入\n\n## 完了条件\n- [x] a\n- [ ] b\n- [X] c\n- [ ] d\n",
   "total": 4,
   "done": 2,
   "over": true
  },
  {
   "name": "節の外と別の節は数えない",
   "text": "---\nid: ISS-1\nscope_size: small\n---\n# ISS-1: t\n\n- [ ] 前\n## 進捗\n- [ ] a\n## スコープ外\n- [ ] x\n- [ ] y\n- [ ] z\n## メモ\n- [ ] m\n",
   "total": 1,
   "done": 0,
   "over": false
  },
  {
   "name": "インデントした項目も数える",
   "text": "---\nid: ISS-1\nscope_size: small\n---\n# ISS-1: t\n\n## 進捗\n- [x] a\n  - [ ] b\n    - [X] c\n  - [ ] d\n- 普通の箇条書き\n",
   "total": 4,
   "done": 2,
   "over": true
  },
  {
   "name": "見出しの後ろに語が付くと別の節",
   "text": "---\nid: ISS-1\nscope_size: small\n---\n# ISS-1: t\n\n## 進捗メモ\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n",
   "total": 0,
   "done": 0,
   "over": false
  },
  {
   "name": "行末の注釈を外して読む",
   "text": "---\nid: ISS-1\nscope_size: small            # 必須。値: small / medium / large\n---\n## 進捗\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n",
   "total": 4,
   "done": 0,
   "over": true
  },
  {
   "name": "引用符で囲んだ値",
   "text": "---\nid: ISS-1\nscope_size: \"small\"\n---\n## 進捗\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n",
   "total": 4,
   "done": 0,
   "over": true
  },
  {
   "name": "不明な値は超過にしない",
   "text": "---\nid: ISS-1\nscope_size: gigantic\n---\n# ISS-1: t\n\n## 進捗\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n",
   "total": 99,
   "done": 0,
   "over": false
  },
  {
   "name": "scope_size が無ければ超過にしない",
   "text": "---\nid: ISS-1\n---\n## 進捗\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n",
   "total": 9,
   "done": 0,
   "over": false
  },
  {
   "name": "BOM 付きのファイルも読む",
   "text": "\ufeff---\nid: ISS-1\nscope_size: small\n---\n# ISS-1: t\n\n## 進捗\n- [ ] t\n- [ ] t\n- [ ] t\n- [ ] t\n",
   "total": 4,
   "done": 0,
   "over": true
  },
  {
   "name": "CRLF 改行でも読む",
   "text": "---\r\nid: ISS-1\r\nscope_size: small\r\n---\r\n## 進捗\r\n- [ ] t\r\n- [ ] t\r\n- [x] t\r\n- [ ] t\r\n",
   "total": 4,
   "done": 1,
   "over": true
  },
  {
   "name": "U+2028 では行を分けない",
   "text": "---\nid: ISS-1\nscope_size: small\n---\n## 進捗\n- [ ] a\u2028- [ ] b\n- [ ] c\n- [ ] d\n- [ ] e\n",
   "total": 4,
   "done": 0,
   "over": true
  }
 ]
}
