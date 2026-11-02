"""Règles métier et seuils de l'agent.

Tout ce qui décide d'un statut ou d'un palier vit ici, en clair, pour rester
auditable (voir le handoff, décisions D1 à D14). Le code applique ces règles ;
il n'en invente pas.
"""

from __future__ import annotations

# --- Récence (D12) : mesurée par rapport à la date d'extraction -------------
WINDOW_RECENT_DAYS = 90    # palier A / B
WINDOW_MAX_DAYS = 180      # au-delà, le signal est "ancien" : visible, ne classe plus

# --- Couche sémantique (semantic.py) -------------------------------------------
SEMANTIC_PROMOTE = 0.65   # le modèle renforce un rôle à partir de ce score
SEMANTIC_DEMOTE = 0.75    # il rétrograde un déclencheur en bruit à partir de ce score

# --- Taille (D1) -------------------------------------------------------------
SIZE_MIN = 100
SIZE_MAX = 1500

# Bandes LinkedIn -> (min, max). None = pas de borne haute.
SIZE_BANDS: dict[str, tuple[int, int | None]] = {
    "Myself Only": (1, 1),
    "1-10": (1, 10),
    "11-50": (11, 50),
    "51-200": (51, 200),
    "201-500": (201, 500),
    "501-1000": (501, 1000),
    "1001-5000": (1001, 5000),
    "5001-10,000": (5001, 10000),
    "10,001+": (10001, None),
}

# --- Géographie (D1) ---------------------------------------------------------
GEO_PRIORITY_1 = {"France", "Germany", "Austria", "Switzerland"}
EUROPE = GEO_PRIORITY_1 | {
    "United Kingdom", "Spain", "Italy", "Belgium", "Netherlands", "Luxembourg",
    "Ireland", "Portugal", "Denmark", "Sweden", "Norway", "Finland", "Poland",
    "Czech Republic", "Czechia", "Romania", "Hungary", "Greece", "Slovakia",
    "Slovenia", "Croatia", "Bulgaria", "Estonia", "Latvia", "Lithuania",
    "Liechtenstein",
}
US = {"United States"}

# Domaine national -> pays, pour repérer un pays déclaré suspect.
CCTLD_COUNTRY = {
    "de": "Germany", "at": "Austria", "ch": "Switzerland", "fr": "France",
    "es": "Spain", "it": "Italy", "be": "Belgium", "nl": "Netherlands",
    "uk": "United Kingdom", "ie": "Ireland", "dk": "Denmark", "se": "Sweden",
    "pl": "Poland", "us": "United States", "ca": "Canada", "uy": "Uruguay",
    "ge": "Georgia", "au": "Australia", "ro": "Romania", "pt": "Portugal",
}
# Forme juridique -> pays plausibles.
LEGAL_FORM_COUNTRIES = {
    "gmbh": {"Germany", "Austria", "Switzerland"},
    "ag": {"Germany", "Austria", "Switzerland"},
    "kg": {"Germany", "Austria"},
    "sas": {"France"},
    "sarl": {"France"},
}

# --- Secteur (D1) ------------------------------------------------------------
# "cible" : dans l'ICP. "adjacent" : biens de conso ou cas ambigu, à juger
# (LLM si disponible, sinon "à creuser"). Tout le reste : hors secteur.
SECTOR_TARGET = {
    "Retail", "Wholesale", "Retail Apparel and Fashion",
    "Online and Mail Order Retail", "Wholesale Building Materials",
    "Retail Luxury Goods and Jewelry", "Retail Office Equipment",
    "Retail Furniture and Home Furnishings", "Retail Groceries",
    "Food and Beverage Retail", "Consumer Goods", "Sporting Goods",
    "Apparel & Fashion", "Furniture", "Consumer Electronics",
}
SECTOR_ADJACENT = {
    "Food and Beverage Manufacturing", "Textile Manufacturing",
    "Sporting Goods Manufacturing", "Dairy Product Manufacturing", "Dairy",
    "Personal Care Product Manufacturing", "Food & Beverages",
    "Appliances, Electrical, and Electronics Manufacturing",
    "Computers and Electronics Manufacturing", "Beverage Manufacturing",
    "Furniture and Home Furnishings Manufacturing", "Food Production",
    "Consumer Services", "Book and Periodical Publishing",
    "Technology, Information and Internet", "Entertainment Providers",
    "Motor Vehicle Parts Manufacturing", "Automotive", "Manufacturing",
}

# --- Signaux (D4 à D8) -------------------------------------------------------
ROLE_TRIGGER = "déclencheur"
ROLE_AMPLIFIER = "amplificateur"
ROLE_CONTEXT = "contexte"
ROLE_NOISE = "bruit"
ROLE_CLIENT = "client_mirakl"
ROLES = (ROLE_TRIGGER, ROLE_AMPLIFIER, ROLE_CONTEXT, ROLE_NOISE, ROLE_CLIENT)

# Natures de déclencheur, pour la règle "plusieurs déclencheurs de natures
# différentes" du palier A (D9).
TRIGGER_NATURES = ("recrutement", "ouverture_vendeurs", "dropship", "acquisition")

# --- Statuts et listes (validés avec Nathan le 2026-10-29) --------------------
# Le statut mesure le fit ICP ; le palier mesure le timing.
STATUS_QUALIFIED = "qualifié"
STATUS_DIG = "à creuser"
STATUS_DISQUALIFIED = "disqualifié"
LIST_CLIENTS = "clients à développer"
LIST_WATCH = "hors ICP à surveiller"

TOP_N = 20
# Vérification web (D5) : seulement sur la présélection.
WEB_CHECK_MAX_ACCOUNTS = 30

# --- Produits Mirakl (D13) : ce que l'agent peut proposer ---------------------
MIRAKL_PRODUCTS = {
    "Marketplace & Dropship": "ajouter des vendeurs tiers, des produits et du drop-ship au site",
    "Catalog": "intégrer les catalogues fournisseurs et fiabiliser la donnée produit (IA)",
    "Connect": "réseau pour onboarder des marques sur les marketplaces",
    "Ads": "retail media on-site pour monétiser l'audience",
    "Payout": "onboarding, paiement et conformité des vendeurs",
    "Nexus": "infrastructure de commerce agentique (achats via agents IA)",
}
