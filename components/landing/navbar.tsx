"use client"

import { motion } from "framer-motion"
import Link from "next/link"
import { ArrowRight, Globe } from "lucide-react"
import { Container } from "@/components/shared/container"
import { LANDING_NAV, COMPANY_NAME } from "@/lib/constants"
import { cn } from "@/lib/utils"
import { Logo } from "@/components/deafference/logo"

export function Navbar() {
  return (
    <motion.header
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: "easeOut" }}
      className="sticky top-0 z-50 border-b border-border/70 bg-background/80 backdrop-blur-xl"
    >
      <Container className="flex h-20 items-center justify-between gap-4">
        <a href="#top" className="flex items-center gap-3 text-foreground">
          <Logo className="shadow-none ring-0" />
          <span className="hidden text-sm font-semibold tracking-wide sm:block">
            {COMPANY_NAME}
          </span>
        </a>

        <nav className="hidden items-center gap-1 lg:flex" aria-label="Primary">
          {LANDING_NAV.map((item) => {
            const className = cn(
              "rounded-full px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
            )

            return item.href.startsWith("#") ? (
              <a key={item.href} href={item.href} className={className}>
                {item.label}
              </a>
            ) : (
              <Link key={item.href} href={item.href} className={className}>
                {item.label}
              </Link>
            )
          })}
        </nav>

        <div className="flex items-center gap-2">
          <a
            href="#faq"
            className="hidden items-center gap-2 rounded-full border border-border bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted sm:inline-flex"
          >
            <Globe className="size-4" />
            Global access
          </a>
          <a
            href="#cta"
            className="hidden items-center gap-2 rounded-full bg-foreground px-4 py-2 text-sm font-semibold text-background transition-transform hover:scale-[1.02] sm:inline-flex"
          >
            <ArrowRight className="size-4" />
            Book a demo
          </a>
          <a
            href="#cta"
            className="inline-flex h-11 items-center rounded-full bg-foreground px-4 text-sm font-semibold text-background transition-transform hover:scale-[1.02] lg:hidden"
          >
            Demo
          </a>
        </div>
      </Container>
    </motion.header>
  )
}
