import React from "react";
import { cn } from "@/lib/utils";

interface AvatarProps extends React.HTMLAttributes<HTMLDivElement> {
  name?: string;
  src?: string;
  size?: "sm" | "md" | "lg";
  status?: "online" | "offline" | "busy";
}

export const Avatar = ({
  name = "User",
  src,
  size = "md",
  status,
  className,
  ...props
}: AvatarProps) => {
  const initials = name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return (
    <div className="relative inline-block" {...props}>
      <div
        className={cn(
          "relative flex items-center justify-center rounded-full bg-slate-800 border border-slate-700/80 font-semibold text-slate-200 overflow-hidden select-none",
          size === "sm" && "w-8 h-8 text-xs",
          size === "md" && "w-10 h-10 text-sm",
          size === "lg" && "w-12 h-12 text-base",
          className
        )}
      >
        {src ? (
          // Standard img for placeholder UI avatar
          // eslint-disable-next-next/no-img-element
          <img src={src} alt={name} className="w-full h-full object-cover" />
        ) : (
          <span>{initials}</span>
        )}
      </div>

      {status && (
        <span
          className={cn(
            "absolute bottom-0 right-0 rounded-full ring-2 ring-slate-950",
            size === "sm" && "w-2.5 h-2.5",
            size === "md" && "w-3 h-3",
            size === "lg" && "w-3.5 h-3.5",
            status === "online" && "bg-emerald-500",
            status === "busy" && "bg-amber-500",
            status === "offline" && "bg-slate-500"
          )}
        />
      )}
    </div>
  );
};
