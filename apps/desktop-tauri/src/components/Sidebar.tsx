import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type NavItem<TKey extends string> = {
  key: TKey;
  label: string;
  icon: LucideIcon;
};

type SidebarProps<TKey extends string> = {
  items: NavItem<TKey>[];
  activeKey: TKey;
  onSelect: (key: TKey) => void;
};

export function Sidebar<TKey extends string>({ items, activeKey, onSelect }: SidebarProps<TKey>) {
  return (
    <aside className="flex min-h-screen flex-col border-0 border-r border-solid border-border/70 bg-[hsl(var(--sidebar))] px-2.5 py-3 text-foreground">
      <div className="mx-1 mb-5 flex items-center gap-2.5 rounded-[8px] px-1 py-1">
        <span className="grid size-8 place-items-center rounded-[8px] bg-foreground text-sm font-semibold text-background shadow-[0_1px_2px_rgba(15,23,42,0.14)]">
          M
        </span>
        <div className="min-w-0">
          <strong className="block truncate text-sm font-semibold leading-5">MINOS-CORE</strong>
          <small className="block truncate text-xs leading-4 text-muted-foreground">Desktop Workbench</small>
        </div>
      </div>

      <nav className="grid gap-1" aria-label="主导航">
        <div className="px-2 pb-1.5 text-[11px] font-medium uppercase leading-4 text-muted-foreground">
          Workspace
        </div>
        {items.map((item) => {
          const Icon = item.icon;
          const isActive = item.key === activeKey;
          return (
            <button
              key={item.key}
              type="button"
              aria-current={isActive ? "page" : undefined}
              className={cn(
                "group relative flex h-8 w-full items-center gap-2 rounded-[8px] border border-transparent bg-transparent px-2.5 text-left text-sm text-muted-foreground",
                "transition-[background-color,border-color,color,transform] [transition-duration:var(--motion-fast)] [transition-timing-function:var(--motion-ease)] hover:bg-muted/65 hover:text-foreground active:translate-y-px",
                isActive && "border-border/80 bg-background/85 text-foreground shadow-[0_1px_2px_rgba(15,23,42,0.06)] hover:bg-background/85"
              )}
              onClick={() => onSelect(item.key)}
            >
              <Icon className={cn("size-4 shrink-0", isActive ? "text-foreground" : "text-muted-foreground group-hover:text-foreground")} />
              <span className="min-w-0 flex-1 truncate">{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="mt-auto border-0 border-t border-solid border-border/60 px-2 pt-3 text-xs leading-5 text-muted-foreground">
        <div className="truncate font-medium text-foreground">Local Workspace</div>
        <div className="truncate">运行数据保留在本机工作区</div>
      </div>
    </aside>
  );
}
