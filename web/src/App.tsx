import { useCallback, useEffect, useState } from "react";
import { BookOpen, History, ListOrdered, LogOut, Moon, Settings, Sun, Upload } from "lucide-react";
import { UNAUTHORIZED, api } from "@/api";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarHeader, SidebarInset,
  SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarProvider, SidebarTrigger,
} from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { go, useAppearance, useLlm, useRoute, type Page } from "@/lib/app";
import { AnalysePage } from "@/pages/AnalysePage";
import { DocPage } from "@/pages/DocPage";
import { HistoryPage } from "@/pages/HistoryPage";
import { ImportPage } from "@/pages/ImportPage";
import { LoginPage } from "@/pages/LoginPage";
import { SettingsPage } from "@/pages/SettingsPage";
import type { Config, RunMeta } from "@/types";

const NAV: { page: Page; label: string; icon: typeof Upload }[] = [
  { page: "import", label: "Import", icon: Upload },
  { page: "analyse", label: "Analyse", icon: ListOrdered },
  { page: "historique", label: "Historique", icon: History },
  { page: "doc", label: "Documentation", icon: BookOpen },
];

export default function App() {
  const route = useRoute();
  const appearance = useAppearance();
  const { llm } = useLlm();
  const [config, setConfig] = useState<Config | null>(null);
  const [runs, setRuns] = useState<RunMeta[]>([]);
  const [error, setError] = useState("");
  const [auth, setAuth] = useState<{ protege: boolean; connecte: boolean } | null>(null);

  const loadRuns = useCallback(() => api.runs().then(setRuns), []);
  const load = useCallback(async () => {
    try {
      const s = await api.session();
      setAuth(s);
      if (!s.connecte) return;
      setConfig(await api.config());
      await loadRuns();
    } catch (e) {
      setError(`API injoignable (${(e as Error).message}). Lance « tamtam-agent serve ».`);
    }
  }, [loadRuns]);
  useEffect(() => {
    load();
    const onUnauthorized = () => setAuth((a) => (a ? { ...a, connecte: false } : a));
    window.addEventListener(UNAUTHORIZED, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED, onUnauthorized);
  }, [load]);
  const logout = async () => {
    await api.logout();
    setConfig(null);
    setAuth({ protege: true, connecte: false });
  };

  const dark = appearance.mode === "sombre" ||
    (appearance.mode === "systeme" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  const toggleDark = () => appearance.setMode(dark ? "clair" : "sombre");

  if (error) return <div className="p-8 text-sm text-destructive">{error}</div>;
  if (auth && !auth.connecte) return <LoginPage onLogin={load} />;
  if (!config) return <div className="p-8 text-sm text-muted-foreground">Chargement…</div>;

  const [p0, p1] = route.params;
  return (
    <TooltipProvider>
      <SidebarProvider>
        <Sidebar collapsible="icon">
          <SidebarHeader>
            <div className="flex items-center gap-2 px-2 py-1.5">
              <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-foreground text-background">
                <span className="font-display text-sm">M</span>
              </div>
              <div className="leading-tight group-data-[collapsible=icon]:hidden">
                <p className="font-display text-lg leading-none">TAM Mirakl</p>
                <p className="text-xs text-muted-foreground">Agent SDR</p>
              </div>
            </div>
          </SidebarHeader>
          <SidebarContent>
            <SidebarGroup>
              <SidebarGroupContent>
                <SidebarMenu>
                  {NAV.map(({ page, label, icon: Icon }) => (
                    <SidebarMenuItem key={page}>
                      <SidebarMenuButton isActive={route.page === page} tooltip={label} onClick={() => go(page)}>
                        <Icon /><span>{label}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          </SidebarContent>
          <SidebarFooter>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton isActive={route.page === "parametres"} tooltip="Paramètres" onClick={() => go("parametres")}>
                  <Settings /><span>Paramètres</span>
                  {!llm && <span className="ml-auto size-2 rounded-full bg-brand-yellow ring-1 ring-black/20" title="Pas de clé LLM" />}
                </SidebarMenuButton>
              </SidebarMenuItem>
              {auth?.protege && (
                <SidebarMenuItem>
                  <SidebarMenuButton tooltip="Se déconnecter" onClick={logout}><LogOut /><span>Se déconnecter</span></SidebarMenuButton>
                </SidebarMenuItem>
              )}
            </SidebarMenu>
          </SidebarFooter>
        </Sidebar>

        <SidebarInset>
          <header className="flex h-12 shrink-0 items-center gap-2 border-b px-4">
            <SidebarTrigger className="-ml-1" />
            <Separator orientation="vertical" className="mr-2 data-[orientation=vertical]:h-4" />
            <span className="text-sm text-muted-foreground">
              {route.page === "parametres" ? "Paramètres" : NAV.find((n) => n.page === route.page)?.label}
            </span>
            <Button variant="ghost" size="icon" className="ml-auto" onClick={toggleDark} aria-label="Basculer jour / nuit">
              {dark ? <Sun /> : <Moon />}
            </Button>
          </header>
          <main className="mx-auto w-full max-w-7xl flex-1 p-4 md:p-6">
            {route.page === "import" && <ImportPage importId={p0} onImportsChanged={() => undefined} />}
            {route.page === "analyse" && <AnalysePage runId={p0} accountId={p1} latestRun={runs[0]?.run_id} onRunsChanged={loadRuns} />}
            {route.page === "historique" && <HistoryPage runs={runs} />}
            {route.page === "doc" && <DocPage rules={config.rules} />}
            {route.page === "parametres" && (
              <SettingsPage models={config.models} {...appearance} />
            )}
          </main>
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  );
}
