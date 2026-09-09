import { useCallback, useEffect, useState } from "react";
import { Activity, CheckCircle2, FileInput, Loader2, RefreshCw, Settings, Share, Table2, WifiOff } from "lucide-react";
import { configureApi, getBootstrap, getHealth, getRecentRuns, getRun } from "./api/client";
import type { BootstrapPayload, DesktopRun, HealthResponse, WorkbenchRow } from "./api/types";
import { AppShell } from "./components/AppShell";
import { Sidebar, type NavItem } from "./components/Sidebar";
import { Toolbar } from "./components/Toolbar";
import { Button } from "./components/ui/button";
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

const pageContext: Record<PageKey, { title: string; subtitle: string }> = {
  workbench: {
    title: "三表工作台",
    subtitle: "工程三表、证据链和导出包在同一个工作台内收敛。"
  },
  import: {
    title: "图纸导入",
    subtitle: "从图纸识别启动项目，并把结果接入当前工作台。"
  },
  closure: {
    title: "评审闭环",
    subtitle: "跟进人工确认、知识建议和链路同步任务。"
  },
  export: {
    title: "导出",
    subtitle: "整理当前运行的输出包、质量门和交付文件。"
  },
  settings: {
    title: "设置",
    subtitle: "配置本地服务、模型连接和桌面工作区。"
  }
};

const apiMeta = {
  checking: {
    label: "检查本地服务",
    tone: "info",
    icon: Loader2,
    activity: "spin"
  },
  online: {
    label: "本地服务在线",
    tone: "success",
    icon: CheckCircle2,
    activity: "none"
  },
  offline: {
    label: "本地服务离线",
    tone: "danger",
    icon: WifiOff,
    activity: "none"
  }
} as const;

function autoRestorableRun(run: DesktopRun): boolean {
  return run.status !== "failed" || run.blocked_stage !== "pfmea";
}

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
        return getRecentRuns(5);
      })
      .then((runs) => {
        const run = runs.find(autoRestorableRun);
        if (run) setActiveRun(run);
      })
      .catch(() => setApiState("offline"));
  }, []);

  const refreshActiveRun = useCallback(async () => {
    setApiState("checking");
    try {
      if (activeRun) {
        const latest = await getRun(activeRun.id);
        setActiveRun(latest);
      } else {
        const runs = await getRecentRuns(5);
        const run = runs.find(autoRestorableRun);
        if (run) setActiveRun(run);
      }
      setApiState("online");
    } catch (caught) {
      setApiState("offline");

    }
  }, [activeRun?.id]);

  const context = pageContext[page];

  return (
    <AppShell
      sidebar={<Sidebar items={navItems} activeKey={page} onSelect={setPage} />}
      toolbar={
        <Toolbar
          title={context.title}
          subtitle={context.subtitle}
          status={apiMeta[apiState]}
          actions={
            <>
              <Button variant="outline" size="icon-sm" className="bg-card/80" title="刷新" aria-label="刷新" onClick={() => void refreshActiveRun()}>
                <RefreshCw size={16} />
              </Button>
              <span className="flex h-7 items-center rounded-full border border-border bg-card/80 px-2.5 text-xs font-medium text-muted-foreground">
                v{bootstrap?.version ?? "3.8.6"}
              </span>
            </>
          }
        />
      }
    >
      {page === "workbench" && (
        <ThreeTableWorkbench
          run={activeRun}
          selectedRow={selectedRow}
          onSelectRow={setSelectedRow}
          onRunUpdated={setActiveRun}
          onRunRefresh={refreshActiveRun}
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
