import React from "react";
import { cn } from "@/lib/utils";

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "secondary" | "success" | "warning" | "danger" | "outline" | "purple";
  size?: "sm" | "md";
}

export const Badge = ({
  className,
  variant = "default",
  size = "md",
  children,
  ...props
}: BadgeProps) => {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full font-medium tracking-wide transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2",
        size === "sm" && "px-2 py-0.5 text-xs",
        size === "md" && "px-2.5 py-1 text-xs",
        variant === "default" && "bg-blue-500/10 text-blue-400 border border-blue-500/20",
        variant === "secondary" && "bg-slate-800 text-slate-300 border border-slate-700/60",
        variant === "success" && "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
        variant === "warning" && "bg-amber-500/10 text-amber-400 border border-amber-500/20",
        variant === "danger" && "bg-rose-500/10 text-rose-400 border border-rose-500/20",
        variant === "purple" && "bg-purple-500/10 text-purple-400 border border-purple-500/20",
        variant === "outline" && "bg-transparent text-slate-400 border border-slate-700",
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
};
