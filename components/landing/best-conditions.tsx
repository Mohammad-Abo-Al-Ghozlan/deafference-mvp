"use client"

import { motion } from "framer-motion"
import { CheckCircle2, Clock3, Headphones, Laptop, ShieldCheck, Smile } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Container } from "@/components/shared/container"
import { SectionTitle } from "@/components/shared/section-title"

const conditions = [
  "Quiet, controlled environments for speech capture",
  "Clear messaging for high-intent, everyday requests",
  "Accessible displays that can sit next to a workflow",
  "Consistent animation and spacing across screens",
]

const cautions = [
  { icon: Headphones, label: "Audio quality", text: "Best results come from clean input and clear microphone pickup." },
  { icon: Laptop, label: "Device readiness", text: "The UI should render reliably across modern browsers and screen sizes." },
  { icon: Clock3, label: "Fast interactions", text: "Short, confident interactions are ideal for live communication contexts." },
  { icon: Smile, label: "User comfort", text: "Simple language and visible feedback reduce stress for first-time users." },
]

export function BestConditions() {
  return (
    <section id="best-conditions" className="border-y border-border/60 bg-muted/20 py-24 sm:py-28">
      <Container>
        <SectionTitle
          eyebrow="Best conditions"
          title="Optimized for practical communication settings"
          description="The product should feel dependable when users need it most, especially in busy or high-stakes environments."
        />

        <div className="mt-12 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.55, ease: "easeOut" }}
          >
            <Card className="h-full p-6">
              <div className="flex items-center gap-3">
                <div className="flex size-11 items-center justify-center rounded-2xl bg-foreground text-background">
                  <CheckCircle2 className="size-5" />
                </div>
                <h3 className="text-xl font-semibold text-foreground">Good-fit conditions</h3>
              </div>
              <ul className="mt-6 space-y-3 text-sm leading-7 text-muted-foreground">
                {conditions.map((item) => (
                  <li key={item} className="flex gap-3">
                    <ShieldCheck className="mt-0.5 size-4 shrink-0 text-brand-red" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.55, ease: "easeOut", delay: 0.05 }}
            className="grid gap-4 sm:grid-cols-2"
          >
            {cautions.map((item) => {
              const Icon = item.icon
              return (
                <Card key={item.label} className="p-5">
                  <div className="flex size-10 items-center justify-center rounded-xl bg-brand-orange/12 text-brand-red">
                    <Icon className="size-4" />
                  </div>
                  <h3 className="mt-4 text-base font-semibold text-foreground">{item.label}</h3>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.text}</p>
                </Card>
              )
            })}
          </motion.div>
        </div>
      </Container>
    </section>
  )
}
