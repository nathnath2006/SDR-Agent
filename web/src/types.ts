// Formes renvoyées par l'API Python (src/tamtam_agent/api.py).

export type Role = "déclencheur" | "amplificateur" | "contexte" | "bruit" | "client_mirakl";
export type Status = "qualifié" | "à creuser" | "disqualifié";
export type Tier = "A" | "B" | "C" | "D" | "-";
export type FitLevel = "dans" | "incertain" | "hors";
export type LlmProvider = "gemini" | "anthropic";

export interface Signal {
  event_id: string;
  date: string;
  age_jours: number;
  fenetre: "récent" | "moyen" | "ancien";
  type: string;
  detail: string;
  libelle: string;
  role: Role;
  nature: string;
  raison: string;
  regle: string;
  origine: string;
}

export interface FitItem {
  niveau: FitLevel;
  detail: string;
  regle: string;
}

export interface Pitch {
  pourquoi_maintenant: string;
  ce_qui_a_change: string;
  axes: { besoin: string; produit: string; argument: string; sources: string[] }[];
  a_verifier: string[];
}

export interface WebCheck {
  marketplace: "existante" | "aucune" | "inconnu";
  detail: string;
  technologie: string;
  anciennete: string;
  sources: { url: string; fait?: string; titre?: string }[];
  sources_outil: { url: string; fait?: string; titre?: string }[];
  statut: string;
}

export interface Account {
  groupe_id: number;
  compte: string;
  rang: number;
  rang_top: number | null;
  a_qualifier: boolean;
  statut: Status;
  palier: Tier;
  regle_palier: string;
  motif: string;
  liste: string;
  pays: string;
  secteur: string;
  taille: string;
  profils_linkedin: number | null;
  site: string;
  entites: string[];
  fusion: string;
  raison: string;
  confiance: "haute" | "moyenne" | "basse";
  evolution: string;
  dernier_signal: string;
  fit: { secteur: FitItem; geographie: FitItem; taille: FitItem };
  signaux: Signal[];
  verification_web: WebCheck | null;
  argumentaire: Pitch | null;
  a_verifier: string[];
  incertitudes: string[];
  evolution_mp: Evolution | null;
}

/** Évolution vers une marketplace depuis l'analyse précédente (option au lancement). */
export interface Evolution {
  verdict: "nette" | "faible" | "aucune";
  explication: string;
  sources: string[];
  confiance: "haute" | "moyenne" | "basse";
  base_run: string;
  base_extraction: string;
  date: string | null;
}

export interface Limits {
  fraicheur: { extraction: string; traitement: string; jours: number };
  crm: string[];
  fusions: string[];
  pays: string[];
  tailles: string[];
  evenements: string;
  groupes: string;
}

export interface RunMeta {
  run_id: string;
  source: string;
  extraction: string;
  traitement: string;
  llm: string;
  explique: boolean;
  fraicheur_jours: number;
  top: number;
  groupes: number;
  top_ids: number[];
  statuts: Record<Status, number>;
  paliers_top: Record<"A" | "B" | "C", number>;
  evolution?: { base: string | null; message?: string; extraction_base?: string; evalues?: number; nette?: number; faible?: number } | null;
  limites?: Limits;
  entres?: string[];
  sortis_top?: string[];
}

export interface RunData {
  meta: RunMeta;
  accounts: Account[];
}

/** Listes exportables d'une analyse (voir outputs.EXPORT_LISTS). */
export type ExportList = "top" | "tous" | "surveiller" | "clients";

export interface Count {
  label: string;
  n: number;
}

export interface GroupSuggestion {
  id: string;
  type: "doublon" | "groupe";
  motifs: string[];
  entites: { id: number; nom: string; pays: string; site: string; secteur: string; taille: string; linkedin: number | null }[];
}

export interface Inspection {
  feuilles: { nom: string; lignes: number; colonnes: string[]; valeurs: (string | number | boolean | null)[][] }[];
  stats: {
    prospects: number;
    evenements: number;
    comptes_avec_evenement: number;
    periode: { debut: string; fin: string };
    evenements_par_type: Count[];
    evenements_par_detail: { type: string; detail: string; n: number }[];
    evenements_par_mois: { mois: string; n: number }[];
    comptes_par_region: Count[];
    comptes_par_pays: Count[];
    comptes_par_secteur: Count[];
    comptes_par_taille: Count[];
  };
  qualite: {
    regroupements: GroupSuggestion[];
    pays: { id: number; nom: string; declare: string; probable: string; note: string }[];
    champs_vides: Record<string, number>;
    evenements_orphelins: number;
    ignore: { feuille: string; colonnes: string[]; lignes: number }[];
  };
}

export interface ImportSummary {
  id: string;
  fichier: string;
  importe_le: string;
  valide: boolean;
  validation?: { decisions: Record<string, boolean>; valide_le: string };
}

export interface ImportDetail extends ImportSummary {
  inspection: Inspection;
}

export interface Config {
  models: Record<LlmProvider, string>;
  rules: { recent_days: number; max_days: number; size_min: number; size_max: number; top_n: number };
}

export interface Job {
  state: "idle" | "running" | "done" | "error";
  message: string;
  run: string | null;
  import_id: string | null;
  logs: string[];
  started: string | null;
}
