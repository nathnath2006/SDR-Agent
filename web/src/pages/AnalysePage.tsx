import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, Play } from "lucide-react";
import { api } from "@/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AccountSheet, AccountTable, sortAccounts, type Sort, type SortKey } from "@/components/accounts";
import { EmptyState, PageHeader, StatCard } from "@/components/blocks";
import { frDate, go, matches, runDate, useLlm } from "@/lib/app";
import type { Account, ImportSummary, Job, RunData, Status, Tier } from "@/types";

type View = "top" | "tous" | "surveiller" | "clients";

export function AnalysePage({ runId, accountId, latestRun, onRunsChanged }: {
  runId?: string;
  accountId?: string;
  latestRun?: string;
  onRunsChanged: () => Promise<void>;
}) {
  const shownRun = runId ?? latestRun;
  const [data, setData] = useState<RunData | null>(null);

  useEffect(() => {
    setData(null);
    if (shownRun) api.run(shownRun).then(setData);
  }, [shownRun]);

  const onDone = useCallback(async (run: string) => {
    await onRunsChanged();
    go("analyse", run);
  }, [onRunsChanged]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analyse"
        description="Lance l'agent sur un import validé : il sort les 20 comptes à appeler en premier, avec le pourquoi."
        actions={data && <Exports data={data} />}
      />
      <Launcher onDone={onDone} />
      {shownRun && !data && <p className="text-sm text-muted-foreground">Chargement des résultats…</p>}
      {data && <Results data={data} accountId={accountId} />}
      {!shownRun && <EmptyState title="Pas encore de résultat">Valide un import puis lance l'analyse.</EmptyState>}
    </div>
  );
}

function Launcher({ onDone }: { onDone: (run: string) => void }) {
  const [imports, setImports] = useState<ImportSummary[]>([]);
  const [importId, setImportId] = useState<string>("");
  const [web, setWeb] = useState(true);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const running = job?.state === "running";
  const { llm } = useLlm();
  const provider = llm?.provider;

  useEffect(() => {
    api.imports().then((list) => {
      const valid = list.filter((i) => i.valide);
      setImports(valid);
      setImportId((cur) => cur || valid[0]?.id || "");
    });
    api.job().then((j) => j.state === "running" && setJob(j));
  }, []);

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(async () => {
      const j = await api.job();
      setJob(j);
      if (j.state === "done" && j.run) onDone(j.run);
    }, 1000);
    return () => clearInterval(timer);
  }, [running, onDone]);

  const start = async () => {
    setError("");
    try {
      setJob(await api.analyze(importId, Boolean(llm) && web, llm));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (imports.length === 0) {
    return (
      <Alert>
        <AlertTitle>Aucun import validé</AlertTitle>
        <AlertDescription>
          Importe un export et valide les regroupements dans l'onglet Import avant de lancer l'analyse.{" "}
          <button className="underline underline-offset-4" onClick={() => go("import")}>Aller à l'import</button>
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Lancer une analyse</CardTitle>
        <CardDescription>
          {provider
            ? `Rédaction avec ta clé ${provider === "gemini" ? "Gemini" : "Anthropic"} (${llm?.model}). Les statuts et paliers sont calculés par les règles.`
            : <>Tu n'as pas de clé LLM : statuts, paliers et Top 20 seront calculés, sans texte rédigé. <button className="underline underline-offset-4" onClick={() => go("parametres")}>Ajouter ta clé</button></>}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-4">
          <div className="space-y-1.5">
            <Label>Import validé</Label>
            <Select value={importId} onValueChange={setImportId} disabled={running}>
              <SelectTrigger className="w-80"><SelectValue /></SelectTrigger>
              <SelectContent>
                {imports.map((i) => <SelectItem key={i.id} value={i.id}>{i.fichier} · {runDate(i.id)}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2 pb-2">
            <Switch id="web" checked={Boolean(provider) && web} disabled={!provider || running} onCheckedChange={setWeb} />
            <Label htmlFor="web" className="font-normal">Vérifier sur le web si les 20 comptes ont déjà une marketplace</Label>
          </div>
          <Button onClick={start} disabled={running || !importId} className="bg-brand-yellow text-[#1c1c1c] hover:bg-brand-yellow/85 ml-auto"><Play />{running ? "Analyse en cours…" : "Lancer l'analyse"}</Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        {job && job.state !== "idle" && (
          <div className="space-y-2">
            {running && <Progress value={null as unknown as number} className="h-1 animate-pulse" />}
            <p className={job.state === "error" ? "text-sm text-destructive" : "text-sm"}>
              {job.state === "running" ? "En cours" : job.state === "done" ? "Terminé" : "Échec"}{job.message && ` : ${job.message}`}
            </p>
            <pre className="max-h-40 overflow-auto rounded-lg bg-muted p-3 text-xs text-muted-foreground">{job.logs.slice(-12).join("\n") || "Démarrage…"}</pre>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Exports({ data }: { data: RunData }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild><Button variant="outline"><Download />Exporter</Button></DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {/* Le menu se ferme avant qu'un lien ne soit suivi : on lance le téléchargement à la sélection.
            Le serveur répond en pièce jointe, la page reste affichée. */}
        {data.files.map((f) => (
          <DropdownMenuItem key={f} onSelect={() => window.location.assign(api.fileUrl(data.meta.run_id, f))}>{f}</DropdownMenuItem>
        ))}
        <DropdownMenuItem onSelect={() => window.location.assign(api.memoryUrl)}>memoire.csv</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Results({ data, accountId }: { data: RunData; accountId?: string }) {
  const { meta, accounts } = data;
  const [view, setView] = useState<View>("top");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<Status | "tous">("tous");
  const [tier, setTier] = useState<Tier | "tous">("tous");
  const [sort, setSort] = useState<Sort>({ key: "rang", desc: false });
  const open = accounts.find((a) => String(a.groupe_id) === accountId) ?? null;

  const views: Record<View, Account[]> = useMemo(() => ({
    top: accounts.filter((a) => a.rang_top),
    tous: accounts,
    surveiller: accounts.filter((a) => a.liste === "hors ICP à surveiller"),
    clients: accounts.filter((a) => a.liste === "clients à développer"),
  }), [accounts]);
  const rows = sortAccounts(
    views[view].filter((a) => (status === "tous" || a.statut === status) && (tier === "tous" || a.palier === tier) && matches(a, query)),
    sort, view === "top",
  );
  const onSort = (key: SortKey) => setSort((s) => ({ key, desc: s.key === key ? !s.desc : false }));
  const p = meta.paliers_top;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm text-muted-foreground">
        <span className="font-medium text-foreground">Analyse du {runDate(meta.run_id)}</span>
        <span>{meta.source}</span>
        <span>Signaux arrêtés au {frDate(meta.extraction)}</span>
        <span>{meta.explique ? `Textes : ${meta.llm}` : "Sans LLM : aucun texte rédigé"}</span>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Top 20" value={<span>{p.A} A · {p.B} B · {p.C} C</span>} hint={p.C ? `${p.C} comptes en palier C complètent la liste : à qualifier avant d'appeler.` : "Tous ont un signal d'intention récent."} />
        <StatCard label="Comptes qualifiés" value={meta.statuts["qualifié"]} hint={`sur ${meta.groupes} comptes (groupes) ; ${meta.statuts["à creuser"]} à creuser`} />
        <StatCard label="Fraîcheur" value={`${meta.fraicheur_jours} j`} tone={meta.fraicheur_jours > 14 ? "warn" : undefined}
                  hint="entre le dernier signal de l'export et l'analyse : vérifier que le sujet est toujours ouvert." />
        <StatCard label="Hors cible à surveiller" value={views.surveiller.length} hint={`${views.clients.length} clients Mirakl détectés`} />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Tabs value={view} onValueChange={(v) => setView(v as View)}>
          <TabsList>
            <TabsTrigger value="top">Top 20</TabsTrigger>
            <TabsTrigger value="tous">Tous ({accounts.length})</TabsTrigger>
            <TabsTrigger value="surveiller">Hors cible à surveiller ({views.surveiller.length})</TabsTrigger>
            <TabsTrigger value="clients">Clients Mirakl ({views.clients.length})</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Input placeholder="Rechercher" className="w-52" value={query} onChange={(e) => setQuery(e.target.value)} />
          <Select value={status} onValueChange={(v) => setStatus(v as Status | "tous")}>
            <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="tous">Tous statuts</SelectItem>
              {(["qualifié", "à creuser", "disqualifié"] as Status[]).map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={tier} onValueChange={(v) => setTier(v as Tier | "tous")}>
            <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="tous">Tous paliers</SelectItem>
              {(["A", "B", "C", "D"] as Tier[]).map((t) => <SelectItem key={t} value={t}>Palier {t}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      <AccountTable accounts={rows} sort={sort} onSort={onSort} topRank={view === "top"} explained={meta.explique}
                    onOpen={(a) => go("analyse", meta.run_id, a.groupe_id)} />
      <AccountSheet account={open} explained={meta.explique} onClose={() => go("analyse", meta.run_id)} />
    </div>
  );
}
