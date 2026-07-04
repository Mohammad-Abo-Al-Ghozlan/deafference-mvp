import { Container } from "./container"

export function PageFooter({
  title = "Deafference",
  description,
}: {
  title?: string
  description?: string
}) {
  return (
    <footer className="border-t border-border/70 py-10">
      <Container className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-foreground">{title}</p>
          {description ? (
            <p className="mt-1 text-sm text-muted-foreground">{description}</p>
          ) : null}
        </div>
        <p className="text-sm text-muted-foreground">Built with Next.js and Tailwind CSS.</p>
      </Container>
    </footer>
  )
}
