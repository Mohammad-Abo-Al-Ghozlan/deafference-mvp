"use client"

import { motion } from "framer-motion"
import { Accordion } from "@/components/ui/accordion"
import { Container } from "@/components/shared/container"
import { SectionTitle } from "@/components/shared/section-title"

const faqs = [
  {
    title: "What does Deafference include today?",
    content:
      "A polished landing page structure and an independent translation app architecture, ready for future product expansion.",
  },
  {
    title: "Does the landing page depend on the translation workflow?",
    content:
      "No. The marketing site and the AI translation app are intentionally separated so they can evolve on different timelines.",
  },
  {
    title: "Can dashboard, pricing, and docs be added later?",
    content:
      "Yes. The folder structure and shared primitives are designed to make additional pages straightforward to add.",
  },
  {
    title: "Is backend logic implemented yet?",
    content:
      "No. This build intentionally stops at architecture, reusable components, and placeholder content.",
  },
]

export function FAQ() {
  return (
    <section id="faq" className="py-24 sm:py-28">
      <Container>
        <SectionTitle
          eyebrow="FAQ"
          title="Common questions, answered simply"
          description="The goal is to make the product story easy to understand before the rest of the platform is built out."
        />

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.2 }}
          transition={{ duration: 0.55, ease: "easeOut" }}
          className="mt-12"
        >
          <Accordion items={faqs} />
        </motion.div>
      </Container>
    </section>
  )
}
