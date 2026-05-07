import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type StatStripProps = {
  stats: Array<{ label: string; value: string | number; tone?: "default" | "warning" | "danger" }>;
};

export function StatStrip({ stats }: StatStripProps) {
  return (
    <div className="grid grid-cols-4 gap-2.5">
      {stats.map((stat) => (
        <Card key={stat.label}>
          <CardContent className="p-[14px]">
            <span className="block text-muted-foreground text-xs">{stat.label}</span>
            <strong
              className={cn(
                "block mt-1.5 text-2xl",
                stat.tone === "danger" && "text-destructive",
                stat.tone === "warning" && "text-[#9a5b00]"
              )}
            >
              {stat.value}
            </strong>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
