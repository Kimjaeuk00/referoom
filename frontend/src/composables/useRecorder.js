import { ref, getCurrentScope, onScopeDispose } from 'vue';
import { createMeterContext, watchMic } from '@/lib/micLevel';

// Browser recording only. Upload and application processing belong to the caller.
export function useRecorder() {
  const state = ref('idle');
  const error = ref(null);
  const blob = ref(null);
  const mimeType = ref('');
  // 녹음 중 입력 음량: level 0~1, speaking(목소리가 들어오는 중), silentMs(목소리가 없던 시간), meterOn(측정이 실제로 돌고 있음)
  const level = ref(0);
  const speaking = ref(false);
  const silentMs = ref(0);
  const meterOn = ref(false);
  let session = null;
  let generation = 0;
  let disposed = false;

  const release = (current) => {
    clearTimeout(current.timer);
    current.stopMeter?.();
    current.stopMeter = null;
    level.value = 0;
    speaking.value = false;
    silentMs.value = 0;
    meterOn.value = false;
    current.stream.getTracks().forEach((track) => track.stop());
  };
  const failure = (message) => new Error(message);

  async function start() {
    if (disposed) throw failure('녹음 기능이 해제되었습니다.');
    if (state.value === 'recording' || state.value === 'processing') {
      throw failure('이미 녹음을 준비하거나 처리 중입니다.');
    }
    const version = ++generation;
    session = null;
    state.value = 'processing';
    error.value = null;
    blob.value = null;
    mimeType.value = '';
    let current;
    // 마이크 권한을 묻기 전, 버튼을 누른 직후에 만들어야 브라우저가 오디오를 멈춰 두지 않는다
    const meterContext = createMeterContext();
    try {
      if (!globalThis.isSecureContext) throw failure('마이크는 localhost 또는 HTTPS에서 사용해 주세요.');
      if (!globalThis.navigator?.mediaDevices?.getUserMedia || !globalThis.MediaRecorder) {
        throw failure('이 브라우저는 음성 녹음을 지원하지 않습니다.');
      }
      const selected = ['audio/webm;codecs=opus', 'audio/mp4'].find(
        (type) => MediaRecorder.isTypeSupported(type),
      );
      if (!selected) throw failure('WebM 또는 MP4 녹음을 지원하는 브라우저를 사용해 주세요.');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (version !== generation || disposed) {
        stream.getTracks().forEach((track) => track.stop());
        meterContext?.close?.()?.catch?.(() => {});
        return;
      }
      current = { stream, timer: null, chunks: [], finish: null, recorder: null };
      current.done = new Promise((resolve) => { current.finish = resolve; });
      session = current;
      const recorder = new MediaRecorder(stream, { mimeType: selected });
      current.recorder = recorder;
      mimeType.value = recorder.mimeType || selected;
      recorder.ondataavailable = (event) => {
        if (session !== current || disposed || state.value === 'error') return;
        if (event.data?.size) current.chunks.push(event.data);
      };
      recorder.onerror = () => {
        if (session !== current) return;
        error.value = failure('녹음에 실패했습니다. 마이크를 확인하고 다시 시도해 주세요.');
        state.value = 'error';
        release(current);
        current.finish(null);
        current.chunks = [];
        if (recorder.state === 'recording') recorder.stop();
      };
      recorder.onstop = () => {
        release(current);
        if (session !== current || disposed || state.value === 'error') {
          current.chunks = [];
          current.finish(null);
          return;
        }
        const result = new Blob(current.chunks, { type: recorder.mimeType || selected });
        if (result.size) {
          blob.value = result;
          state.value = 'idle';
          current.finish(result);
        } else {
          error.value = failure('녹음된 음성이 없습니다. 다시 녹음해 주세요.');
          state.value = 'error';
          current.finish(null);
        }
        current.chunks = [];
      };
      recorder.start();
      // 음량 측정은 보조 기능이다. 실패해도 녹음은 그대로 진행한다
      current.stopMeter = watchMic(stream, (meter) => {
        level.value = meter.level;
        speaking.value = meter.speaking;
        silentMs.value = meter.silentMs;
        meterOn.value = meter.available;
      }, { context: meterContext });
      state.value = 'recording';
      current.timer = setTimeout(() => { void stop().catch(() => {}); }, 60_000);
    } catch (cause) {
      if (current) { release(current); current.finish(null); }
      else meterContext?.close?.()?.catch?.(() => {});
      if (version !== generation || disposed) return;
      error.value = cause?.name === 'NotAllowedError'
        ? failure('마이크 사용 권한을 허용해 주세요.')
        : failure(cause?.name === 'NotFoundError' ? '사용 가능한 마이크가 없습니다.'
          : '녹음을 시작할 수 없습니다. 브라우저 지원 및 localhost/HTTPS 환경을 확인해 주세요.');
      state.value = 'error';
      throw error.value;
    }
  }

  async function stop() {
    const current = session;
    if (!current || (state.value === 'processing' && !current.recorder)) {
      ++generation;
      state.value = 'idle';
      return null;
    }
    if (current.recorder?.state === 'recording') {
      if (state.value !== 'error') state.value = 'processing';
      clearTimeout(current.timer);
      current.recorder.stop();
    }
    const result = await current.done;
    if (!result && error.value) throw error.value;
    return result;
  }

  function dispose() {
    disposed = true;
    ++generation;
    if (session) {
      const current = session;
      session = null;
      if (current.recorder?.state === 'recording') current.recorder.stop();
      release(current);
      current.chunks = [];
      current.finish(null);
    }
    blob.value = null;
    state.value = 'idle';
  }

  if (getCurrentScope()) onScopeDispose(dispose);
  return { state, error, blob, mimeType, level, speaking, silentMs, meterOn, start, stop, dispose };
}
