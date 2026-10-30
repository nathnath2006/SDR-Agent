import { useState } from "react";
import { Check, Monitor, Moon, Sun } from "lucide-react";
import { api } from "@/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { PageHeader } from "@/components/blocks";
import { THEMES, type Mode, type Theme } from "@/lib/app";
import { cn } from "@/lib/utils";
import type { LlmProvider, LlmSettings } from "@/types";

const NAMES: Record<LlmProvider, string> = { gemini: "Gemini (Google)", anthropic: "Anthropic (Claude)" };

export function SettingsPage({ llm, onSaved, mode, setMode, theme, setTheme }: {
  llm: LlmSettings;
  onSaved: (s: LlmSettings) => void;
  mode: Mode;
  setMode: (m: Mode) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
}) {
  return (
    <div className="max-w-3xl space-y-6">
      <PageHeader title="Paramètres" />
      <LlmCard llm={llm} onSaved={onSaved} />
      <Card>
        <CardHeader>
          <CardTitle>Apparence</CardTitle>
          <CardDescription>Propre à ce navigateur.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <Label>Mode</Label>
            <ToggleGroup type="single" variant="outline" value={mode} onValueChange={(v) => v && setMode(v as Mode)}>
              <ToggleGroupItem value="clair"><Sun />Jour</ToggleGroupItem>
              <ToggleGroupItem value="sombre"><Moon />Nuit</ToggleGroupItem>
              <ToggleGroupItem value="systeme"><Monitor />Système</ToggleGroupItem>
            </ToggleGroup>
          </div>
          <div className="space-y-2">
            <Label>Thème</Label>
            <div className="flex flex-wrap gap-2">
              {THEMES.map((t) => (
                <button key={t.id} onClick={() => setTheme(t.id)}
                        className={cn("flex items-center gap-2 rounded-lg border px-3 py-2 text-sm", theme === t.id && "border-primary ring-1 ring-primary")}>
                  <span className="size-4 rounded-full" style={{ background: t.swatch }} />
                  {t.label}
                  {theme === t.id && <Check className="size-3.5" />}
                </button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function LlmCard({ llm, onSaved }: { llm: LlmSettings; onSaved: (s: LlmSettings) => void }) {
  const [provider, setProvider] = useState<LlmProvider>(llm.provider ?? "gemini");
  const [key, setKey] = useState("");
  const [model, setModel] = useState(llm.providers[provider].model);
  const [state, setState] = useState<{ kind: "idle" | "busy" | "ok" | "error"; text?: string }>({ kind: "idle" });
  const current = llm.providers[provider];
  const canSave = Boolean(key || current.key_set);

  const choose = (p: LlmProvider) => {
    setProvider(p);
    setModel(llm.providers[p].model);
    setKey("");
    setState({ kind: "idle" });
  };

  const save = async (test: boolean) => {
    setState({ kind: "busy" });
    try {
      onSaved(await api.saveSettings({ provider, api_key: key || undefined, model }));
      setKey("");
      if (test) {
        const r = await api.testSettings();
        setState({ kind: "ok", text: `Clé valide, modèle ${r.model}.` });
      } else {
        setState({ kind: "ok", text: "Enregistré." });
      }
    } catch (e) {
      setState({ kind: "error", text: (e as Error).message });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Modèle et clé API</CardTitle>
        <CardDescription>Le LLM rédige les raisons et les fiches d'appel et vérifie le web. Il ne décide ni du statut ni du palier.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <RadioGroup value={provider} onValueChange={(v) => choose(v as LlmProvider)} className="grid gap-2 sm:grid-cols-2">
          {(Object.keys(NAMES) as LlmProvider[]).map((p) => (
            <Label key={p} htmlFor={p} className={cn("flex cursor-pointer items-center gap-3 rounded-lg border p-3 font-normal", provider === p && "border-primary")}>
              <RadioGroupItem id={p} value={p} />
              <span className="flex-1">
                <span className="block font-medium">{NAMES[p]}</span>
                <span className="text-xs text-muted-foreground">{llm.providers[p].key_set ? `clé enregistrée (${llm.providers[p].key_hint})` : "pas de clé"}</span>
              </span>
            </Label>
          ))}
        </RadioGroup>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="model">Modèle</Label>
            <Input id="model" value={model} onChange={(e) => setModel(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="key">Clé API</Label>
            <Input id="key" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)}
                   placeholder={current.key_set ? "laisser vide pour garder la clé actuelle" : "coller la clé"} />
          </div>
        </div>
        <p className="text-xs text-muted-foreground">La clé est écrite dans le fichier .env de ce dossier, jamais versionné ni affiché en clair.</p>
      </CardContent>
      <CardFooter className="gap-2 border-t">
        <Button onClick={() => save(true)} disabled={!canSave || state.kind === "busy"}>Enregistrer et tester</Button>
        <Button variant="outline" onClick={() => save(false)} disabled={!canSave || state.kind === "busy"}>Enregistrer</Button>
        <span className={cn("ml-2 text-sm", state.kind === "error" && "text-destructive", state.kind === "ok" && "text-tier-a")}>
          {state.kind === "busy" ? "Vérification…" : state.text}
        </span>
      </CardFooter>
    </Card>
  );
}
