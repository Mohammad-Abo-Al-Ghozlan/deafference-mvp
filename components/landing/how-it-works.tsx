"use client"

import { motion } from "framer-motion"
import { ArrowRight, Mic, Settings2, Sparkles, Wand2 } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Container } from "@/components/shared/container"
import { SectionTitle } from "@/components/shared/section-title"
import { IconBadge } from "@/components/shared/icon-badge"

const steps = [
  {
    icon: Mic,
    title: "Capture intent",
    description: "Users speak or type a sentence in a simple interface designed for fast comprehension.",
  },
  {
    icon: Wand2,
    title: "Normalize language",
    description: "The workflow can simplify phrasing and prepare the message for sign presentation.",
  },
  {
    icon: Sparkles,
    title: "Render the output",
    description: "An avatar or sign animation can present the final result with polished motion cues.",
  },
  {
    icon: Settings2,
    title: "Scale safely",
    description: "Future pages and features can be introduced without changing the landing structure.",
  },
]

export function HowItWorks() {
  return (
    <section id="how-it-works" className="border-y border-border/60 bg-muted/20 py-24 sm:py-28">
      <Container>
        <SectionTitle
          eyebrow="How it works"
          title="A simple flow with room to grow"
          description="The landing page explains the product in a way that maps cleanly to the eventual translation workflow."
        />

        <div className="mt-12 grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.55, ease: "easeOut" }}
            className="grid gap-4 sm:grid-cols-2"
          >
            {steps.map((step, index) => {
              const Icon = step.icon
              return (
                <Card key={step.title} className="p-6">
                  <div className="flex items-center justify-between gap-4">
                    <IconBadge icon={Icon} variant="solid" />
                    <span className="text-sm font-semibold text-muted-foreground">0{index + 1}</span>
                  </div>
                  <h3 className="mt-5 text-lg font-semibold text-foreground">{step.title}</h3>
                  <p className="mt-3 text-sm leading-7 text-muted-foreground">{step.description}</p>
                </Card>
              )
            })}
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.6, ease: "easeOut" }}
          >
            <Card className="flex h-full flex-col justify-between bg-foreground p-8 text-background">
              <div>
                <p className="text-sm font-medium tracking-[0.24em] text-background/70 uppercase">
                  Product flow
                </p>
                <h3 className="mt-4 text-2xl font-semibold tracking-tight sm:text-3xl">
                  From voice input to sign-ready output in one clear path.
                </h3>
                <p className="mt-4 max-w-md text-sm leading-7 text-background/75">
                  Each future workflow page can follow the same design logic: capture, process,
                  present, and expand.
                </p>
              </div>
              <a
                href="#features"
                className="mt-8 inline-flex items-center gap-2 text-sm font-semibold text-background/90 transition-colors hover:text-background"
              >
                Explore features
                <ArrowRight className="size-4" />
              </a>
            </Card>
          </motion.div>
        </div>
      </Container>
    </section>
  )
}
