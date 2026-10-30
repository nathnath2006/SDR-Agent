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

/** Les règles de l'agent, en clair. Les seuils viennent de config.py. */
export function DocPage({ rules }: { rules: Config["rules"] }) {
  const { recent_days: r, max_days: m, size_min, size_max, top_n } = rules;
  const fmt = (n: number) => n.toLocaleString("fr-FR");
  return (
    <div className="space-y-6">
      <PageHeader title="Documentation" description="Comment l'agent choisit les comptes à appeler, et pourquoi." />

      <Block title="En bref">
        <ol className="list-decimal space-y-1 pl-5">
          <li><strong>Import</strong> : l'export Tamtam est lu, contrôlé, et le SDR valide les doublons et groupes.</li>
          <li><strong>Statut</strong> : chaque compte est-il dans la cible de Mirakl ?</li>
          <li><strong>Palier</strong> : y a-t-il une raison de l'appeler maintenant ?</li>
          <li><strong>Top {top_n}</strong> : les paliers A, puis B, complétés par les meilleurs C.</li>
          <li><strong>Textes</strong> : le LLM rédige la raison et la fiche d'appel, sans rien décider.</li>
        </ol>
        <p className="text-muted-foreground">Les règles décident seules : un même export donne toujours le même Top {top_n}.</p>
      </Block>

      <div className="grid gap-6 lg:grid-cols-2">
        <Block title="Le statut : est-ce une cible ?">
          <dl className="grid grid-cols-[100px_1fr] gap-x-4 gap-y-2">
            <dt><StatusText status="qualifié" /></dt>
            <dd>Retail, distribution ou biens de consommation ; Europe (France et DACH d'abord) ou États-Unis ; {fmt(size_min)} à {fmt(size_max)} salariés.</dd>
            <dt><StatusText status="à creuser" /></dt>
            <dd>Un critère reste incertain : pays manquant ou incohérent, secteur adjacent (agroalimentaire, fabricant…), taille inconnue.</dd>
            <dt><StatusText status="disqualifié" /></dt>
            <dd>Clairement hors cible, ou déjà client Mirakl. S'il a un signal, il reste visible dans « Hors cible à surveiller ».</dd>
          </dl>
        </Block>

        <Block title="La taille">
          <p>La <strong>taille déclarée fait foi</strong>. Une bande hors de {fmt(size_min)} à {fmt(size_max)} disqualifie, même si LinkedIn dit autre chose : tout le monde n'est pas sur LinkedIn.</p>
          <p>LinkedIn ne sert qu'à confirmer. Il ne tranche qu'une bande à cheval sur le seuil (1001-5000) : plus de {fmt(size_max)} profils prouve que l'entreprise est trop grande.</p>
          <p className="text-muted-foreground">Une bande à cheval qualifie, avec un point « taille à confirmer » dans la fiche.</p>
        </Block>
      </div>

      <Block title="Les signaux" description="Chaque événement de l'export reçoit un rôle, selon son type et son contenu.">
        <Table className="table-fixed [&_td]:align-top [&_td]:whitespace-normal">
          <TableHeader><TableRow><TableHead className="w-36">Rôle</TableHead><TableHead>Exemples</TableHead><TableHead className="w-64">Effet</TableHead></TableRow></TableHeader>
          <TableBody>
            <TableRow><TableCell className="font-medium">Déclencheur</TableCell><TableCell>Recrutement marketplace ou e-commerce stratégique (Head of Marketplace, E-commerce Director, Category Manager assortiment tiers), ouverture du site à des vendeurs tiers, lancement de drop-ship, acquisition pour élargir l'assortiment.</TableCell><TableCell>Intention marketplace : fait entrer en palier A ou B.</TableCell></TableRow>
            <TableRow><TableCell className="font-medium">Amplificateur</TableCell><TableCell>Levée de fonds, nouveau CEO, croissance des effectifs hors magasin, poste data ou dev.</TableCell><TableCell>Renforce un déclencheur ; seul, palier C.</TableCell></TableRow>
            <TableRow><TableCell className="font-medium">Contexte</TableCell><TableCell>Technologie en place (VTEX = concurrent ; Salesforce, commercetools, Shopify = plateforme sans marketplace), nouveau CFO, postes commerciaux, croissance en magasin.</TableCell><TableCell>Oriente l'angle d'approche, pas le palier.</TableCell></TableRow>
            <TableRow><TableCell className="font-medium">Client Mirakl</TableCell><TableCell>Mirakl détecté sur le site, « marketplace powered by Mirakl ».</TableCell><TableCell>Sort des prospects, à transmettre aux account managers.</TableCell></TableRow>
            <TableRow><TableCell className="font-medium">Bruit</TableCell><TableCell>Sponsoring, RSE, hausse de prix, entrepôt, bureau, partenariat fournisseur.</TableCell><TableCell>Ignoré.</TableCell></TableRow>
          </TableBody>
        </Table>
      </Block>

      <Block title="Les paliers : faut-il appeler maintenant ?" description={`L'âge d'un signal se compte depuis le dernier événement de l'export, pas depuis aujourd'hui.`}>
        <dl className="grid grid-cols-[40px_1fr] items-start gap-x-4 gap-y-3">
          <dt><TierBadge tier="A" /></dt><dd>Un déclencheur de moins de {r} jours, <strong>renforcé</strong> : un amplificateur, ou un second déclencheur d'une autre nature (par exemple une annonce d'ouverture aux vendeurs et un recrutement).</dd>
          <dt><TierBadge tier="B" /></dt><dd>Un déclencheur de moins de {r} jours seul, ou de moins de {m} jours avec un amplificateur.</dd>
          <dt><TierBadge tier="C" /></dt><dd>Contexte favorable sans intention (levée de fonds seule), déclencheur de {r} à {m} jours sans renfort, ou déclencheur plus ancien.</dd>
          <dt><TierBadge tier="D" /></dt><dd>Aucun signal exploitable dans les {m} derniers jours : veille.</dd>
        </dl>
      </Block>

      <div className="grid gap-6 lg:grid-cols-2">
        <Block title={`Le Top ${top_n}`}>
          <p>Les comptes non disqualifiés, dans cet ordre : palier A, puis B, puis C pour compléter jusqu'à {top_n}.</p>
          <p>Dans un palier : le signal le plus récent d'abord, puis qualifié avant à creuser, puis la zone (France et DACH, reste de l'Europe, États-Unis).</p>
          <p className="text-muted-foreground">Les comptes en palier C sont marqués « à qualifier » : ils n'ont pas de signal d'intention récent, on vérifie avant de pitcher. La force du renfort ne change pas l'ordre (deux signaux ne passent pas devant un signal plus récent).</p>
        </Block>

        <Block title="Doublons et groupes">
          <p>L'unité d'appel est le groupe : deux fiches de la même entreprise (même nom, même site) ou d'un même groupe (Verdalis et sa filiale espagnole) sont proposées à la fusion.</p>
          <p>Le SDR valide chaque proposition à l'import. Une fois fusionnés, les signaux des filiales s'ajoutent à la ligne du groupe, avec leur origine.</p>
        </Block>

        <Block title="Le rôle du LLM">
          <p>Le LLM ne décide rien : statut, palier et ordre viennent des règles. Il traduit les événements, rédige la raison de chaque compte et la fiche d'appel, et vérifie sur le web si les comptes du Top ont déjà une marketplace.</p>
          <p className="text-muted-foreground">Chaque affirmation cite sa source : E = événement, P = profil Tamtam (photo de 2024), W = web. Un angle sans source est retiré. Sans clé, tout est calculé, rien n'est rédigé.</p>
        </Block>

        <Block title="Limites à garder en tête">
          <ul className="list-disc space-y-1 pl-5">
            <li>Les signaux datent de l'export : plus il est ancien, plus il faut vérifier en début d'appel.</li>
            <li>L'onglet CRM ne contient pas les clients de Mirakl : les clients ne sont repérés que par les événements.</li>
            <li>Le profil Tamtam (stratégie, e-commerce) est une photo de 2024.</li>
          </ul>
        </Block>
      </div>
    </div>
  );
}
