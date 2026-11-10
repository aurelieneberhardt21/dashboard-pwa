"""Régressions : linéaire (MCO), logistique binaire, logistique multinomiale.

Moteur : statsmodels (OLS, Logit, MNLogit). Ce module construit la matrice des
prédicteurs (indicatrices avec modalité de référence explicite, interactions), lance
l'estimation et met en forme une sortie lisible : une ligne par terme, *y compris les
modalités de référence* (coefficient 0, odds ratio 1), tests par variable, qualité
d'ajustement, diagnostics.

Validé contre R dans tests/test_bivarie.py : lm, glm(family = binomial), confint,
sandwich::vcovHC (HC3), car::Anova (type II), car::vif, nnet::multinom.

Rappels de lecture, repris dans les avertissements quand c'est utile :
- un coefficient mesure une association « toutes choses égales par ailleurs » *au sens des
  variables du modèle* ; il ne dit rien de la causalité ;
- un odds ratio n'est pas un rapport de probabilités ; les effets marginaux moyens (AME)
  traduisent l'association en points de probabilité et se comparent mieux entre modèles ;
- avec de petits effectifs, peu de paramètres : viser au moins ~10 événements par paramètre.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.tools.sm_exceptions import ConvergenceWarning, PerfectSeparationError

try:  # présent selon la version de statsmodels
    from statsmodels.tools.sm_exceptions import PerfectSeparationWarning
except ImportError:  # pragma: no cover
    PerfectSeparationWarning = ConvergenceWarning  # type: ignore[misc,assignment]

from .univarie import en_categorie, est_quanti, nettoyer

__all__ = ["regression_lineaire", "regression_logistique", "regression_multinomiale"]

CONSTANTE = "Constante"
_MAX_POINTS = 5000


# =========================================================================== matrice des prédicteurs

@dataclass
class _Plan:
    """Données prêtes pour l'estimation, après exclusion des lignes incomplètes."""
    y: pd.Series
    X: pd.DataFrame                       # première colonne : Constante
    termes: list[dict]                    # {"nom", "type", "colonnes", "ddl", "variables"}
    colonnes: dict[str, dict]             # nom de colonne → {"variable", "modalite"}
    references: dict[str, object]         # variable qualitative → modalité de référence
    effectifs: dict[str, dict]            # variable qualitative → {modalité: n}
    types: dict[str, str]                 # variable → "quanti" | "quali"
    garde: np.ndarray                     # masque booléen des lignes conservées
    n_exclus: int
    exclus_par_variable: dict[str, int]
    avertissements: list[str] = field(default_factory=list)


def _preparer(y: pd.Series, X: pd.DataFrame, references: dict | None, interactions: list | None, nom_y: str = "y") -> _Plan:
    """Exclusion « listwise » puis construction des indicatrices et des interactions."""
    if not isinstance(X, pd.DataFrame):
        X = pd.DataFrame(X)
    if not isinstance(y, pd.Series):
        y = pd.Series(y, name=nom_y)
    if len(y) != len(X):
        raise ValueError("y et X doivent avoir le même nombre de lignes.")
    if X.shape[1] == 0:
        raise ValueError("Aucune variable explicative.")
    y = y.reset_index(drop=True)
    X = X.reset_index(drop=True)
    X.columns = [str(c) for c in X.columns]
    references = dict(references or {})
    avertissements: list[str] = []

    exclus = {str(y.name if y.name is not None else nom_y): int(y.isna().sum())}
    exclus.update({c: int(X[c].isna().sum()) for c in X.columns})
    garde = (y.notna() & X.notna().all(axis=1)).to_numpy()
    n_exclus = int((~garde).sum())
    y = y[garde].reset_index(drop=True)
    X = X[garde].reset_index(drop=True)
    if len(y) == 0:
        raise ValueError("Aucun individu complet : toutes les lignes ont au moins une valeur manquante.")

    plan = pd.DataFrame({CONSTANTE: np.ones(len(y))})
    termes: list[dict] = []
    colonnes: dict[str, dict] = {CONSTANTE: {"variable": None, "modalite": None}}
    refs: dict[str, object] = {}
    effectifs: dict[str, dict] = {}
    types: dict[str, str] = {}
    blocs: dict[str, list[str]] = {}

    for var in X.columns:
        s = X[var]
        if est_quanti(s):
            types[var] = "quanti"
            v = s.astype(float)
            if v.nunique() < 2:
                avertissements.append(f"« {var} » est constante sur les individus retenus : retirée du modèle.")
                continue
            plan[var] = v.to_numpy()
            colonnes[var] = {"variable": var, "modalite": None}
            blocs[var] = [var]
            termes.append({"nom": var, "type": "quanti", "colonnes": [var], "ddl": 1, "variables": [var]})
            continue
        types[var] = "quali"
        c = en_categorie(s)
        inutilisees = [m for m in c.cat.categories if (c == m).sum() == 0]
        if inutilisees:
            avertissements.append(f"« {var} » : modalité(s) sans individu après exclusion des manquants, ignorée(s) : "
                                  + ", ".join(str(m) for m in inutilisees) + ".")
            c = c.cat.remove_unused_categories()
        modalites = list(c.cat.categories)
        if len(modalites) < 2:
            avertissements.append(f"« {var} » n'a qu'une modalité sur les individus retenus : retirée du modèle.")
            continue
        ref = references.get(var, modalites[0])
        if ref not in modalites:
            raise ValueError(f"Modalité de référence {ref!r} absente de « {var} » (modalités : {modalites}).")
        refs[var] = ref
        effectifs[var] = {m: int((c == m).sum()) for m in modalites}
        noms = []
        for m in modalites:
            if m == ref:
                continue
            nom = f"{var} : {m}"
            plan[nom] = (c == m).to_numpy().astype(float)
            colonnes[nom] = {"variable": var, "modalite": m}
            noms.append(nom)
        blocs[var] = noms
        termes.append({"nom": var, "type": "quali", "colonnes": noms, "ddl": len(noms), "variables": [var]})

    for a, b in (interactions or []):
        a, b = str(a), str(b)
        if a not in blocs or b not in blocs:
            raise ValueError(f"Interaction {a} × {b} : les deux variables doivent figurer dans le modèle.")
        nom_terme = f"{a} × {b}"
        noms = []
        for ca in blocs[a]:
            for cb in blocs[b]:
                nom = f"{ca} × {cb}"
                produit = plan[ca].to_numpy() * plan[cb].to_numpy()
                if np.allclose(produit, produit[0]):
                    avertissements.append(f"Interaction « {nom} » : combinaison sans variation (cellule vide ?), retirée.")
                    continue
                plan[nom] = produit
                ma, mb = colonnes[ca]["modalite"], colonnes[cb]["modalite"]
                mod = " × ".join(str(m) for m in (ma, mb) if m is not None) or None
                colonnes[nom] = {"variable": nom_terme, "modalite": mod}
                noms.append(nom)
        if noms:
            termes.append({"nom": nom_terme, "type": "interaction", "colonnes": noms, "ddl": len(noms), "variables": [a, b]})

    if not termes:
        raise ValueError("Aucune variable explicative utilisable (toutes constantes ?).")
    if len(y) <= plan.shape[1]:
        raise ValueError(f"Trop peu d'individus complets (n = {len(y)}) pour {plan.shape[1]} paramètres.")
    if np.linalg.matrix_rank(plan.to_numpy()) < plan.shape[1]:
        raise ValueError("Colinéarité parfaite entre prédicteurs : une variable (ou une modalité) est une combinaison exacte "
                         "des autres. Retirer une variable redondante ou regrouper des modalités.")
    return _Plan(y=y, X=plan, termes=termes, colonnes=colonnes, references=refs, effectifs=effectifs, types=types,
                 garde=garde, n_exclus=n_exclus, exclus_par_variable=exclus, avertissements=avertissements)


def _sous_modeles_type2(plan: _Plan, terme: dict) -> tuple[list[str], list[str]]:
    """Colonnes des deux modèles comparés par un test de type II pour `terme`.

    Principe de marginalité : un effet principal est testé dans le modèle privé des
    interactions qui le contiennent ; une interaction est testée dans le modèle complet.
    Renvoie (colonnes du modèle sans le terme, colonnes du modèle avec le terme).
    """
    if terme["type"] == "interaction":
        parents: list[dict] = []
    else:
        parents = [t for t in plan.termes if t["type"] == "interaction" and terme["nom"] in t["variables"]]
    exclues = {c for t in parents for c in t["colonnes"]}
    avec = [c for c in plan.X.columns if c not in exclues]
    sans = [c for c in avec if c not in terme["colonnes"]]
    return sans, avec


def _gvif(cov: np.ndarray, noms: list[str], plan: _Plan) -> list[dict]:
    """Facteurs d'inflation de la variance généralisés (Fox & Monette 1992), comme car::vif.

    Calculés à partir de la matrice de corrélation des coefficients (hors constante) :
    GVIF = det(R_terme) · det(R_autres) / det(R). Pour un terme à 1 ddl c'est le VIF usuel ;
    pour une variable qualitative à k−1 indicatrices, on compare GVIF^(1/(2·ddl)) (colonne
    `gvif_ajuste`), dont le carré se lit comme un VIF. Repère courant : gvif_ajuste² > 5
    (voire 10) signale une colinéarité qui gonfle les erreurs-types.
    """
    if len(plan.termes) < 2:
        return []
    idx = [i for i, c in enumerate(noms) if c != CONSTANTE]
    V = cov[np.ix_(idx, idx)]
    d = np.sqrt(np.diag(V))
    R = V / np.outer(d, d)
    det_r = np.linalg.det(R)
    noms_h = [noms[i] for i in idx]
    sortie = []
    for t in plan.termes:
        s = [noms_h.index(c) for c in t["colonnes"]]
        reste = [i for i in range(len(noms_h)) if i not in s]
        g = np.linalg.det(R[np.ix_(s, s)]) * np.linalg.det(R[np.ix_(reste, reste)]) / det_r
        sortie.append({"terme": t["nom"], "gvif": float(g), "ddl": t["ddl"], "gvif_ajuste": float(g ** (1 / (2 * t["ddl"])))})
    return sortie


def _lignes_termes(plan: _Plan, coef: pd.Series, se: pd.Series, stat: pd.Series, p: pd.Series, ic: pd.DataFrame,
                   exponentielle: bool, nom_exp: str = "odds_ratio", prefixe_exp: str = "or") -> list[dict]:
    """Une ligne par coefficient, avec une ligne explicite pour chaque modalité de référence."""
    def ligne(col: str) -> dict:
        info = plan.colonnes[col]
        l = {"terme": col, "variable": info["variable"], "modalite": info["modalite"], "reference": False,
             "coef": coef[col], "se": se[col], "stat": stat[col], "p": p[col], "ic_bas": ic.loc[col, 0], "ic_haut": ic.loc[col, 1]}
        if info["variable"] in plan.effectifs and info["modalite"] in plan.effectifs[info["variable"]]:
            l["n"] = plan.effectifs[info["variable"]][info["modalite"]]
        if exponentielle:
            l[nom_exp] = math.exp(min(coef[col], 700)) if col != CONSTANTE else None
            l[f"{prefixe_exp}_ic_bas"] = math.exp(min(ic.loc[col, 0], 700)) if col != CONSTANTE else None
            l[f"{prefixe_exp}_ic_haut"] = math.exp(min(ic.loc[col, 1], 700)) if col != CONSTANTE else None
        return l

    lignes = [ligne(CONSTANTE)]
    for t in plan.termes:
        if t["type"] == "quali":
            var = t["nom"]
            ref = plan.references[var]
            l = {"terme": f"{var} : {ref}", "variable": var, "modalite": ref, "reference": True,
                 "coef": 0.0, "se": None, "stat": None, "p": None, "ic_bas": None, "ic_haut": None,
                 "n": plan.effectifs[var][ref]}
            if exponentielle:
                l.update({nom_exp: 1.0, f"{prefixe_exp}_ic_bas": None, f"{prefixe_exp}_ic_haut": None})
            lignes.append(l)
        lignes.extend(ligne(c) for c in t["colonnes"])
    return lignes


def _avertissements_communs(plan: _Plan, n: int, n_param: int, gvif: list[dict]) -> list[str]:
    av = list(plan.avertissements)
    if plan.n_exclus:
        pire = max(plan.exclus_par_variable.items(), key=lambda kv: kv[1])
        av.append(f"{plan.n_exclus} individu(s) exclu(s) car au moins une variable du modèle est manquante "
                  f"(exclusion « listwise » ; la variable la plus touchée est « {pire[0] } » : {pire[1]} manquant(s)). "
                  "Le modèle ne porte que sur les individus complets : vérifier qu'ils ne diffèrent pas trop des autres.")
    for var, eff in plan.effectifs.items():
        petits = [f"{m} (n = {k})" for m, k in eff.items() if k < 5]
        if petits:
            av.append(f"« {var} » : modalité(s) de moins de 5 individus — {', '.join(petits)}. Coefficients très imprécis ; envisager un regroupement.")
    forts = [g for g in gvif if g["gvif_ajuste"] ** 2 > 5]
    if forts:
        av.append("Colinéarité marquée (GVIF ajusté² > 5) pour : " + ", ".join(g["terme"] for g in forts)
                  + ". Les erreurs-types de ces termes sont gonflées ; leurs coefficients sont difficiles à séparer.")
    if any(t["type"] == "interaction" for t in plan.termes):
        av.append("Modèle avec interaction : le coefficient d'un effet principal impliqué dans une interaction est l'effet "
                  "*lorsque l'autre variable est à sa référence (ou à 0)*, pas un effet moyen.")
    return av


def _echantillon(n: int) -> np.ndarray:
    return np.arange(n) if n <= _MAX_POINTS else np.unique(np.linspace(0, n - 1, _MAX_POINTS).astype(int))


# =========================================================================== régression linéaire

def regression_lineaire(y: pd.Series, X: pd.DataFrame, *, references: dict | None = None, robuste: str | None = None,
                        interactions: list[tuple[str, str]] | None = None, ic: float = 0.95) -> dict:
    """Régression linéaire par moindres carrés ordinaires.

    `X` mêle variables quantitatives et qualitatives (ces dernières deviennent des
    indicatrices ; modalité de référence = `references[var]` ou première catégorie).
    `robuste="HC3"` (ou HC0-HC2) : erreurs-types robustes à l'hétéroscédasticité
    (sandwich::vcovHC dans R) ; les coefficients sont inchangés, seules l'incertitude
    et les tests le sont. `interactions` : liste de couples de variables de X.

    Tests par variable (`tests_variables`) : F de type II (car::Anova), c'est-à-dire l'apport
    de la variable une fois toutes les autres prises en compte (hors interactions qui la
    contiennent). Avec `robuste`, ce sont des tests de Wald fondés sur la covariance robuste.

    AIC/BIC suivent la convention de R (la variance résiduelle compte comme un paramètre).
    """
    yy = pd.to_numeric(pd.Series(y) if not isinstance(y, pd.Series) else y, errors="coerce").astype(float)
    plan = _preparer(yy, X, references, interactions)
    n, k = plan.X.shape
    modele = sm.OLS(plan.y.to_numpy(), plan.X)
    classique = modele.fit()
    if robuste:
        if robuste not in ("HC0", "HC1", "HC2", "HC3"):
            raise ValueError("robuste doit valoir None, 'HC0', 'HC1', 'HC2' ou 'HC3'.")
        fit = modele.fit(cov_type=robuste, use_t=True)
    else:
        fit = classique
    alpha = 1 - ic
    icf = fit.conf_int(alpha=alpha)
    termes = _lignes_termes(plan, fit.params, fit.bse, fit.tvalues, fit.pvalues, icf, exponentielle=False)

    # coefficients standardisés des prédicteurs quantitatifs (bêta = b · σx / σy)
    sy = plan.y.std(ddof=1)
    for l in termes:
        if l["terme"] in plan.types and plan.types[l["terme"]] == "quanti" and sy > 0:
            l["coef_standardise"] = float(l["coef"] * plan.X[l["terme"]].std(ddof=1) / sy)

    # --- tests par variable
    rss_complet = float(classique.ssr)
    ddl_res = int(classique.df_resid)
    tests = []
    for t in plan.termes:
        if robuste:
            L = np.zeros((t["ddl"], k))
            for i, c in enumerate(t["colonnes"]):
                L[i, list(plan.X.columns).index(c)] = 1
            w = fit.f_test(L)
            tests.append({"terme": t["nom"], "ddl": t["ddl"], "ddl_residus": ddl_res, "stat": float(np.squeeze(w.fvalue)),
                          "p": float(w.pvalue), "test": f"Wald F (covariance {robuste})"})
        else:
            sans, avec = _sous_modeles_type2(plan, t)
            rss0 = float(sm.OLS(plan.y.to_numpy(), plan.X[sans]).fit().ssr)
            rss1 = float(sm.OLS(plan.y.to_numpy(), plan.X[avec]).fit().ssr)
            f = ((rss0 - rss1) / t["ddl"]) / (rss_complet / ddl_res)
            tests.append({"terme": t["nom"], "ddl": t["ddl"], "ddl_residus": ddl_res, "stat": f,
                          "p": float(stats.f.sf(f, t["ddl"], ddl_res)), "test": "F de type II",
                          "somme_carres": rss0 - rss1})

    llf = float(classique.llf)
    sigma = math.sqrt(rss_complet / ddl_res)
    ajustement = {
        "r2": float(classique.rsquared), "r2_ajuste": float(classique.rsquared_adj),
        "f": float(classique.fvalue), "ddl_modele": int(classique.df_model), "ddl_residus": ddl_res, "p_f": float(classique.f_pvalue),
        "sigma": sigma, "log_vraisemblance": llf,
        "aic": -2 * llf + 2 * (k + 1), "bic": -2 * llf + math.log(n) * (k + 1),
    }

    gvif = _gvif(np.asarray(classique.cov_params()), list(plan.X.columns), plan)
    influence = classique.get_influence()
    standardises = influence.resid_studentized_internal
    ech = _echantillon(n)
    residus = {
        "ajustes": classique.fittedvalues.to_numpy()[ech], "residus": classique.resid.to_numpy()[ech],
        "standardises": standardises[ech], "echantillonne": bool(len(ech) < n),
        "n_extremes": int((np.abs(standardises) > 3).sum()),
        "levier_max": float(influence.hat_matrix_diag.max()), "distance_cook_max": float(influence.cooks_distance[0].max()),
    }

    av = _avertissements_communs(plan, n, k, gvif)
    if n / (k - 1) < 10:
        av.append(f"Seulement {n / (k - 1):.1f} individus par paramètre estimé : risque de sur-ajustement, R² optimiste.")
    if residus["n_extremes"]:
        av.append(f"{residus['n_extremes']} résidu(s) standardisé(s) au-delà de ±3 : vérifier ces individus atypiques (graphique des résidus).")
    if not robuste:
        av.append("Erreurs-types classiques (variance des résidus supposée constante). Si le graphique des résidus s'évase, "
                  "relancer avec des erreurs-types robustes (HC3) et comparer.")

    return nettoyer({
        "type": "lineaire",
        "n": n, "n_exclus": plan.n_exclus, "exclus_par_variable": plan.exclus_par_variable,
        "y": {"nom": getattr(y, "name", None), "moyenne": float(plan.y.mean()), "ecart_type": float(sy)},
        "termes": termes, "tests_variables": tests, "ajustement": ajustement,
        "diagnostics": {"vif": gvif, "effectifs_modalites": plan.effectifs, "individus_par_parametre": n / (k - 1)},
        "residus": residus,
        "references": plan.references, "robuste": robuste, "niveau_ic": ic,
        "methode": {
            "nom": "Régression linéaire (moindres carrés ordinaires)",
            "moteur": "statsmodels.OLS",
            "valeurs_manquantes": "exclusion des individus incomplets (listwise)",
            "variables_qualitatives": "indicatrices, modalité de référence explicite (contraste « traitement »)",
            "erreurs_types": f"robustes {robuste} (sandwich), tests t à {ddl_res} ddl" if robuste else "classiques (homoscédasticité supposée)",
            "tests_variables": "Wald F avec covariance robuste" if robuste else "F de type II (car::Anova), respect du principe de marginalité",
            "intervalle_confiance": f"{100 * ic:g} %, loi de Student",
            "criteres_information": "AIC et BIC à la manière de R (variance résiduelle comptée comme paramètre)",
            "colinearite": "GVIF de Fox & Monette (car::vif)",
        },
        "avertissements": av,
    })


# =========================================================================== régression logistique

def _binaire(y: pd.Series, modalite_cible) -> tuple[pd.Series, object, object, list[str]]:
    """Code y en 0/1. Renvoie (y codé avec NaN conservés, modalité cible, libellé du reste, avertissements)."""
    av: list[str] = []
    if pd.api.types.is_bool_dtype(y.dtype):
        y = y.astype(pd.CategoricalDtype([False, True]))
    elif est_quanti(y):
        valeurs = sorted(y.dropna().unique().tolist())
        y = y.astype(pd.CategoricalDtype(valeurs))
    c = en_categorie(y).cat.remove_unused_categories()
    modalites = list(c.cat.categories)
    if len(modalites) < 2:
        raise ValueError("La variable à expliquer n'a qu'une modalité observée.")
    if modalite_cible is None:
        if len(modalites) > 2:
            raise ValueError(f"La variable à expliquer a {len(modalites)} modalités ({modalites}) : préciser `modalite_cible` "
                             "(elle sera opposée à toutes les autres) ou utiliser la régression multinomiale.")
        modalite_cible = modalites[1]
    if modalite_cible not in modalites:
        raise ValueError(f"Modalité cible {modalite_cible!r} absente de la variable à expliquer (modalités : {modalites}).")
    autres = [m for m in modalites if m != modalite_cible]
    if len(autres) > 1:
        av.append(f"La variable à expliquer a {len(modalites)} modalités : « {modalite_cible} » est opposée à l'ensemble des autres "
                  f"({', '.join(str(m) for m in autres)}), qui sont donc traitées comme équivalentes.")
        reste: object = "Autres : " + " / ".join(str(m) for m in autres)
    else:
        reste = autres[0]
    code = (c == modalite_cible).astype(float).where(c.notna())
    code.name = y.name
    return code, modalite_cible, reste, av


def _ajuster_logit(yb: np.ndarray, X: pd.DataFrame):
    """Ajuste un Logit en capturant les signaux de séparation. Renvoie (fit | None, séparation, convergence)."""
    separation = False
    with warnings.catch_warnings(record=True) as captures:
        warnings.simplefilter("always")
        try:
            fit = sm.Logit(yb, X).fit(disp=0, maxiter=200, method="newton")
        except PerfectSeparationError:
            return None, True, False
        except np.linalg.LinAlgError:
            return None, True, False
    for w in captures:
        if issubclass(w.category, PerfectSeparationWarning) and "separation" in str(w.message).lower():
            separation = True
    converge = bool(fit.mle_retvals.get("converged", True))
    # séparation quasi complète : coefficients ou erreurs-types démesurés
    if np.any(np.abs(fit.params.to_numpy()[1:]) > 15) or not np.all(np.isfinite(fit.bse)) or np.any(fit.bse.to_numpy() > 500):
        separation = True
    return fit, separation, converge


def _deviance_logit(yb: np.ndarray, X: pd.DataFrame) -> float | None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            return float(-2 * sm.Logit(yb, X).fit(disp=0, maxiter=200, method="newton").llf)
        except Exception:
            return None


def regression_logistique(y: pd.Series, X: pd.DataFrame, *, modalite_cible=None, references: dict | None = None,
                          interactions: list[tuple[str, str]] | None = None, ic: float = 0.95) -> dict:
    """Régression logistique binaire (maximum de vraisemblance).

    On modélise la probabilité que y vaille `modalite_cible` (par défaut la seconde
    catégorie, comme glm() dans R). Chaque terme reçoit son coefficient (échelle logit),
    son odds ratio = exp(coef) et les intervalles de Wald correspondants (confint.default).

    Sortie complémentaire :
    - `tests_variables` : tests du rapport de vraisemblance de type II (car::Anova) ;
    - `ajustement` : log-vraisemblance, déviance, AIC, BIC, pseudo-R² de McFadden et de
      Nagelkerke, test du rapport de vraisemblance contre le modèle sans prédicteur ;
    - `effets_marginaux` : effets marginaux moyens (AME), en variation de probabilité —
      pour une indicatrice, écart moyen de probabilité prédite entre la modalité et sa
      référence ; non calculés en présence d'interactions ;
    - `classement` : taux de bons classements (seuil 0,5) et AUC, donnés à titre descriptif ;
    - `diagnostics` : GVIF, effectifs et nombre d'événements par modalité, événements par
      paramètre, détection de la séparation (quasi) complète.
    """
    y = pd.Series(y) if not isinstance(y, pd.Series) else y
    yb, cible, reste, av_y = _binaire(y, modalite_cible)
    plan = _preparer(yb, X, references, interactions)
    n, k = plan.X.shape
    y01 = plan.y.to_numpy()
    n1, n0 = int(y01.sum()), int(n - y01.sum())
    if n1 == 0 or n0 == 0:
        raise ValueError("Après exclusion des valeurs manquantes, la variable à expliquer n'a plus qu'une modalité.")

    methode = {
        "nom": "Régression logistique binaire",
        "moteur": "statsmodels.Logit (maximum de vraisemblance, Newton-Raphson)",
        "valeurs_manquantes": "exclusion des individus incomplets (listwise)",
        "variables_qualitatives": "indicatrices, modalité de référence explicite",
        "intervalle_confiance": f"Wald à {100 * ic:g} % sur le coefficient, puis exponentielle pour l'odds ratio (confint.default de R)",
        "tests_variables": "rapport de vraisemblance de type II (car::Anova)",
        "effets_marginaux": "effets marginaux moyens (statsmodels get_margeff, at='overall') ; variation discrète 0→1 pour les indicatrices",
        "colinearite": "GVIF de Fox & Monette (car::vif)",
    }
    evenements = []
    for var, eff in plan.effectifs.items():
        c = en_categorie(pd.Series(X[var]).reset_index(drop=True))[plan.garde]
        for m, nm in eff.items():
            evenements.append({"variable": var, "modalite": m, "n": nm, "n_cible": int(y01[(c == m).to_numpy()].sum())})
    epp = min(n1, n0) / (k - 1)
    base = {
        "type": "logistique",
        "n": n, "n_exclus": plan.n_exclus, "exclus_par_variable": plan.exclus_par_variable,
        "y": {"nom": y.name, "modalite_cible": cible, "modalite_reference": reste, "n_cible": n1, "n_reference": n0,
              "part_cible": n1 / n},
        "references": plan.references, "niveau_ic": ic,
    }

    fit, separation, converge = _ajuster_logit(y01, plan.X)
    av = av_y + _avertissements_communs(plan, n, k, [])
    vides = [e for e in evenements if e["n_cible"] == 0 or e["n_cible"] == e["n"]]
    if vides:
        av.append("Modalité(s) où tous les individus ont la même valeur de y (cause classique de séparation) : "
                  + ", ".join(f"{e['variable']} = {e['modalite']} ({e['n_cible']}/{e['n']})" for e in vides) + ".")
    if separation:
        av.append("Séparation (quasi) complète détectée : une combinaison de prédicteurs prédit parfaitement y pour une partie "
                  "des individus. Les coefficients concernés et leurs erreurs-types tendent vers l'infini et ne sont pas "
                  "interprétables. Pistes : regrouper des modalités rares, retirer la variable en cause, ou réduire le modèle.")
    if fit is None:
        return nettoyer({**base, "termes": [], "tests_variables": [], "ajustement": None, "classement": None,
                         "effets_marginaux": [],
                         "diagnostics": {"vif": [], "effectifs_modalites": plan.effectifs, "evenements_par_modalite": evenements,
                                         "evenements_par_parametre": epp, "separation": True, "convergence": False},
                         "methode": methode, "avertissements": av + ["L'estimation a échoué (séparation parfaite) : aucun coefficient fourni."]})
    if not converge:
        av.append("L'algorithme n'a pas convergé : résultats à ne pas utiliser en l'état.")

    icf = fit.conf_int(alpha=1 - ic)
    termes = _lignes_termes(plan, fit.params, fit.bse, fit.tvalues, fit.pvalues, icf, exponentielle=True)
    for l in termes:
        ev = next((e for e in evenements if e["variable"] == l["variable"] and e["modalite"] == l["modalite"]), None)
        if ev:
            l["n_cible"] = ev["n_cible"]

    deviance = float(-2 * fit.llf)
    tests = []
    for t in plan.termes:
        sans, avec = _sous_modeles_type2(plan, t)
        d0 = _deviance_logit(y01, plan.X[sans])
        d1 = deviance if len(avec) == k else _deviance_logit(y01, plan.X[avec])
        if d0 is None or d1 is None:
            tests.append({"terme": t["nom"], "ddl": t["ddl"], "stat": None, "p": None, "test": "rapport de vraisemblance (non calculable)"})
            continue
        lr = max(0.0, d0 - d1)
        tests.append({"terme": t["nom"], "ddl": t["ddl"], "stat": lr, "p": float(stats.chi2.sf(lr, t["ddl"])),
                      "test": "rapport de vraisemblance de type II"})

    ll, ll0 = float(fit.llf), float(fit.llnull)
    lr_global = 2 * (ll - ll0)
    ajustement = {
        "log_vraisemblance": ll, "log_vraisemblance_nulle": ll0,
        "deviance": deviance, "deviance_nulle": -2 * ll0,
        "aic": -2 * ll + 2 * k, "bic": -2 * ll + math.log(n) * k,
        "pseudo_r2_mcfadden": 1 - ll / ll0,
        "pseudo_r2_nagelkerke": (1 - math.exp(2 * (ll0 - ll) / n)) / (1 - math.exp(2 * ll0 / n)),
        "lr_chi2": lr_global, "lr_ddl": k - 1, "lr_p": float(stats.chi2.sf(lr_global, k - 1)),
    }

    proba = np.asarray(fit.predict(plan.X))
    rangs = stats.rankdata(proba)
    auc = (rangs[y01 == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
    classement = {
        "seuil": 0.5, "taux_bons_classements": float(((proba >= 0.5) == (y01 == 1)).mean()),
        "taux_modele_nul": max(n1, n0) / n, "auc": float(auc),
        "vrais_positifs": int(((proba >= 0.5) & (y01 == 1)).sum()), "faux_positifs": int(((proba >= 0.5) & (y01 == 0)).sum()),
        "vrais_negatifs": int(((proba < 0.5) & (y01 == 0)).sum()), "faux_negatifs": int(((proba < 0.5) & (y01 == 1)).sum()),
        "note": "Indicateurs descriptifs calculés sur les données qui ont servi à l'estimation (donc optimistes). "
                "Un modèle explicatif ne vise pas à classer : un faible pouvoir de classement n'invalide pas les associations estimées.",
    }

    ame = []
    if any(t["type"] == "interaction" for t in plan.termes):
        av.append("Effets marginaux moyens non calculés : avec une interaction, l'effet d'une variable dépend de l'autre "
                  "et ne se résume pas à un seul nombre.")
    elif not separation:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                me = fit.get_margeff(at="overall", method="dydx", dummy=True)
                ic_me = me.conf_int(alpha=1 - ic)
            noms_me = [c for c in plan.X.columns if c != CONSTANTE]
            for i, col in enumerate(noms_me):
                info = plan.colonnes[col]
                ame.append({"terme": col, "variable": info["variable"], "modalite": info["modalite"],
                            "ame": float(me.margeff[i]), "se": float(me.margeff_se[i]), "p": float(me.pvalues[i]),
                            "ic_bas": float(ic_me[i, 0]), "ic_haut": float(ic_me[i, 1]),
                            "type": "variation discrète (modalité vs référence)" if info["modalite"] is not None else "dérivée moyenne (pour +1 unité)"})
        except Exception as e:  # pragma: no cover - dépend de statsmodels
            av.append(f"Effets marginaux non calculables ({e}).")

    gvif = _gvif(np.asarray(fit.cov_params()), list(plan.X.columns), plan)
    forts = [g for g in gvif if g["gvif_ajuste"] ** 2 > 5]
    if forts:
        av.append("Colinéarité marquée (GVIF ajusté² > 5) pour : " + ", ".join(g["terme"] for g in forts) + ".")
    if epp < 10:
        av.append(f"Seulement {epp:.1f} événements par paramètre (la modalité la moins fréquente de y compte {min(n1, n0)} individus "
                  f"pour {k - 1} paramètres). En dessous d'environ 10, coefficients biaisés et intervalles peu fiables : réduire le modèle.")
    if min(n1, n0) < 10:
        av.append(f"La modalité la moins fréquente de y ne compte que {min(n1, n0)} individus : le modèle est très fragile.")

    return nettoyer({
        **base,
        "termes": termes, "tests_variables": tests, "ajustement": ajustement, "classement": classement,
        "effets_marginaux": ame,
        "diagnostics": {"vif": gvif, "effectifs_modalites": plan.effectifs, "evenements_par_modalite": evenements,
                        "evenements_par_parametre": epp, "separation": separation, "convergence": converge},
        "methode": methode, "avertissements": av,
    })


# =========================================================================== régression multinomiale

def regression_multinomiale(y: pd.Series, X: pd.DataFrame, *, reference_y=None, references: dict | None = None,
                            ic: float = 0.95) -> dict:
    """Régression logistique multinomiale (y qualitative non ordonnée à plus de deux modalités).

    Estime, pour chaque modalité de y autre que `reference_y` (par défaut la première),
    un jeu de coefficients décrivant le logarithme du rapport P(y = modalité) / P(y = référence).
    exp(coef) est un « rapport de risques relatifs » (RRR) : il se lit comme un odds ratio,
    mais *relativement à la modalité de référence de y* seulement.

    Équivalent de nnet::multinom dans R (mêmes coefficients à la précision de l'optimiseur).
    `tests_variables` : rapport de vraisemblance, chaque variable retirée tour à tour
    (ddl = nombre de coefficients de la variable × (nombre de modalités de y − 1)).
    """
    y = pd.Series(y) if not isinstance(y, pd.Series) else y
    c = en_categorie(y)
    code_complet = pd.Series(np.where(c.notna(), 0.0, np.nan), name=y.name)   # sert seulement au repérage des manquants
    plan = _preparer(code_complet, X, references, None)
    cy = c.reset_index(drop=True)[plan.garde].cat.remove_unused_categories()
    modalites = list(cy.cat.categories)
    if len(modalites) < 3:
        raise ValueError("La variable à expliquer doit avoir au moins trois modalités observées (sinon : régression logistique binaire).")
    ref = modalites[0] if reference_y is None else reference_y
    if ref not in modalites:
        raise ValueError(f"Modalité de référence {ref!r} absente de la variable à expliquer (modalités : {modalites}).")
    ordre = [ref] + [m for m in modalites if m != ref]
    codes = cy.cat.reorder_categories(ordre).cat.codes.to_numpy()
    n, k = plan.X.shape
    J = len(ordre)

    def ajuster(Xm: pd.DataFrame):
        with warnings.catch_warnings(record=True) as captures:
            warnings.simplefilter("always")
            f = sm.MNLogit(codes, Xm).fit(disp=0, maxiter=500, method="newton")
        return f, captures

    av = _avertissements_communs(plan, n, k, [])
    try:
        fit, captures = ajuster(plan.X)
    except Exception as e:
        raise ValueError(f"L'estimation du modèle multinomial a échoué ({e}). Cause fréquente : modalité de y ou de X trop rare (séparation).")
    params = np.asarray(fit.params)       # (k, J-1)
    bse = np.asarray(fit.bse)
    separation = bool(np.any(np.abs(params[1:]) > 15) or not np.all(np.isfinite(bse)) or np.any(bse > 500))
    converge = bool(fit.mle_retvals.get("converged", True))
    z = stats.norm.ppf(0.5 + ic / 2)

    termes = []
    for j, modalite in enumerate(ordre[1:]):
        coef = pd.Series(params[:, j], index=plan.X.columns)
        se = pd.Series(bse[:, j], index=plan.X.columns)
        stat = coef / se
        p = pd.Series(2 * stats.norm.sf(np.abs(stat)), index=plan.X.columns)
        icf = pd.DataFrame({0: coef - z * se, 1: coef + z * se})
        for l in _lignes_termes(plan, coef, se, stat, p, icf, exponentielle=True, nom_exp="rrr", prefixe_exp="rrr"):
            termes.append({"modalite_y": modalite, **l})

    ll, ll0 = float(fit.llf), float(fit.llnull)
    n_param = k * (J - 1)
    tests = []
    for t in plan.termes:
        sans = [col for col in plan.X.columns if col not in t["colonnes"]]
        try:
            f0, _ = ajuster(plan.X[sans])
            lr = max(0.0, 2 * (ll - float(f0.llf)))
            ddl = t["ddl"] * (J - 1)
            tests.append({"terme": t["nom"], "ddl": ddl, "stat": lr, "p": float(stats.chi2.sf(lr, ddl)), "test": "rapport de vraisemblance"})
        except Exception:
            tests.append({"terme": t["nom"], "ddl": t["ddl"] * (J - 1), "stat": None, "p": None, "test": "rapport de vraisemblance (non calculable)"})

    effectifs_y = {m: int((cy == m).sum()) for m in ordre}
    proba = np.asarray(fit.predict(plan.X))
    if separation:
        av.append("Séparation (quasi) complète probable : certains coefficients sont démesurés et non interprétables. "
                  "Regrouper des modalités rares de y ou des prédicteurs.")
    if not converge:
        av.append("L'algorithme n'a pas convergé : résultats à ne pas utiliser en l'état.")
    petit = min(effectifs_y.values())
    if petit / (k - 1) < 10:
        av.append(f"La modalité la plus rare de y compte {petit} individus pour {k - 1} paramètres par équation "
                  "(moins de 10 par paramètre) : estimations fragiles.")
    av.append("Les coefficients comparent chaque modalité de y à la référence « " + str(ref) + " » : changer de référence change "
              "tous les coefficients (mais pas le modèle ni ses probabilités prédites).")

    return nettoyer({
        "type": "multinomiale",
        "n": n, "n_exclus": plan.n_exclus, "exclus_par_variable": {**plan.exclus_par_variable},
        "y": {"nom": y.name, "modalites": ordre, "modalite_reference": ref, "effectifs": effectifs_y},
        "termes": termes, "tests_variables": tests,
        "ajustement": {
            "log_vraisemblance": ll, "log_vraisemblance_nulle": ll0, "deviance": -2 * ll,
            "n_parametres": n_param, "aic": -2 * ll + 2 * n_param, "bic": -2 * ll + math.log(n) * n_param,
            "pseudo_r2_mcfadden": 1 - ll / ll0,
            "lr_chi2": 2 * (ll - ll0), "lr_ddl": (k - 1) * (J - 1), "lr_p": float(stats.chi2.sf(2 * (ll - ll0), (k - 1) * (J - 1))),
        },
        "classement": {"taux_bons_classements": float((proba.argmax(axis=1) == codes).mean()),
                       "taux_modele_nul": max(effectifs_y.values()) / n,
                       "note": "Descriptif, calculé sur les données d'estimation (optimiste)."},
        "diagnostics": {"effectifs_modalites": plan.effectifs, "separation": separation, "convergence": converge},
        "references": plan.references, "niveau_ic": ic,
        "methode": {
            "nom": "Régression logistique multinomiale",
            "moteur": "statsmodels.MNLogit (maximum de vraisemblance, Newton-Raphson)",
            "valeurs_manquantes": "exclusion des individus incomplets (listwise)",
            "intervalle_confiance": f"Wald à {100 * ic:g} %",
            "tests_variables": "rapport de vraisemblance (variable retirée de toutes les équations)",
        },
        "avertissements": av,
    })
