"use client"

import { Card } from "@/components/ui/card"

const entries = [
  { phrase: "I need help", status: "Completed" },
  { phrase: "Please repeat", status: "Completed" },
  { phrase: "Where is the bathroom?", status: "Draft" },
]

export function TranslationHistory() {
  return (
    <Card>
      <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
        Translation history
      </p>
      <div className="mt-4 space-y-3">
        {entries.map((entry) => (
          <div key={entry.phrase} className="flex items-center justify-between gap-4 rounded-xl border border-border bg-background px-4 py-3">
            <div>
              <p className="text-sm font-medium text-foreground">{entry.phrase}</p>
              <p className="text-xs text-muted-foreground">{entry.status}</p>
            </div>
            <span className="text-xs font-semibold text-muted-foreground">Saved</span>
          </div>
        ))}
      </div>
    </Card>
  )
}
