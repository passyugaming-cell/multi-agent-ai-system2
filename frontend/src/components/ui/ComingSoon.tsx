import React from "react";
import { Lock, Sparkles, Clock, AlertCircle } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";

export interface ComingSoonProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  badgeLabel?: string;
  status?: "coming_soon" | "locked" | "available";
}

export const ComingSoon: React.FC<ComingSoonProps> = ({
  title,
  description = "Fitur ini akan hadir pada rilis AI BOS mendatang.",
  icon,
  badgeLabel = "COMING SOON",
  status = "coming_soon",
  className,
  ...props
}) => {
  return (
    <Card
      variant="glass"
      className={cn(
        "flex flex-col items-center justify-center p-8 text-center border-dashed border-slate-800 bg-slate-900/30 min-h-[320px] max-w-2xl mx-auto my-8 relative overflow-hidden",
        className
      )}
      {...props}
    >
      {/* Background glow element */}
      <div className="absolute -top-24 -left-24 w-48 h-48 bg-blue-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute -bottom-24 -right-24 w-48 h-48 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />

      <div className="mb-4 relative">
        <div className="w-16 h-16 rounded-2xl bg-slate-800/80 border border-slate-700/60 flex items-center justify-center shadow-inner text-slate-300">
          {icon ? (
            icon
          ) : status === "locked" ? (
            <Lock className="w-8 h-8 text-amber-400" />
          ) : (
            <Sparkles className="w-8 h-8 text-blue-400" />
          )}
        </div>
        <div className="absolute -bottom-1 -right-1 p-1 bg-slate-950 rounded-full border border-slate-800">
          <Clock className="w-3.5 h-3.5 text-slate-400" />
        </div>
      </div>

      <div className="mb-3">
        <Badge
          variant={status === "locked" ? "warning" : "purple"}
          className="uppercase tracking-wider font-semibold text-[10px] px-3 py-0.5"
        >
          {badgeLabel}
        </Badge>
      </div>

      <h2 className="text-xl font-bold text-slate-100 tracking-tight mb-2">
        {title}
      </h2>

      <p className="text-sm text-slate-400 max-w-md leading-relaxed mb-6">
        {description}
      </p>

      <div className="flex items-center gap-2 text-xs text-slate-500 bg-slate-950/60 px-3 py-1.5 rounded-lg border border-slate-800/60">
        <AlertCircle className="w-3.5 h-3.5 text-slate-400 shrink-0" />
        <span>Fitur ini masih dalam tahap pengembangan aktif</span>
      </div>
    </Card>
  );
};
