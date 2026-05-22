import * as React from "react"
import type { LucideIcon } from "lucide-react"
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react"

import { cn } from "@/lib/utils"

type Tone = "neutral" | "info" | "success" | "warning" | "danger"

const toneClasses: Record<Tone, string> = {
  neutral: "border-[hsl(var(--surface-border))] bg-[hsl(var(--surface-muted))] text-foreground",
  info: "border-[hsl(var(--info-border))] bg-[hsl(var(--info-surface))] text-primary",
  success: "border-[hsl(var(--success-border))] bg-[hsl(var(--success-surface))] text-[hsl(var(--success-foreground))]",
  warning: "border-[hsl(var(--warning-border))] bg-[hsl(var(--warning-surface))] text-[hsl(var(--warning-foreground))]",
  danger: "border-[hsl(var(--danger-border))] bg-[hsl(var(--danger-surface))] text-destructive",
}

const noticeIcons: Record<Exclude<Tone, "neutral">, LucideIcon> = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
}

type SurfaceProps = React.ComponentProps<"section"> & {
  inset?: "none" | "sm" | "md"
  interactive?: boolean
}

const surfaceInsetClasses: Record<NonNullable<SurfaceProps["inset"]>, string> = {
  none: "p-0",
  sm: "p-3",
  md: "p-4",
}

function Surface({
  className,
  inset = "md",
  interactive = false,
  ...props
}: SurfaceProps) {
  return (
    <section
      data-slot="surface"
      className={cn(
        "rounded-lg border border-[hsl(var(--surface-border))] bg-[hsl(var(--surface))] text-[hsl(var(--surface-foreground))] shadow-[var(--surface-shadow)]",
        "transition-[background-color,border-color,box-shadow,transform] [transition-duration:var(--motion-base)] [transition-timing-function:var(--motion-ease)] motion-reduce:transition-none",
        surfaceInsetClasses[inset],
        interactive && "hover:border-foreground/20 hover:bg-[hsl(var(--surface-hover))] hover:shadow-[var(--surface-shadow-hover)]",
        className
      )}
      {...props}
    />
  )
}

type NoticeProps = Omit<React.ComponentProps<"div">, "title"> & {
  title?: React.ReactNode
  tone?: Tone
  icon?: LucideIcon | false
}

function Notice({ className, title, tone = "info", icon, children, ...props }: NoticeProps) {
  const Icon = icon === false ? null : icon ?? (tone === "neutral" ? Info : noticeIcons[tone])

  return (
    <div
      data-slot="notice"
      role={tone === "danger" ? "alert" : "status"}
      className={cn(
        "flex gap-2.5 rounded-lg border px-3 py-2.5 text-sm leading-5",
        "transition-colors [transition-duration:var(--motion-base)] [transition-timing-function:var(--motion-ease)] motion-reduce:transition-none",
        toneClasses[tone],
        className
      )}
      {...props}
    >
      {Icon ? <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" /> : null}
      <div className="min-w-0">
        {title ? <div className="font-medium leading-5">{title}</div> : null}
        {children ? <div className={cn(title && "mt-0.5 text-foreground/70")}>{children}</div> : null}
      </div>
    </div>
  )
}

type StatusPillProps = React.ComponentProps<"span"> & {
  tone?: Tone
  icon?: LucideIcon
  activity?: "none" | "pulse" | "spin"
}

function StatusPill({
  className,
  tone = "neutral",
  icon: Icon,
  activity = "none",
  children,
  ...props
}: StatusPillProps) {
  return (
    <span
      data-slot="status-pill"
      className={cn(
        "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium",
        "transition-colors [transition-duration:var(--motion-fast)] [transition-timing-function:var(--motion-ease)] motion-reduce:transition-none",
        toneClasses[tone],
        className
      )}
      {...props}
    >
      {Icon ? (
        <Icon
          className={cn(
            "size-3.5",
            activity === "pulse" && "animate-pulse motion-reduce:animate-none",
            activity === "spin" && "animate-spin motion-reduce:animate-none"
          )}
          aria-hidden="true"
        />
      ) : null}
      {children}
    </span>
  )
}

type ContextPanelProps = Omit<React.ComponentProps<"aside">, "title"> & {
  title?: React.ReactNode
  description?: React.ReactNode
  action?: React.ReactNode
}

function ContextPanel({
  className,
  title,
  description,
  action,
  children,
  ...props
}: ContextPanelProps) {
  return (
    <aside
      data-slot="context-panel"
      className={cn(
        "rounded-lg border border-[hsl(var(--surface-border))] bg-[hsl(var(--surface))] p-3.5 text-sm text-[hsl(var(--surface-foreground))] shadow-[var(--surface-shadow)]",
        className
      )}
      {...props}
    >
      {(title || description || action) && (
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            {title ? <div className="font-medium leading-5">{title}</div> : null}
            {description ? <div className="mt-0.5 text-xs leading-5 text-muted-foreground">{description}</div> : null}
          </div>
          {action ? <div className="shrink-0">{action}</div> : null}
        </div>
      )}
      {children}
    </aside>
  )
}

type EmptyStateProps = Omit<React.ComponentProps<"div">, "title"> & {
  icon?: LucideIcon
  title: React.ReactNode
  description?: React.ReactNode
  action?: React.ReactNode
}

function EmptyState({
  className,
  icon: Icon,
  title,
  description,
  action,
  ...props
}: EmptyStateProps) {
  return (
    <div
      data-slot="empty-state"
      className={cn(
        "grid min-h-[180px] place-items-center rounded-lg border border-dashed border-[hsl(var(--surface-border))] bg-[hsl(var(--surface-muted))] px-6 py-8 text-center",
        className
      )}
      {...props}
    >
      <div className="max-w-[360px]">
        {Icon ? (
          <div className="mx-auto mb-3 grid size-9 place-items-center rounded-full bg-muted text-muted-foreground">
            <Icon className="size-4" aria-hidden="true" />
          </div>
        ) : null}
        <div className="text-sm font-medium">{title}</div>
        {description ? <div className="mt-1.5 text-sm leading-6 text-muted-foreground">{description}</div> : null}
        {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
      </div>
    </div>
  )
}

export { ContextPanel, EmptyState, Notice, StatusPill, Surface }
