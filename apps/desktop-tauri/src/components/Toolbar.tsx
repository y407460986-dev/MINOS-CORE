import { RefreshCw, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type ToolbarProps = {
  title: string;
  apiState: "checking" | "online" | "offline";
  version: string;
};

export function Toolbar({ title, apiState, version }: ToolbarProps) {
  return (
    <header className="flex justify-between gap-5 items-center px-6 py-[18px] border-0 border-b border-solid border-border bg-[rgba(250,250,252,0.9)]">
      <div>
        <h1 className="m-0 mb-1 text-[22px]">{title}</h1>
        <p className="m-0 text-[13px] text-muted-foreground">
          工程三表、证据链和导出包在同一个工作台内收敛。
        </p>
      </div>
      <div className="flex items-center gap-2.5">
        <div className="flex items-center gap-[7px] h-[30px] border border-border rounded-lg px-2.5 bg-white text-[#56565b] text-[13px]">
          <Search size={15} />
          <span>快速定位</span>
        </div>
        <Badge
          variant="outline"
          className={cn(
            "h-[30px] text-[13px]",
            apiState === "online" && "text-[#116d2d]",
            apiState === "offline" && "text-destructive"
          )}
        >
          {apiState === "online"
            ? "本地服务已连接"
            : apiState === "offline"
              ? "本地服务未连接"
              : "检查本地服务"}
        </Badge>
        <Button variant="outline" size="icon" className="w-[30px] h-[30px]" title="刷新">
          <RefreshCw size={16} />
        </Button>
        <span className="h-[30px] border border-border rounded-lg px-2.5 bg-white text-[#56565b] text-[13px] flex items-center">
          v{version}
        </span>
      </div>
    </header>
  );
}
