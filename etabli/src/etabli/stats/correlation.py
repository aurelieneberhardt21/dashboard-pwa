"""Corrélations entre variables quantitatives (ou ordinales codées numériquement).

Moteur : scipy.stats (pearsonr, spearmanr, kendalltau). Validé contre `cor.test` et
`p.adjust` de R (tests/test_bivarie.py).

Trois coefficients :
- Pearson : liaison linéaire ; sensible aux valeurs extrêmes ; suppose des variables d'intervalle ;
- Spearman : Pearson calculé sur les rangs → liaison monotone ; adapté aux échelles ordinales ;
- Kendall (tau-b) : fondé sur les paires concordantes / discordantes, corrigé des ex æquo ;
  plus robuste avec de petits effectifs et beaucoup d'ex æquo (échelles en 4-5 points),
  mais ses valeurs sont mécaniquement plus faibles que celles de Spearman.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
from scipy import stats

from .univarie import ajuster_p, nettoyer

__all__ = ["matrice_correlation", "correlation_paire"]

_NOMS = {"pearson": "r de Pearson", "spearman": "rho de Spearman", "kendall": "tau-b de Kendall"}


def correlation_paire(a: np.ndarray, b: np.ndarray, methode: str = "pearson", ic: float = 0.95) -> dict:
    """Corrélation entre deux vecteurs numériques sans valeurs manquantes.

    p-valeurs : Pearson et Spearman par la loi de Student à n−2 ddl (pour Spearman, c'est
    l'approximation de cor.test(exact = FALSE)) ; Kendall par approximation normale avec
    correction des ex æquo. Intervalle de confiance par la transformation z de Fisher
    (erreur-type 1/√(n−3)) : exact pour Pearson sous normalité bivariée, approché pour
    Spearman, non fourni pour Kendall.
    """
    n = len(a)
    vide = {"r": None, "n": n, "ic_bas": None, "ic_haut": None, "p": None}
    if n < 3 or np.all(a == a[0]) or np.all(b == b[0]):
        return vide
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if methode == "pearson":
            res = stats.pearsonr(a, b)
        elif methode == "spearman":
            res = stats.spearmanr(a, b)
        elif methode == "kendall":
            res = stats.kendalltau(a, b, variant="b", method="asymptotic")
        else:
            raise ValueError(f"Méthode inconnue : {methode!r} (attendu : pearson, spearman, kendall)")
    r, p = float(res.statistic), float(res.pvalue)
    bas = haut = None
    if methode in ("pearson", "spearman") and n > 3 and abs(r) < 1:
        z = math.atanh(r)
        demi = stats.norm.ppf(0.5 + ic / 2) / math.sqrt(n - 3)
        bas, haut = math.tanh(z - demi), math.tanh(z + demi)
    return {"r": r, "n": n, "ic_bas": bas, "ic_haut": haut, "p": p}


def matrice_correlation(X: pd.DataFrame, *, methode: str = "pearson", ajustement: str = "holm", ic: float = 0.95) -> dict:
    """Matrice de corrélations avec effectifs par paire, IC et p ajustées.

    Les valeurs manquantes sont exclues *par paire* (« pairwise ») : chaque coefficient
    utilise tous les individus renseignés sur les deux variables, donc les effectifs
    peuvent différer d'une case à l'autre (voir `matrice_n`).

    Avec k variables on réalise k(k−1)/2 tests : `p_ajustee` corrige cette multiplicité
    (`ajustement` = "holm", "bh" ou "aucun").
    """
    if methode not in _NOMS:
        raise ValueError(f"Méthode inconnue : {methode!r} (attendu : pearson, spearman, kendall)")
    X = pd.DataFrame(X).reset_index(drop=True)
    noms = [str(c) for c in X.columns]
    D = X.apply(pd.to_numeric, errors="coerce").astype(float)
    k = len(noms)
    avertissements: list[str] = []

    mat_r = np.full((k, k), np.nan)
    mat_n = np.zeros((k, k), dtype=int)
    mat_p = np.full((k, k), np.nan)
    paires = []
    for i in range(k):
        xi = D.iloc[:, i]
        mat_n[i, i] = int(xi.notna().sum())
        mat_r[i, i] = 1.0 if mat_n[i, i] > 1 and xi.nunique() > 1 else np.nan
        for j in range(i + 1, k):
            xj = D.iloc[:, j]
            ok = xi.notna() & xj.notna()
            res = correlation_paire(xi[ok].to_numpy(), xj[ok].to_numpy(), methode, ic)
            mat_n[i, j] = mat_n[j, i] = res["n"]
            if res["r"] is not None:
                mat_r[i, j] = mat_r[j, i] = res["r"]
                mat_p[i, j] = mat_p[j, i] = res["p"]
            paires.append({"x": noms[i], "y": noms[j], **res})

    ajustees = ajuster_p([p["p"] for p in paires], ajustement)
    mat_pa = np.full((k, k), np.nan)
    indice = 0
    for i in range(k):
        for j in range(i + 1, k):
            paires[indice]["p_ajustee"] = ajustees[indice]
            if ajustees[indice] is not None:
                mat_pa[i, j] = mat_pa[j, i] = ajustees[indice]
            indice += 1
    n_tests = sum(p["p"] is not None for p in paires)

    non_calculables = [f"{p['x']} × {p['y']}" for p in paires if p["r"] is None]
    if non_calculables:
        avertissements.append("Corrélations non calculables (moins de 3 paires complètes ou variable constante) : "
                              + ", ".join(non_calculables) + ".")
    faibles = [f"{p['x']} × {p['y']} (n = {p['n']})" for p in paires if p["r"] is not None and p["n"] < 30]
    if faibles:
        avertissements.append("Paires à effectif faible (< 30), coefficients instables : " + ", ".join(faibles) + ".")
    effectifs = {p["n"] for p in paires}
    if len(effectifs) > 1:
        avertissements.append(
            f"Les effectifs varient selon les paires (de {min(effectifs)} à {max(effectifs)}) à cause des valeurs manquantes : "
            "les coefficients ne portent pas tous sur les mêmes individus."
        )
    if n_tests > 1:
        avertissements.append(f"Comparaisons multiples : {n_tests} corrélations testées ; les p ajustées en tiennent compte, pas les p brutes.")

    return nettoyer({
        "methode_correlation": methode,
        "coefficient": _NOMS[methode],
        "variables": noms,
        "matrice": mat_r, "matrice_n": mat_n, "matrice_p": mat_p, "matrice_p_ajustee": mat_pa,
        "paires": paires,
        "n_tests": n_tests,
        "ajustement": ajustement,
        "niveau_ic": ic,
        "methode": {
            "nom": f"Matrice de corrélations ({_NOMS[methode]})",
            "valeurs_manquantes": "exclusion par paire (pairwise)",
            "test": {"pearson": "loi de Student à n−2 ddl", "spearman": "loi de Student à n−2 ddl sur le rho (cor.test exact = FALSE)",
                     "kendall": "approximation normale avec correction des ex æquo (cor.test exact = FALSE)"}[methode],
            "intervalle_confiance": "transformation z de Fisher, erreur-type 1/√(n−3)" if methode != "kendall" else "non fourni pour le tau de Kendall",
            "ajustement": {"holm": "Holm (contrôle du risque d'au moins un faux positif)", "bh": "Benjamini-Hochberg (taux de fausses découvertes)",
                           "bonferroni": "Bonferroni", "aucun": "aucun"}.get(ajustement, ajustement),
            "moteur": "scipy.stats",
        },
        "avertissements": avertissements,
    })
