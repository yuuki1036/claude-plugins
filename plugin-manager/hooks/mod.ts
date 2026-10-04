// plugin-manager の mods の入口（hooks.json の `modules` はプラグインに 1 つだけ）
import type { Register } from 'claude-code'

import { registerUpdateAll } from './update-all'

export const register: Register = on => {
  registerUpdateAll(on)
}
