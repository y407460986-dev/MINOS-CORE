import { useEffect, useMemo, useState } from "react";
import { Activity, FileInput, PanelRight, Settings, Share, Table2 } from "lucide-react";
import { configureApi, getBootstrap, getHealth, getRecentRuns } from "./api/client";
import type { BootstrapPayload, DesktopRun, HealthResponse, WorkbenchRow } from "./api/types";
import { AppShell } from "./components/AppShell";
import { Sidebar, type NavItem } from "./components/Sidebar";
import { Toolbar } from "./components/Toolbar";
import { InspectorPanel } from "./components/InspectorPanel";
import DrawingImportPage from "./pages/DrawingImportPage";
import ThreeTableWorkbench from "./pages/ThreeTableWorkbench";
import ReviewClosurePage from "./pages/ReviewClosurePage";
import ExportPage from "./pages/ExportPage";
import SettingsPage from "./pages/SettingsPage";

type PageKey = "workbench" | "import" | "closure" | "export" | "settings";

const navItems: NavItem<PageKey>[] = [
  { key: "workbench", label: "三表工作台", icon: Table2 },
  { key: "import", label: "图纸导入", icon: FileInput },
  { key: "closure", label: "评审闭环", icon: Activity },
  { key: "export", label: "导出", icon: Share },
  { key: "settings", label: "设置", icon: Settings }
];

export default function App() {
  const [page, setPage] = useState<PageKey>("workbench");
  const [selectedRow, setSelectedRow] = useState<WorkbenchRow | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [bootstrap, setBootstrap] = useState<BootstrapPayload | null>(null);
  const [activeRun, setActiveRun] = useState<DesktopRun | null>(null);
  const [apiState, setApiState] = useState<"checking" | "online" | "offline">("checking");

  useEffect(() => {
    void getBootstrap()
      .then((value) => {
        setBootstrap(value);
        configureApi(value);
        return getHealth();
      })
      .catch(() => getHealth())
      .then((value) => {
        setHealth(value);
        setApiState("online");
        return getRecentRuns(1);
      })
      .then((runs) => {
        if (runs[0]) setActiveRun(runs[0]);
      })
      .catch(() => setApiState("offline"));
  }, []);

  const title = useMemo(() => navItems.find((item) => item.key === page)?.label ?? "MINOS", [page]);

  return (
    <AppShell
      sidebar={<Sidebar items={navItems} activeKey={page} onSelect={setPage} />}
      toolbar={<Toolbar title={title} apiState={apiState} version={bootstrap?.version ?? "1.14"} />}
      inspector={
        <InspectorPanel
          row={selectedRow}
          health={health}
          bootstrap={bootstrap}
          emptyHint={page === "workbench" ? "选择一行查看联动证据" : "当前页面无选中对象"}
        />
      }
    >
      {page === "workbench" && (
        <ThreeTableWorkbench
          run={activeRun}
          selectedRow={selectedRow}
          onSelectRow={setSelectedRow}
          onRunUpdated={setActiveRun}
        />
      )}
      <div hidden={page !== "import"}>
        <DrawingImportPage
          activeRun={activeRun}
          onRunCreated={(run) => {
            setActiveRun(run);
            setSelectedRow(null);
          }}
          onRunUpdated={setActiveRun}
          onOpenWorkbench={() => setPage("workbench")}
        />
      </div>
      {page === "closure" && <ReviewClosurePage run={activeRun} onRunUpdated={setActiveRun} />}
      {page === "export" && <ExportPage run={activeRun} />}
      {page === "settings" && <SettingsPage apiState={apiState} bootstrap={bootstrap} />}
    </AppShell>
  );
}
