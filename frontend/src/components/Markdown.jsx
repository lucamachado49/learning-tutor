// src/components/Markdown.jsx
// Renderiza markdown com tabelas (GFM), fórmulas LaTeX (KaTeX) e blocos de código.
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'

// Durante o streaming o LLM emite as tags de seção; mostramos só a [MENSAGEM].
export function visiblePart(text) {
  let t = text.replace(/^\s*\[ME[NS]S?A(?:GEM|JE|GE)\]\s*/i, '')
  const cut = t.search(/\[(FEEDBACK|ERROS)/i)
  return cut >= 0 ? t.slice(0, cut).trimEnd() : t
}

// remark-math só entende $...$ e $$...$$; muitos LLMs usam \( \) e \[ \]
function normalizeMath(text) {
  return (text ?? '')
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, m) => `\n$$${m}$$\n`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, m) => `$${m.trim()}$`)
}

export default function Markdown({ children }) {
  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {normalizeMath(children)}
      </ReactMarkdown>
    </div>
  )
}
