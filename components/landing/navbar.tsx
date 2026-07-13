"use client"

import { useState } from "react"
import { AnimatePresence, motion } from "framer-motion"
import Link from "next/link"
import { ArrowRight, Globe, Menu, X } from "lucide-react"
import { Container } from "@/components/shared/container"
import { LANDING_NAV, APP_ROUTES } from "@/lib/constants"
import { cn } from "@/lib/utils"
import { Logo } from "@/components/deafference/logo"

const navLinkClassName =
  "rounded-full px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"

function NavLink({ href, label, className, onClick }: { href: string; label: string; className: string; onClick?: () => void }) {
  return href.startsWith("#") ? (
    <a href={href} className={className} onClick={onClick}>
      {label}
    </a>
  ) : (
    <Link href={href} className={className} onClick={onClick}>
      {label}
    </Link>
  )
}

export function Navbar() {
  const [isMenuOpen, setIsMenuOpen] = useState(false)

  return (
    <motion.header
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: "easeOut" }}
      className="sticky top-0 z-50 border-b border-border/70 bg-background/80 backdrop-blur-xl"
    >
      <Container className="flex h-20 items-center justify-between gap-4">
        <a href="#top" className="flex items-center text-foreground">
          <Logo />
        </a>

        <nav className="hidden items-center gap-1 md:flex" aria-label="Primary">
          {LANDING_NAV.map((item) => (
            <NavLink key={item.href} href={item.href} label={item.label} className={navLinkClassName} />
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <a
            href="#faq"
            className="hidden items-center gap-2 rounded-full border border-border bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted md:inline-flex"
          >
            <Globe className="size-4" />
            Global access
          </a>
          <Link
            href={APP_ROUTES.translate}
            className="brand-gradient hidden items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold text-white shadow-md transition-transform hover:scale-[1.02] md:inline-flex"
          >
            <ArrowRight className="size-4" />
            App: Translate
          </Link>

          <button
            type="button"
            onClick={() => setIsMenuOpen((open) => !open)}
            aria-expanded={isMenuOpen}
            aria-controls="mobile-nav"
            aria-label={isMenuOpen ? "Close menu" : "Open menu"}
            className="inline-flex size-11 items-center justify-center rounded-full border border-border bg-background text-foreground transition-colors hover:bg-muted md:hidden"
          >
            {isMenuOpen ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </Container>

      <AnimatePresence>
        {isMenuOpen && (
          <motion.nav
            id="mobile-nav"
            aria-label="Primary mobile"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
            className="overflow-hidden border-t border-border/70 bg-background/95 backdrop-blur-xl md:hidden"
          >
            <Container className="flex flex-col gap-1 py-4">
              {LANDING_NAV.map((item) => (
                <NavLink
                  key={item.href}
                  href={item.href}
                  label={item.label}
                  className={cn(navLinkClassName, "w-full text-left")}
                  onClick={() => setIsMenuOpen(false)}
                />
              ))}
              <Link
                href={APP_ROUTES.translate}
                onClick={() => setIsMenuOpen(false)}
                className="brand-gradient mt-2 inline-flex items-center justify-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold text-white shadow-md transition-transform hover:scale-[1.02]"
              >
                <ArrowRight className="size-4" />
                App: Translate
              </Link>
            </Container>
          </motion.nav>
        )}
      </AnimatePresence>
    </motion.header>
  )
}
