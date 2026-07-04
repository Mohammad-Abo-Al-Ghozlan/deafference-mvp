"use client"

import { motion } from "framer-motion"
import { Globe2, Mail, MessageSquare } from "lucide-react"
import { Container } from "@/components/shared/container"
import { LANDING_NAV, COMPANY_NAME } from "@/lib/constants"
import { Logo } from "@/components/deafference/logo"

const socialLinks = [
  { label: "Email", href: "mailto:hello@deafference.ai", icon: Mail },
  { label: "Updates", href: "#", icon: MessageSquare },
  { label: "Website", href: "#", icon: Globe2 },
]

export function Footer() {
  return (
    <motion.footer
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.45, ease: "easeOut" }}
      className="border-t border-border/60 py-10"
    >
      <Container className="grid gap-8 lg:grid-cols-[1fr_auto_auto] lg:items-start">
        <div className="max-w-sm">
          <div className="flex items-center gap-3">
            <Logo className="shadow-none ring-0" />
            <span className="text-sm font-semibold tracking-wide text-foreground">{COMPANY_NAME}</span>
          </div>
          <p className="mt-4 text-sm leading-7 text-muted-foreground">
            Professional AI landing architecture with a separate translation workflow and room for
            future product pages.
          </p>
        </div>

        <div>
          <p className="text-sm font-semibold text-foreground">Explore</p>
          <nav className="mt-4 flex flex-col gap-3 text-sm text-muted-foreground">
            {LANDING_NAV.map((item) => (
              <a key={item.href} href={item.href} className="transition-colors hover:text-foreground">
                {item.label}
              </a>
            ))}
          </nav>
        </div>

        <div>
          <p className="text-sm font-semibold text-foreground">Social</p>
          <div className="mt-4 flex flex-col gap-3 text-sm text-muted-foreground">
            {socialLinks.map((item) => {
              const Icon = item.icon
              return (
                <a key={item.label} href={item.href} className="inline-flex items-center gap-2 transition-colors hover:text-foreground">
                  <Icon className="size-4" />
                  {item.label}
                </a>
              )
            })}
          </div>
        </div>
      </Container>
    </motion.footer>
  )
}
