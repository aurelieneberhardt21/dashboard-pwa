# Établi — journal de projet

Document de reprise : état du logiciel, décisions de conception, ce qui est vérifié, ce qui reste à faire.
À mettre à jour à chaque session de travail.

## État au 10 novembre 2026 (v0.1.0)

Premier parcours complet, utilisable de bout en bout : **import → dictionnaire → préparation → analyses →
journal et exports**. 57 tests automatiques passent (`uv run pytest`), plus un parcours de 24 étapes dans un
vrai navigateur (`tests/interface/parcours.cjs`).

### Ce qui fonctionne (vérifié)

| Fonction | Vérification |
|---|---|
| Import LimeSurvey CSV / Excel (en-têtes texte, codes, code + texte), typage des colonnes, familles (choix multiples, matrices), échelles ordinales, colonnes sensibles | tests de parcours (données fictives) ; essai manuel sur un export réel de 349 réponses × 399 colonnes |
| Statuts de non-réponse (non concerné / non atteint / non-réponse / vide / modalité NR / mis en manquant) ; règle « N/A partiel = non coché » | tests de parcours |
| Propositions de champ des questions conditionnelles (une condition, conjonction de deux, réunion) | test de parcours ; sur l'export réel, 105 questions conditionnelles sur 109 reçoivent une proposition |
| Recette : recoder, découper, score, règles, fusionner, convertir, croiser, exclure, classes d'une classification ; aperçu avant enregistrement | tests de parcours (recoder, score, exclure, partition) ; les autres types : essais manuels seulement |
| Populations ; ré-import d'un nouvel export en conservant annotations, recette, analyses | tests de parcours |
| Historique, annuler / rétablir, versions nommées, restauration | tests de parcours |
| Tri à plat, croisement (tableau, moyennes, corrélation), réponses multiples, corrélations, régressions linéaire / logistique / multinomiale, exploration | validés contre R (`tests/test_bivarie.py`, 24 tests) |
| ACP, AFC, ACM, ACM spécifique, AFDM, éléments supplémentaires, CAH + consolidation + description des classes | validés contre FactoMineR / GDAtools (`tests/test_geometrique.py`, 28 tests) |
| Exports : Excel, copie de tableau, SVG / PNG, script R + données, journal méthodologique, données préparées | test de parcours (présence et contenu minimal). Les scripts R générés ont été **exécutés dans R** pour les 11 types d'analyse sur les données fictives et redonnent les chiffres d'Établi (valeurs propres ACM spécifique / ACP / AFC / AFDM, chi², V, coefficients, déviance, effectifs des classes, % par item) — vérification manuelle, pas encore automatisée |
| Interface (4 écrans) | `tests/interface/parcours.cjs` (Playwright, clics réels, données fictives) : recodage avec aperçu, croisement construit à la main, fiche de calcul, aide, modalité rendue passive depuis la carte, comparaison, historique, annulation, journal. Essais manuels sur l'export réel. Vérifié dans Chromium seulement (ni Safari ni Firefox) |

### Ce qui n'est pas fait ou pas vérifié

- **Lanceur macOS** (`Lancer Etabli.command`) : écrit, jamais exécuté sur un Mac.
- **Scripts R de reproduction** : vérifiés à la main sur les données fictives uniquement ; à rejouer sur un
  projet réel (libellés longs, apostrophes typographiques) et à automatiser quand R est disponible.
- **Étapes fusionner / règles / convertir / croiser / découper** : sans test automatique.
- **Plusieurs sources dans un projet** (deux pays) : le moteur empile les sources (`construire_table`, alias,
  identifiants préfixés) mais l'interface ne le propose pas et rien n'est testé.
- Fichier `.lss` (structure LimeSurvey) : non lu.
- Pondération hors analyses géométriques ; régression ordinale ; AFM ; imputation.
- Mode sombre : jetons de couleur prévus (CSS), non vérifié visuellement.

## Décisions de conception (et pourquoi)

1. **Application web locale** : serveur Python (FastAPI) + interface dans le navigateur, sur `127.0.0.1`.
   Python pour s'appuyer sur numpy / scipy / statsmodels ; aucun service externe ; un seul outil à installer
   (`uv`). Alternative écartée : R + Shiny (FactoMineR natif, mais installation plus lourde et interface moins
   maîtrisable).
2. **Moteur géométrique écrit sur `numpy.linalg.svd` et validé contre FactoMineR / GDAtools** plutôt que
   dépendance à `prince` (résultats ACM moins sûrs, pas d'ACM spécifique). Les formules sont dans le code,
   lisibles ; les références R sont versionnées ; chaque analyse s'exporte en script R.
3. **Données brutes immuables, recette déclarative** : aucune étape ne modifie une variable ; chacune en
   ajoute une. La table de travail est recalculée (≈ 0,5 s pour 350 × 400) à partir des sources + recette.
4. **Statut par cellule** plutôt qu'un simple « manquant » : c'est la difficulté centrale des questionnaires
   à parcours conditionnels. Le *champ* d'une question est une annotation du dictionnaire, proposée par
   inférence et validée par l'utilisateur.
5. **Identifiants stables** (`v012`, `d003`, `e002`, `p001`, `a004`) ; noms courts et libellés modifiables
   sans casser les références. Au ré-import, les colonnes sont ré-appariées par (en-tête, occurrence).
6. **Tout résultat a une fiche de calcul** construite par `analyses.Contexte.fiche` : flux d'effectifs,
   exclusions par variable et par motif, lignage des variables construites, méthode, avertissements.
7. **Pas de verdict automatique** : tailles d'effet et intervalles avant les p-valeurs, pas d'étoiles ;
   l'exploration trie par intensité et affiche les p ajustées et le nombre de tests.
8. **Interface sans étape de compilation** : Preact + htm embarqués (`web/vendor`), modules ES, graphiques
   SVG écrits à la main (`web/js/graphiques.js`) → modifiable sans Node, exports SVG propres.
9. **Rendu différé** : `options.debounceRendering = setTimeout` (dans `web/js/base.js`). Par défaut Preact
   redessine dans une micro-tâche, donc au milieu de la propagation d'un clic réel ; un nœud réutilisé
   recevait alors le clic qui venait de le créer (le sélecteur de variable se rouvrait aussitôt). Ne pas retirer.
10. **Historique en instantanés** (`historique/*.json.gz`) : simple et sûr ; l'état d'un projet reste petit.

## Pistes pour la suite (par ordre d'intérêt pour la thèse)

1. **Réunir deux enquêtes** (France / États-Unis) : interface « ajouter une source », variable `source`
   automatique, étape *fusionner* guidée par un tableau de correspondance des questions, avec note de
   comparabilité obligatoire.
2. **Lire le `.lss`** : codes, groupes thématiques, ordre des modalités et conditions d'affichage exacts
   (remplacerait l'inférence des champs quand le fichier est disponible).
3. **Codage assisté des questions ouvertes** (professions des parents → PCS) : recherche par mots, règles
   réutilisables — sans appel externe.
4. Automatiser la vérification des scripts R générés ; étendre le test d'interface (éditeurs d'étapes autres
   que le recodage, populations, ré-import) ; essayer Safari.
5. Analyse des données structurées : effets et écarts entre points moyens de sous-nuages, typicalité
   (Le Roux & Rouanet) au-delà des ellipses de concentration ; ACM de classes (CSA).
6. Sections thématiques du questionnaire (le serveur les stocke déjà : `sections`), pour naviguer par thème.
7. Pondération / redressement ; régression ordinale ; export Word des tableaux.

## Repères techniques

- Lancer : `uv run etabli` ; tests : `uv run pytest` ; projets dans `~/Etabli` (`ETABLI_DOSSIER`).
- Régénérer les références R : `Rscript tests/reference/geometrique.R` et `tests/reference/bivarie.R`
  (R 4.3, FactoMineR 2.9 ; GDAtools, ca, descriptio, car, sandwich via `R_LIBS` ou `ETABLI_R_LIBS`).
- Ajouter une analyse : exécuteur dans `analyses.py` (`EXECUTEURS`), rendu dans `web/js/resultats.js`
  (`RENDUS` dans `analyses.js`), formulaire dans `Constructeur`, aide dans `aide.js`, script dans `export.py`.
- Ajouter un type d'étape : `recette.py` (`APPLICATEURS`, `sources_etape`), formulaire dans
  `web/js/preparation.js` (`FORMULAIRES`), description dans `export._decrire_etape`.
- **Ne jamais commiter de données d'enquête** : les essais sur données réelles se font dans un dossier de
  travail hors dépôt.
