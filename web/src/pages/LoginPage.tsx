import { useState } from "react";
import { api } from "@/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.login(password);
      onLogin();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-svh items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div className="mb-2 flex size-8 items-center justify-center rounded-md bg-foreground text-background"><span className="font-display">M</span></div>
          <CardTitle className="font-display text-3xl leading-none">TAM Mirakl</CardTitle>
          <CardDescription>Agent de priorisation. Entre le mot de passe de l'équipe.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="password">Mot de passe</Label>
              <Input id="password" type="password" autoFocus autoComplete="current-password" value={password}
                     onChange={(e) => setPassword(e.target.value)} />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="bg-brand-yellow text-[#1c1c1c] hover:bg-brand-yellow/85 w-full" disabled={busy || !password}>{busy ? "Connexion…" : "Se connecter"}</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
