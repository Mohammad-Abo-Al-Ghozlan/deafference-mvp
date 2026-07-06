"use client"

import { motion } from "framer-motion"
import { Cloud, Cpu, PanelsTopLeft, Palette, ShieldCheck, Terminal } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { Container } from "@/components/shared/container"
import { SectionTitle } from "@/components/shared/section-title"

const stack = [
  { icon: PanelsTopLeft, label: "Framer Motion" },
  { icon: Palette, label: "Tailwind CSS" },
  { icon: Terminal, label: "TypeScript" },
  { icon: ShieldCheck, label: "Base UI" },
  { icon: Cpu, label: "React 19" },
  { icon: Cloud, label: "Next.js 16" },
]

export function Technology() {
  return (
    <section id="technology" className="border-y border-border/60 bg-muted/20 py-24 sm:py-28">
      <Container>
        <SectionTitle
          eyebrow="Technology"
          title="Built on a modern, focused stack"
          description="The architecture keeps the landing system light while leaving room for a product surface, APIs, and future integrations."
        />

        <div className="mt-12 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.55, ease: "easeOut" }}
          >
            <Card className="h-full p-6">
              <p className="text-sm font-medium tracking-[0.24em] text-muted-foreground uppercase">
                Stack intent
              </p>
              <h3 className="mt-4 text-2xl font-semibold tracking-tight text-foreground">
                A clean foundation for speed, polish, and long-term maintainability.
              </h3>
              <p className="mt-4 text-sm leading-7 text-muted-foreground">
                This setup uses a composable design language and keeps all future product pages
                isolated from the marketing site.
              </p>
              <div className="mt-6 flex flex-wrap gap-2">
                {[
                  "App Router",
                  "Reusable components",
                  "Accessible primitives",
                  "Motion-driven UI",
                ].map((item) => (
                  <Badge key={item}>{item}</Badge>
                ))}
              </div>
            </Card>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.55, ease: "easeOut", delay: 0.05 }}
            className="grid gap-4 sm:grid-cols-2"
          >
            {stack.map((item) => {
              const Icon = item.icon
              return (
                <Card key={item.label} className="flex items-center gap-4 p-5">
                  <div className="flex size-11 items-center justify-center rounded-2xl bg-foreground text-background">
                    <Icon className="size-5" />
                  </div>
                  <p className="text-sm font-semibold text-foreground">{item.label}</p>
                </Card>
              )
            })}
          </motion.div>
        </div>
      </Container>
    </section>
  )
}
