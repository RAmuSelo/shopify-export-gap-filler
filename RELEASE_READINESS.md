# RELEASE READINESS — shopify-export-gap-filler V1

- **Date :** 2026-06-03
- **Spec source finale :** `pilot_shopify_export_gap_filler_v1_spec_LOCKED_FINAL.md` (+ `.tsv`), conservée hors du repo (dossier de travail privé).

## État git
- Branche : `master` · **Remote : aucun** (local seulement).
- 30 fichiers de projet staged (`A`) + ce `RELEASE_READINESS.md`. **Aucun commit encore.**
- Pas de `.env`, pas d'outputs réels staged. `*.egg-info/`, `.venv/`, `build/`, `dist/` ignorés.

## Installation réelle
- `python -m venv` (hors repo, `/tmp/sgf-venv-check`) + `pip install -e ".[dev]"` → **OK** (wheel editable construit, setuptools). Deps runtime : `requests` ; dev : `pytest`.

## Tests
- `python -m pytest -q` dans l'environnement editable → **69 passed / 0 failed**, zéro appel réseau.

## CLI (entry point installé)
- `shopify-gap-filler --help` → **OK** (sous-commandes `orders`, `abandoned-checkouts`).
- `shopify-gap-filler orders --help` / `abandoned-checkouts --help` → **OK** (args : `--format csv|json|both`, `--out`, `--since`, `--until`, `--limit`, `--api-version`, `--dry-run`, `--env-file`, `--no-transactions` pour orders, `--quiet/--verbose`).

## Dry-run sans credentials (`env -i`, aucun token lu)
- `--dry-run` **valide la configuration** (`SHOPIFY_SHOP` + `SHOPIFY_ADMIN_API_TOKEN`) avant tout aperçu, pour `orders` ET `abandoned-checkouts`.
- **Sans credentials :** exit **2**, message clair « Missing required configuration … (see .env.example) », **aucun traceback**, **aucun token**.
- **Avec credentials factices (`env -i` isolé) :** exit **0**, aperçu du document GraphQL + variables, **aucun appel réseau**, **aucun token affiché**, **aucun fichier de sortie écrit**.

## Greps sécurité (interprétés)
- Marqueurs de versions futures interdits : **0 occurrence active**.
- Secrets/chemins/client : seulement placeholders (`.env.example` → `SHOPIFY_SHOP=your-store`, jeton factice évident) et fixtures synthétiques de test (`example-store`). **Aucun vrai token, aucun chemin personnel absolu, aucun nom client réel, aucune clé d'API tierce.**
- PCI : `paymentDetails`/mots carte uniquement dans la denylist (`security.py`), les tests anti-fuite, et la doc d'exclusion (README/PKG-INFO). **Jamais dans une query active.**

## Vérification des requêtes GraphQL
- `orders` : `sortKey: PROCESSED_AT` ✓ · `abandonedCheckouts` : `sortKey: CREATED_AT` ✓ (confirmé existant côté Shopify).
- **Aucune** sous-sélection `paymentDetails`.
- Défaut `DEFAULT_API_VERSION = "2026-04"` ✓ (override `SHOPIFY_API_VERSION` / `--api-version`).

## Incertitudes restantes
1. (Résolu) `--dry-run` valide la config et échoue proprement (exit 2) sans credentials — plus d'ambiguïté.
2. Aucun appel réseau live exécuté (hors scope) ; `2026-04 latest` / `2026-07 RC` confirmés par toi via la doc.
3. Le CLI requiert `pip install -e .` ou `PYTHONPATH=src` (normal).

## MAJ 2026-06-03 — `--dry-run` strict appliqué (décision utilisateur)
- `--dry-run` **valide désormais la config** (`SHOPIFY_SHOP` + `SHOPIFY_ADMIN_API_TOKEN`) AVANT tout aperçu, pour `orders` ET `abandoned-checkouts`.
- **Sans credentials :** exit **2**, message clair « Missing required configuration: SHOPIFY_SHOP, SHOPIFY_ADMIN_API_TOKEN … (see .env.example) », **aucun traceback**, **aucun token**.
- **Avec credentials factices :** exit **0**, **aucun appel réseau**, **aucun token affiché** (seuls boutique + version d'API), aucun fichier de sortie écrit.
- Aucun mode « afficher la query sans creds » séparé n'a été créé (non nécessaire pour l'instant).
- Tests : **71 passed** (5 tests dry-run, dont 2 nouveaux pour l'échec propre sans creds). Greps sécurité re-passés : `2027` actif = 0, aucun vrai secret, PCI seulement en denylist/tests/doc.

## Recommandation
**Prêt pour un premier commit local : OUI.** Comportement `--dry-run` conforme à la règle stricte ; aucun blocage de sécurité.

## MAJ 2026-06-04 (post-publication + correction Codex)
- **Repo publié** : https://github.com/RAmuSelo/shopify-export-gap-filler — **public**, branche par défaut **`main`**, remote `origin` présent, dernier commit publié `789ec12`.
- **gitleaks** : était à 0 finding **avant** la publication ; aucun `.env` publié.
- **Fichiers de supervision Codex** (`CODEX_SUPERVISION_*`) : **internes, non publiés** (exclus via `.git/info/exclude`).
- **Correction de minimisation des données** (revue Codex = CORRIGER) : champ **`phone` retiré de la query `orders`** (donnée client protégée non utilisée dans les outputs) ; `email`/`billingAddress`/`shippingAddress` conservés (utilisés, dégradation gérée).
- **CI** : **aucune** (pas de `.github/workflows/` — prévu dans une passe séparée).
- **Tag / release** : **aucun** pour l'instant.
- Cette correction n'est **pas encore commitée** (en attente de validation).

