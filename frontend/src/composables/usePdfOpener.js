import { ref } from 'vue'
import { errorText } from '@/api/errors'
import { toast } from '@/composables/useToast'
import { openPaperPdf, pdfErrorText } from '@/lib/paperPdf'

// 원문 PDF 열기 버튼들이 같이 쓰는 상태: 열리는 동안 그 버튼만 잠그고, 실패하면 토스트로 알린다.
// key는 버튼을 구분하는 값(근거 라벨 등). open()은 클릭 핸들러 안에서 바로 불러야 한다(await 뒤에서 부르면 새 탭이 팝업으로 막힌다).
export function usePdfOpener() {
  const opening = ref(new Set())

  async function open(key, paperId, page) {
    if (opening.value.has(key)) return
    opening.value = new Set(opening.value).add(key)
    try {
      await openPaperPdf(paperId, page)
    } catch (e) {
      toast(pdfErrorText(e, errorText(e)), { tone: 'error' })
    } finally {
      const next = new Set(opening.value)
      next.delete(key)
      opening.value = next
    }
  }

  return { opening, open }
}
