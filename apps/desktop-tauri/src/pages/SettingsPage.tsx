import { useEffect, useState } from "react";
import { FolderOpen, Save } from "lucide-react";
import { getSettings, selectOutputDir, setDefaultOutputDir } from "../api/client";
import type { BootstrapPayload, DesktopSettings } from "../api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

type SettingsPageProps = {
  apiState: "checking" | "online" | "offline";
  bootstrap: BootstrapPayload | null;
};

export default function SettingsPage({ apiState, bootstrap }: SettingsPageProps) {
  const [settings, setSettings] = useState<DesktopSettings | null>(null);
  const [outputDir, setOutputDir] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    void getSettings()
      .then((value) => {
        setSettings(value);
        setOutputDir(value.default_output_dir);
      })
      .catch((caught) => setMessage(caught instanceof Error ? caught.message : String(caught)));
  }, []);

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
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : String(caught));
    }
  }

  const ai = settings?.ai_config;
  const serviceState = apiState === "online" ? "已连接" : apiState === "offline" ? "未连接" : "检查中";

  return (
    <section className="grid gap-4">
      <div>
        <span className="text-primary text-xs font-bold">Settings</span>
        <h2 className="mt-1 mb-0 text-[22px]">运行设置</h2>
      </div>

      <Card className="max-w-[760px]">
        <CardContent className="p-[18px] grid gap-4">
          <label className="grid gap-[7px]">
            <span className="text-[#56565b] text-[13px]">默认输出目录</span>
            <div className="flex gap-2 items-center">
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
          {message && <span className="text-[#56565b] text-[13px]">{message}</span>}
        </CardContent>
      </Card>

      <Card className="overflow-hidden">
        {[
          ["本地服务状态", serviceState],
          ["本地服务地址", bootstrap?.apiBaseUrl ?? "http://127.0.0.1:8000"],
          ["本地后端托管", bootstrap?.sidecarManaged ? "已启用" : "未启用"],
          ["AI 提供方", ai?.provider ?? "-"],
          ["模型", ai?.model_configured ? ai.model : "未配置"],
          ["模型密钥", ai?.api_key_configured ? `已配置：${ai.api_key_env_name || ai.api_key_source}` : "未配置"],
          ["桌面版本", bootstrap?.version ?? "1.14.0"],
        ].map(([label, value], i) => (
          <div key={label}>
            <div className="grid grid-cols-[160px_1fr] gap-4 items-start px-4 py-[14px]">
              <span className="text-muted-foreground">{label}</span>
              <strong>{value}</strong>
            </div>
            {i < 6 && <Separator />}
          </div>
        ))}
      </Card>
    </section>
  );
}
