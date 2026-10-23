<script setup>
import { ref, watch } from 'vue'
import { api, TIMEOUT } from '@/api/client'
import { errorText } from '@/api/errors'
import { usePolling } from '@/composables/usePolling'
import { isBatchDone } from '@/lib/format'
import BatchProgress from './BatchProgress.vue'
import Icon from '@/components/common/Icon.vue'

// compact: 질문하기 왼쪽 패널용 작은 모양. inputId를 주면 다른 곳의 <label for>로 파일 창을 열 수 있다.
const props = defineProps({
  compact: { type: Boolean, default: false },
  inputId: { type: String, default: undefined },
})
const emit = defineEmits(['done'])
const MAX_BYTES = 20 * 1024 * 1024

const file = ref(null)
const tags = ref('')
const dragging = ref(false)
const uploading = ref(false)
const error = ref('')
const batchId = ref(null)

const { data: batch, running: polling, error: pollError, start } = usePolling(
  () => api.rag(`/ingest/batches/${batchId.value}`),
  { isDone: isBatchDone },
)

watch(polling, (now, before) => {
  if (before && !now) emit('done', batch.value)
})

function choose(f) {
  error.value = ''
  if (!f) return
  if (!/\.pdf$/i.test(f.name) && f.type !== 'application/pdf') {
    error.value = 'PDF 파일만 올릴 수 있어요.'
    return
  }
  if (f.size > MAX_BYTES) {
    error.value = '20MB 이하 PDF만 올릴 수 있어요.'
    return
  }
  file.value = f
}

function onDrop(event) {
  dragging.value = false
  choose(event.dataTransfer?.files?.[0])
}

async function upload() {
  if (!file.value || uploading.value) return
  const form = new FormData()
  form.append('file', file.value)
  if (tags.value.trim()) form.append('tags', tags.value.trim())
  uploading.value = true
  error.value = ''
  try {
    const data = await api.rag('/upload-paper', { method: 'POST', formData: form, timeout: TIMEOUT.upload })
    batchId.value = data.batch_id
    file.value = null
    tags.value = ''
    start()
  } catch (e) {
    error.value = errorText(e, {
      CONFLICT: '이미 등록된 논문이에요',
      VALIDATION_ERROR: '글자를 읽을 수 없는 PDF예요. 스캔본이면 텍스트가 들어 있는 PDF로 올려 주세요.',
    })
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <section class="upload">
    <label
      class="drop"
      :class="{ dragging, compact: props.compact }"
      @dragenter.prevent="dragging = true"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <input :id="props.inputId" class="visually-hidden" type="file" accept="application/pdf,.pdf" @change="choose($event.target.files?.[0]); $event.target.value = ''" />
      <span v-if="file" class="file">{{ file.name }} <span class="hint">{{ (file.size / 1024 / 1024).toFixed(1) }}MB</span></span>
      <template v-else-if="props.compact">
        <Icon name="upload" class="up" />
        <span class="hint">PDF를 끌어다 놓거나 눌러서 올리기</span>
      </template>
      <span v-else>PDF를 여기에 끌어다 놓거나 <span class="pick">파일을 선택</span>하세요</span>
      <span v-if="!props.compact" class="hint">최대 20MB. 글자가 들어 있는 PDF여야 해요(스캔본은 읽을 수 없어요).</span>
    </label>

    <div v-if="file" class="row" :class="{ stack: props.compact }">
      <div class="field tags">
        <label class="label" for="upload-tags">태그 (선택)</label>
        <input id="upload-tags" v-model="tags" class="input" placeholder="쉼표로 구분, 예: transformer, peft" />
      </div>
      <button type="button" class="btn btn-primary" :disabled="uploading" @click="upload">{{ uploading ? '올리는 중' : '올리기' }}</button>
      <button type="button" class="btn" :disabled="uploading" @click="file = null">취소</button>
    </div>

    <p v-if="error" class="field-error" role="alert">{{ error }}</p>
    <p v-if="pollError" class="field-error" role="alert">{{ errorText(pollError) }}</p>
    <BatchProgress v-if="batch" :batch="batch" />
  </section>
</template>

<style scoped>
.upload {
  display: grid;
  gap: 12px;
}

.drop {
  display: grid;
  gap: 4px;
  padding: 24px;
  border: 1.5px dashed var(--c-rule-strong);
  border-radius: var(--radius-m);
  background: var(--c-surface);
  text-align: center;
  font-size: var(--fs-sm);
  cursor: pointer;
}

.drop.compact {
  justify-items: center;
  padding: 18px 12px;
  background: transparent;
}

.up {
  color: var(--c-ink-muted);
}

.drop.dragging,
.drop:focus-within {
  border-color: var(--c-accent-2);
  background: var(--c-accent-2-wash);
}

.pick {
  color: var(--c-accent);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.file {
  font-weight: 500;
}

.row {
  display: flex;
  align-items: end;
  gap: 8px;
}

.tags {
  flex: 1;
}

/* 좁은 패널에서는 태그 칸을 한 줄 전체로 */
.row.stack {
  flex-wrap: wrap;
}

.row.stack .tags {
  flex-basis: 100%;
}

@media (max-width: 720px) {
  .row {
    flex-wrap: wrap;
  }

  .tags {
    flex-basis: 100%;
  }
}
</style>
