"use client"

import { motion } from "framer-motion"
import { AudioLines, Camera, Languages, Layers3, ShieldCheck, Wand2 } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Container } from "@/components/shared/container"
import { SectionTitle } from "@/components/shared/section-title"
import { IconBadge } from "@/components/shared/icon-badge"

const features = [
  {
    icon: AudioLines,
    title: "Voice-first input",
    description: "A conversational interface for fast capture and low-friction interactions.",
  },
  {
    icon: Languages,
    title: "Language flexibility",
    description: "Prepared for multilingual support and expansion into additional language packs.",
  },
  {
    icon: Camera,
    title: "Visual translation surface",
    description: "A camera or avatar preview can sit beside the translation workflow when needed.",
  },
  {
    icon: Wand2,
    title: "AI normalization",
    description: "The product can simplify and structure phrases before presentation.",
  },
  {
    icon: Layers3,
    title: "Composable UI",
    description: "Reusable sections make it easy to add pricing, docs, dashboards, or auth pages later.",
  },
  {
    icon: ShieldCheck,
    title: "Enterprise-ready presentation",
    description: "Minimal styling, clear spacing, and high readability across breakpoints.",
  },
]

export function Features() {
  return (
    <section id="features" className="py-24 sm:py-28">
      <Container>
        <SectionTitle
          eyebrow="Features"
          title="Designed as a true product system"
          description="The landing page should communicate the platform, not just the demo. These features frame the AI product as extensible and credible."
        />

        <motion.div
          initial={{ opacity: 0, y: 22 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.2 }}
          transition={{ duration: 0.55, ease: "easeOut" }}
          className="mt-12 grid gap-4 md:grid-cols-2 xl:grid-cols-3"
        >
          {features.map((feature) => {
            const Icon = feature.icon
            return (
              <Card key={feature.title} className="p-6">
                <IconBadge icon={Icon} />
                <h3 className="mt-5 text-lg font-semibold text-foreground">{feature.title}</h3>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">{feature.description}</p>
              </Card>
            )
          })}
        </motion.div>
      </Container>
    </section>
  )
}
