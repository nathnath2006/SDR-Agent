import { useEffect, useState } from "react";
import type { Account, LlmProvider, Role } from "@/types";

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
export type Theme = "tamtam" | "bleu" | "nuit" | "violet" | "orange";
export const THEMES: { id: Theme; label: string; swatch: string }[] = [
  { id: "tamtam", label: "Tamtam", swatch: "#1c1c1c" },
  { id: "bleu", label: "Bleu", swatch: "#0c31c1" },
  { id: "nuit", label: "Bleu nuit", swatch: "#0c1c5a" },
  { id: "violet", label: "Violet", swatch: "#8a4fe0" },
  { id: "orange", label: "Orange", swatch: "#f18101" },
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
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = read<Theme>("tamtam-theme", "tamtam");
    return THEMES.some((t) => t.id === stored) ? stored : "tamtam";
  });

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

// --- Clé LLM de l'utilisateur : gardée dans ce navigateur, envoyée seulement avec ses analyses ---
export interface LlmChoice {
  provider: LlmProvider;
  model: string;
  api_key: string;
}

const LLM_KEY = "tamtam-llm";

export function readLlm(): LlmChoice | null {
  try {
    const raw = localStorage.getItem(LLM_KEY);
    const v = raw ? (JSON.parse(raw) as LlmChoice) : null;
    return v?.api_key ? v : null;
  } catch {
    return null;
  }
}

export function useLlm() {
  const [llm, setLlm] = useState<LlmChoice | null>(readLlm);
  useEffect(() => {
    const onChange = () => setLlm(readLlm());
    window.addEventListener("tamtam-llm-change", onChange);
    window.addEventListener("storage", onChange);
    return () => {
      window.removeEventListener("tamtam-llm-change", onChange);
      window.removeEventListener("storage", onChange);
    };
  }, []);
  const save = (value: LlmChoice | null) => {
    try {
      if (value) localStorage.setItem(LLM_KEY, JSON.stringify(value));
      else localStorage.removeItem(LLM_KEY);
    } catch { /* navigation privée : la clé ne sera pas mémorisée */ }
    setLlm(value);
    window.dispatchEvent(new Event("tamtam-llm-change"));
  };
  return { llm, save };
}

export function maskKey(key: string): string {
  return key.length > 8 ? `…${key.slice(-4)}` : "définie";
}
