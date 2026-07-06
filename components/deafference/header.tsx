"use client"

import { Building2, Moon, Settings2, Sun } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Logo } from "./logo"
import { LanguageSelector } from "./language-selector"
import { useSettings } from "./settings-provider"

const NAV = [
  { label: "Translate", href: "#translate" },
  { label: "Quick Phrases", href: "#phrases" },
  { label: "Accessibility", href: "#accessibility" },
  { label: "Help", href: "#help" },
]

export function Header({ onOpenAccessibility }: { onOpenAccessibility: () => void }) {
  const { settings, toggleTheme } = useSettings()

  return (
    <header className="sticky top-0 z-40 border-b border-border/70 bg-background/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
        <div className="flex items-center gap-3">
          <a href="#top" className="flex items-center rounded-xl" aria-label="Deafference home">
            <Logo />
          </a>
        </div>

        <nav aria-label="Primary" className="hidden items-center gap-1 lg:flex">
          {NAV.map((item) => (
            <a
              key={item.href}
              href={item.href}
              onClick={
                item.label === "Accessibility"
                  ? (e) => {
                      e.preventDefault()
                      onOpenAccessibility()
                    }
                  : undefined
              }
              className="rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              {item.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-1.5 sm:gap-2">
          <LanguageSelector />

          <Button
            variant="ghost"
            size="icon"
            aria-label={
              settings.theme === "light" ? "Switch to dark mode" : "Switch to light mode"
            }
            onClick={toggleTheme}
          >
            {settings.theme === "light" ? <Moon /> : <Sun />}
          </Button>

          <Button
            variant="outline"
            size="icon"
            aria-label="Open accessibility settings"
            onClick={onOpenAccessibility}
          >
            <Settings2 />
          </Button>

          <a
            href="#help"
            className="hidden items-center gap-1.5 rounded-lg px-2.5 py-2 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground sm:inline-flex"
          >
            <Building2 className="size-4" />
            For Organizations
          </a>
        </div>
      </div>
    </header>
  )
}
