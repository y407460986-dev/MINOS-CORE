import type { ReactNode } from "react";

type AppShellProps = {
  sidebar: ReactNode;
  toolbar: ReactNode;
  children: ReactNode;
};

export function AppShell({ sidebar, toolbar, children }: AppShellProps) {
  return (
    <div className="grid grid-cols-[236px_minmax(620px,1fr)] min-h-screen text-foreground">
      {sidebar}
      <section className="grid grid-rows-[auto_1fr] min-w-0">
        {toolbar}
        <main className="p-6 overflow-auto">{children}</main>
      </section>
    </div>
  );
}
