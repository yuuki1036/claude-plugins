// dev-workflow の mods の入口（hooks.json の `modules` はプラグインに 1 つだけ）
import type { Register } from 'claude-code'

import { registerWorktreeGc } from './worktree-gc'

export const register: Register = (on, options) => {
  registerWorktreeGc(on, options)
}
