// code-review の mods の入口。hooks.json の `modules` はプラグインに 1 つしか書けない（2 つ目は読み込みで拒否）ので、ここで束ねる
import type { Register } from 'claude-code'

import { registerGuideDiff } from './guide-diff'
import { ledgerSpawned, registerLedger } from './review-ledger'
import { registerProgress } from './review-progress'

export const register: Register = on => {
  registerGuideDiff(on)
  registerLedger(on)
  // `agent.spawn` は 1 度しか登録できないので、受ける review-progress から ledger へ渡す
  registerProgress(on, ledgerSpawned)
}
