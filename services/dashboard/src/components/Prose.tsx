/**
 * Readable rendering for the run's own prose (the post-mortem summary, the
 * diagnosis, an execution log line). The graph writes plain text with blank-line
 * paragraphs, `- ` bullets, and the occasional `**emphasis**`, so dumping it
 * into a single `<p>` loses the structure the author put there.
 *
 * Deliberately not a markdown library: this covers what the graph actually
 * emits, and nothing downstream of it needs more.
 */

import type { ReactNode } from 'react'

/** Split a line into text, `**bold**`, and `` `code` `` runs. */
function renderInline(text: string, prefix: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
  return parts.filter(Boolean).map((part, index) => {
    const key = `${prefix}-${index}`
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={key} className="font-semibold text-slate-100">
          {part.slice(2, -2)}
        </strong>
      )
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code key={key} className="rounded bg-slate-800 px-1 py-0.5 font-mono text-[0.8em] text-slate-200">
          {part.slice(1, -1)}
        </code>
      )
    }
    return <span key={key}>{part}</span>
  })
}

const BULLET = /^\s*[-*]\s+/
const ORDERED = /^\s*\d+[.)]\s+/

export function Prose({ text }: { text: string }) {
  const blocks = text.trim().split(/\n{2,}/)

  return (
    <div className="space-y-3 leading-relaxed">
      {blocks.map((block, blockIndex) => {
        const lines = block.split('\n')
        const bullets = lines.filter((line) => line.trim() !== '')

        if (bullets.length > 0 && bullets.every((line) => BULLET.test(line))) {
          return (
            <ul key={blockIndex} className="list-disc space-y-1 pl-5">
              {bullets.map((line, lineIndex) => (
                <li key={lineIndex}>{renderInline(line.replace(BULLET, ''), `${blockIndex}-${lineIndex}`)}</li>
              ))}
            </ul>
          )
        }

        if (bullets.length > 0 && bullets.every((line) => ORDERED.test(line))) {
          return (
            <ol key={blockIndex} className="list-decimal space-y-1 pl-5">
              {bullets.map((line, lineIndex) => (
                <li key={lineIndex}>{renderInline(line.replace(ORDERED, ''), `${blockIndex}-${lineIndex}`)}</li>
              ))}
            </ol>
          )
        }

        return (
          <p key={blockIndex} className="whitespace-pre-line">
            {renderInline(block, String(blockIndex))}
          </p>
        )
      })}
    </div>
  )
}

/** A single labelled value, used for plan parameters and execution details. */
export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-0.5 py-1">
      <dt className="text-xs tracking-wide text-slate-500 uppercase">{label}</dt>
      <dd className="text-slate-300">{children}</dd>
    </div>
  )
}
