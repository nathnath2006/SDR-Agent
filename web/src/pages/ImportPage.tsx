import { useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, FileSpreadsheet, Upload } from "lucide-react";
import { api } from "@/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { BarChartCard, EmptyState, PageHeader, StatCard } from "@/components/blocks";
import { frDate, frDateTime, go } from "@/lib/app";
import { cn } from "@/lib/utils";
import type { ImportDetail, ImportSummary, Inspection } from "@/types";

export function ImportPage({ importId, onImportsChanged }: { importId?: string; onImportsChanged: () => void }) {
  const [imports, setImports] = useState<ImportSummary[]>([]);
  const [detail, setDetail] = useState<ImportDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.imports().then((list) => {
      setImports(list);
      const id = importId ?? list[0]?.id;
      if (id) api.import(id).then(setDetail).catch((e) => setError(e.message));
      else setDetail(null);
    });
  }, [importId]);

  const upload = async (file?: File) => {
    if (!file) return;
    setError("");
    setBusy(true);
    try {
      const created = await api.upload(file);
      onImportsChanged();
      go("import", created.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Import"
        description="Charge l'export Tamtam, vérifie les feuilles et les chiffres, puis valide les regroupements avant l'analyse."
        actions={imports.length > 0 && (
          <Select value={detail?.id} onValueChange={(id) => go("import", id)}>
            <SelectTrigger className="w-72"><SelectValue placeholder="Imports précédents" /></SelectTrigger>
            <SelectContent>
              {imports.map((i) => (
                <SelectItem key={i.id} value={i.id}>{i.fichier} · {frDateTime(i.importe_le)}{i.valide ? " · validé" : ""}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      />

      <Dropzone busy={busy} onFile={upload} compact={Boolean(detail)} />
      {error && <Alert variant="destructive"><AlertTitle>Import impossible</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}

      {detail ? <ImportReview key={detail.id} detail={detail} onValidated={(s) => { setDetail({ ...detail, ...s }); onImportsChanged(); }} />
        : !busy && <EmptyState title="Aucun export importé">Dépose le fichier Excel exporté de Tamtam (onglets tamtam_prospects, events, crm_mirakl_accounts).</EmptyState>}
    </div>
  );
}

function Dropzone({ onFile, busy, compact }: { onFile: (f?: File) => void; busy: boolean; compact: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); onFile(e.dataTransfer.files[0]); }}
      className={cn("flex items-center gap-4 rounded-xl border border-dashed p-4 transition-colors",
                    compact ? "justify-between" : "flex-col justify-center py-12 text-center",
                    over && "border-primary bg-primary/5")}
    >
      <div className={cn("flex items-center gap-3", !compact && "flex-col")}>
        <Upload className="size-5 text-muted-foreground" />
        <div className="text-sm">
          <p className="font-medium">{busy ? "Lecture du fichier…" : "Dépose un export Tamtam (.xlsx)"}</p>
          <p className="text-muted-foreground">Les colonnes ou tableaux ajoutés à la main sont ignorés et signalés.</p>
        </div>
      </div>
      <Button variant={compact ? "outline" : "default"} disabled={busy} onClick={() => input.current?.click()}>Choisir un fichier</Button>
      <input ref={input} type="file" accept=".xlsx" className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
    </div>
  );
}

function ImportReview({ detail, onValidated }: { detail: ImportDetail; onValidated: (s: ImportSummary) => void }) {
  const { stats, qualite } = detail.inspection;
  const groups = qualite.regroupements;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <FileSpreadsheet className="size-5 text-muted-foreground" />
        <span className="font-medium">{detail.fichier}</span>
        <span className="text-sm text-muted-foreground">importé le {frDateTime(detail.importe_le)}</span>
        {detail.valide
          ? <Badge className="gap-1"><CheckCircle2 />Validé</Badge>
          : <Badge variant="outline">À valider</Badge>}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Prospects" value={stats.prospects} hint={`${qualite.champs_vides.Country} sans pays, ${qualite.champs_vides.CompanySize} sans taille`} />
        <StatCard label="Événements" value={stats.evenements} hint={`sur ${stats.comptes_avec_evenement} comptes`} />
        <StatCard label="Période des événements" value={<span className="text-lg">{frDate(stats.periode.debut)} → {frDate(stats.periode.fin)}</span>}
                  hint="La fin de période sert de date de référence pour l'âge des signaux." />
        <StatCard label="Regroupements à valider" value={groups.length} hint="doublons et filiales d'un même groupe" tone={groups.length && !detail.valide ? "warn" : undefined} />
      </div>

      <Tabs defaultValue="controle">
        <TabsList>
          <TabsTrigger value="controle">Contrôle</TabsTrigger>
          <TabsTrigger value="feuilles">Feuilles du fichier</TabsTrigger>
          <TabsTrigger value="validation">Validation{groups.length > 0 && !detail.valide && <Badge variant="secondary" className="ml-1">{groups.length}</Badge>}</TabsTrigger>
        </TabsList>
        <TabsContent value="controle" className="mt-4"><Controls inspection={detail.inspection} /></TabsContent>
        <TabsContent value="feuilles" className="mt-4"><Sheets inspection={detail.inspection} /></TabsContent>
        <TabsContent value="validation" className="mt-4"><Validation detail={detail} onValidated={onValidated} /></TabsContent>
      </Tabs>
    </div>
  );
}

function Controls({ inspection }: { inspection: Inspection }) {
  const { stats, qualite } = inspection;
  const [type, setType] = useState("tous");
  const types = stats.evenements_par_type.map((t) => t.label);
  const details = stats.evenements_par_detail.filter((d) => type === "tous" || d.type === type);
  return (
    <div className="space-y-4">
      {(qualite.ignore.length > 0 || qualite.evenements_orphelins > 0) && (
        <Alert>
          <AlertTitle>Éléments ignorés à l'import</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-5">
              {qualite.ignore.map((i) => (
                <li key={i.feuille}>Feuille {i.feuille} : {i.colonnes.length} colonne(s) sans en-tête{i.lignes > 0 && `, ${i.lignes} ligne(s) hors données`} (tableau ajouté à la main ?).</li>
              ))}
              {qualite.evenements_orphelins > 0 && <li>{qualite.evenements_orphelins} événement(s) sans prospect correspondant.</li>}
            </ul>
          </AlertDescription>
        </Alert>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <BarChartCard title="Événements par type" data={stats.evenements_par_type} horizontal height={240} />
        <BarChartCard title="Événements par mois" description="Répartition dans le temps" data={stats.evenements_par_mois.map((m) => ({ label: m.mois, n: m.n }))} height={240} />
        <BarChartCard title="Comptes par région" data={stats.comptes_par_region} horizontal height={200} />
        <BarChartCard title="Comptes par taille déclarée" data={stats.comptes_par_taille} height={200} />
        <BarChartCard title="Comptes par pays" data={stats.comptes_par_pays} horizontal height={380} />
        <BarChartCard title="Secteurs les plus représentés" data={stats.comptes_par_secteur} horizontal height={380} />
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div className="space-y-1">
            <CardTitle>Événements par détail</CardTitle>
            <CardDescription>Le contenu exact de chaque type d'événement.</CardDescription>
          </div>
          <Select value={type} onValueChange={setType}>
            <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="tous">Tous les types</SelectItem>
              {types.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
            </SelectContent>
          </Select>
        </CardHeader>
        <CardContent>
          <Table className="[&_td]:whitespace-normal">
            <TableHeader><TableRow><TableHead className="w-40">Type</TableHead><TableHead>Détail</TableHead><TableHead className="w-20 text-right">Nombre</TableHead></TableRow></TableHeader>
            <TableBody>
              {details.map((d) => (
                <TableRow key={d.type + d.detail}>
                  <TableCell className="text-muted-foreground">{d.type}</TableCell>
                  <TableCell>{d.detail}</TableCell>
                  <TableCell className="text-right tabular-nums">{d.n}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {qualite.pays.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Pays manquants ou suspects</CardTitle>
            <CardDescription>Le pays probable vient du domaine du site et de la forme juridique ; le compte reste « à creuser » sur la zone.</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader><TableRow><TableHead>Compte</TableHead><TableHead>Pays déclaré</TableHead><TableHead>Pays probable</TableHead></TableRow></TableHeader>
              <TableBody>
                {qualite.pays.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-medium">{p.nom}</TableCell>
                    <TableCell>{p.declare || <span className="text-muted-foreground">vide</span>}</TableCell>
                    <TableCell>{p.probable || <span className="text-muted-foreground">inconnu</span>}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

const PAGE = 50;

function Sheets({ inspection }: { inspection: Inspection }) {
  const [sheet, setSheet] = useState(inspection.feuilles.find((f) => f.nom === "tamtam_prospects")?.nom ?? inspection.feuilles[0].nom);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const current = inspection.feuilles.find((f) => f.nom === sheet)!;
  const rows = useMemo(() => {
    const q = query.toLowerCase();
    return q ? current.valeurs.filter((r) => r.some((v) => String(v ?? "").toLowerCase().includes(q))) : current.valeurs;
  }, [current, query]);
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
        <ToggleGroup type="single" variant="outline" value={sheet} onValueChange={(v) => { if (v) { setSheet(v); setPage(0); setQuery(""); } }}>
          {inspection.feuilles.map((f) => <ToggleGroupItem key={f.nom} value={f.nom}>{f.nom} <span className="text-muted-foreground">{f.lignes}</span></ToggleGroupItem>)}
        </ToggleGroup>
        <Input placeholder="Rechercher dans la feuille" className="w-64" value={query} onChange={(e) => { setQuery(e.target.value); setPage(0); }} />
      </CardHeader>
      <CardContent>
        <div className="max-h-[560px] overflow-auto rounded-lg ring-1 ring-foreground/10">
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-card">
              <TableRow>{current.colonnes.map((c) => <TableHead key={c} className={cn(c.startsWith("Unnamed") && "text-muted-foreground/60")}>{c.startsWith("Unnamed") ? "(sans en-tête)" : c}</TableHead>)}</TableRow>
            </TableHeader>
            <TableBody>
              {rows.slice(page * PAGE, page * PAGE + PAGE).map((r, i) => (
                <TableRow key={i}>
                  {r.map((v, j) => <TableCell key={j} className="max-w-72 truncate" title={v === null ? "" : String(v)}>{v === null ? "" : String(v)}</TableCell>)}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
      <CardFooter className="justify-between text-sm text-muted-foreground">
        <span>{rows.length} ligne(s) · {current.colonnes.length} colonnes</span>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Précédent</Button>
          <span>{page + 1} / {pages}</span>
          <Button variant="outline" size="sm" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Suivant</Button>
        </div>
      </CardFooter>
    </Card>
  );
}

function Validation({ detail, onValidated }: { detail: ImportDetail; onValidated: (s: ImportSummary) => void }) {
  const groups = detail.inspection.qualite.regroupements;
  const [decisions, setDecisions] = useState<Record<string, boolean>>(
    () => detail.validation?.decisions ?? Object.fromEntries(groups.map((g) => [g.id, true])),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      onValidated(await api.validate(detail.id, decisions));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        L'agent propose de fusionner ces fiches : l'unité d'appel est le groupe, et ses signaux s'additionnent. Garde-les séparées
        si ce sont des acheteurs distincts (par exemple une filiale nationale autonome).
      </p>
      {groups.length === 0 && <EmptyState title="Aucun doublon ni groupe détecté" />}
      {groups.map((g) => (
        <Card key={g.id} size="sm">
          <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle className="flex items-center gap-2">
                {g.entites[0].nom}
                <Badge variant={g.type === "doublon" ? "secondary" : "outline"}>{g.type === "doublon" ? "doublon probable" : "groupe et filiales"}</Badge>
              </CardTitle>
              <CardDescription>{g.motifs.join(" ; ")}</CardDescription>
            </div>
            <ToggleGroup type="single" variant="outline" size="sm" value={decisions[g.id] ? "fusion" : "separe"}
                         onValueChange={(v) => v && setDecisions({ ...decisions, [g.id]: v === "fusion" })}>
              <ToggleGroupItem value="fusion">Fusionner</ToggleGroupItem>
              <ToggleGroupItem value="separe">Garder séparés</ToggleGroupItem>
            </ToggleGroup>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader><TableRow><TableHead>Fiche</TableHead><TableHead>Pays</TableHead><TableHead>Site</TableHead><TableHead>Secteur</TableHead><TableHead>Taille</TableHead><TableHead className="text-right">LinkedIn</TableHead></TableRow></TableHeader>
              <TableBody>
                {g.entites.map((e, i) => (
                  <TableRow key={e.id}>
                    <TableCell className="font-medium">{e.nom} <span className="text-xs text-muted-foreground">{e.id}</span>{i === 0 && decisions[g.id] && <Badge variant="outline" className="ml-2">fiche retenue</Badge>}</TableCell>
                    <TableCell>{e.pays || "—"}</TableCell>
                    <TableCell className="max-w-48 truncate">{e.site}</TableCell>
                    <TableCell>{e.secteur}</TableCell>
                    <TableCell>{e.taille}</TableCell>
                    <TableCell className="text-right tabular-nums">{e.linkedin ?? ""}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ))}
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={save} disabled={saving}>{detail.valide ? "Mettre à jour la validation" : "Valider les données"}</Button>
        {detail.valide && <Button variant="outline" onClick={() => go("analyse")}>Passer à l'analyse</Button>}
        {detail.validation && <span className="text-sm text-muted-foreground">Validé le {frDateTime(detail.validation.valide_le)}</span>}
        {error && <span className="text-sm text-destructive">{error}</span>}
      </div>
    </div>
  );
}
