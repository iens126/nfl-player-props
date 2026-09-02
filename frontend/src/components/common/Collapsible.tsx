import { Disclosure, DisclosureButton, DisclosurePanel } from '@headlessui/react'
import { ChevronDownIcon } from '@heroicons/react/24/outline'
import type { ReactNode } from 'react'

export function Collapsible({ title, children, defaultOpen = false }: { title: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  return (
    <Disclosure defaultOpen={defaultOpen}>
      {({ open }) => (
        <div className="rounded-2xl border border-border bg-surface">
          <DisclosureButton className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left">
            <span className="text-sm font-semibold text-text">{title}</span>
            <ChevronDownIcon className={`h-4 w-4 shrink-0 text-text-faint transition-transform ${open ? 'rotate-180' : ''}`} />
          </DisclosureButton>
          <DisclosurePanel
            transition
            className="origin-top px-5 pb-5 text-sm leading-relaxed text-text-muted transition duration-150 ease-out data-[closed]:-translate-y-1 data-[closed]:opacity-0"
          >
            {children}
          </DisclosurePanel>
        </div>
      )}
    </Disclosure>
  )
}
