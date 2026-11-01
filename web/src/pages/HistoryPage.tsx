import { Download } from "lucide-react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { api, download } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, PageHeader } from "@/components/blocks";
import { frDate, go, runDate } from "@/lib/app";
import type { RunMeta } from "@/types";

const chartConfig = {
  A: { label: "Palier A", color: "var(--tier-a)" },
  B: { label: "Palier B", color: "var(--tier-b)" },
  C: { label: "Palier C", color: "var(--tier-c)" },
} satisfies ChartConfig;

/** Continuité d'une analyse à l'autre : composition du Top 20 et comptes entrés ou sortis. */
export function HistoryPage({ runs }: { runs: RunMeta[] }) {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Historique"
        description="Chaque analyse lancée, et ce qui a changé dans le Top 20 par rapport à la précédente."
        actions={runs.length > 0 && <Button variant="outline" onClick={() => download(api.memoryUrl, "memoire.csv").catch((e) => window.alert((e as Error).message))}><Download />Mémoire (CSV)</Button>}
      />
      {runs.length === 0 ? <EmptyState title="Aucune analyse pour l'instant">Les analyses lancées depuis l'onglet Analyse apparaîtront ici.</EmptyState> : (
        <>
          {runs.length > 1 && (
            <Card>
              <CardHeader>
                <CardTitle>Composition du Top 20</CardTitle>
                <CardDescription>Plus il y a de paliers A et B, plus la semaine est riche en signaux d'intention.</CardDescription>
              </CardHeader>
              <CardContent>
                <ChartContainer config={chartConfig} className="h-56 w-full">
                  <BarChart data={[...runs].reverse().map((r) => ({ run: runDate(r.run_id), ...r.paliers_top }))}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="run" tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
                    <YAxis width={24} tickLine={false} axisLine={false} allowDecimals={false} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <ChartLegend content={<ChartLegendContent />} />
                    <Bar dataKey="A" stackId="t" fill="var(--color-A)" isAnimationActive={false} />
                    <Bar dataKey="B" stackId="t" fill="var(--color-B)" isAnimationActive={false} />
                    <Bar dataKey="C" stackId="t" fill="var(--color-C)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                  </BarChart>
                </ChartContainer>
              </CardContent>
            </Card>
          )}
          <div className="overflow-hidden rounded-xl ring-1 ring-foreground/10">
            <Table>
              <TableHeader className="bg-muted/50">
                <TableRow>
                  <TableHead>Analyse</TableHead>
                  <TableHead>Fichier</TableHead>
                  <TableHead>Signaux au</TableHead>
                  <TableHead>Top 20</TableHead>
                  <TableHead className="text-right">Qualifiés</TableHead>
                  <TableHead>Entrés dans le Top</TableHead>
                  <TableHead>Sortis du Top</TableHead>
                  <TableHead>Textes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((r, i) => (
                  <TableRow key={r.run_id} className="cursor-pointer" onClick={() => go("analyse", r.run_id)}>
                    <TableCell className="font-medium whitespace-nowrap">{runDate(r.run_id)}{i === 0 && <Badge variant="secondary" className="ml-2">dernière</Badge>}</TableCell>
                    <TableCell className="max-w-48 truncate">{r.source}</TableCell>
                    <TableCell className="whitespace-nowrap">{frDate(r.extraction)}</TableCell>
                    <TableCell className="whitespace-nowrap tabular-nums">{r.paliers_top.A} A · {r.paliers_top.B} B · {r.paliers_top.C} C</TableCell>
                    <TableCell className="text-right tabular-nums">{r.statuts["qualifié"]}</TableCell>
                    <TableCell className="max-w-56 truncate" title={r.entres?.join(", ")}>
                      {i === runs.length - 1 ? <span className="text-muted-foreground">première analyse</span> : r.entres?.length ? r.entres.join(", ") : <span className="text-muted-foreground">aucun</span>}
                    </TableCell>
                    <TableCell className="max-w-56 truncate" title={r.sortis_top?.join(", ")}>
                      {r.sortis_top?.length ? r.sortis_top.join(", ") : <span className="text-muted-foreground">{i === runs.length - 1 ? "" : "aucun"}</span>}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">{r.explique ? r.llm.split(" / ")[1] : "sans LLM"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </>
      )}
    </div>
  );
}
