import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { StatusPill } from "@/components/ui/experience";

type ToolbarStatus = {
  label: ReactNode;
  tone?: "neutral" | "info" | "success" | "warning" | "danger";
  icon?: LucideIcon;
  activity?: "none" | "pulse" | "spin";
};

type ToolbarProps = {
  title: string;
  subtitle?: ReactNode;
  status?: ToolbarStatus;
  actions?: ReactNode;
};

export function Toolbar({ title, subtitle, status, actions }: ToolbarProps) {
  return (
    <header className="flex min-h-[64px] items-center justify-between gap-4 border-0 border-b border-solid border-border/70 bg-card/80 px-5 backdrop-blur supports-[backdrop-filter]:bg-card/75">
      <div className="min-w-0">
        <h1 className="m-0 truncate text-[18px] font-semibold leading-6 tracking-normal">{title}</h1>
        {subtitle ? (
          <p className="m-0 mt-0.5 truncate text-[13px] leading-5 text-muted-foreground">{subtitle}</p>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {status ? (
          <StatusPill
            aria-live="polite"
            tone={status.tone}
            icon={status.icon}
            activity={status.activity}
          >
            {status.label}
          </StatusPill>
        ) : null}
        {actions}
      </div>
    </header>
  );
}

export type { ToolbarStatus };
