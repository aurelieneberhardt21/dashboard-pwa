"""Statistiques univariées : tri à plat d'une variable qualitative, résumé d'une variable quantitative.

Ce module contient aussi les petits outils communs aux modules bivariés
(`nettoyer`, `ic_wilson`, `ajuster_p`, `est_quanti`, `en_categorie`).

Conventions communes à tout `etabli.stats` :
- les entrées sont des objets pandas déjà préparés par l'appelant ; les valeurs
  manquantes (NaN) sont simplement exclues ici et comptées dans `n_manquants` /
  `n_exclus` (la distinction entre « non concerné », « abandon » et « non-réponse »
  est faite en amont, pas dans ce module) ;
- les sorties sont des dictionnaires 100 % JSON-sérialisables (NaN et infinis → None),
  avec toujours `methode` (ce qui a été calculé, avec quels paramètres) et
  `avertissements` (phrases en français destinées à l'utilisateur).

Moteurs : numpy / pandas pour les décomptes, scipy.stats pour les lois,
statsmodels pour l'intervalle de Wilson et l'ajustement des p-valeurs.
Résultats validés contre R (voir tests/reference/bivarie.R et tests/test_bivarie.py).
"""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import proportion_confint

__all__ = ["tri_a_plat", "resume_quanti", "nettoyer", "ic_wilson", "ajuster_p", "est_quanti", "en_categorie"]


# --------------------------------------------------------------------------- outils communs

def nettoyer(objet: Any) -> Any:
    """Convertit récursivement un résultat en types Python natifs sérialisables en JSON.

    numpy → natif ; NaN, NA pandas et ±inf → None ; clés de dictionnaire → str.
    """
    if objet is None or isinstance(objet, (str, bool)):
        return objet
    if isinstance(objet, dict):
        return {str(k): nettoyer(v) for k, v in objet.items()}
    if isinstance(objet, (list, tuple, set)):
        return [nettoyer(v) for v in objet]
    if isinstance(objet, np.ndarray):
        return [nettoyer(v) for v in objet.tolist()]
    if isinstance(objet, (pd.Series, pd.Index)):
        return [nettoyer(v) for v in objet.tolist()]
    if isinstance(objet, np.bool_):
        return bool(objet)
    if isinstance(objet, (int, np.integer)):
        return int(objet)
    if isinstance(objet, (float, np.floating)):
        v = float(objet)
        return v if math.isfinite(v) else None
    if objet is pd.NA or objet is pd.NaT:
        return None
    if isinstance(objet, pd.Timestamp):
        return objet.isoformat()
    return str(objet)


def ic_wilson(k: float, n: float, niveau: float = 0.95) -> tuple[float | None, float | None]:
    """Intervalle de confiance de Wilson (score) pour une proportion k/n.

    Identique à `prop.test(k, n, correct = FALSE)$conf.int` de R. Préféré à l'intervalle
    de Wald (p ± 1,96·√(p(1-p)/n)) car il reste valide pour les petits effectifs et les
    proportions proches de 0 ou de 1 — situation courante avec des catégories rares.
    """
    if n is None or n <= 0:
        return None, None
    bas, haut = proportion_confint(k, n, alpha=1 - niveau, method="wilson")
    return float(max(0.0, bas)), float(min(1.0, haut))


def ajuster_p(p: Iterable[float | None], methode: str = "holm") -> list[float | None]:
    """Ajuste une famille de p-valeurs pour les comparaisons multiples.

    `methode` : "holm" (contrôle du risque d'au moins un faux positif, FWER — toujours valide),
    "bh" (Benjamini-Hochberg : contrôle du taux de fausses découvertes, FDR — moins sévère),
    "bonferroni" ou "aucun". Les p manquantes (None/NaN) sont laissées de côté : elles ne
    comptent pas dans le nombre de tests. Équivalent de `p.adjust` de R.
    """
    valeurs = [None if (v is None or (isinstance(v, float) and math.isnan(v))) else float(v) for v in p]
    indices = [i for i, v in enumerate(valeurs) if v is not None]
    if methode in ("aucun", None) or not indices:
        return valeurs
    nom = {"holm": "holm", "bh": "fdr_bh", "bonferroni": "bonferroni"}.get(methode)
    if nom is None:
        raise ValueError(f"Méthode d'ajustement inconnue : {methode!r} (attendu : holm, bh, bonferroni, aucun)")
    ajustees = multipletests([valeurs[i] for i in indices], method=nom)[1]
    sortie: list[float | None] = [None] * len(valeurs)
    for i, v in zip(indices, ajustees):
        sortie[i] = float(min(1.0, v))
    return sortie


def est_quanti(s: pd.Series) -> bool:
    """Vrai si la série est numérique (hors booléens et catégories)."""
    return (
        pd.api.types.is_numeric_dtype(s.dtype)
        and not pd.api.types.is_bool_dtype(s.dtype)
        and not isinstance(s.dtype, pd.CategoricalDtype)
    )


def en_categorie(s: pd.Series) -> pd.Series:
    """Renvoie la série sous forme `Categorical` (ordre déclaré conservé, sinon ordre trié)."""
    if isinstance(s.dtype, pd.CategoricalDtype):
        return s
    valeurs = s.dropna().unique().tolist()
    try:
        valeurs = sorted(valeurs)
    except TypeError:
        valeurs = sorted(valeurs, key=str)
    return s.astype(pd.CategoricalDtype(categories=valeurs))


def _serie(s: Any, nom: str = "variable") -> pd.Series:
    if not isinstance(s, pd.Series):
        s = pd.Series(s, name=nom)
    return s


# --------------------------------------------------------------------------- tri à plat

def tri_a_plat(s: pd.Series, *, ic: float = 0.95) -> dict:
    """Tri à plat d'une variable qualitative.

    Pour chaque modalité : effectif, pourcentage des réponses valides et intervalle de
    confiance de Wilson. Les catégories déclarées mais vides sont conservées (effectif 0).
    Si la variable est ordonnée, le pourcentage cumulé est ajouté.

    L'intervalle de confiance n'a de sens que si les répondants peuvent être vus comme un
    échantillon aléatoire de la population visée ; il quantifie l'incertitude
    d'échantillonnage, pas les biais de recrutement ou de non-réponse.
    """
    s = _serie(s)
    cat = en_categorie(s)
    n_total = int(len(cat))
    valides = cat.dropna()
    n = int(len(valides))
    ordonnee = bool(cat.dtype.ordered)
    decompte = valides.value_counts(sort=False).reindex(cat.dtype.categories, fill_value=0)

    modalites = []
    cumul = 0
    for modalite, k in decompte.items():
        k = int(k)
        cumul += k
        bas, haut = ic_wilson(k, n, ic)
        ligne = {
            "modalite": modalite,
            "n": k,
            "pct": 100 * k / n if n else None,
            "ic_bas": None if bas is None else 100 * bas,
            "ic_haut": None if haut is None else 100 * haut,
        }
        if ordonnee:
            ligne["pct_cumule"] = 100 * cumul / n if n else None
        modalites.append(ligne)

    maxi = int(decompte.max()) if n else 0
    mode = [m for m, k in decompte.items() if k == maxi] if n else []

    avertissements = []
    if n == 0:
        avertissements.append("Aucune réponse valide pour cette variable.")
    elif n < 30:
        avertissements.append(
            f"Effectif faible (n = {n}) : les pourcentages sont instables, voir la largeur des intervalles de confiance."
        )
    rares = [str(m) for m, k in decompte.items() if 0 < k < 5]
    if rares:
        avertissements.append(
            "Modalités à très faible effectif (< 5) : " + ", ".join(rares)
            + ". Elles sont fragiles dans les croisements et potentiellement réidentifiantes."
        )
    vides = [str(m) for m, k in decompte.items() if k == 0]
    if vides:
        avertissements.append("Modalités déclarées mais sans réponse : " + ", ".join(vides) + ".")

    return nettoyer({
        "type": "quali",
        "nom": s.name,
        "n": n,
        "n_manquants": n_total - n,
        "n_total": n_total,
        "ordonnee": ordonnee,
        "modalites": modalites,
        "mode": mode,
        "niveau_ic": ic,
        "methode": {
            "nom": "Tri à plat",
            "pourcentages": "calculés sur les réponses valides (valeurs manquantes exclues)",
            "intervalle_confiance": f"Wilson (score) à {100 * ic:g} %, équivalent de prop.test(correct = FALSE) dans R",
            "moteur": "statsmodels.stats.proportion.proportion_confint(method='wilson')",
        },
        "avertissements": avertissements,
    })


# --------------------------------------------------------------------------- résumé quantitatif

def _bornes_histogramme(x: np.ndarray, classes: int | list[float] | None) -> np.ndarray:
    """Bornes des classes de l'histogramme.

    - `classes` entier : ce nombre de classes d'amplitude égale entre min et max ;
    - `classes` liste : bornes imposées (les valeurs hors bornes ne sont pas comptées) ;
    - None : règle de Freedman-Diaconis (amplitude = 2·EIQ·n^(-1/3)), bornée entre 5 et 30 classes.
    """
    if isinstance(classes, (list, tuple, np.ndarray)):
        return np.asarray(sorted(float(b) for b in classes), dtype=float)
    mini, maxi = float(x.min()), float(x.max())
    if mini == maxi:
        return np.array([mini - 0.5, maxi + 0.5])
    if classes is not None:
        k = max(1, int(classes))
    else:
        k = len(np.histogram_bin_edges(x, bins="fd")) - 1
        k = int(min(30, max(5, k)))
    return np.linspace(mini, maxi, k + 1)


def resume_quanti(s: pd.Series, *, classes: int | list[float] | None = None, ic: float = 0.95) -> dict:
    """Résumé d'une variable quantitative.

    n, moyenne, écart-type (dénominateur n-1), médiane, quartiles et déciles extrêmes
    (méthode 7 de R : interpolation linéaire, celle de `quantile()` par défaut), min, max,
    intervalle de confiance de la moyenne (loi de Student), asymétrie et aplatissement
    corrigés du biais (G1 et G2, conventions SAS/SPSS), histogramme.

    Classes de l'histogramme : fermées à gauche, ouvertes à droite, sauf la dernière qui
    inclut sa borne supérieure (convention de numpy.histogram).
    """
    s = _serie(s)
    num = pd.to_numeric(s, errors="coerce").astype(float)
    n_total = int(len(num))
    x = num.dropna().to_numpy()
    n = int(len(x))
    avertissements: list[str] = []
    methode = {
        "nom": "Résumé d'une variable quantitative",
        "ecart_type": "dénominateur n - 1",
        "quantiles": "interpolation linéaire (type 7 de R, défaut de quantile())",
        "intervalle_confiance": f"moyenne ± t(n-1) × erreur-type, niveau {100 * ic:g} %",
        "asymetrie": "coefficients G1 et G2 corrigés du biais (scipy.stats.skew/kurtosis, bias=False)",
        "histogramme": "bornes imposées" if isinstance(classes, (list, tuple, np.ndarray))
        else (f"{classes} classes d'amplitude égale" if classes is not None
              else "règle de Freedman-Diaconis, entre 5 et 30 classes"),
    }
    base = {"type": "quanti", "nom": s.name, "n": n, "n_manquants": n_total - n, "n_total": n_total, "niveau_ic": ic}
    if n == 0:
        return nettoyer({**base, "methode": methode, "avertissements": ["Aucune valeur numérique valide."]})

    moyenne = float(x.mean())
    ecart_type = float(x.std(ddof=1)) if n > 1 else None
    q10, q25, q50, q75, q90 = (float(v) for v in np.quantile(x, [0.10, 0.25, 0.5, 0.75, 0.90]))
    if n > 1 and ecart_type and ecart_type > 0:
        demi = stats.t.ppf(0.5 + ic / 2, n - 1) * ecart_type / math.sqrt(n)
        ic_bas, ic_haut = moyenne - demi, moyenne + demi
    else:
        ic_bas = ic_haut = None
    asymetrie = float(stats.skew(x, bias=False)) if n > 2 and ecart_type else None
    aplatissement = float(stats.kurtosis(x, bias=False)) if n > 3 and ecart_type else None

    bornes = _bornes_histogramme(x, classes)
    effectifs, bornes = np.histogram(x, bins=bornes)
    hors_bornes = n - int(effectifs.sum())
    if hors_bornes:
        avertissements.append(f"{hors_bornes} valeur(s) en dehors des bornes imposées ne figurent pas dans l'histogramme.")
    if n < 30:
        avertissements.append(
            f"Effectif faible (n = {n}) : moyenne et écart-type sensibles aux valeurs extrêmes ; regarder aussi médiane et quartiles."
        )
    if asymetrie is not None and abs(asymetrie) > 1:
        avertissements.append(
            f"Distribution nettement asymétrique (asymétrie = {asymetrie:.2f}) : la médiane résume mieux la tendance centrale que la moyenne."
        )
    n_distinctes = int(len(np.unique(x)))

    return nettoyer({
        **base,
        "moyenne": moyenne,
        "ecart_type": ecart_type,
        "variance": None if ecart_type is None else ecart_type ** 2,
        "erreur_type": None if ecart_type is None else ecart_type / math.sqrt(n),
        "ic_bas": ic_bas,
        "ic_haut": ic_haut,
        "min": float(x.min()),
        "d1": q10,
        "q1": q25,
        "mediane": q50,
        "q3": q75,
        "d9": q90,
        "max": float(x.max()),
        "ecart_interquartile": q75 - q25,
        "asymetrie": asymetrie,
        "aplatissement": aplatissement,
        "n_valeurs_distinctes": n_distinctes,
        "histogramme": {"bornes": bornes, "effectifs": effectifs},
        "methode": methode,
        "avertissements": avertissements,
    })
