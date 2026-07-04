"use client"

import { useState } from "react"
import { ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"

export function Accordion({
  items,
  className,
}: {
  items: Array<{ title: string; content: React.ReactNode }>
  className?: string
}) {
  return (
    <div className={cn("space-y-3", className)}>
      {items.map((item) => (
        <AccordionItem key={item.title} title={item.title} content={item.content} />
      ))}
    </div>
  )
}

function AccordionItem({
  title,
  content,
}: {
  title: string
  content: React.ReactNode
}) {
  const [open, setOpen] = useState(false)

  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-card">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="text-sm font-medium text-foreground sm:text-base">{title}</span>
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
      </button>
      {open ? <div className="px-5 pb-4 text-sm leading-7 text-muted-foreground">{content}</div> : null}
    </div>
  )
}
