import type { ReactNode } from "react";

type AppShellProps = {
  sidebar: ReactNode;
  toolbar: ReactNode;
  inspector: ReactNode;
  children: ReactNode;
};

export function AppShell({ sidebar, toolbar, inspector, children }: AppShellProps) {
  return (
    <div className="grid grid-cols-[236px_minmax(620px,1fr)_300px] min-h-screen text-foreground">
      {sidebar}
      <section className="grid grid-rows-[auto_1fr] min-w-0">
        {toolbar}
        <main className="p-6 overflow-auto">{children}</main>
      </section>
      {inspector}
    </div>
  );
}
