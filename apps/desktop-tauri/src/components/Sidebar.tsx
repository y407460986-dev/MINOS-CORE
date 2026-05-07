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
    <aside className="bg-white/82 border-0 border-r border-solid border-border px-3 py-4">
      <div className="flex gap-2 h-7 items-center" aria-hidden="true">
        <span className="w-3 h-3 rounded-full bg-[#ff5f57]" />
        <span className="w-3 h-3 rounded-full bg-[#febc2e]" />
        <span className="w-3 h-3 rounded-full bg-[#28c840]" />
      </div>

      <div className="flex items-center gap-2.5 my-4 mx-1 mb-[22px]">
        <span className="grid place-items-center w-8 h-8 rounded-lg bg-foreground text-white font-bold">
          M
        </span>
        <div>
          <strong className="block">MINOS-CORE</strong>
          <small className="block text-muted-foreground">V1.14 Workbench</small>
        </div>
      </div>

      <nav className="grid gap-1" aria-label="主导航">
        {items.map((item) => {
          const Icon = item.icon;
          const isActive = item.key === activeKey;
          return (
            <button
              key={item.key}
              type="button"
              className={cn(
                "flex items-center gap-[9px] w-full h-9 border-0 rounded-lg px-2.5 text-left bg-transparent text-[#303034]",
                isActive && "bg-[#e8e8ed] text-primary"
              )}
              onClick={() => onSelect(item.key)}
            >
              <Icon size={17} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
