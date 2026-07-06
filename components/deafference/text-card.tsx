"use client"

import { useEffect } from "react"
import { X } from "lucide-react"
import { Button } from "@/components/ui/button"

/**
 * A large, high-contrast text card intended to be shown to the other person
 * in the conversation as a text-only fallback.
 */
export function TextCard({
  open,
  phrase,
  onClose,
}: {
  open: boolean
  phrase: string
  onClose: () => void
}) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    if (open) document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Text card"
      className="fixed inset-0 z-50 flex flex-col bg-background"
    >
      <div className="flex items-center justify-between px-4 py-3 sm:px-6">
        <span className="text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          Text Card
        </span>
        <Button variant="ghost" size="icon" aria-label="Close text card" onClick={onClose}>
          <X />
        </Button>
      </div>
      <div className="flex flex-1 items-center justify-center p-6">
        <p className="max-w-4xl text-center text-4xl leading-tight font-bold text-balance text-foreground sm:text-6xl">
          {phrase || "Type or say a phrase to show it here."}
        </p>
      </div>
      <p className="pb-8 text-center text-sm text-muted-foreground">
        Show this screen to the person you are speaking with · Press Esc to close
      </p>
    </div>
  )
}
