import { useState } from "react";
import { ArrowDown, ArrowUp, ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusText, TierBadge } from "@/components/blocks";
import { ROLE_LABEL, frDate, mainSignal } from "@/lib/app";
import { cn } from "@/lib/utils";
import type { Account } from "@/types";

export type SortKey = "rang" | "compte" | "pays" | "age";
export interface Sort { key: SortKey; desc: boolean }

export function sortAccounts(accounts: Account[], sort: Sort, useTopRank: boolean): Account[] {
  const value = (a: Account): number | string => {
    switch (sort.key) {
      case "compte": return a.compte.toLowerCase();
      case "pays": return a.pays || "~";
      case "age": return mainSignal(a)?.age_jours ?? 99999;
      default: return useTopRank ? a.rang_top ?? a.rang : a.rang;
    }
  };
  return [...accounts].sort((x, y) => {
    const a = value(x), b = value(y);
    const cmp = a < b ? -1 : a > b ? 1 : 0;
    return sort.desc ? -cmp : cmp;
  });
}

const TIER_EDGE: Record<string, string> = {
  A: "shadow-[inset_3px_0_0_var(--tier-a)]",
  B: "shadow-[inset_3px_0_0_var(--tier-b)]",
  C: "shadow-[inset_3px_0_0_var(--tier-c)]",
  "-": "shadow-[inset_3px_0_0_var(--tier-client)]",
};

export function AccountTable({ accounts, sort, onSort, onOpen, topRank, explained }: {
  accounts: Account[];
  sort: Sort;
  onSort: (k: SortKey) => void;
  onOpen: (a: Account) => void;
  topRank: boolean;
  explained: boolean;
}) {
  const head = (key: SortKey | null, label: string, className?: string) => (
    <TableHead className={className}>
      {key ? (
        <button className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => onSort(key)}>
          {label}
          {sort.key === key && (sort.desc ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
        </button>
      ) : label}
    </TableHead>
  );
  return (
    <div className="overflow-hidden rounded-xl ring-1 ring-foreground/10">
      <Table className="table-fixed">
        <colgroup>
          <col className="w-12" /><col className="w-52" /><col className="w-16" /><col className="w-28" />
          <col className="w-32" /><col className="w-72" /><col className="w-16" /><col />
        </colgroup>
        <TableHeader className="bg-muted/50">
          <TableRow>
            {head("rang", "#", "text-right")}
            {head("compte", "Compte")}
            {head(null, "Palier")}
            {head(null, "Statut")}
            {head("pays", "Pays")}
            {head(null, "Signal principal")}
            {head("age", "Âge", "text-right")}
            {head(null, "Raison")}
          </TableRow>
        </TableHeader>
        <TableBody>
          {accounts.map((a) => {
            const s = mainSignal(a);
            return (
              <TableRow key={a.groupe_id} onClick={() => onOpen(a)} className={cn("cursor-pointer", TIER_EDGE[a.palier])}>
                <TableCell className="text-right text-muted-foreground tabular-nums">{topRank ? a.rang_top ?? a.rang : a.rang}</TableCell>
                <TableCell className="truncate font-medium" title={a.compte}>{a.compte}</TableCell>
                <TableCell><TierBadge tier={a.palier} toQualify={a.a_qualifier} /></TableCell>
                <TableCell><StatusText status={a.statut} /></TableCell>
                <TableCell className="truncate">{a.pays || <span className="text-muted-foreground">inconnu</span>}</TableCell>
                <TableCell className="truncate" title={s?.libelle}>{s ? s.libelle : <span className="text-muted-foreground">aucun</span>}</TableCell>
                <TableCell className="text-right tabular-nums">{s ? `${s.age_jours} j` : ""}</TableCell>
                <TableCell className="truncate text-muted-foreground" title={a.raison || a.regle_palier}>
                  {a.a_qualifier && <Badge variant="outline" className="mr-2">à qualifier</Badge>}
                  <span className={cn(a.raison && "text-foreground")}>{a.raison || (explained ? "" : a.regle_palier)}</span>
                </TableCell>
              </TableRow>
            );
          })}
          {accounts.length === 0 && (
            <TableRow><TableCell colSpan={8} className="py-10 text-center text-muted-foreground">Aucun compte ne correspond aux filtres.</TableCell></TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}

const WEB_STATE = { existante: "Une marketplace est déjà en place.", aucune: "Aucune marketplace trouvée.", inconnu: "Rien de concluant sur le web." };
const FIT_LABEL = { secteur: "Secteur", geographie: "Zone", taille: "Taille" } as const;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      {children}
    </section>
  );
}

/** Fiche d'un compte : décision calculée par les règles, puis explication rédigée. */
export function AccountSheet({ account: a, explained, onClose }: { account: Account | null; explained: boolean; onClose: () => void }) {
  const [focus, setFocus] = useState<string | null>(null);
  if (!a) return null;
  const pitch = a.argumentaire;
  const signals = a.signaux.filter((s) => s.role !== "bruit");
  const web = a.verification_web;
  const cite = (id: string) => {
    setFocus(id);
    document.getElementById(`ev-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-xl">
        <SheetHeader className="border-b">
          <div className="flex items-center gap-2">
            <TierBadge tier={a.palier} toQualify={a.a_qualifier} />
            <SheetTitle className="font-display text-2xl leading-none">{a.compte}</SheetTitle>
          </div>
          <SheetDescription className="flex flex-wrap gap-x-3 gap-y-1">
            <StatusText status={a.statut} />
            <span>{a.pays || "pays inconnu"}</span>
            <span>{a.secteur || "secteur inconnu"}</span>
            {a.site && (
              <a href={a.site} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline-offset-4 hover:underline">
                {a.site.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")}<ExternalLink className="size-3" />
              </a>
            )}
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 space-y-6 overflow-x-hidden overflow-y-auto p-4 [overflow-wrap:anywhere]">
          <dl className="grid grid-cols-[88px_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-sm">
            <dt className="text-muted-foreground">Palier</dt>
            <dd>{a.regle_palier}{a.a_qualifier && " — complète le Top 20, à qualifier avant d'appeler"}</dd>
            <dt className="text-muted-foreground">Statut</dt>
            <dd>{a.statut}{a.motif && <span className="text-muted-foreground"> : {a.motif}</span>}</dd>
            <dt className="text-muted-foreground">Taille</dt>
            <dd>{a.taille ? `bande ${a.taille}` : "bande inconnue"}{a.profils_linkedin ? `, ${a.profils_linkedin} profils LinkedIn` : ""}</dd>
            {a.entites.length > 1 && (<><dt className="text-muted-foreground">Groupe</dt><dd>{a.entites.join(", ")}</dd></>)}
          </dl>

          {pitch ? (
            <>
              <div className="space-y-2 rounded-lg border bg-card p-3">
                <p className="text-sm text-muted-foreground">Pourquoi maintenant ?</p>
                <div className="flex flex-wrap gap-1.5">
                  {signals.filter((s) => s.role === "déclencheur" || s.role === "amplificateur").slice(0, 3).map((s) => (
                    <span key={s.event_id} className={cn("why", s.role === "déclencheur" ? "text-why-blue" : "text-why-violet")}>{s.libelle}</span>
                  ))}
                </div>
                <p className="text-sm leading-relaxed">{pitch.pourquoi_maintenant}</p>
              </div>
              {pitch.ce_qui_a_change && (
                <Section title="Ce qui a changé depuis le profil Tamtam de 2024"><p className="text-sm leading-relaxed">{pitch.ce_qui_a_change}</p></Section>
              )}
              {pitch.axes.length > 0 && (
                <Section title="Angles d'approche">
                  <ul className="space-y-3">
                    {pitch.axes.map((axe, i) => (
                      <li key={i} className="border-l-2 pl-3 text-sm">
                        <p className="font-medium">{axe.besoin}</p>
                        <p className="text-muted-foreground">
                          <span className="font-medium text-foreground">{axe.produit}</span> : {axe.argument}{" "}
                          {axe.sources.map((s) => (
                            <button key={s} onClick={() => cite(s)} className="ml-1 text-xs text-primary underline underline-offset-2">{s}</button>
                          ))}
                        </p>
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
            </>
          ) : a.raison ? (
            <Section title="Raison"><p className="text-sm">{a.raison}</p></Section>
          ) : !explained ? (
            <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
              Pas de texte rédigé : l'analyse a tourné sans clé LLM. Ajoute une clé dans Paramètres puis relance.
            </p>
          ) : null}

          {(web || a.rang_top) && (
            <Section title="Marketplace aujourd'hui">
              {web?.statut === "vérifié" ? (
                <>
                  <p className="text-sm">{WEB_STATE[web.marketplace]} {web.detail}{web.technologie && ` Technologie : ${web.technologie}.`}</p>
                  <ul id="ev-W1" className="list-disc space-y-0.5 pl-5 text-xs">
                    {[...web.sources, ...web.sources_outil].map((s, i) => (
                      <li key={i}><a className="text-primary underline-offset-2 hover:underline" href={s.url} target="_blank" rel="noreferrer">{s.fait || s.titre || s.url}</a></li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">Non vérifiée{web?.statut ? ` (${web.statut})` : ""}. À demander en début d'appel.</p>
              )}
            </Section>
          )}

          {(a.incertitudes.length > 0 || a.fusion) && (
            <Section title="À vérifier pendant l'appel">
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {a.incertitudes.map((d) => <li key={d}>{d}</li>)}
                {a.fusion && <li className="text-muted-foreground">{a.fusion}</li>}
              </ul>
            </Section>
          )}

          <Separator />

          <Section title="Signaux">
            {signals.length === 0 ? <p className="text-sm text-muted-foreground">Aucun signal exploitable.</p> : (
              <ul className="divide-y text-sm">
                {signals.map((s) => (
                  <li key={s.event_id} id={`ev-${s.event_id}`} className={cn("grid grid-cols-[92px_minmax(0,1fr)] gap-3 rounded-md py-2", focus === s.event_id && "bg-primary/10")}>
                    <div className="text-xs text-muted-foreground">{frDate(s.date)}<br />{s.age_jours} j · {s.event_id}</div>
                    <div>
                      <span className={cn("why mb-1", s.role === "déclencheur" && "text-why-blue", s.role === "amplificateur" && "text-why-violet",
                                          s.role === "contexte" && "text-why-green", s.role === "client_mirakl" && "text-tier-client")}>{ROLE_LABEL[s.role]}</span>
                      <p>{s.libelle}</p>
                      <p className="text-xs text-muted-foreground">{s.raison}{s.origine && `, ${s.origine}`}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Fit ICP">
            <ul className="divide-y text-sm">
              {(Object.keys(FIT_LABEL) as (keyof typeof FIT_LABEL)[]).map((k) => (
                <li key={k} className="grid grid-cols-[88px_80px_minmax(0,1fr)] gap-2 py-2">
                  <span className="text-muted-foreground">{FIT_LABEL[k]}</span>
                  <span className={cn("font-medium", a.fit[k].niveau === "dans" && "text-tier-a", a.fit[k].niveau === "incertain" && "text-tier-c", a.fit[k].niveau === "hors" && "text-destructive")}>
                    {a.fit[k].niveau}
                  </span>
                  <span>{a.fit[k].detail}<span className="block text-xs text-muted-foreground">{a.fit[k].regle}</span></span>
                </li>
              ))}
            </ul>
          </Section>
        </div>
      </SheetContent>
    </Sheet>
  );
}
