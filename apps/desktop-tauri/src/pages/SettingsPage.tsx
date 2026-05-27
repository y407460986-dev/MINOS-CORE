import { useEffect, useState, type ReactNode } from "react";
import { Archive, Bot, Database, FolderOpen, Info, RotateCcw, Save, Settings2, ShieldAlert, ShieldCheck, Trash2 } from "lucide-react";
import {
  backupDataManagement,
  clearDataManagement,
  getDataManagementStatus,
  getSettings,
  openPath,
  revealFile,
  selectOutputDir,
  setDefaultOutputDir,
  updateAiConfig,
  updateProcessBoundaryConfig
} from "../api/client";
import type {
  BootstrapPayload,
  DesktopDataClearScope,
  DesktopDataManagementStatus,
  DesktopSettings,
  ProcessBoundaryConfig
} from "../api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Notice, StatusPill, Surface } from "@/components/ui/experience";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";

type SettingsPageProps = {
  apiState: "checking" | "online" | "offline";
  bootstrap: BootstrapPayload | null;
};

const DEFAULT_PROCESS_BOUNDARY_CONFIG: ProcessBoundaryConfig = {
  enabled: true,
  process_scope: "本公司总成制造过程",
  supplier_processes_excluded: true,
  in_house_processes: ["来料检验", "冲压", "冲孔", "机加工", "装配", "铆接", "检验", "包装", "仓储"],
  purchased_inputs: ["锻件", "铸件", "标准件", "外购表面处理件"],
  disallowed_internal_operations: ["加热坯料", "锻造成形", "锻造切边", "热处理锻件", "抛丸清理锻件", "锻压", "锻造模具", "锻压机", "摩擦压力机"]
};

export default function SettingsPage({ apiState, bootstrap }: SettingsPageProps) {
  const [settings, setSettings] = useState<DesktopSettings | null>(null);
  const [dataStatus, setDataStatus] = useState<DesktopDataManagementStatus | null>(null);
  const [outputDir, setOutputDir] = useState("");
  const [message, setMessage] = useState("");
  const [aiMessage, setAiMessage] = useState("");
  const [aiBaseUrl, setAiBaseUrl] = useState("");
  const [aiApiKey, setAiApiKey] = useState("");
  const [aiModel, setAiModel] = useState("");
  const [dataMessage, setDataMessage] = useState("");
  const [deleteOutputs, setDeleteOutputs] = useState(true);
  const [processBoundaryMessage, setProcessBoundaryMessage] = useState("");
  const [processBoundaryEditing, setProcessBoundaryEditing] = useState(false);
  const [processBoundaryEnabled, setProcessBoundaryEnabled] = useState(true);
  const [processBoundaryScope, setProcessBoundaryScope] = useState("");
  const [supplierProcessesExcluded, setSupplierProcessesExcluded] = useState(true);
  const [inHouseProcessesText, setInHouseProcessesText] = useState("");
  const [purchasedInputsText, setPurchasedInputsText] = useState("");
  const [disallowedOperationsText, setDisallowedOperationsText] = useState("");

  useEffect(() => {
    void getSettings()
      .then((value) => {
        setSettings(value);
        setOutputDir(value.default_output_dir);
        setAiBaseUrl(value.ai_config.base_url_override ?? "");
        setAiModel(value.ai_config.model_override ?? "");
        syncProcessBoundaryForm(value.process_boundary_config);
      })
      .catch((caught) => setMessage(caught instanceof Error ? caught.message : String(caught)));
    void refreshDataStatus();
  }, []);

  async function refreshDataStatus() {
    try {
      setDataStatus(await getDataManagementStatus());
    } catch (caught) {
      setDataMessage(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function chooseOutputDir() {
    const path = await selectOutputDir();
    if (path) setOutputDir(path);
  }

  async function saveOutputDir() {
    setMessage("正在保存...");
    try {
      const value = await setDefaultOutputDir(outputDir);
      setSettings(value);
      setMessage("默认输出目录已保存");
      await refreshDataStatus();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : String(caught));
    }
  }

  function syncAiForm(value: DesktopSettings) {
    setSettings(value);
    setAiBaseUrl(value.ai_config.base_url_override ?? "");
    setAiApiKey("");
    setAiModel(value.ai_config.model_override ?? "");
  }

  function syncProcessBoundaryForm(config: ProcessBoundaryConfig) {
    setProcessBoundaryEnabled(config.enabled);
    setProcessBoundaryScope(config.process_scope);
    setSupplierProcessesExcluded(config.supplier_processes_excluded);
    setInHouseProcessesText(config.in_house_processes.join("\n"));
    setPurchasedInputsText(config.purchased_inputs.join("\n"));
    setDisallowedOperationsText(config.disallowed_internal_operations.join("\n"));
  }

  function processBoundaryPayload(): ProcessBoundaryConfig {
    return {
      enabled: processBoundaryEnabled,
      process_scope: processBoundaryScope.trim() || DEFAULT_PROCESS_BOUNDARY_CONFIG.process_scope,
      supplier_processes_excluded: supplierProcessesExcluded,
      in_house_processes: linesFromTextarea(inHouseProcessesText),
      purchased_inputs: linesFromTextarea(purchasedInputsText),
      disallowed_internal_operations: linesFromTextarea(disallowedOperationsText)
    };
  }

  async function saveAiConfig() {
    setAiMessage("正在保存...");
    const payload: { base_url?: string; api_key?: string; model?: string } = {
      base_url: aiBaseUrl,
      model: aiModel
    };
    if (aiApiKey !== "") payload.api_key = aiApiKey;
    try {
      const value = await updateAiConfig(payload);
      syncAiForm(value);
      setAiMessage("AI 配置已保存");
    } catch (caught) {
      setAiMessage(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function clearAiConfig() {
    setAiMessage("正在清除...");
    try {
      const value = await updateAiConfig({ base_url: "", api_key: "", model: "" });
      syncAiForm(value);
      setAiMessage("已清除自定义 AI 配置");
    } catch (caught) {
      setAiMessage(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function saveProcessBoundaryConfig(payload = processBoundaryPayload()) {
    setProcessBoundaryMessage("正在保存...");
    try {
      const value = await updateProcessBoundaryConfig(payload);
      setSettings(value);
      syncProcessBoundaryForm(value.process_boundary_config);
      setProcessBoundaryEditing(false);
      setProcessBoundaryMessage("公司工艺边界已保存");
    } catch (caught) {
      setProcessBoundaryMessage(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function restoreDefaultProcessBoundary() {
    await saveProcessBoundaryConfig(DEFAULT_PROCESS_BOUNDARY_CONFIG);
  }

  async function backupData() {
    setDataMessage("正在备份...");
    try {
      const result = await backupDataManagement();
      setDataMessage(`已备份到 ${result.backup_path}`);
      await refreshDataStatus();
    } catch (caught) {
      setDataMessage(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function clearData(scope: DesktopDataClearScope) {
    const confirmText = scope === "workspace" ? "清空项目" : "恢复初始状态";
    const typed = window.prompt(`此操作会修改本地数据。请先确认已经备份，然后输入“${confirmText}”继续。`);
    if (typed !== confirmText) {
      setDataMessage(`已取消：需要输入“${confirmText}”。`);
      return;
    }
    setDataMessage("正在处理本地数据...");
    try {
      const status = await clearDataManagement({
        scope,
        delete_outputs: deleteOutputs,
        confirm_text: typed
      });
      setDataStatus(status);
      setDataMessage(scope === "workspace" ? "项目与运行记录已清空" : "已恢复初始状态");
    } catch (caught) {
      setDataMessage(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function openLocalPath(path: string) {
    if (!path) return;
    try {
      await openPath(path);
    } catch (caught) {
      setDataMessage(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function revealBackup(path: string) {
    if (!path) return;
    try {
      await revealFile(path);
    } catch (caught) {
      setDataMessage(caught instanceof Error ? caught.message : String(caught));
    }
  }

  const ai = settings?.ai_config;
  const serviceState = apiState === "online" ? "已连接" : apiState === "offline" ? "未连接" : "检查中";
  const processBoundaryConfig = settings?.process_boundary_config ?? DEFAULT_PROCESS_BOUNDARY_CONFIG;
  const lastBackup = dataStatus?.last_backup_path
    ? `${dataStatus.last_backup_path}${dataStatus.last_backup_created_at ? `（${dataStatus.last_backup_created_at}）` : ""}`
    : "暂无备份";
  const aboutRows = [
    ["本地服务状态", serviceState],
    ["本地服务地址", bootstrap?.apiBaseUrl ?? "http://127.0.0.1:8000"],
    ["本地后端托管", bootstrap?.sidecarManaged ? "已启用" : "未启用"],
    ["AI 提供方", ai?.provider ?? "-"],
    ["AI 服务地址", ai?.base_url ?? "-"],
    ["模型", ai?.model_configured ? ai.model : "未配置"],
    ["模型密钥", ai?.api_key_configured ? `已配置：${ai.api_key_env_name || ai.api_key_source}` : "未配置"],
    ["桌面版本", bootstrap?.version ?? "-"],
  ];

  return (
    <section className="grid gap-5">
      <div>
        <span className="text-primary text-xs font-bold">Settings</span>
        <h2 className="mt-1 mb-0 text-[22px]">设置</h2>
        <p className="m-0 mt-1 text-[13px] text-muted-foreground">
          常用路径、AI 覆盖项、本地数据和版本信息分区管理。
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {[
          ["#settings-general", "通用"],
          ["#settings-ai", "AI"],
          ["#settings-process-boundary", "公司工艺边界"],
          ["#settings-data", "数据管理"],
          ["#settings-about", "关于"],
        ].map(([href, label]) => (
          <a key={href} href={href} className="rounded-md border bg-[hsl(var(--surface))] px-3 py-1.5 text-[13px] font-semibold text-muted-foreground no-underline transition-colors hover:bg-muted/50">
            {label}
          </a>
        ))}
      </div>

      <SettingsSection
        id="settings-general"
        icon={<Settings2 size={18} />}
        title="通用"
        description="默认输出目录会作为新运行的初始保存位置。"
      >
        <label className="grid gap-[7px]">
          <span className="text-[13px] text-muted-foreground">默认输出目录</span>
          <div className="flex gap-2 items-center max-[720px]:flex-col max-[720px]:items-stretch">
            <Input
              value={outputDir}
              onChange={(event) => setOutputDir(event.target.value)}
              className="flex-1"
            />
            <Button variant="outline" size="sm" onClick={chooseOutputDir}>
              <FolderOpen size={16} className="mr-[7px]" />
              选择
            </Button>
            <Button variant="outline" size="sm" onClick={saveOutputDir}>
              <Save size={16} className="mr-[7px]" />
              保存
            </Button>
          </div>
        </label>
        {message && <StatusText>{message}</StatusText>}
      </SettingsSection>

      <SettingsSection
        id="settings-ai"
        icon={<Bot size={18} />}
        title="AI"
        description="覆盖桌面端 AI 服务地址、API Key 和模型名；环境变量存在时仍优先生效。"
      >
        <div className="grid grid-cols-3 gap-3 max-[920px]:grid-cols-1">
          <label className="grid gap-[7px]">
            <FieldLabel label="服务地址" status={aiStatus(ai?.base_url_locked_by_env, ai?.base_url_override)} />
            <Input
              value={aiBaseUrl}
              onChange={(event) => setAiBaseUrl(event.target.value)}
              placeholder="https://cx.allincoding.cc"
              disabled={ai?.base_url_locked_by_env}
            />
          </label>

          <label className="grid gap-[7px]">
            <FieldLabel
              label="API Key"
              status={aiStatus(ai?.api_key_locked_by_env, ai?.api_key_override_set ? "set" : "")}
            />
            <Input
              type="password"
              value={aiApiKey}
              onChange={(event) => setAiApiKey(event.target.value)}
              placeholder={ai?.api_key_override_set ? "已配置请留空保持不变" : "未配置则填入"}
              disabled={ai?.api_key_locked_by_env}
            />
          </label>

          <label className="grid gap-[7px]">
            <FieldLabel label="模型名" status={aiStatus(ai?.model_locked_by_env, ai?.model_override)} />
            <Input
              value={aiModel}
              onChange={(event) => setAiModel(event.target.value)}
              placeholder="gpt-5.5"
              disabled={ai?.model_locked_by_env}
            />
          </label>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={saveAiConfig}>
            <Save size={16} className="mr-[7px]" />
            保存 AI 配置
          </Button>
          <Button variant="ghost" size="sm" onClick={clearAiConfig}>
            <RotateCcw size={16} className="mr-[7px]" />
            清除自定义
          </Button>
        </div>

        {aiMessage && <StatusText>{aiMessage}</StatusText>}
      </SettingsSection>

      <SettingsSection
        id="settings-process-boundary"
        icon={<ShieldCheck size={18} />}
        title="公司工艺边界"
        description="PFD 默认表达本公司总成制造过程；外购件只进入来料检验，不展开供应商制程。"
        wide
      >
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill tone={processBoundaryConfig.enabled ? "info" : "neutral"}>
            {processBoundaryConfig.enabled ? "已启用" : "未启用"}
          </StatusPill>
          <StatusPill tone={processBoundaryConfig.supplier_processes_excluded ? "info" : "neutral"}>
            {processBoundaryConfig.supplier_processes_excluded ? "排除供应商制程" : "未排除供应商制程"}
          </StatusPill>
          <span className="text-[13px] text-muted-foreground">{processBoundaryConfig.process_scope}</span>
        </div>

        {!processBoundaryEditing ? (
          <div className="grid grid-cols-3 gap-3 max-[920px]:grid-cols-1">
            <BoundaryPreview label="本厂可做" items={processBoundaryConfig.in_house_processes} />
            <BoundaryPreview label="外购输入" items={processBoundaryConfig.purchased_inputs} />
            <BoundaryPreview label="禁止作为本厂工序" items={processBoundaryConfig.disallowed_internal_operations} />
          </div>
        ) : (
          <div className="grid gap-3">
            <div className="grid grid-cols-[minmax(220px,0.8fr)_minmax(260px,1fr)] gap-3 max-[920px]:grid-cols-1">
              <label className="grid gap-[7px]">
                <span className="text-[13px] text-muted-foreground">过程范围</span>
                <Input
                  value={processBoundaryScope}
                  onChange={(event) => setProcessBoundaryScope(event.target.value)}
                  placeholder="本公司总成制造过程"
                />
              </label>
              <div className="flex flex-wrap items-end gap-4">
                <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={processBoundaryEnabled}
                    onChange={(event) => setProcessBoundaryEnabled(event.target.checked)}
                  />
                  启用公司工艺边界
                </label>
                <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={supplierProcessesExcluded}
                    onChange={(event) => setSupplierProcessesExcluded(event.target.checked)}
                  />
                  不展开供应商制程
                </label>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3 max-[920px]:grid-cols-1">
              <BoundaryTextarea
                label="本厂可做"
                value={inHouseProcessesText}
                onChange={setInHouseProcessesText}
              />
              <BoundaryTextarea
                label="外购输入"
                value={purchasedInputsText}
                onChange={setPurchasedInputsText}
              />
              <BoundaryTextarea
                label="禁止作为本厂工序"
                value={disallowedOperationsText}
                onChange={setDisallowedOperationsText}
              />
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {!processBoundaryEditing && (
            <Button variant="outline" size="sm" onClick={() => setProcessBoundaryEditing(true)}>
              <Settings2 size={16} className="mr-[7px]" />
              编辑
            </Button>
          )}
          {processBoundaryEditing && (
            <Button variant="outline" size="sm" onClick={() => saveProcessBoundaryConfig()}>
              <Save size={16} className="mr-[7px]" />
              保存
            </Button>
          )}
          {processBoundaryEditing && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                syncProcessBoundaryForm(processBoundaryConfig);
                setProcessBoundaryEditing(false);
              }}
            >
              取消
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={restoreDefaultProcessBoundary}>
            <RotateCcw size={16} className="mr-[7px]" />
            恢复默认
          </Button>
        </div>

        {processBoundaryMessage && <StatusText>{processBoundaryMessage}</StatusText>}
      </SettingsSection>

      <SettingsSection
        id="settings-data"
        icon={<Database size={18} />}
        title="数据管理"
        description="本地数据位于 Windows 用户数据目录；卸载重装默认不会删除这里的数据。"
        wide
      >
        <div className="grid grid-cols-[minmax(260px,1fr)_minmax(260px,0.85fr)] gap-4 max-[920px]:grid-cols-1">
          <div className="grid gap-2">
            <PathRow label="数据目录" value={dataStatus?.data_dir ?? "-"} />
            <PathRow label="数据库文件" value={dataStatus?.db_path ?? "-"} />
            <PathRow label="输出目录" value={dataStatus?.output_dir ?? "-"} />
            <PathRow label="日志目录" value={dataStatus?.log_dir ?? "-"} />
            <PathRow label="备份目录" value={dataStatus?.backup_dir ?? "-"} />
            <PathRow label="最后备份" value={lastBackup} />
          </div>

          <div className="grid gap-3">
            <div className="grid grid-cols-2 gap-2">
              <Metric label="项目数量" value={dataStatus?.project_count ?? 0} />
              <Metric label="运行记录" value={dataStatus?.run_count ?? 0} />
              <Metric label="本地知识规则" value={dataStatus?.knowledge_rule_count ?? 0} />
              <Metric label="输出文件占用" value={formatBytes(dataStatus?.output_size_bytes ?? 0)} />
              <Metric label="数据库大小" value={formatBytes(dataStatus?.db_size_bytes ?? 0)} />
            </div>

            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => openLocalPath(dataStatus?.data_dir ?? "")}>
                <FolderOpen size={16} className="mr-[7px]" />
                打开数据目录
              </Button>
              <Button variant="outline" size="sm" onClick={() => openLocalPath(dataStatus?.output_dir ?? "")}>
                <FolderOpen size={16} className="mr-[7px]" />
                打开输出目录
              </Button>
              <Button variant="outline" size="sm" onClick={backupData}>
                <Archive size={16} className="mr-[7px]" />
                备份数据
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!dataStatus?.last_backup_path}
                onClick={() => revealBackup(dataStatus?.last_backup_path ?? "")}
              >
                <FolderOpen size={16} className="mr-[7px]" />
                定位备份文件
              </Button>
            </div>
          </div>
        </div>

        <Notice tone="danger" title="危险操作" icon={ShieldAlert} className="grid">
          <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
            <input
              type="checkbox"
              checked={deleteOutputs}
              onChange={(event) => setDeleteOutputs(event.target.checked)}
            />
            清空时同时删除输出目录内容，不删除备份目录
          </label>
          <div className="flex flex-wrap gap-2">
            <Button variant="destructive" size="sm" onClick={() => clearData("workspace")}>
              <Trash2 size={16} className="mr-[7px]" />
              清空项目与运行记录
            </Button>
            <Button variant="destructive" size="sm" onClick={() => clearData("factory_reset")}>
              <RotateCcw size={16} className="mr-[7px]" />
              恢复初始状态
            </Button>
          </div>
        </Notice>

        {dataMessage && <StatusText>{dataMessage}</StatusText>}
      </SettingsSection>

      <SettingsSection
        id="settings-about"
        icon={<Info size={18} />}
        title="关于"
        description="当前桌面壳、本地服务和运行时配置状态。"
        wide
      >
        <div className="overflow-hidden rounded-lg border">
          {aboutRows.map(([label, value], i) => (
            <div key={label}>
              <div className="grid grid-cols-[160px_1fr] gap-4 items-start px-4 py-[14px] max-[640px]:grid-cols-1 max-[640px]:gap-1">
                <span className="text-muted-foreground">{label}</span>
                <strong className="break-words">{value}</strong>
              </div>
              {i < aboutRows.length - 1 && <Separator />}
            </div>
          ))}
        </div>
      </SettingsSection>
    </section>
  );
}

function SettingsSection({
  id,
  icon,
  title,
  description,
  children,
  wide = false
}: {
  id: string;
  icon: ReactNode;
  title: string;
  description: string;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <Surface id={id} className={wide ? "max-w-[1040px]" : "max-w-[820px]"}>
      <div className="grid gap-4">
        <div className="flex items-start gap-3">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border bg-muted/35 text-primary">
            {icon}
          </div>
          <div>
            <h3 className="m-0 text-[17px]">{title}</h3>
            <p className="m-0 mt-1 text-[13px] leading-6 text-muted-foreground">{description}</p>
          </div>
        </div>
        {children}
      </div>
    </Surface>
  );
}

function StatusText({ children }: { children: ReactNode }) {
  return <Notice tone="info" icon={false}>{children}</Notice>;
}

function FieldLabel({ label, status }: { label: string; status: string }) {
  return (
    <span className="flex items-center justify-between gap-3 text-[13px] text-muted-foreground">
      <span>{label}</span>
      <StatusPill tone={status === "默认" ? "neutral" : "info"} className="h-5 px-2">{status}</StatusPill>
    </span>
  );
}

function aiStatus(locked?: boolean, override?: string | boolean) {
  if (locked) return "已被环境变量接管";
  return override ? "已自定义" : "默认";
}

function PathRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[120px_1fr] gap-3 items-center">
      <span className="text-[13px] text-muted-foreground">{label}</span>
      <code className="overflow-x-auto rounded-md border bg-muted/40 px-2 py-1 text-[12px] whitespace-nowrap">
        {value}
      </code>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <Surface inset="sm" className="rounded-md px-3 py-2">
      <div className="text-[12px] text-muted-foreground">{label}</div>
      <strong className="text-[15px]">{value}</strong>
    </Surface>
  );
}

function BoundaryPreview({ label, items }: { label: string; items: string[] }) {
  return (
    <div className="rounded-md border bg-muted/20 px-3 py-2">
      <div className="mb-2 text-[12px] font-semibold text-muted-foreground">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {items.length > 0 ? (
          items.map((item) => (
            <span key={item} className="rounded-md border bg-muted/40 px-2 py-1 text-[12px]">
              {item}
            </span>
          ))
        ) : (
          <span className="text-[12px] text-muted-foreground">未设置</span>
        )}
      </div>
    </div>
  );
}

function BoundaryTextarea({
  label,
  value,
  onChange
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-[7px]">
      <span className="text-[13px] text-muted-foreground">{label}</span>
      <Textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-36 resize-y text-[13px] leading-6"
      />
    </label>
  );
}

function linesFromTextarea(value: string) {
  return value
    .split(/\r?\n|,|，|、|;|；/)
    .map((item) => item.trim())
    .filter((item, index, items) => item.length > 0 && items.indexOf(item) === index);
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
