// issue-workflow の mods の入口（hooks.json の `modules` はプラグインに 1 つだけ）
import type { Register } from 'claude-code'

import { registerIssueBand } from './issue-band'

export const register: Register = on => {
  registerIssueBand(on)
}
