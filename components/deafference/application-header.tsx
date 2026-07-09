"use client"

import { Settings2, ShieldCheck, UserCircle2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Container } from "@/components/shared/container"
import { Logo } from "./logo"

export function ApplicationHeader({
  onOpenAccessibility,
  onOpenSettings,
}: {
  onOpenAccessibility: () => void
  onOpenSettings: () => void
}) {
  return (
    <header className="border-b border-border/70 bg-background/85 backdrop-blur-xl">
      <Container className="flex min-h-20 items-center justify-between gap-4 py-4">
        <div className="flex items-center gap-4">
          <Logo />
          <div>
            <p className="text-xs font-medium tracking-[0.22em] text-muted-foreground uppercase">
              Deafference AI Sign Language Translator
            </p>
            <h1 className="mt-1 text-lg font-semibold tracking-tight text-foreground sm:text-xl">
              Listening Workspace
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" aria-label="Open settings" onClick={onOpenSettings}>
            <Settings2 className="size-4" />
          </Button>
          <Button variant="outline" size="icon" aria-label="Open accessibility settings" onClick={onOpenAccessibility}>
            <ShieldCheck className="size-4" />
          </Button>
          <div className="flex size-9 items-center justify-center rounded-full border border-border bg-muted text-sm font-semibold text-foreground">
            <UserCircle2 className="size-4" />
          </div>
        </div>
      </Container>
    </header>
  )
}
