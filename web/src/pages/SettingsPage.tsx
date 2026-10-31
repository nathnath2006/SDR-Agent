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
import { THEMES, maskKey, useLlm, type Mode, type Theme } from "@/lib/app";
import { cn } from "@/lib/utils";
import type { Config, LlmProvider } from "@/types";

const NAMES: Record<LlmProvider, string> = { gemini: "Gemini (Google)", anthropic: "Anthropic (Claude)" };

export function SettingsPage({ models, mode, setMode, theme, setTheme }: {
  models: Config["models"];
  mode: Mode;
  setMode: (m: Mode) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
}) {
  return (
    <div className="max-w-3xl space-y-6">
      <PageHeader title="Paramètres" />
      <LlmCard models={models} />
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
                        className={cn("flex items-center gap-2 rounded-lg border bg-card px-3 py-2 text-sm", theme === t.id && "border-foreground ring-1 ring-foreground")}>
                  <span className="size-4 rounded-full ring-1 ring-black/10" style={{ background: t.swatch }} />
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

/** Chaque utilisateur apporte sa clé : elle reste dans ce navigateur. */
function LlmCard({ models }: { models: Config["models"] }) {
  const { llm, save } = useLlm();
  const [provider, setProvider] = useState<LlmProvider>(llm?.provider ?? "gemini");
  const [model, setModel] = useState(llm?.model ?? models[provider]);
  const [key, setKey] = useState("");
  const [state, setState] = useState<{ kind: "idle" | "busy" | "ok" | "error"; text?: string }>({ kind: "idle" });
  const sameProvider = llm?.provider === provider;
  const effectiveKey = key || (sameProvider ? llm?.api_key ?? "" : "");

  const choose = (p: LlmProvider) => {
    setProvider(p);
    setModel(llm?.provider === p ? llm.model : models[p]);
    setKey("");
    setState({ kind: "idle" });
  };

  const submit = async () => {
    const choice = { provider, model: model || models[provider], api_key: effectiveKey };
    setState({ kind: "busy" });
    try {
      const r = await api.testLlm(choice);
      save(choice);
      setKey("");
      setState({ kind: "ok", text: `Clé valide, modèle ${r.model}. Enregistrée dans ce navigateur.` });
    } catch (e) {
      setState({ kind: "error", text: (e as Error).message });
    }
  };

  const forget = () => {
    save(null);
    setKey("");
    setState({ kind: "ok", text: "Clé oubliée par ce navigateur." });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Ta clé API</CardTitle>
        <CardDescription>
          Chacun utilise sa propre clé. Elle reste dans ton navigateur et n'est envoyée qu'avec tes analyses : le serveur ne la conserve pas.
          Sans clé, le Top 20 est calculé mais aucun texte n'est rédigé.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <RadioGroup value={provider} onValueChange={(v) => choose(v as LlmProvider)} className="grid gap-2 sm:grid-cols-2">
          {(Object.keys(NAMES) as LlmProvider[]).map((p) => (
            <Label key={p} htmlFor={p} className={cn("flex cursor-pointer items-center gap-3 rounded-lg border bg-card p-3 font-normal", provider === p && "border-foreground")}>
              <RadioGroupItem id={p} value={p} />
              <span className="flex-1">
                <span className="block font-medium">{NAMES[p]}</span>
                <span className="text-xs text-muted-foreground">
                  {llm?.provider === p ? `clé enregistrée (${maskKey(llm.api_key)})` : "pas de clé"}
                </span>
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
                   placeholder={sameProvider && llm ? "laisser vide pour garder ta clé" : "coller ta clé"} />
          </div>
        </div>
      </CardContent>
      <CardFooter className="flex-wrap gap-2 border-t">
        <Button className="bg-brand-yellow text-[#1c1c1c] hover:bg-brand-yellow/85" onClick={submit} disabled={!effectiveKey || state.kind === "busy"}>Tester et enregistrer</Button>
        {llm && <Button variant="outline" onClick={forget}>Oublier ma clé</Button>}
        <span className={cn("ml-2 text-sm", state.kind === "error" && "text-destructive", state.kind === "ok" && "text-why-green")}>
          {state.kind === "busy" ? "Vérification…" : state.text}
        </span>
      </CardFooter>
    </Card>
  );
}
