<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { api, TIMEOUT } from '@/api/client'
import { errorText } from '@/api/errors'
import { audioFileName, MAX_RECORD_SECONDS, micErrorText, useRecorder } from '@/lib/voice'
import Icon from '@/components/common/Icon.vue'

// 눌러서 녹음 → 다시 누르면 POST /stt → 인식한 문장을 transcript로 넘긴다(Q&A 입력창에 채움, DEV_04 7절)
const props = defineProps({
  language: { type: String, default: 'ko' },
  disabled: { type: Boolean, default: false },
  compact: { type: Boolean, default: false }, // 입력창 안의 아이콘 버튼 모양
})
const emit = defineEmits(['transcript'])

const recorder = useRecorder()
const recognizing = ref(false)
const error = ref('')
const recording = computed(() => recorder.state.value === 'recording')
let limit = null

async function toggle() {
  if (recording.value) return finish()
  error.value = ''
  try {
    await recorder.start()
    limit = setTimeout(finish, MAX_RECORD_SECONDS * 1000)
  } catch (e) {
    error.value = micErrorText(e)
  }
}

async function finish() {
  clearTimeout(limit)
  recognizing.value = true
  try {
    const blob = await recorder.stop()
    const form = new FormData()
    form.append('audio', blob, audioFileName(blob))
    form.append('language', props.language)
    const data = await api.voice('/stt', { method: 'POST', formData: form, timeout: TIMEOUT.query })
    emit('transcript', data.text)
  } catch (e) {
    error.value = errorText(e, { STT_EMPTY: '말소리를 알아듣지 못했어요. 조금 더 가까이에서 다시 말해 주세요.' })
  } finally {
    recognizing.value = false
  }
}

onBeforeUnmount(() => {
  clearTimeout(limit)
  if (recording.value) recorder.stop().catch(() => {})
})
</script>

<template>
  <span class="mic-wrap">
    <button
      type="button"
      :class="[props.compact ? 'rec' : 'btn mic', { on: recording }]"
      :aria-label="props.compact ? (recognizing ? '알아듣는 중' : recording ? '말하기 끝' : '말로 묻기') : undefined"
      :aria-pressed="recording"
      :disabled="props.disabled || recognizing"
      @click="toggle"
    >
      <Icon v-if="props.compact" name="mic" />
      <template v-else>{{ recognizing ? '알아듣는 중' : recording ? '말하기 끝' : '말로 묻기' }}</template>
    </button>
    <span v-if="error" class="field-error" role="alert">{{ error }}</span>
  </span>
</template>

<style scoped>
.mic-wrap {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.mic::before {
  content: "";
  width: 8px;
  height: 8px;
  margin-right: 8px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.4;
}

/* 입력창 안: Vorb의 코랄 동그라미 녹음 버튼. 듣는 동안은 바깥 고리가 생긴다 */
.rec {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 50%;
  background: var(--c-accent-2);
  color: #fff;
  cursor: pointer;
}

.rec:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.rec.on {
  box-shadow: 0 0 0 4px var(--c-accent-2-wash);
}

.mic.on {
  border-color: var(--c-danger);
  color: var(--c-danger);
}

.mic.on::before {
  opacity: 1;
}
</style>
