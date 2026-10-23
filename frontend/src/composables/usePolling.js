import { onBeforeUnmount, ref } from 'vue'

// 업로드·주제 수집·Zotero 동기화 배치를 2초 간격으로 확인한다. 화면을 떠나면 멈춘다.
export function usePolling(fetcher, { interval = 2000, isDone }) {
  const data = ref(null)
  const error = ref(null)
  const running = ref(false)
  let timer = null

  async function tick() {
    try {
      data.value = await fetcher()
      if (isDone(data.value)) return stop()
    } catch (e) {
      error.value = e
      return stop()
    }
    if (running.value) timer = setTimeout(tick, interval)
  }

  function start() {
    stop()
    data.value = null
    error.value = null
    running.value = true
    tick()
  }

  function stop() {
    running.value = false
    clearTimeout(timer)
  }

  onBeforeUnmount(stop)
  return { data, error, running, start, stop }
}
