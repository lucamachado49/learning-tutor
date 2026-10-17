// src/components/Markdown.jsx
// Renderiza markdown com tabelas (GFM), fórmulas LaTeX (KaTeX) e blocos de código.
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'

// Durante o streaming o LLM emite as tags de seção; mostramos só a [MENSAGEM].
export function visiblePart(text) {
  let t = text.replace(/^\s*\[MENSAGEM\]\s*/i, '')
  const cut = t.search(/\[(FEEDBACK|ERROS)/i)
  return cut >= 0 ? t.slice(0, cut).trimEnd() : t
}

export default function Markdown({ children }) {
  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {children}
      </ReactMarkdown>
    </div>
  )
}
