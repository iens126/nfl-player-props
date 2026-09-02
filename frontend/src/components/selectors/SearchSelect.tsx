import { useState } from 'react'
import {
  Combobox,
  ComboboxButton,
  ComboboxInput,
  ComboboxOption,
  ComboboxOptions,
} from '@headlessui/react'
import { ChevronUpDownIcon, CheckIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'

export interface SelectItem {
  value: string
  label: string
  sublabel?: string
  accent?: string | null
}

export function SearchSelect({
  label,
  placeholder,
  items,
  value,
  onChange,
  disabled = false,
  disabledHint,
}: {
  label: string
  placeholder: string
  items: SelectItem[]
  value: string | null
  onChange: (value: string | null) => void
  disabled?: boolean
  disabledHint?: string
}) {
  const [query, setQuery] = useState('')

  const filtered =
    query === ''
      ? items
      : items.filter((item) => item.label.toLowerCase().includes(query.toLowerCase()))

  const selected = items.find((i) => i.value === value) ?? null

  return (
    <div>
      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-text-faint">{label}</label>
      <Combobox
        value={value}
        onChange={(v) => onChange(v)}
        disabled={disabled}
        immediate
      >
        <div className="relative">
          <div
            className={clsx(
              'flex items-center rounded-xl border bg-surface-2 transition-colors',
              disabled ? 'border-border-soft opacity-50' : 'border-border focus-within:border-accent',
            )}
          >
            <ComboboxInput
              className="w-full bg-transparent py-2.5 pl-3.5 pr-9 text-sm text-text placeholder:text-text-faint outline-none disabled:cursor-not-allowed"
              displayValue={() => (selected ? selected.label : '')}
              placeholder={disabled ? (disabledHint ?? placeholder) : placeholder}
              onChange={(event) => setQuery(event.target.value)}
            />
            <ComboboxButton className="absolute right-2.5 flex items-center">
              <ChevronUpDownIcon className="h-4 w-4 text-text-faint" />
            </ComboboxButton>
          </div>

          <ComboboxOptions
            anchor="bottom start"
            transition
            className="z-30 mt-1.5 max-h-72 w-[var(--input-width)] overflow-auto rounded-xl border border-border bg-surface-2 py-1 shadow-2xl shadow-black/50 outline-none scroll-thin transition duration-100 ease-out empty:invisible data-[closed]:scale-95 data-[closed]:opacity-0"
          >
            {filtered.length === 0 && (
              <div className="px-3.5 py-3 text-sm text-text-faint">No matches</div>
            )}
            {filtered.map((item) => (
              <ComboboxOption
                key={item.value}
                value={item.value}
                className="group flex cursor-pointer items-center justify-between gap-2 px-3.5 py-2.5 text-sm text-text data-[focus]:bg-surface-3"
              >
                <span className="flex items-center gap-2">
                  {item.accent && (
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: item.accent }} />
                  )}
                  <span>{item.label}</span>
                  {item.sublabel && <span className="text-xs text-text-faint">{item.sublabel}</span>}
                </span>
                <CheckIcon className="hidden h-4 w-4 text-accent-soft group-data-[selected]:block" />
              </ComboboxOption>
            ))}
          </ComboboxOptions>
        </div>
      </Combobox>
    </div>
  )
}
