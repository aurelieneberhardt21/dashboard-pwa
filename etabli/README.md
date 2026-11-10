# Établi

**Atelier local d'analyse quantitative d'enquêtes par questionnaire, pour les sciences sociales.**

Établi sert à comprendre un export de questionnaire (LimeSurvey en priorité), à préparer les données sans
jamais modifier le fichier d'origine, à mener des analyses (tris, croisements, régressions, ACM, ACP, AFC,
AFDM, classification) et à garder la trace de chaque décision. Ce n'est ni une boîte noire ni un langage
de programmation : chaque résultat est accompagné de sa *fiche de calcul* (quelles données, quelles
exclusions, quelle méthode) et d'une aide de lecture.

Tout tourne sur votre ordinateur. Le serveur n'écoute que sur `127.0.0.1` ; l'interface ne charge aucune
ressource externe ; aucune donnée ne quitte la machine.

## Installer et lancer (macOS)

1. Récupérez le dossier `etabli/` (clone du dépôt ou archive).
2. Double-cliquez sur **`Lancer Etabli.command`**.
   - La première fois, macOS peut demander une confirmation (clic droit → *Ouvrir*).
   - Si l'outil [`uv`](https://docs.astral.sh/uv/) n'est pas installé, le lanceur propose de l'installer.
     `uv` télécharge ensuite Python et les bibliothèques scientifiques *dans ce dossier* (une à deux minutes,
     connexion nécessaire cette fois-là seulement).
3. Le navigateur s'ouvre sur `http://127.0.0.1:8765`. Pour arrêter : fermez la fenêtre du Terminal.

En ligne de commande :

```bash
cd etabli
uv run etabli                      # options : --port 9000  --sans-navigateur
```

Les projets sont enregistrés dans `~/Etabli/` (un dossier par projet ; variable d'environnement
`ETABLI_DOSSIER` pour changer d'emplacement). **Sauvegardez ce dossier** : il contient les fichiers
d'origine, le dictionnaire, la recette, les analyses et tout l'historique.

> Établi a été développé et testé sous Linux (Python 3.13, navigateur Chromium). Le lanceur macOS suit la
> procédure standard de `uv` mais n'a pas pu être exécuté sur un Mac pendant le développement.

## Le parcours en bref

| Écran | Ce qu'on y fait |
|---|---|
| **Données** | Parcourir les questions (recherche sur les intitulés, items et modalités), lire la distribution d'une variable et ses *types de non-réponse*, renommer, ordonner les modalités, documenter le *champ* d'une question (à qui elle a été posée). |
| **Préparation** | La *recette* : recoder, découper en classes, construire un score, une variable par règles, fusionner des questions comparables, exclure des individus — chaque étape avec aperçu, justification, et possibilité de la modifier ou de la désactiver. Les *populations* (sous-groupes nommés). Le ré-import d'un nouvel export. |
| **Analyses** | Choisir une méthode, la spécifier ; le résultat se calcule aussitôt. À droite : fiche de calcul, aide « Comprendre », notes. Enregistrer, dupliquer pour essayer une variante, comparer deux analyses. |
| **Journal** | Historique complet (annuler, revenir à un état, nommer une version), carnet de recherche, journal méthodologique exportable, données préparées. |

Pour découvrir l'outil : bouton **Ouvrir la démonstration** sur l'accueil (questionnaire *fictif*, signalé
comme tel sur chaque écran et dans chaque export).

## Ce qu'Établi sait lire

- Exports de réponses LimeSurvey en CSV ou Excel, avec en-têtes « texte complet », « codes » ou
  « code + texte », réponses complètes ou codes. Séparateur et encodage détectés.
- Reconnus automatiquement (et toujours modifiables) : questions à choix multiples et matrices
  (colonnes `Question [item]`), échelles ordinales usuelles, tranches numériques, textes libres, précisions
  « Si autre… », paradonnées LimeSurvey, colonnes contenant des courriels ou téléphones (marquées
  *sensibles* : jamais affichées ni exportées).
- N'importe quel tableau CSV/Excel avec une ligne d'en-têtes.

### Les types de non-réponse

Chaque cellule sans réponse reçoit un statut, visible partout :

| Statut | Signification |
|---|---|
| Non concerné | la question n'a pas été présentée (parcours conditionnel) |
| Non atteint | le répondant a abandonné avant la question |
| Non-réponse | la question était posée, pas de réponse |
| Vide (champ non documenté) | on ne sait pas encore trancher entre les deux premiers cas |
| Modalité de non-réponse | « Préfère ne pas répondre », « Ne sait pas »… déclarée comme telle |
| Mis en manquant | par une étape de préparation |

LimeSurvey exporte la même cellule vide pour « non présentée » et « passée » (sauf les cases à cocher,
exportées `N/A`). Établi *propose* donc, à partir des parcours observés, le champ de chaque question
conditionnelle ; rien n'est appliqué sans validation.

## Méthodes et validation

Les calculs s'appuient sur numpy, scipy et statsmodels. Les formules propres à Établi (analyse géométrique,
PEM, résidus, effets marginaux…) sont écrites lisiblement dans `src/etabli/stats/` et **comparées à R** par
des tests automatiques (`tests/`, valeurs de référence versionnées dans `tests/reference/`) :

| Domaine | Référence | Tolérance |
|---|---|---|
| ACP, AFC, ACM, AFDM, éléments supplémentaires | FactoMineR 2.9 | 1e-8 |
| ACM spécifique (modalités passives), taux modifiés | GDAtools 2.3 (`speMCA`, `modif.rate`), `MCA(excl=)` | 1e-8 à 6e-7 |
| CAH de Ward, consolidation, description des classes | FactoMineR `HCPC`, `catdes` | 1e-8 |
| Chi², résidus, Fisher, V de Cramér, gamma, tau-b | R `chisq.test`, `fisher.test`, `cor.test` | 1e-8 |
| PEM local et global (Cibois) | `descriptio` 1.5 (`pem.table`, lignes et colonnes ordonnées par l'AFC) | 1e-6 |
| Comparaison de moyennes, corrélations, ajustements | `aov`, `oneway.test`, `kruskal.test`, `cor.test`, `p.adjust` | 1e-7 |
| Régressions linéaire, logistique, multinomiale | `lm`, `glm`, `car::Anova`, `car::vif`, `sandwich`, `nnet::multinom` | 1e-7 à 2e-3 |

Les divergences assumées avec ces logiciels (cos² des individus en ACM spécifique chez GDAtools, cos² des
modalités de `FAMD` avec individus supplémentaires, parangons pondérés de `HCPC`) sont documentées dans les
tests et dans l'en-tête des modules.

```bash
uv run pytest                      # 57 tests : moteurs statistiques + parcours complet sur données fictives
Rscript tests/reference/geometrique.R   # (facultatif) régénérer les références avec R
node tests/interface/parcours.cjs       # (facultatif) parcours de l'interface dans un navigateur — voir l'en-tête du fichier
```

Chaque analyse peut être exportée en **script R + données analysées** (onglet *Fiche de calcul*), pour
refaire le calcul avec un logiciel de référence.

## Confidentialité

- Aucune connexion sortante ; serveur limité à `127.0.0.1`.
- Variables *sensibles* masquées à l'écran et absentes de tous les exports ; réponses textuelles absentes des
  exports de données.
- Effectifs inférieurs à 5 signalés dans les tris, les croisements et les recodages.
- Les exports « script + données » et « données préparées » contiennent des réponses individuelles :
  l'interface le rappelle au moment de l'export.

## Limites actuelles

- Pas de pondération (redressement) dans les analyses uni/bivariées et les régressions.
- Un projet = une source ; la réunion de plusieurs enquêtes (deux pays, deux vagues) dans un même projet est
  préparée dans le moteur mais pas proposée dans l'interface.
- Le fichier de structure LimeSurvey (`.lss`) n'est pas lu : l'ordre des modalités et les conditions
  d'affichage sont reconstitués à partir des réponses (et restent à valider).
- Pas d'imputation des valeurs manquantes ; pas de régression ordinale ni de modèles multiniveaux.
- Analyses factorielles : pas de rotation, pas d'AFM (analyse factorielle multiple).
- Interface en français uniquement ; mise en page pensée pour un écran d'ordinateur.

Voir `PROJECT_STATUS.md` pour l'état détaillé et les prochaines étapes.

## Organisation du code

```
src/etabli/
  importer.py     lecture des exports, reconnaissance de la structure du questionnaire
  table.py        table de travail (valeurs + statut de chaque cellule), conditions, propositions de champ
  recette.py      étapes de préparation (déclaratives, rejouables)
  projet.py       dossier de projet, enregistrement, historique, ré-import
  analyses.py     de la spécification au résultat + fiche de calcul
  stats/          moteurs statistiques validés contre R
  export.py       Excel, script R, données préparées, journal méthodologique
  server.py       API locale (FastAPI)       demo.py   questionnaire fictif
  web/            interface (Preact + htm embarqués, graphiques SVG, aucun appel externe)
tests/            tests et références R
```
