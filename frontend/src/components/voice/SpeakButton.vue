<script setup>
import { ref } from 'vue'
import { api, TIMEOUT } from '@/api/client'
import { errorText } from '@/api/errors'
import { audioUrl, speakable, useAudioPlayer } from '@/lib/voice'

// "답변 듣기": POST /tts → audio_url을 Bearer로 받아 재생, 재생 중에 누르면 멈춘다(DEV_04 7절)
const props = defineProps({ text: { type: String, required: true } })

const player = useAudioPlayer()
const preparing = ref(false)
const error = ref('')

async function toggle() {
  if (player.playing.value) return player.stop()
  preparing.value = true
  error.value = ''
  try {
    const data = await api.voice('/tts', { method: 'POST', json: { text: speakable(props.text) }, timeout: TIMEOUT.query })
    preparing.value = false
    await player.play(audioUrl(data.audio_url))
  } catch (e) {
    error.value = errorText(e)
  } finally {
    preparing.value = false
  }
}
</script>

<template>
  <span class="speak-wrap">
    <button type="button" class="btn" :aria-pressed="player.playing.value" :disabled="preparing" @click="toggle">
      {{ preparing ? '음성을 만드는 중' : player.playing.value ? '그만 듣기' : '답변 듣기' }}
    </button>
    <span v-if="error" class="field-error" role="alert">{{ error }}</span>
  </span>
</template>

<style scoped>
.speak-wrap {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}
</style>
