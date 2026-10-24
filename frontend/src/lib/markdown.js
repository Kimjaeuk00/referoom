import MarkdownIt from 'markdown-it'
import * as katexModule from '@vscode/markdown-it-katex'
import DOMPurify from 'dompurify'
import { toneOfLabel } from './format'

// CommonJS 패키지라 번들러에 따라 default가 한 겹 더 감싸여 들어온다
const katexPlugin = katexModule.default?.default ?? katexModule.default ?? katexModule

// html: false → 응답 안의 HTML 태그는 글자로 취급한다. 그 위에 DOMPurify로 한 번 더 거른다.
const md = new MarkdownIt({ html: false, linkify: true, breaks: true }).use(katexPlugin, { throwOnError: false })

DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

const LABEL = /\[(S\d{1,3})\]/

// LLM 응답(마크다운 + $...$ 수식)을 안전한 HTML로 바꾼다.
// [S1] 같은 근거 라벨은 sanitize가 끝난 뒤 글자 노드에서만, 실제로 있는 출처 라벨만 칩으로 바꾼다.
// HTML 문자열을 통째로 치환하면 링크 title 같은 속성 안의 [S1]까지 바뀌어 따옴표가 깨진다.
export function renderMarkdown(text, labels) {
  const html = DOMPurify.sanitize(md.render(text ?? ''))
  if (!labels?.size) return html

  const box = document.createElement('template')
  box.innerHTML = html
  const walker = document.createTreeWalker(box.content, NodeFilter.SHOW_TEXT)
  const found = []
  while (walker.nextNode()) if (LABEL.test(walker.currentNode.data)) found.push(walker.currentNode)

  for (const node of found) {
    const frag = document.createDocumentFragment()
    // split에 괄호 그룹이 있으면 [글자, 라벨, 글자, 라벨, ...] 순서로 나온다
    node.data.split(LABEL).forEach((part, i) => {
      if (i % 2 === 0) return part && frag.append(part)
      if (!labels.has(part)) return frag.append(`[${part}]`)
      const chip = document.createElement('button')
      chip.type = 'button'
      chip.className = 'cite'
      chip.dataset.label = part
      chip.dataset.tone = toneOfLabel(part)
      chip.setAttribute('aria-label', `근거 ${part} 보기`)
      chip.textContent = part
      frag.append(chip)
    })
    node.replaceWith(frag)
  }
  return box.innerHTML
}
