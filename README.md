# SDR Agent

Outil de priorisation de prospects. À partir d'un export Tamtam (prospects et événements), il produit la liste des 20 comptes à contacter en priorité pour Mirakl, avec la raison de chaque choix. Il peut être relancé à chaque nouvel export au même format.

## Installation

Prérequis : Python 3.11 ou plus, Node 20 ou plus.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[api,anthropic,gemini,dev]"
cd web && npm install && npm run build && cd ..
.venv/bin/tamtam-agent serve   # http://localhost:8000
```

Avec Docker :

```bash
docker build -t tamtam-agent .
docker run -p 8000:8000 -v "$PWD/data:/app/data" -v "$PWD/outputs:/app/outputs" tamtam-agent
```

Les volumes `data` et `outputs` conservent les imports et les analyses entre deux lancements. Le modèle sémantique (environ 220 Mo) est téléchargé à la construction de l'image ; en local, il l'est à la première analyse, dans `.cache/models/`.

Les données du cas ne sont pas incluses dans le dépôt. Le fichier Excel s'importe depuis l'interface, ou se place dans `data/mirakl_case_data.xlsx` pour la ligne de commande et les tests.

## Utilisation

1. **Paramètres** : saisir une clé API Gemini ou Anthropic. La clé est conservée dans le navigateur et n'est pas stockée sur le serveur.
2. **Import** : charger l'export, vérifier les statistiques, puis valider les doublons et les groupes proposés.
3. **Analyse** : lancer l'analyse sur un import validé. Chaque compte du Top 20 ouvre une fiche détaillée.
4. **Historique** : consulter les analyses précédentes et les changements d'une analyse à l'autre.
5. **Documentation** : description des règles appliquées.

Sans clé API, les statuts, les paliers et le Top 20 sont calculés, mais aucun texte n'est rédigé.

Ligne de commande : `.venv/bin/tamtam-agent run --data export.xlsx` (clé lue dans `.env`, voir `.env.example`).

## Règles

- **Statut** : qualifié, à creuser ou disqualifié, selon le secteur, la zone et la taille déclarée.
- **Signaux** : chaque événement reçoit un rôle (déclencheur, amplificateur, contexte, client Mirakl, bruit) par des règles à mots-clés. Un modèle d'embeddings local et gratuit (`paraphrase-multilingual-MiniLM-L12-v2`, via `fastembed`) relit ensuite chaque texte et corrige les cas nets ; chaque signal reclassé est marqué « à relire ».
- **Palier** : A, B, C ou D, selon la présence d'un signal d'intention, son ancienneté (moins de 90 ou de 180 jours) et l'existence de signaux qui le renforcent.
- **Top 20** : paliers A, puis B, complétés par les meilleurs comptes C (marqués « à qualifier »). Aucun compte disqualifié.
- **Évolutions** (option au lancement) : chaque compte est comparé à la dernière analyse d'un export plus ancien. Le modèle juge si les signaux nouveaux montrent une évolution vers une marketplace : une évolution nette compte comme un déclencheur, une évolution faible comme un amplificateur.

Sans l'option, les règles et le modèle sémantique déterminent seuls le classement, sans LLM. Le LLM (Gemini ou Anthropic) sert alors uniquement à traduire les événements, rédiger les explications et vérifier certaines informations sur le web. Les seuils sont définis dans `src/tamtam_agent/config.py`.

## Structure

```
src/tamtam_agent/
  config.py       seuils et listes (fenêtres de 90 et 180 jours, taille, secteurs, zones)
  load.py         lecture du fichier Excel
  importer.py     import : aperçu des feuilles, statistiques, validation
  clean.py        doublons, groupes, pays incohérents
  icp.py          statut (secteur, zone, taille)
  signals.py      rôle de chaque événement (règles)
  semantic.py     relecture des rôles par le modèle sémantique local
  tiers.py        palier A, B, C ou D
  agent.py        enchaînement des étapes et construction du Top 20
  enrich.py       textes rédigés par le modèle et vérification web
  evolution.py    option évolutions : comparaison avec l'analyse précédente
  memory.py       comparaison entre analyses
  outputs.py      écriture des fichiers de sortie
  settings.py     clé et modèle pour la ligne de commande (.env)
  llm/            clients Gemini et Anthropic
  api.py          API FastAPI et service de l'interface
  cli.py          commandes run et serve
web/src/
  pages/          Import, Analyse, Historique, Documentation, Paramètres
  components/     tableaux, fiches et blocs d'interface
  lib/            navigation, apparence, clé API du navigateur
tests/            règles, cas de référence, import, API
Dockerfile        image de l'application (API et interface)

data/imports/<id>/    fichier importé, inspection, validation
outputs/runs/<id>/    une analyse : top20.md, tam_priorise.xlsx et .csv, explications.jsonl, meta.json
outputs/memoire.csv   suivi des comptes d'une analyse à l'autre
```

## Déploiement

L'application est conteneurisée (`Dockerfile`) et peut être déployée sur Google Cloud Run :

```bash
gcloud run deploy sdr-agent --source . --region europe-west1 --allow-unauthenticated \
  --min-instances 0 --max-instances 1 --no-cpu-throttling --memory 1Gi --timeout 3600 \
  --set-secrets APP_PASSWORD=app-password:latest --set-env-vars TAMTAM_STORE=/mnt/store \
  --add-volume name=store,type=cloud-storage,bucket=BUCKET \
  --add-volume-mount volume=store,mount-path=/mnt/store
```

- `APP_PASSWORD` (Secret Manager) protège l'accès à l'application.
- `TAMTAM_STORE` pointe vers un bucket Cloud Storage qui conserve les imports et les analyses.
- Aucune clé API n'est stockée côté serveur.

## Développement

- Interface avec rechargement à chaud : `tamtam-agent serve`, puis `cd web && npm run dev` (http://localhost:5173).
- Tests : `.venv/bin/pytest`.
