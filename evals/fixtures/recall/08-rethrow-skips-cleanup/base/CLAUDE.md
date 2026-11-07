# CLAUDE.md

## server action の呼び出し規約

- server action の中の `redirect()` / `notFound()` は、クライアントでは await した promise の reject として catch に届く。
- server action を await する catch では、先頭で `unstable_rethrow(err)` を呼んで投げ直す。握りつぶすと画面が移らず、失敗のトーストが出る。
