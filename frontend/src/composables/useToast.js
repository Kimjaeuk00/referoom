import { reactive } from 'vue'

const toasts = reactive([])
let seq = 0

export function dismissToast(id) {
  const index = toasts.findIndex((t) => t.id === id)
  if (index >= 0) toasts.splice(index, 1)
}

export function toast(message, { tone = 'info', timeout = 3500 } = {}) {
  const id = ++seq
  toasts.push({ id, message, tone })
  setTimeout(() => dismissToast(id), timeout)
}

export function useToasts() {
  return toasts
}
