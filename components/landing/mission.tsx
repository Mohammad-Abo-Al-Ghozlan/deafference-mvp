"use client"

import { motion } from "framer-motion"
import { ArrowUpRight, Compass, HeartHandshake, ShieldCheck } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Container } from "@/components/shared/container"
import { SectionTitle } from "@/components/shared/section-title"
import { IconBadge } from "@/components/shared/icon-badge"

const values = [
  {
    icon: Compass,
    title: "Clarity first",
    description: "The interface should be easy to understand before users ever need a demo.",
  },
  {
    icon: HeartHandshake,
    title: "Human-centered",
    description: "Accessibility and trust matter more than decorative complexity.",
  },
  {
    icon: ShieldCheck,
    title: "Built responsibly",
    description: "The product presentation should set realistic expectations and future-proof the brand.",
  },
]

export function Mission() {
  return (
    <section id="mission" className="border-y border-border/60 bg-muted/20 py-24 sm:py-28">
      <Container>
        <SectionTitle
          eyebrow="Mission"
          title="Help people communicate with less friction and more dignity"
          description="The Deafference brand is grounded in practical accessibility and a clean product narrative."
        />

        <div className="mt-12 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.55, ease: "easeOut" }}
          >
            <Card className="h-full p-6 sm:p-8">
              <p className="text-sm font-medium tracking-[0.24em] text-muted-foreground uppercase">
                Our approach
              </p>
              <h3 className="mt-4 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                Build an AI company page that feels calm, capable, and ready for expansion.
              </h3>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-muted-foreground sm:text-base">
                The landing experience should communicate the product vision while staying
                independent from the translation app and any future authenticated surfaces.
              </p>
              <a
                href="#cta"
                className="mt-8 inline-flex items-center gap-2 text-sm font-semibold text-foreground transition-colors hover:text-brand-red"
              >
                See the roadmap
                <ArrowUpRight className="size-4" />
              </a>
            </Card>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.55, ease: "easeOut", delay: 0.05 }}
            className="grid gap-4"
          >
            {values.map((item) => {
              const Icon = item.icon
              return (
                <Card key={item.title} className="p-5">
                  <div className="flex items-start gap-4">
                    <IconBadge icon={Icon} />
                    <div>
                      <h3 className="text-lg font-semibold text-foreground">{item.title}</h3>
                      <p className="mt-2 text-sm leading-7 text-muted-foreground">{item.description}</p>
                    </div>
                  </div>
                </Card>
              )
            })}
          </motion.div>
        </div>
      </Container>
    </section>
  )
}
