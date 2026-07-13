import { cn } from "@/lib/utils"

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-3xl border border-border bg-card p-6 shadow-sm transition-shadow duration-300 hover:shadow-md",
        className,
      )}
      {...props}
    />
  )
}
