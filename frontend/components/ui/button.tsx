import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export function buttonStyles(variant: ButtonVariant = "primary", className?: string) {
  return cn(
    "focus-ring inline-flex h-10 items-center justify-center gap-2 rounded-md px-4 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50",
    variant === "primary" && "bg-pine text-white hover:bg-[#11564a]",
    variant === "secondary" && "border border-[#ccd7d5] bg-white text-ink hover:bg-mist",
    variant === "ghost" && "text-ink hover:bg-white/70",
    variant === "danger" && "bg-coral text-white hover:bg-[#bf4d36]",
    className
  );
}

export function Button({
  className,
  variant = "primary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      className={buttonStyles(variant, className)}
      {...props}
    />
  );
}
