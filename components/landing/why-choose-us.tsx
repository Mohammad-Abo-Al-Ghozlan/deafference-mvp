"use client"

import { motion } from "framer-motion"
import { ShieldCheck, LayoutGrid, Sparkles, Workflow } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Container } from "@/components/shared/container"
import { SectionTitle } from "@/components/shared/section-title"
import { IconBadge } from "@/components/shared/icon-badge"

const reasons = [
  {
    icon: ShieldCheck,
    title: "Trustworthy by design",
    description: "Clear structure, stable components, and a clean visual hierarchy for enterprise buyers.",
  },
  {
    icon: LayoutGrid,
    title: "Independent surfaces",
    description: "Marketing pages and the translation workflow can evolve without coupling to each other.",
  },
  {
    icon: Workflow,
    title: "Scalable architecture",
    description: "Shared primitives, reusable sections, and future-ready folders for new product lines.",
  },
  {
    icon: Sparkles,
    title: "Modern AI brand",
    description: "A minimal, polished system inspired by the best SaaS landing pages in the market.",
  },
]

export function WhyChooseUs() {
  return (
    <section id="why-choose-us" className="py-24 sm:py-28">
      <Container>
        <SectionTitle
          eyebrow="Why choose us"
          title="A focused system for a serious AI product"
          description="Deafference is framed like a modern software company: clear positioning, clean layout, and deliberate separation between marketing and product UX."
        />

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.2 }}
          transition={{ duration: 0.55, ease: "easeOut" }}
          className="mt-12 grid gap-4 md:grid-cols-2 xl:grid-cols-4"
        >
          {reasons.map((item) => {
            const Icon = item.icon
            return (
              <Card key={item.title} className="h-full p-6 transition-transform duration-300 hover:-translate-y-1">
                <IconBadge icon={Icon} />
                <h3 className="mt-5 text-lg font-semibold text-foreground">{item.title}</h3>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">{item.description}</p>
              </Card>
            )
          })}
        </motion.div>
      </Container>
    </section>
  )
}
