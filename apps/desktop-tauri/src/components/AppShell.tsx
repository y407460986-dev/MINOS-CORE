import type { ReactNode } from "react";

type AppShellProps = {
  sidebar: ReactNode;
  toolbar: ReactNode;
  children: ReactNode;
};

export function AppShell({ sidebar, toolbar, children }: AppShellProps) {
  return (
    <div className="grid min-h-screen grid-cols-[220px_minmax(0,1fr)] bg-[hsl(var(--shell))] text-foreground">
      {sidebar}
      <section className="grid min-w-0 grid-rows-[auto_minmax(0,1fr)] bg-background/45">
        {toolbar}
        <main className="min-h-0 overflow-auto px-5 py-4">
          <div className="mx-auto w-full max-w-[1440px]">{children}</div>
        </main>
      </section>
    </div>
  );
}
