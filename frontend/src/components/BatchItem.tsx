import { AlertTriangle, Check, ChevronDown, Copy, RotateCcw, X } from 'lucide-react'
import type { Draft, DraftResult } from '../api'
import { ARTICLE_TEXT, cardsFor, DraftFields, headword, tagValue } from './DraftEditor'
import { Button, PlayButton, Spinner } from './ui'

export type ItemStatus = 'queued' | 'drafting' | 'ready' | 'failed' | 'saving' | 'saved'

export interface Item {
  id: string
  input: string
  status: ItemStatus
  result?: DraftResult
  draft?: Draft
  error?: string
  /** anki-manager refused it as a duplicate of a note with the same note type. */
  duplicate?: boolean
  selected: boolean
  expanded: boolean
}

export function BatchItem({
  item,
  onChange,
  onRemove,
  onRetry,
  onAddAnyway,
}: {
  item: Item
  onChange: (patch: Partial<Item>) => void
  onRemove: () => void
  onRetry: () => void
  onAddAnyway: () => void
}) {
  const { status, draft, result } = item
  const warnings = result?.checks.filter((c) => c.level === 'warn').length ?? 0
  const known = (result?.duplicates.length ?? 0) > 0
  const editable = status === 'ready' && draft && result

  return (
    <li className="bg-white first:rounded-t-lg last:rounded-b-lg dark:bg-zinc-900">
      <div className="flex items-center gap-2 px-3 py-2.5">
        <input
          type="checkbox"
          aria-label={`Add ${draft ? headword(draft) : item.input}`}
          checked={item.selected}
          disabled={!editable}
          onChange={(e) => onChange({ selected: e.target.checked })}
          className="size-4 shrink-0 accent-zinc-900 disabled:opacity-30 dark:accent-zinc-100"
        />

        <button
          type="button"
          disabled={!editable}
          onClick={() => onChange({ expanded: !item.expanded })}
          aria-expanded={item.expanded}
          className="flex min-w-0 flex-1 items-baseline gap-2 text-left disabled:cursor-default"
        >
          {draft ? (
            <>
              <span
                className={`shrink-0 font-semibold ${draft.kind === 'noun' && draft.article ? ARTICLE_TEXT[draft.article] : ''}`}
              >
                {headword(draft)}
              </span>
              <span className="truncate text-sm text-zinc-500 dark:text-zinc-400">{draft.meaning}</span>
              {draft.tags.length > 0 && (
                <span className="ml-auto hidden shrink-0 text-xs text-zinc-400 sm:inline dark:text-zinc-500">
                  {[tagValue(draft.tags, 'level'), tagValue(draft.tags, 'topic')].filter(Boolean).join(' · ')}
                </span>
              )}
            </>
          ) : (
            <span className="truncate text-zinc-500 dark:text-zinc-400">{item.input}</span>
          )}
        </button>

        <div className="flex shrink-0 items-center gap-1.5 text-xs">
          {(status === 'queued' || status === 'drafting' || status === 'saving') && (
            <span className="flex items-center gap-1.5 text-zinc-500 dark:text-zinc-400">
              <Spinner className="size-3.5" />
              {status === 'queued' ? 'Waiting' : status === 'drafting' ? 'Drafting' : 'Adding'}
            </span>
          )}
          {status === 'saved' && draft && (
            <span className="flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
              <Check className="size-3.5" /> Added · {cardsFor(draft.kind).length} cards
            </span>
          )}
          {status === 'ready' && known && (
            <span
              title="Already in your collection"
              className="flex items-center gap-1 rounded bg-amber-100 px-1.5 py-0.5 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
            >
              <Copy className="size-3" /> Have it
            </span>
          )}
          {status === 'ready' && warnings > 0 && (
            <span
              title="Check the warnings"
              className="flex items-center gap-1 rounded bg-amber-100 px-1.5 py-0.5 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
            >
              <AlertTriangle className="size-3" /> {warnings}
            </span>
          )}
          {draft && status !== 'saved' && <PlayButton text={headword(draft)} />}
          {editable && (
            <button
              type="button"
              aria-label={item.expanded ? 'Collapse' : 'Edit'}
              title={item.expanded ? 'Collapse' : 'Edit'}
              onClick={() => onChange({ expanded: !item.expanded })}
              className="inline-flex size-8 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
            >
              <ChevronDown className={`size-4 transition-transform ${item.expanded ? 'rotate-180' : ''}`} />
            </button>
          )}
          {status !== 'saving' && (
            <button
              type="button"
              aria-label="Remove from list"
              title="Remove from list"
              onClick={onRemove}
              className="inline-flex size-8 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
            >
              <X className="size-4" />
            </button>
          )}
        </div>
      </div>

      {item.error && (
        <div className="flex flex-wrap items-center gap-2 px-3 pb-2.5 pl-9 text-sm text-red-700 dark:text-red-400">
          <span className="text-pretty">{item.error}</span>
          {status === 'failed' && (
            <Button variant="ghost" className="px-2 py-1" onClick={onRetry}>
              <RotateCcw className="size-3.5" /> Retry
            </Button>
          )}
          {item.duplicate && status === 'ready' && (
            <Button variant="ghost" className="px-2 py-1" onClick={onAddAnyway}>
              Add anyway
            </Button>
          )}
        </div>
      )}

      {editable && item.expanded && (
        <div className="border-t border-zinc-100 px-4 py-4 sm:pl-9 dark:border-zinc-800">
          <DraftFields result={result} draft={draft} onChange={(d) => onChange({ draft: d })} />
        </div>
      )}
    </li>
  )
}
