"use client"

import { X } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "./button"
import { Dialog } from "./dialog"

export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={title} description={description}>
      <div className="flex items-center justify-end">
        <Button
          variant="ghost"
          size="icon"
          aria-label="Close dialog"
          onClick={() => onOpenChange(false)}
        >
          <X className="size-4" />
        </Button>
      </div>
      <div className={cn("mt-2")}>{children}</div>
    </Dialog>
  )
}
