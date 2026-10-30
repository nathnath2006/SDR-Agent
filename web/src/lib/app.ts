import { useEffect, useState } from "react";
import type { Account, Role } from "@/types";

// --- Navigation : #/page/param1/param2 -------------------------------------------
export type Page = "import" | "analyse" | "historique" | "doc" | "parametres";
const PAGES: Page[] = ["import", "analyse", "historique", "doc", "parametres"];

export interface Route {
  page: Page;
  params: string[];
}

function parse(): Route {
  const [page, ...params] = window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  return { page: PAGES.includes(page as Page) ? (page as Page) : "import", params };
}

export function useRoute(): Route {
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const onHash = () => setRoute(parse());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return route;
}

export const go = (page: Page, ...params: (string | number)[]) => {
  window.location.hash = `/${[page, ...params].join("/")}`;
};

// --- Apparence : mode et thème, propres à ce navigateur -----------------------------
export type Mode = "clair" | "sombre" | "systeme";
export type Theme = "neutre" | "bleu" | "vert" | "violet" | "orange";
export const THEMES: { id: Theme; label: string; swatch: string }[] = [
  { id: "neutre", label: "Neutre", swatch: "oklch(0.3 0 0)" },
  { id: "bleu", label: "Bleu", swatch: "oklch(0.55 0.2 260)" },
  { id: "vert", label: "Vert", swatch: "oklch(0.55 0.14 155)" },
  { id: "violet", label: "Violet", swatch: "oklch(0.55 0.2 295)" },
  { id: "orange", label: "Orange", swatch: "oklch(0.65 0.17 55)" },
];

function read<T extends string>(key: string, fallback: T): T {
  try {
    return (localStorage.getItem(key) as T) || fallback;
  } catch {
    return fallback;
  }
}

export function useAppearance() {
  const [mode, setMode] = useState<Mode>(() => read("tamtam-mode", "systeme"));
  const [theme, setTheme] = useState<Theme>(() => read("tamtam-theme", "neutre"));

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () =>
      document.documentElement.classList.toggle("dark", mode === "sombre" || (mode === "systeme" && media.matches));
    apply();
    media.addEventListener("change", apply);
    try { localStorage.setItem("tamtam-mode", mode); } catch { /* navigation privée */ }
    return () => media.removeEventListener("change", apply);
  }, [mode]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("tamtam-theme", theme); } catch { /* navigation privée */ }
  }, [theme]);

  return { mode, setMode, theme, setTheme };
}

// --- Formats ------------------------------------------------------------------------
const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];

export function frDate(iso: string): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

export function frDateTime(iso: string): string {
  return `${frDate(iso)}, ${iso.slice(11, 16).replace("-", ":")}`;
}

export function runDate(runId: string): string {
  const [day, time] = runId.split("_");
  return `${frDate(day)}, ${time.slice(0, 2)}:${time.slice(2, 4)}`;
}

export const ROLE_LABEL: Record<Role, string> = {
  déclencheur: "Déclencheur",
  amplificateur: "Amplificateur",
  contexte: "Contexte",
  bruit: "Bruit",
  client_mirakl: "Client Mirakl",
};

export function mainSignal(a: Account) {
  return (
    a.signaux.find((s) => s.role === "déclencheur" && s.fenetre !== "ancien") ??
    a.signaux.find((s) => s.role === "amplificateur" && s.fenetre !== "ancien") ??
    a.signaux.find((s) => s.role === "déclencheur") ??
    a.signaux.find((s) => s.role === "client_mirakl")
  );
}

export function matches(a: Account, query: string): boolean {
  if (!query) return true;
  const q = query.toLowerCase();
  return [a.compte, a.raison, a.pays, a.secteur, ...a.entites].some((x) => x?.toLowerCase().includes(q));
}
