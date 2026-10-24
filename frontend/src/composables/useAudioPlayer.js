import { ref, getCurrentScope, onScopeDispose } from 'vue';

// The frontend owns apiBlob, including Bearer, credentials:omit, and 401 handling.
export function useAudioPlayer({ apiBlob, baseUrl }) {
  if (typeof apiBlob !== 'function') throw new TypeError('apiBlob 함수를 전달해 주세요.');
  const state = ref('idle');
  const error = ref(null);
  let audio = null;
  let objectUrl = null;
  let generation = 0;
  let disposed = false;

  function release() {
    if (audio) {
      audio.onended = null;
      audio.onerror = null;
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
      audio = null;
    }
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = null;
  }

  function stop() {
    ++generation;
    release();
    state.value = 'idle';
  }

  async function play(path) {
    if (disposed) throw new Error('음성 재생 기능이 해제되었습니다.');
    stop();
    const version = generation;
    error.value = null;
    state.value = 'loading';
    try {
      const content = await apiBlob(baseUrl, path);
      if (version !== generation || disposed) return false;
      if (!(content instanceof Blob) || !content.size) throw new Error('Empty audio');
      objectUrl = URL.createObjectURL(content);
      const current = new Audio(objectUrl);
      audio = current;
      current.onended = () => { if (audio === current) stop(); };
      current.onerror = () => {
        if (audio !== current) return;
        stop();
        error.value = new Error('음성을 재생할 수 없습니다. 다시 시도해 주세요.');
        state.value = 'error';
      };
      await current.play();
      if (version !== generation || disposed) return false;
      state.value = 'playing';
      return true;
    } catch {
      if (version !== generation || disposed) return false;
      release();
      error.value = new Error('음성을 불러오거나 재생하지 못했습니다. 다시 시도해 주세요.');
      state.value = 'error';
      throw error.value;
    }
  }

  function dispose() { disposed = true; stop(); }
  if (getCurrentScope()) onScopeDispose(dispose);
  return { state, error, play, stop, dispose };
}
