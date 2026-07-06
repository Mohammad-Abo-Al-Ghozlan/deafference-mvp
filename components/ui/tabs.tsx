"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"

export function Tabs({
  tabs,
  defaultValue,
  className,
}: {
  tabs: Array<{ value: string; label: string; content: React.ReactNode }>
  defaultValue?: string
  className?: string
}) {
  const [active, setActive] = useState(defaultValue ?? tabs[0]?.value)
  const current = tabs.find((tab) => tab.value === active) ?? tabs[0]

  return (
    <div className={cn("space-y-4", className)}>
      <div className="inline-flex rounded-full border border-border bg-muted p-1">
        {tabs.map((tab) => {
          const selected = tab.value === current?.value
          return (
            <button
              key={tab.value}
              type="button"
              onClick={() => setActive(tab.value)}
              className={cn(
                "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                selected ? "bg-background text-foreground shadow-sm" : "text-muted-foreground",
              )}
            >
              {tab.label}
            </button>
          )
        })}
      </div>
      <div>{current?.content}</div>
    </div>
  )
}
