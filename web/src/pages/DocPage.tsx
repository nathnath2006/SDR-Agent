import type { ReactNode } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, StatusText, TierBadge } from "@/components/blocks";
import type { Config } from "@/types";

function Block({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-3 text-sm leading-relaxed">{children}</CardContent>
    </Card>
  );
}

const TABLE = "table-fixed [&_td]:align-top [&_td]:whitespace-normal";

/** Les règles de l'agent, en clair. Les seuils viennent de config.py. */
export function DocPage({ rules }: { rules: Config["rules"] }) {
  const { recent_days: r, max_days: m, size_min, size_max, top_n } = rules;
  const fmt = (n: number) => n.toLocaleString("fr-FR");
  return (
    <div className="space-y-6">
      <PageHeader title="Documentation" description="Comment l'agent choisit les comptes à appeler, et pourquoi." />

      <Block title="Le parcours">
        <ol className="list-decimal space-y-1 pl-5">
          <li><strong>Import</strong> de l'export Tamtam (prospects et événements).</li>
          <li><strong>Doublons et groupes</strong> validés par le SDR : un groupe devient un seul compte, avec les signaux de ses filiales.</li>
          <li><strong>Statut</strong> : l'entreprise est-elle dans la cible de Mirakl ?</li>
          <li><strong>Signaux</strong> : chaque événement reçoit un rôle (déclencheur, amplificateur, contexte, client Mirakl, bruit).</li>
          <li><strong>Évolutions</strong> (option) : comparaison avec l'analyse précédente.</li>
          <li><strong>Palier</strong> : faut-il l'appeler maintenant ?</li>
          <li><strong>Top {top_n}</strong>, puis les textes rédigés par le LLM si une clé est enregistrée.</li>
        </ol>
      </Block>

      <Block title="Le statut : est-ce le bon type d'entreprise ?" description="Trois critères jugés séparément.">
        <Table className={TABLE}>
          <TableHeader><TableRow><TableHead className="w-24">Critère</TableHead><TableHead>Dans la cible</TableHead><TableHead>Incertain</TableHead><TableHead>Hors cible</TableHead></TableRow></TableHeader>
          <TableBody>
            <TableRow><TableCell className="font-medium">Secteur</TableCell><TableCell>Retail, distribution, e-commerce, biens de consommation</TableCell><TableCell>Secteur voisin (agroalimentaire, textile, sport…) ou non renseigné</TableCell><TableCell>Tout le reste</TableCell></TableRow>
            <TableRow><TableCell className="font-medium">Zone</TableCell><TableCell>France et DACH (prioritaires), reste de l'Europe, États-Unis</TableCell><TableCell>Pays manquant ou suspect (déduit du site ou de la forme juridique)</TableCell><TableCell>Autres pays</TableCell></TableRow>
            <TableRow><TableCell className="font-medium">Taille</TableCell><TableCell>Bande LinkedIn entre {fmt(size_min)} et {fmt(size_max)}</TableCell><TableCell>Bande inconnue sans estimation LinkedIn</TableCell><TableCell>Bande hors de {fmt(size_min)} à {fmt(size_max)}</TableCell></TableRow>
          </TableBody>
        </Table>
        <dl className="grid grid-cols-[100px_minmax(0,1fr)] gap-x-4 gap-y-2">
          <dt><StatusText status="qualifié" /></dt><dd>Les trois critères sont dans la cible.</dd>
          <dt><StatusText status="à creuser" /></dt><dd>Au moins un critère est incertain.</dd>
          <dt><StatusText status="disqualifié" /></dt><dd>Au moins un critère est hors cible, ou Mirakl est déjà en place.</dd>
        </dl>
        <p className="text-muted-foreground">
          Pour la taille, la bande déclarée fait foi : tout le monde n'est pas sur LinkedIn. Le nombre de profils ne tranche qu'une bande à cheval sur {fmt(size_max)} (1001-5000) :
          au-delà de {fmt(size_max)} profils, l'entreprise est trop grande. Sinon, la bande qualifie avec un point « taille à confirmer ».
        </p>
      </Block>

      <Block title="Les signaux : le rôle de chaque événement" description="Les règles se lisent de haut en bas ; la première qui correspond s'applique.">
        <Table className={TABLE}>
          <TableHeader><TableRow><TableHead className="w-32">Rôle</TableHead><TableHead>Ce qui le déclenche</TableHead><TableHead className="w-60">Effet</TableHead></TableRow></TableHeader>
          <TableBody>
            <TableRow><TableCell className="font-medium">Client Mirakl</TableCell><TableCell>« Mirakl » apparaît dans l'événement (Mirakl détecté sur le site, « marketplace powered by Mirakl »).</TableCell><TableCell>Sort des prospects, liste « Clients Mirakl » pour les account managers.</TableCell></TableRow>
            <TableRow><TableCell className="font-medium">Déclencheur</TableCell><TableCell>Acquisition pour élargir l'assortiment en ligne ; annonce d'ouverture aux vendeurs tiers ; lancement de drop-ship ; offre d'emploi marketplace, assortiment tiers ou onboarding vendeurs ; recrutement du dirigeant e-commerce (E-commerce Director, Head of e-commerce, Digital commerce, E-commerce strategist).</TableCell><TableCell>Intention marketplace : fait entrer en palier A ou B.</TableCell></TableRow>
            <TableRow><TableCell className="font-medium">Amplificateur</TableCell><TableCell>Levée de fonds ; nouveau CEO ; acquisition sans lien e-commerce ; croissance des effectifs hors magasin ; poste data, dev ou de management.</TableCell><TableCell>Renforce un déclencheur ; seul, le compte reste en C.</TableCell></TableRow>
            <TableRow><TableCell className="font-medium">Contexte</TableCell><TableCell>Technologie en place (VTEX = concurrent ; Shopify, Salesforce, commercetools = plateforme sans marketplace) ; postes commerciaux ; changement de direction hors CEO (CFO…) ; croissance en magasin ou en production ; autres offres d'emploi.</TableCell><TableCell>Donne un angle d'approche, ne change pas le palier.</TableCell></TableRow>
            <TableRow><TableCell className="font-medium">Bruit</TableCell><TableCell>Tout le reste : sponsoring, RSE, prix, entrepôt, bureau, partenariat fournisseur…</TableCell><TableCell>Ignoré.</TableCell></TableRow>
          </TableBody>
        </Table>
        <p className="text-muted-foreground">
          L'âge d'un signal se compte depuis la date de l'export, pas depuis aujourd'hui : récent jusqu'à {r} jours, moyen jusqu'à {m} jours, ancien au-delà (visible, mais ne classe plus).
        </p>
      </Block>

      <Block title="Les paliers : faut-il appeler maintenant ?">
        <dl className="grid grid-cols-[40px_minmax(0,1fr)] items-start gap-x-4 gap-y-3">
          <dt><TierBadge tier="A" /></dt><dd>Un déclencheur de {r} jours ou moins, <strong>renforcé</strong> : par un amplificateur de {m} jours ou moins, ou par un second déclencheur d'une autre nature (par exemple une ouverture aux vendeurs et un recrutement).</dd>
          <dt><TierBadge tier="B" /></dt><dd>Un déclencheur de {r} jours ou moins seul, ou un déclencheur de {m} jours ou moins avec un amplificateur.</dd>
          <dt><TierBadge tier="C" /></dt><dd>Un déclencheur de {r + 1} à {m} jours sans renfort, un contexte favorable sans intention (une levée de fonds seule), ou un déclencheur ancien à revérifier.</dd>
          <dt><TierBadge tier="D" /></dt><dd>Aucun signal exploitable dans les {m} derniers jours : veille.</dd>
        </dl>
        <p className="text-muted-foreground">Un client Mirakl n'a pas de palier.</p>
      </Block>

      <div className="grid gap-6 lg:grid-cols-2">
        <Block title={`Le Top ${top_n}`}>
          <p>Les comptes non disqualifiés : d'abord les A, puis les B, puis les meilleurs C pour arriver à {top_n}. Les C sont marqués « à qualifier » : pas de signal d'intention récent, on vérifie avant de pitcher.</p>
          <p>Dans un palier : le signal le plus récent d'abord, puis qualifié avant à creuser, puis la zone (France et DACH, reste de l'Europe, États-Unis).</p>
          <p className="text-muted-foreground">Deux listes à part : « Hors cible à surveiller » (disqualifiés avec de vrais signaux) et « Clients Mirakl ».</p>
        </Block>

        <Block title="Évolutions entre deux analyses (option)">
          <p>Si l'option est cochée au lancement, chaque compte est comparé à la dernière analyse d'un export plus ancien. Les comptes qui ont des signaux nouveaux sont soumis au LLM, qui rend un verdict :</p>
          <ul className="list-disc space-y-1 pl-5">
            <li><strong>nette</strong> : compte comme un déclencheur ;</li>
            <li><strong>faible</strong> : compte comme un amplificateur ;</li>
            <li><strong>aucune</strong> : rien ne change.</li>
          </ul>
          <p className="text-muted-foreground">Un verdict qui ne cite aucun signal nouveau est ignoré. L'évolution est une nature à part : avec un autre déclencheur récent, elle fait passer en A.</p>
        </Block>

        <Block title="Le rôle du LLM">
          <p>Sans l'option évolutions, le LLM ne décide rien : statut, palier et ordre viennent des règles. Il traduit les événements, rédige la raison de chaque compte et la fiche des {top_n} (pourquoi maintenant, angles d'approche, points à vérifier), et vérifie sur le web s'ils ont déjà une marketplace.</p>
          <p className="text-muted-foreground">Chaque affirmation cite sa source : E = événement, P = profil Tamtam (photo de 2024), W = web. Un angle sans source est retiré. Sans clé, tout est calculé, rien n'est rédigé.</p>
        </Block>

        <Block title="Doublons et groupes">
          <p>L'unité d'appel est le groupe : deux fiches de la même entreprise (même nom, même site) ou d'un même groupe (Verdalis et sa filiale espagnole) sont proposées à la fusion.</p>
          <p>Le SDR valide chaque proposition à l'import. Une fois fusionnés, les signaux des filiales s'ajoutent à la ligne du groupe, avec leur origine.</p>
        </Block>

        <Block title="Ce que l'on récupère">
          <ul className="list-disc space-y-1 pl-5">
            <li><strong>Analyse</strong> : le Top {top_n}, tous les comptes, et une fiche par compte (raison, évolution, pourquoi maintenant, angles, marketplace, points à vérifier, signaux, fit).</li>
            <li><strong>Exports</strong> : un Excel unifié (un onglet par liste) ou une liste seule en Excel ou en CSV.</li>
            <li><strong>Historique</strong> : chaque analyse se rouvre, avec les comptes entrés et sortis du Top.</li>
          </ul>
        </Block>

        <Block title="Limites à garder en tête">
          <ul className="list-disc space-y-1 pl-5">
            <li>Les signaux datent de l'export : plus il est ancien, plus il faut vérifier en début d'appel.</li>
            <li>L'onglet CRM ne contient pas les clients de Mirakl : les clients ne sont repérés que par les événements.</li>
            <li>Le profil Tamtam (stratégie, e-commerce) est une photo de 2024.</li>
            <li>Les règles lisent des mots-clés : un poste au service des clients du compte (« E-commerce Strategist to help brands… ») compte encore comme déclencheur.</li>
          </ul>
        </Block>
      </div>
    </div>
  );
}
