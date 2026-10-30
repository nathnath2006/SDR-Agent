import type { ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { cn } from "@/lib/utils";
import type { Status, Tier } from "@/types";

/** Palier : la couleur code le timing, du plus chaud (A) au plus froid (D). */
export function TierBadge({ tier, toQualify, className }: { tier: Tier; toQualify?: boolean; className?: string }) {
  const label = tier === "-" ? "Client" : tier;
  return (
    <span
      className={cn(
        "inline-flex h-6 min-w-6 items-center justify-center rounded-md px-1.5 text-xs font-semibold",
        tier === "A" && "bg-tier-a text-white",
        tier === "B" && "bg-tier-b text-white",
        tier === "C" && "bg-tier-c/15 text-tier-c ring-1 ring-tier-c/40 ring-inset",
        tier === "D" && "bg-muted text-muted-foreground",
        tier === "-" && "bg-tier-client/15 text-tier-client",
        className,
      )}
      title={toQualify ? "Palier C : à qualifier avant d'appeler" : undefined}
    >
      {label}
    </span>
  );
}

export function StatusText({ status }: { status: Status }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap",
        status === "à creuser" && "text-tier-c",
        status === "disqualifié" && "text-muted-foreground",
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          status === "qualifié" && "bg-tier-a",
          status === "à creuser" && "bg-tier-c",
          status === "disqualifié" && "bg-muted-foreground/50",
        )}
      />
      {status}
    </span>
  );
}

export function StatCard({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "warn" }) {
  return (
    <Card size="sm" className="gap-1">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <div className={cn("text-2xl font-semibold tracking-tight tabular-nums", tone === "warn" && "text-tier-c")}>{value}</div>
      </CardHeader>
      {hint && <CardContent className="text-xs text-muted-foreground">{hint}</CardContent>}
    </Card>
  );
}

export function BarChartCard({ title, description, data, horizontal, height = 220 }: {
  title: string;
  description?: string;
  data: { label: string; n: number }[];
  horizontal?: boolean;
  height?: number;
}) {
  const config = { n: { label: "Nombre", color: "var(--chart-2)" } } satisfies ChartConfig;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        <ChartContainer config={config} className="w-full" style={{ height }}>
          {horizontal ? (
            <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
              <CartesianGrid horizontal={false} />
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="label" width={150} tickLine={false} axisLine={false}
                     tick={{ fontSize: 12 }} interval={0} />
              <ChartTooltip cursor={false} content={<ChartTooltipContent hideLabel={false} />} />
              <Bar dataKey="n" fill="var(--color-n)" radius={4} isAnimationActive={false} />
            </BarChart>
          ) : (
            <BarChart data={data} margin={{ top: 8 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 11 }} interval={0}
                     angle={data.length > 8 ? -35 : 0} textAnchor={data.length > 8 ? "end" : "middle"}
                     height={data.length > 8 ? 60 : 30} />
              <YAxis width={28} tickLine={false} axisLine={false} tick={{ fontSize: 11 }} allowDecimals={false} />
              <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
              <Bar dataKey="n" fill="var(--color-n)" radius={4} isAnimationActive={false} />
            </BarChart>
          )}
        </ChartContainer>
      </CardContent>
    </Card>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <Card className="items-center py-16 text-center">
      <CardHeader className="w-full items-center">
        <CardTitle>{title}</CardTitle>
        {children && <CardDescription className="max-w-md">{children}</CardDescription>}
      </CardHeader>
      {action && <CardContent>{action}</CardContent>}
    </Card>
  );
}
