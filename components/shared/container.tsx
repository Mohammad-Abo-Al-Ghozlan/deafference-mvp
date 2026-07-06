import { cn } from "@/lib/utils"

export function Container({
  className,
  as: Component = "div",
  ...props
}: React.ComponentPropsWithoutRef<"div"> & {
  as?: React.ElementType
}) {
  return <Component className={cn("mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8", className)} {...props} />
}
