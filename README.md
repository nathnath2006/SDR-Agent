# tamtam-agent

Agent qui transforme l'export Tamtam (prospects + événements) en **Top 20 des comptes à appeler, et pourquoi maintenant**, pour l'équipe sales de Mirakl. Relançable à chaque nouvel export au même format.

## Lancer

Première installation (Python ≥ 3.11, Node ≥ 20) :

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[api,anthropic,gemini,dev]"
cd web && npm install && npm run build && cd ..
```

Puis :

```bash
.venv/bin/tamtam-agent serve        # http://localhost:8000
```

L'export Tamtam du cas n'est pas versionné (données du cas). Dépose-le via l'onglet Import, ou dans `data/mirakl_case_data.xlsx` pour la ligne de commande et les tests.

Avec Docker :

```bash
docker build -t tamtam-agent .
docker run -p 8000:8000 --env-file .env -v "$PWD/data:/app/data" -v "$PWD/outputs:/app/outputs" tamtam-agent
```

## Le parcours

1. **Paramètres** : ta clé API (Gemini ou Anthropic) et le modèle, mode jour / nuit, thème. **Chacun apporte sa clé** : elle reste dans son navigateur et n'est envoyée qu'avec ses analyses ; le serveur ne la stocke pas.
2. **Import** : dépose l'export. Contrôle les feuilles, les chiffres (événements par type et détail, période, régions, tailles, secteurs), les pays suspects et ce qui a été ignoré ; **valide les doublons et groupes** (fusionner ou garder séparés).
3. **Analyse** : lance l'agent sur l'import validé. Il sort le Top 20 ; un clic sur un compte ouvre sa fiche (pourquoi maintenant, angles d'approche, points à vérifier, signaux, fit).
4. **Historique** : chaque analyse, la composition de son Top 20 et les comptes entrés ou sortis depuis la précédente.
5. **Documentation** : les règles expliquées simplement.

Sans clé LLM, tout est calculé (statuts, paliers, Top 20) mais aucun texte n'est rédigé.

En ligne de commande, sans interface : `.venv/bin/tamtam-agent run --data export.xlsx` (tous les regroupements fusionnés ; clé lue dans `.env`, voir `.env.example`).

## Les règles en bref

- **Statut** (fit) : qualifié / à creuser / disqualifié, d'après secteur, zone et taille. La **bande de taille déclarée fait foi** ; LinkedIn ne fait que confirmer.
- **Palier** (timing) : A = signal d'intention marketplace de moins de 90 jours renforcé ; B = signal de moins de 90 jours seul, ou de moins de 180 jours renforcé ; C = contexte favorable sans intention, ou signal ancien ; D = rien.
- **Top 20** : paliers A, puis B, **complétés par les meilleurs C** (signal le plus récent d'abord), jamais un disqualifié. Les C sont marqués « à qualifier ».
- **Les règles décident seules** : même export, même Top 20. Le LLM traduit, rédige les raisons et fiches (chaque affirmation sourcée) et vérifie le web.

Seuils et listes : `src/tamtam_agent/config.py`. Décisions détaillées : note `Grill - Détection d'opportunité` (vault Obsidian).

## Structure

```
src/tamtam_agent/
  config.py     seuils et règles (fenêtres 90 / 180 j, taille, secteurs, zones)
  load.py       lecture de l'Excel (ignore les colonnes et tableaux ajoutés à la main)
  importer.py   import : aperçu des feuilles, statistiques, regroupements proposés
  clean.py      doublons, groupes, pays suspects
  icp.py        statut
  signals.py    rôle de chaque événement (règles) ; traduction par le LLM
  tiers.py      palier A / B / C / D
  agent.py      enchaîne les étapes, construit le Top 20
  enrich.py     textes rédigés par le LLM : raisons, fiches, vérification web
  memory.py     comparaison d'une analyse à l'autre
  outputs.py    fichiers de sortie
  settings.py   clé et modèle LLM (.env)
  llm/          Gemini et Anthropic derrière une même interface (cache .cache/llm/)
  api.py, cli.py
web/src/        front React + TypeScript (shadcn/ui, Tailwind, Recharts)
  pages/        Import, Analyse, Historique, Documentation, Paramètres
tests/          règles, cas de référence du handoff, import, API

data/imports/<id>/          fichier importé, inspection, validation du SDR
outputs/runs/<id>/          une analyse : top20.md, tam_priorise.xlsx/.csv, explications.jsonl, meta.json
outputs/memoire.csv         une ligne par entreprise, comparée d'une analyse à l'autre
```

## Déploiement Cloud Run

L'image Docker tourne telle quelle sur Google Cloud Run. Configuration utilisée :

| Élément | Réglage |
|---|---|
| Accès | `APP_PASSWORD` (Secret Manager) : écran de connexion, cookie de session ; toute l'API est fermée sans lui |
| Données | bucket Cloud Storage monté sur `/mnt/store`, `TAMTAM_STORE=/mnt/store` (imports, analyses, historique) |
| Instances | une seule (`--max-instances 1`), éteinte au repos (`--min-instances 0`), CPU gardé pendant l'analyse (`--no-cpu-throttling`) |
| Clé LLM | aucune côté serveur : chaque utilisateur apporte la sienne |

```bash
PROJECT=mon-projet; BUCKET=$PROJECT-data
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com storage.googleapis.com --project $PROJECT
gcloud storage buckets create gs://$BUCKET --project $PROJECT --location europe-west1 \
  --uniform-bucket-level-access --public-access-prevention
printf 'mot-de-passe' | gcloud secrets create app-password --project $PROJECT --data-file=-
# Donner au compte de service de Cloud Run : secretmanager.secretAccessor (secret),
# storage.objectAdmin (bucket), run.builder (projet).
gcloud run deploy sdr-agent --source . --project $PROJECT --region europe-west1 \
  --allow-unauthenticated --execution-environment gen2 \
  --min-instances 0 --max-instances 1 --no-cpu-throttling --memory 1Gi --timeout 3600 \
  --set-secrets APP_PASSWORD=app-password:latest --set-env-vars TAMTAM_STORE=/mnt/store \
  --add-volume name=store,type=cloud-storage,bucket=$BUCKET --add-volume-mount volume=store,mount-path=/mnt/store
```

`.gcloudignore` garde `.env`, `data/` et `outputs/` hors du build. Pour changer le mot de passe : ajouter une version au secret `app-password`, puis `gcloud run services update sdr-agent`.

## Développement

- Front avec rechargement à chaud : `tamtam-agent serve` dans un terminal, `cd web && npm run dev` dans un autre (http://localhost:5173).
- Tests : `.venv/bin/pytest`.
