import React from "react";
import { cn } from "@/lib/utils";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", children, disabled, ...props }, ref) => {
    return (
      <button
        ref={ref}
        disabled={disabled}
        className={cn(
          "inline-flex items-center justify-center font-medium rounded-lg transition-all focus:outline-none focus:ring-2 focus:ring-blue-500/50 disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]",
          size === "sm" && "px-3 py-1.5 text-xs gap-1.5",
          size === "md" && "px-4 py-2 text-sm gap-2",
          size === "lg" && "px-5 py-2.5 text-base gap-2.5",
          variant === "primary" &&
            "bg-blue-600 hover:bg-blue-500 text-white shadow-md shadow-blue-900/20 active:bg-blue-700",
          variant === "secondary" &&
            "bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700/80 active:bg-slate-850",
          variant === "outline" &&
            "border border-slate-700 hover:border-slate-600 hover:bg-slate-800/50 text-slate-300",
          variant === "ghost" &&
            "hover:bg-slate-800/60 text-slate-300 hover:text-white",
          variant === "danger" &&
            "bg-rose-600 hover:bg-rose-500 text-white shadow-md shadow-rose-900/20",
          className
        )}
        {...props}
      >
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";
