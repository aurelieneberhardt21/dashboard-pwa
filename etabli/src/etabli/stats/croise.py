"""Statistiques bivariées : tableau croisé, comparaison de groupes, questions à choix multiples.

Moteurs : scipy.stats (chi², Fisher exact 2×2, tables aléatoires à marges fixées, lois,
Kruskal-Wallis, Mann-Whitney, Levene, Kendall) et statsmodels (ANOVA de Welch). Sont
écrits ici, à partir de leurs formules, les indicateurs absents de ces bibliothèques :
résidus ajustés, V de Cramér (brut, corrigé, intervalle de confiance), PEM de Cibois,
gamma de Goodman-Kruskal, tailles d'effet (eta², omega², epsilon², d, g).

Validation : chaque résultat est comparé à R dans tests/test_bivarie.py
(chisq.test, fisher.test, t.test, oneway.test, aov, kruskal.test, wilcox.test,
car::leveneTest, cor.test) ; le PEM, sans référence R installée, est vérifié sur un
exemple calculé à la main.

Philosophie : on donne d'abord les effectifs, les écarts et les tailles d'effet, puis
les p-valeurs. Aucun verdict automatique (« significatif » / « non significatif »).
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
from scipy import optimize, stats
from statsmodels.stats.oneway import anova_oneway

from .univarie import ajuster_p, en_categorie, ic_wilson, nettoyer

__all__ = ["tableau_croise", "comparer_groupes", "choix_multiples", "v_cramer", "pem"]

_EPS = 64 * np.finfo(float).eps  # même garde-fou numérique que R pour les p simulées


# =========================================================================== briques de calcul

def _chi2(obs: np.ndarray) -> tuple[float, int, float, np.ndarray]:
    """Chi² de Pearson sans correction : (statistique, ddl, p, effectifs théoriques)."""
    n = obs.sum()
    theo = np.outer(obs.sum(axis=1), obs.sum(axis=0)) / n
    chi2 = float(((obs - theo) ** 2 / theo).sum())
    ddl = (obs.shape[0] - 1) * (obs.shape[1] - 1)
    p = float(stats.chi2.sf(chi2, ddl)) if ddl > 0 else float("nan")
    return chi2, ddl, p, theo


def _ic_ncp(chi2: float, ddl: int, niveau: float) -> tuple[float, float]:
    """Intervalle de confiance du paramètre de non-centralité d'un chi² observé.

    On cherche les valeurs de non-centralité pour lesquelles le chi² observé se situe au
    quantile 1-α/2 (borne basse) puis α/2 (borne haute) de la loi du chi² non central.
    """
    a = (1 - niveau) / 2
    central = float(stats.chi2.cdf(chi2, ddl))

    def ecart(ncp: float, cible: float) -> float:
        return float(stats.ncx2.cdf(chi2, ddl, ncp)) - cible

    def racine(cible: float) -> float:
        if central < cible:  # même sans association, le chi² observé est en deçà du quantile : borne = 0
            return 0.0
        haut = max(10.0, 2 * chi2)
        while ecart(haut, cible) > 0 and haut < 1e9:
            haut *= 2
        return float(optimize.brentq(ecart, 1e-12, haut, args=(cible,), xtol=1e-12, rtol=1e-13))

    return racine(1 - a), racine(a)


def v_cramer(obs: np.ndarray, niveau: float = 0.95) -> dict:
    """V de Cramér d'un tableau d'effectifs (sans ligne ni colonne vide).

    - `v` : √(χ² / (n·(k-1))), k = min(lignes, colonnes). Varie de 0 (indépendance) à 1.
    - `v_corrige` : correction du biais de Bergsma (2013). Le V brut est biaisé vers le haut,
      d'autant plus que l'échantillon est petit et le tableau grand ; la version corrigée
      est préférable pour comparer des tableaux de tailles différentes.
    - intervalle de confiance du V brut par inversion du chi² non central
      (Smithson 2003 ; méthode « ncchisq » de DescTools::CramerV dans R).
    """
    obs = np.asarray(obs, dtype=float)
    n = obs.sum()
    r, c = obs.shape
    k = min(r, c)
    if k < 2 or n <= 1:
        return {"v": None, "v_corrige": None, "ic_bas": None, "ic_haut": None,
                "methode_ic": "non calculable (une seule ligne ou colonne)"}
    chi2, ddl, _, _ = _chi2(obs)
    phi2 = chi2 / n
    v = math.sqrt(phi2 / (k - 1))
    phi2_c = max(0.0, phi2 - (r - 1) * (c - 1) / (n - 1))
    r_c = r - (r - 1) ** 2 / (n - 1)
    c_c = c - (c - 1) ** 2 / (n - 1)
    denominateur = min(r_c - 1, c_c - 1)
    v_c = math.sqrt(phi2_c / denominateur) if denominateur > 0 else None
    bas, haut = _ic_ncp(chi2, ddl, niveau)
    return {
        "v": v,
        "v_corrige": v_c,
        "ic_bas": min(1.0, math.sqrt(bas / (n * (k - 1)))),
        "ic_haut": min(1.0, math.sqrt(haut / (n * (k - 1)))),
        "niveau_ic": niveau,
        "methode_ic": "inversion du chi² non central (Smithson 2003), porte sur le V brut",
    }


def _pem_local(obs: np.ndarray, theo: np.ndarray) -> np.ndarray:
    """PEM local de chaque cellule (en %, signé)."""
    n = obs.sum()
    lig = obs.sum(axis=1)[:, None]
    col = obs.sum(axis=0)[None, :]
    ecart = obs - theo
    maxi = np.minimum(lig, col) - theo                 # écart maximal positif : la cellule absorbe toute la plus petite marge
    mini = theo - np.maximum(0.0, lig + col - n)       # écart maximal négatif : la cellule se vide autant que les marges le permettent
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(ecart >= 0, 100 * ecart / maxi, 100 * ecart / mini)


def _ordre_premier_facteur(obs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Ordre des lignes et des colonnes selon le premier facteur de l'analyse des correspondances."""
    n = obs.sum()
    P = obs / n
    r = P.sum(axis=1)
    c = P.sum(axis=0)
    S = (P - np.outer(r, c)) / np.sqrt(np.outer(r, c))
    U, _, Vt = np.linalg.svd(S, full_matrices=False)
    return np.argsort(U[:, 0] / np.sqrt(r), kind="stable"), np.argsort(Vt[0] / np.sqrt(c), kind="stable")


def _pem_global(obs: np.ndarray, theo: np.ndarray) -> float:
    """PEM global : somme des écarts positifs observés / somme des écarts positifs du tableau
    de liaison maximale ayant les mêmes marges (lignes et colonnes réordonnées selon le
    premier facteur de l'AFC, puis remplissage « en diagonale »). En %.
    """
    ecarts_positifs = np.clip(obs - theo, 0, None).sum()
    if ecarts_positifs <= 1e-12:
        return 0.0
    ol, oc = _ordre_premier_facteur(obs)
    reste_l = obs.sum(axis=1)[ol].astype(float)
    reste_c = obs.sum(axis=0)[oc].astype(float)
    maximal = np.zeros((len(reste_l), len(reste_c)))
    i = j = 0
    while i < len(reste_l) and j < len(reste_c):
        m = min(reste_l[i], reste_c[j])
        maximal[i, j] = m
        reste_l[i] -= m
        reste_c[j] -= m
        if reste_l[i] <= 1e-9:
            i += 1
        elif reste_c[j] <= 1e-9:
            j += 1
    theo_ord = theo[np.ix_(ol, oc)]
    return float(100 * ecarts_positifs / np.clip(maximal - theo_ord, 0, None).sum())


def pem(obs: np.ndarray) -> dict:
    """Pourcentage de l'écart maximum (Cibois 1993) d'un tableau sans ligne/colonne vide.

    PEM local d'une cellule = écart à l'indépendance (observé − théorique) rapporté à l'écart
    maximum possible dans cette cellule compte tenu des marges :
      - attraction (écart ≥ 0) : maximum = min(total ligne, total colonne) − théorique ;
      - répulsion  (écart < 0) : maximum = théorique − max(0, total ligne + total colonne − n).
    Il vaut 0 à l'indépendance, +100 % si l'attraction est aussi forte que les marges le
    permettent, −100 % pour la répulsion maximale. Contrairement au chi², il ne dépend pas
    de l'effectif total : c'est une mesure d'intensité de la liaison, pas de sa
    « significativité ». Repères usuels de Cibois : un PEM local > 10 % signale une
    attraction notable, > 50 % une attraction exceptionnelle — à condition que les
    effectifs en jeu ne soient pas dérisoires.
    Algorithme identique à GDAtools::pem (R).
    """
    obs = np.asarray(obs, dtype=float)
    _, _, _, theo = _chi2(obs)
    return {"local": _pem_local(obs, theo), "global": _pem_global(obs, theo)}


def _simulation(obs: np.ndarray, n_sim: int, graine: int) -> dict:
    """p-valeurs par simulation de Monte-Carlo, à marges fixées (algorithme de Patefield).

    On tire `n_sim` tableaux ayant exactement les marges observées sous l'hypothèse
    d'indépendance, et on compte ceux qui sont au moins aussi « extrêmes » que l'observé :
      - `p_chi2` : selon la statistique du chi² (équivalent de chisq.test(simulate.p.value=TRUE)) ;
      - `p_fisher` : selon la probabilité du tableau (test de Fisher-Freeman-Halton,
        équivalent de fisher.test(simulate.p.value=TRUE)).
    p = (1 + nombre de tableaux simulés aussi extrêmes) / (n_sim + 1).
    Ces p ne supposent pas d'effectifs théoriques suffisants. Leur précision est limitée par
    le nombre de simulations (erreur-type ≈ √(p(1-p)/n_sim)).
    """
    lig = obs.sum(axis=1).astype(int)
    col = obs.sum(axis=0).astype(int)
    rng = np.random.default_rng(graine)
    tables = stats.random_table(lig, col, seed=rng).rvs(n_sim).astype(float)
    theo = np.outer(lig, col) / lig.sum()
    chi2_obs = ((obs - theo) ** 2 / theo).sum()
    chi2_sim = ((tables - theo) ** 2 / theo).sum(axis=(1, 2))
    p_chi2 = (1 + np.sum(chi2_sim >= chi2_obs * (1 - _EPS))) / (n_sim + 1)
    from scipy.special import gammaln
    logp_obs = -gammaln(obs + 1).sum()
    logp_sim = -gammaln(tables + 1).sum(axis=(1, 2))
    p_fisher = (1 + np.sum(logp_sim <= logp_obs + abs(logp_obs) * _EPS)) / (n_sim + 1)
    return {"p_chi2": float(p_chi2), "p_fisher": float(p_fisher), "n_simulations": int(n_sim), "graine": int(graine)}


def _conditions_chi2(theo: np.ndarray) -> dict:
    """Règle de Cochran : tous les effectifs théoriques ≥ 1 et au plus 20 % d'entre eux < 5."""
    n_cellules = int(theo.size)
    inf5 = int((theo < 5).sum())
    inf1 = int((theo < 1).sum())
    return {
        "min_theorique": float(theo.min()),
        "n_cellules": n_cellules,
        "n_theoriques_inf_5": inf5,
        "part_theoriques_inf_5": inf5 / n_cellules,
        "n_theoriques_inf_1": inf1,
        "respectees": bool(inf1 == 0 and inf5 / n_cellules <= 0.20),
        "regle": "règle de Cochran : tous les effectifs théoriques ≥ 1 et au plus 20 % d'entre eux < 5",
    }


def _paires(obs: np.ndarray) -> tuple[float, float, np.ndarray, np.ndarray]:
    """Paires concordantes (C) et discordantes (D) d'un tableau ordonné, et, pour chaque
    cellule, le nombre d'observations concordantes / discordantes avec elle."""
    r, c = obs.shape
    conc = np.zeros_like(obs, dtype=float)
    disc = np.zeros_like(obs, dtype=float)
    for i in range(r):
        for j in range(c):
            conc[i, j] = obs[:i, :j].sum() + obs[i + 1:, j + 1:].sum()
            disc[i, j] = obs[:i, j + 1:].sum() + obs[i + 1:, :j].sum()
    return float((obs * conc).sum() / 2), float((obs * disc).sum() / 2), conc, disc


def _ordinal(obs: np.ndarray, niveau: float) -> dict:
    """Mesures d'association pour deux variables ordonnées.

    - gamma de Goodman-Kruskal = (C − D) / (C + D) : ignore les ex æquo, donc tend à être
      plus élevé que le tau-b ; erreur-type asymptotique (ASE1, Agresti) pour l'intervalle
      de confiance et le test de Wald ;
    - tau-b de Kendall : corrige les ex æquo ; p asymptotique (équivalent de
      cor.test(method = "kendall", exact = FALSE) dans R).
    """
    C, D, conc, disc = _paires(obs)
    sortie: dict = {"paires_concordantes": C, "paires_discordantes": D}
    if C + D > 0:
        gamma = (C - D) / (C + D)
        psi = 2 * (D * conc - C * disc) / (C + D) ** 2
        ase = math.sqrt(float((obs * psi ** 2).sum()))
        z = stats.norm.ppf(0.5 + niveau / 2)
        sortie["gamma"] = {
            "valeur": gamma, "erreur_type": ase,
            "ic_bas": max(-1.0, gamma - z * ase), "ic_haut": min(1.0, gamma + z * ase),
            "p": float(2 * stats.norm.sf(abs(gamma) / ase)) if ase > 0 else None,
            "test": "Wald (gamma / erreur-type asymptotique)",
        }
    else:
        sortie["gamma"] = None
    # tau-b sur données individuelles reconstituées à partir du tableau
    li, co = np.nonzero(obs)
    poids = obs[li, co].astype(int)
    kt = stats.kendalltau(np.repeat(li, poids), np.repeat(co, poids), variant="b", method="asymptotic")
    sortie["tau_b"] = {"valeur": float(kt.statistic), "p": float(kt.pvalue),
                       "test": "approximation normale avec correction des ex æquo"}
    return sortie


def _deux_par_deux(obs: np.ndarray, niveau: float) -> dict:
    """Indicateurs propres aux tableaux 2×2."""
    a, b, c, d = obs[0, 0], obs[0, 1], obs[1, 0], obs[1, 1]
    lig, col = obs.sum(axis=1), obs.sum(axis=0)
    phi = (a * d - b * c) / math.sqrt(lig[0] * lig[1] * col[0] * col[1])
    correction = bool((obs == 0).any())
    aa, bb, cc, dd = (v + 0.5 for v in (a, b, c, d)) if correction else (a, b, c, d)
    rapport = aa * dd / (bb * cc)
    se = math.sqrt(1 / aa + 1 / bb + 1 / cc + 1 / dd)
    z = stats.norm.ppf(0.5 + niveau / 2)
    yates = stats.chi2_contingency(obs, correction=True)
    exact = stats.fisher_exact(obs.astype(int), alternative="two-sided")
    cond = stats.contingency.odds_ratio(obs.astype(int), kind="conditional")
    ic_cond = cond.confidence_interval(confidence_level=niveau)
    return {
        "phi": float(phi),
        "odds_ratio": {
            "valeur": float(rapport),
            "ic_bas": float(math.exp(math.log(rapport) - z * se)),
            "ic_haut": float(math.exp(math.log(rapport) + z * se)),
            "correction_cellule_nulle": correction,
            "methode": "rapport des produits croisés (a·d)/(b·c), IC de Wald sur le logarithme (Woolf)"
            + (" ; 0,5 ajouté à chaque cellule car une cellule est nulle (Haldane-Anscombe)" if correction else ""),
            "lecture": "rapport de cotes de la 1re colonne (vs la 2e) pour la 1re ligne par rapport à la 2e ligne",
        },
        "yates": {"statistique": float(yates.statistic), "p": float(yates.pvalue)},
        "fisher": {
            "p": float(exact.pvalue),
            "methode": "test exact de Fisher bilatéral (loi hypergéométrique)",
            "odds_ratio_conditionnel": float(cond.statistic),
            "ic_bas": float(ic_cond.low),
            "ic_haut": float(ic_cond.high),
        },
    }


def _table(x: pd.Series, y: pd.Series) -> tuple[pd.DataFrame, int]:
    """Tableau d'effectifs complet (toutes catégories déclarées) et nombre de paires exclues."""
    if not isinstance(x, pd.Series):
        x = pd.Series(x, name="x")
    if not isinstance(y, pd.Series):
        y = pd.Series(y, name="y")
    if len(x) != len(y):
        raise ValueError("Les deux variables doivent avoir la même longueur.")
    cx = en_categorie(x.reset_index(drop=True))
    cy = en_categorie(y.reset_index(drop=True))
    ok = cx.notna() & cy.notna()
    codes_x = cx[ok].cat.codes.to_numpy()
    codes_y = cy[ok].cat.codes.to_numpy()
    obs = np.zeros((len(cx.cat.categories), len(cy.cat.categories)), dtype=float)
    np.add.at(obs, (codes_x, codes_y), 1)
    tab = pd.DataFrame(obs, index=list(cx.cat.categories), columns=list(cy.cat.categories))
    return tab, int((~ok).sum())


# =========================================================================== tableau croisé

def tableau_croise(x: pd.Series, y: pd.Series, *, simulation: int = 10000, graine: int = 0, ic: float = 0.95) -> dict:
    """Tableau croisé de deux variables qualitatives (x en lignes, y en colonnes).

    Renvoie les effectifs, les trois familles de pourcentages, les effectifs théoriques sous
    indépendance, les écarts cellule par cellule (résidus de Pearson, résidus ajustés,
    contributions au chi², PEM), puis les mesures globales (V de Cramér, PEM global) et les
    tests (chi², p simulée, Fisher).

    Lecture des résidus ajustés : sous l'indépendance, chacun suit approximativement une loi
    normale centrée réduite ; |résidu| > 2 désigne une cellule qui s'écarte nettement de
    l'indépendance (à interpréter en gardant en tête le nombre de cellules examinées).

    Les modalités sans aucun effectif restent dans les tableaux affichés mais sont retirées
    pour les tests (et signalées). `simulation=0` désactive les p-valeurs simulées.
    Si les deux variables sont ordonnées (Categorical ordered), ajoute gamma et tau-b.
    """
    tab, n_exclus = _table(x, y)
    obs_complet = tab.to_numpy()
    n = float(obs_complet.sum())
    lignes, colonnes = list(tab.index), list(tab.columns)
    marge_l = obs_complet.sum(axis=1)
    marge_c = obs_complet.sum(axis=0)
    avertissements: list[str] = []

    with np.errstate(divide="ignore", invalid="ignore"):
        pct_ligne = 100 * obs_complet / marge_l[:, None]
        pct_colonne = 100 * obs_complet / marge_c[None, :]
        pct_total = 100 * obs_complet / n if n else np.full_like(obs_complet, np.nan)

    sortie: dict = {
        "nom_x": getattr(x, "name", None), "nom_y": getattr(y, "name", None),
        "n": int(n), "n_exclus": n_exclus,
        "lignes": lignes, "colonnes": colonnes,
        "effectifs": obs_complet.astype(int),
        "marge_lignes": marge_l.astype(int), "marge_colonnes": marge_c.astype(int),
        "pct_ligne": pct_ligne, "pct_colonne": pct_colonne, "pct_total": pct_total,
        "pct_marge_lignes": 100 * marge_l / n if n else None,      # répartition de x (profil colonne moyen)
        "pct_marge_colonnes": 100 * marge_c / n if n else None,    # répartition de y (profil ligne moyen)
    }

    garde_l = marge_l > 0
    garde_c = marge_c > 0
    lignes_vides = [l for l, g in zip(lignes, garde_l) if not g]
    colonnes_vides = [c for c, g in zip(colonnes, garde_c) if not g]
    sortie["lignes_vides"], sortie["colonnes_vides"] = lignes_vides, colonnes_vides
    if lignes_vides or colonnes_vides:
        avertissements.append(
            "Modalités sans effectif retirées pour les tests et mesures d'association : "
            + ", ".join(str(v) for v in lignes_vides + colonnes_vides) + "."
        )
    obs = obs_complet[np.ix_(garde_l, garde_c)]
    r, c = obs.shape

    methode = {
        "nom": "Tableau croisé",
        "valeurs_manquantes": "paires incomplètes exclues (voir n_exclus)",
        "chi2": "chi² de Pearson sans correction de continuité (scipy.stats), équivalent de chisq.test(correct = FALSE)",
        "residus_ajustes": "(observé − théorique) / √(théorique·(1 − part ligne)·(1 − part colonne)) — « stdres » de R",
        "v_cramer": "V brut, V corrigé du biais (Bergsma 2013), IC par chi² non central (Smithson 2003)",
        "pem": "pourcentage de l'écart maximum (Cibois), algorithme de GDAtools::pem",
        "simulation": None if not simulation else
        f"{simulation} tableaux simulés à marges fixées (Patefield), graine {graine}",
        "niveau_ic": ic,
    }

    if n == 0 or r < 2 or c < 2:
        avertissements.append(
            "Tableau dégénéré (moins de deux lignes ou de deux colonnes non vides) : aucun test ni mesure d'association calculable."
        )
        for cle in ("theoriques", "residus", "residus_ajustes", "contributions_chi2", "pem"):
            sortie[cle] = None
        sortie.update({"chi2": None, "conditions_chi2": None, "v_cramer": None, "pem_global": None,
                       "simulation": None, "fisher": None, "deux_par_deux": None, "ordinal": None,
                       "recommandation": None, "methode": methode, "avertissements": avertissements})
        return nettoyer(sortie)

    chi2, ddl, p, theo = _chi2(obs)
    lig_r = obs.sum(axis=1)[:, None] / n
    col_r = obs.sum(axis=0)[None, :] / n
    residus = (obs - theo) / np.sqrt(theo)
    ajustes = (obs - theo) / np.sqrt(theo * (1 - lig_r) * (1 - col_r))
    contributions = 100 * residus ** 2 / chi2 if chi2 > 0 else np.zeros_like(obs)
    pem_r = pem(obs)

    def complet(m: np.ndarray) -> np.ndarray:
        """Replace une matrice calculée sur le tableau réduit dans le tableau complet (NaN ailleurs)."""
        plein = np.full(obs_complet.shape, np.nan)
        plein[np.ix_(garde_l, garde_c)] = m
        return plein

    conditions = _conditions_chi2(theo)
    sortie.update({
        "theoriques": complet(theo), "residus": complet(residus), "residus_ajustes": complet(ajustes),
        "contributions_chi2": complet(contributions), "pem": complet(pem_r["local"]), "pem_global": pem_r["global"],
        "chi2": {"statistique": chi2, "ddl": int(ddl), "p": p},
        "conditions_chi2": conditions,
        "v_cramer": v_cramer(obs, ic),
    })

    sim = _simulation(obs, int(simulation), graine) if simulation and simulation > 0 else None
    sortie["simulation"] = sim

    if r == 2 and c == 2:
        dd = _deux_par_deux(obs, ic)
        sortie["chi2"]["yates"] = dd.pop("yates")
        sortie["fisher"] = dd.pop("fisher")
        sortie["deux_par_deux"] = dd
    else:
        sortie["deux_par_deux"] = None
        sortie["fisher"] = None if sim is None else {
            "p": sim["p_fisher"],
            "methode": f"test de Fisher-Freeman-Halton, p estimée par simulation de Monte-Carlo ({sim['n_simulations']} tableaux, graine {sim['graine']})",
        }

    ordonnees = (isinstance(getattr(x, "dtype", None), pd.CategoricalDtype) and x.dtype.ordered
                 and isinstance(getattr(y, "dtype", None), pd.CategoricalDtype) and y.dtype.ordered)
    sortie["ordinal"] = _ordinal(obs, ic) if ordonnees else None

    # --- avertissements et recommandation (sans rien imposer)
    if not conditions["respectees"]:
        avertissements.append(
            f"Conditions du chi² non réunies : {conditions['n_theoriques_inf_5']} cellule(s) sur {conditions['n_cellules']} "
            f"ont un effectif théorique < 5 (minimum : {conditions['min_theorique']:.2f}). "
            "La p-valeur du chi² asymptotique n'est pas fiable."
        )
        if r == 2 and c == 2:
            recommandation = ("Effectifs théoriques faibles : préférer le test exact de Fisher à la p-valeur du chi².")
        else:
            recommandation = ("Effectifs théoriques faibles : préférer la p-valeur simulée (Monte-Carlo), ou regrouper "
                              "des modalités proches si cela a un sens sociologique.")
    else:
        recommandation = ("Les conditions d'application du chi² sont réunies (règle de Cochran) ; "
                          "la p-valeur asymptotique et la p-valeur simulée doivent être proches.")
    if n < 30:
        avertissements.append(f"Effectif total faible (n = {int(n)}) : pourcentages et mesures d'association très instables.")
    if (obs == 0).any():
        avertissements.append("Le tableau contient des cellules vides : vérifier s'il s'agit de combinaisons impossibles (zéros structurels) ou simplement rares.")
    if n_exclus:
        avertissements.append(f"{n_exclus} individu(s) exclu(s) car au moins une des deux variables est manquante.")
    vc = sortie["v_cramer"]
    if vc["v"] is not None and vc["v_corrige"] is not None and vc["v"] - vc["v_corrige"] > 0.05:
        avertissements.append(
            f"Le V de Cramér brut ({vc['v']:.2f}) est nettement supérieur au V corrigé du biais ({vc['v_corrige']:.2f}) : "
            "avec cet effectif et cette taille de tableau, une partie de l'association apparente tient au hasard d'échantillonnage."
        )
    sortie.update({"recommandation": recommandation, "methode": methode, "avertissements": avertissements})
    return nettoyer(sortie)


# =========================================================================== comparaison de groupes

def _decrire(v: np.ndarray, niveau: float) -> dict:
    n = len(v)
    moyenne = float(v.mean()) if n else None
    et = float(v.std(ddof=1)) if n > 1 else None
    if n > 1 and et is not None and et > 0:
        demi = stats.t.ppf(0.5 + niveau / 2, n - 1) * et / math.sqrt(n)
        bas, haut = moyenne - demi, moyenne + demi
    else:
        bas = haut = None
    q = np.quantile(v, [0.25, 0.5, 0.75]) if n else [None] * 3
    return {"n": n, "moyenne": moyenne, "ecart_type": et, "mediane": q[1], "q1": q[0], "q3": q[2],
            "min": float(v.min()) if n else None, "max": float(v.max()) if n else None, "ic_bas": bas, "ic_haut": haut}


def comparer_groupes(y_quanti: pd.Series, groupe: pd.Series, *, ic: float = 0.95) -> dict:
    """Compare une variable quantitative entre les modalités d'une variable qualitative.

    Par groupe : effectif, moyenne, écart-type, médiane, quartiles, IC de la moyenne.
    Globalement :
      - ANOVA à un facteur (suppose des variances égales) avec eta² (part de variance
        « expliquée » dans l'échantillon) et omega² (estimation moins biaisée pour la population) ;
      - ANOVA de Welch (ne suppose pas l'égalité des variances ; oneway.test de R) ;
      - Kruskal-Wallis (sur les rangs : pas d'hypothèse de normalité) avec epsilon² = H/(n−1) ;
      - test de Levene centré sur la médiane (Brown-Forsythe) pour l'égalité des variances.
    Avec exactement deux groupes : t de Welch et IC de la différence, d de Cohen et g de Hedges
    (IC approché), Mann-Whitney (exact si aucun ex æquo et n < 50 par groupe, sinon approximation
    normale avec correction de continuité, comme wilcox.test) et corrélation bisérielle de rang.
    """
    if not isinstance(y_quanti, pd.Series):
        y_quanti = pd.Series(y_quanti, name="y")
    if not isinstance(groupe, pd.Series):
        groupe = pd.Series(groupe, name="groupe")
    y = pd.to_numeric(y_quanti.reset_index(drop=True), errors="coerce").astype(float)
    g = en_categorie(groupe.reset_index(drop=True))
    ok = y.notna() & g.notna()
    n_exclus = int((~ok).sum())
    y, g = y[ok], g[ok]
    n = int(len(y))
    avertissements: list[str] = []

    groupes, echantillons, noms = [], [], []
    for modalite in g.cat.categories:
        v = y[g == modalite].to_numpy()
        groupes.append({"groupe": modalite, **_decrire(v, ic)})
        if len(v) > 0:
            echantillons.append(v)
            noms.append(modalite)
        else:
            avertissements.append(f"Groupe sans observation, ignoré dans les tests : {modalite}.")
    k = len(echantillons)

    methode = {
        "nom": "Comparaison d'une variable quantitative entre groupes",
        "valeurs_manquantes": "individus exclus si la variable ou le groupe est manquant (voir n_exclus)",
        "anova": "ANOVA à un facteur (scipy.stats.f_oneway), eta² = SC inter / SC totale, omega² = (SC inter − (k−1)·CM intra) / (SC totale + CM intra)",
        "welch": "ANOVA de Welch (statsmodels anova_oneway, use_var='unequal'), équivalent de oneway.test(var.equal = FALSE)",
        "kruskal": "Kruskal-Wallis avec correction des ex æquo (scipy.stats.kruskal), epsilon² = H/(n−1)",
        "levene": "Levene centré sur la médiane (Brown-Forsythe), équivalent de car::leveneTest",
        "niveau_ic": ic,
    }
    sortie: dict = {"nom_y": y_quanti.name, "nom_groupe": groupe.name, "n": n, "n_exclus": n_exclus,
                    "n_groupes": k, "groupes": groupes,
                    "anova": None, "welch": None, "kruskal": None, "levene": None, "deux_groupes": None}

    petits = [str(nm) for nm, v in zip(noms, echantillons) if len(v) < 5]
    if petits:
        avertissements.append("Groupes de moins de 5 individus : " + ", ".join(petits)
                              + ". Leurs moyennes sont très instables ; envisager un regroupement.")
    if k < 2 or any(len(v) < 2 for v in echantillons):
        avertissements.append("Il faut au moins deux groupes d'au moins deux individus pour les tests.")
        sortie.update({"methode": methode, "avertissements": avertissements})
        return nettoyer(sortie)

    tout = np.concatenate(echantillons)
    grande_moyenne = tout.mean()
    sc_inter = sum(len(v) * (v.mean() - grande_moyenne) ** 2 for v in echantillons)
    sc_intra = sum(((v - v.mean()) ** 2).sum() for v in echantillons)
    sc_totale = sc_inter + sc_intra
    ddl1, ddl2 = k - 1, n - k

    if sc_intra > 0 and ddl2 > 0:
        cm_intra = sc_intra / ddl2
        f = (sc_inter / ddl1) / cm_intra
        sortie["anova"] = {
            "f": f, "ddl1": ddl1, "ddl2": ddl2, "p": float(stats.f.sf(f, ddl1, ddl2)),
            "eta2": sc_inter / sc_totale,
            "omega2": (sc_inter - ddl1 * cm_intra) / (sc_totale + cm_intra),
            "sc_inter": sc_inter, "sc_intra": sc_intra,
        }
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                w = anova_oneway(echantillons, use_var="unequal", welch_correction=True)
                sortie["welch"] = {"f": float(w.statistic), "ddl1": float(w.df_num), "ddl2": float(w.df_denom), "p": float(w.pvalue)}
            except Exception:  # variance nulle dans un groupe, etc.
                avertissements.append("ANOVA de Welch non calculable (variance nulle dans un groupe ?).")
            lv = stats.levene(*echantillons, center="median")
            sortie["levene"] = {"w": float(lv.statistic), "p": float(lv.pvalue)}
        if sortie["levene"]["p"] is not None and sortie["levene"]["p"] < 0.05:
            avertissements.append(
                "Les dispersions diffèrent sensiblement entre groupes (test de Levene) : privilégier l'ANOVA de Welch ou Kruskal-Wallis à l'ANOVA classique."
            )
    else:
        avertissements.append("Variance intra-groupe nulle : ANOVA non calculable.")

    try:
        kw = stats.kruskal(*echantillons)
        sortie["kruskal"] = {"h": float(kw.statistic), "ddl": k - 1, "p": float(kw.pvalue),
                             "epsilon2": float(kw.statistic) / (n - 1)}
    except ValueError:
        avertissements.append("Kruskal-Wallis non calculable (toutes les valeurs sont identiques).")

    if k == 2:
        a, b = echantillons
        n1, n2 = len(a), len(b)
        methode["deux_groupes"] = ("t de Welch (variances inégales) ; d de Cohen avec écart-type commun, g de Hedges = d·(1 − 3/(4(n1+n2−2)−1)), "
                                   "IC approché (erreur-type de Hedges & Olkin) ; Mann-Whitney comme wilcox.test de R")
        tw = stats.ttest_ind(a, b, equal_var=False)
        ict = tw.confidence_interval(confidence_level=ic)
        deux: dict = {
            "groupe_1": noms[0], "groupe_2": noms[1],
            "t_welch": {"t": float(tw.statistic), "ddl": float(tw.df), "p": float(tw.pvalue),
                        "difference": float(a.mean() - b.mean()), "ic_bas": float(ict.low), "ic_haut": float(ict.high)},
        }
        sp = math.sqrt(((n1 - 1) * a.var(ddof=1) + (n2 - 1) * b.var(ddof=1)) / (n1 + n2 - 2))
        if sp > 0:
            d = (a.mean() - b.mean()) / sp
            j = 1 - 3 / (4 * (n1 + n2 - 2) - 1)
            g_h = d * j
            se_g = j * math.sqrt((n1 + n2) / (n1 * n2) + d ** 2 / (2 * (n1 + n2)))
            z = stats.norm.ppf(0.5 + ic / 2)
            deux["d_cohen"] = {"d": float(d), "g_hedges": float(g_h), "ic_bas": float(g_h - z * se_g), "ic_haut": float(g_h + z * se_g),
                               "methode_ic": "approximation normale autour de g (Hedges & Olkin 1985)"}
        else:
            deux["d_cohen"] = None
        sans_ex_aequo = len(np.unique(tout)) == len(tout)
        exact = sans_ex_aequo and n1 < 50 and n2 < 50
        mw = stats.mannwhitneyu(a, b, alternative="two-sided", method="exact" if exact else "asymptotic", use_continuity=True)
        deux["mann_whitney"] = {
            "u": float(mw.statistic), "p": float(mw.pvalue),
            "r_biseriale": float(2 * mw.statistic / (n1 * n2) - 1),
            "test": "exact" if exact else "approximation normale avec correction de continuité et des ex æquo",
            "lecture": "r > 0 : les valeurs du groupe 1 tendent à dépasser celles du groupe 2 ; r = 2·P(Y1 > Y2) − 1 (ex æquo comptés pour moitié)",
        }
        sortie["deux_groupes"] = deux

    if n_exclus:
        avertissements.append(f"{n_exclus} individu(s) exclu(s) pour valeur manquante.")
    sortie.update({"methode": methode, "avertissements": avertissements})
    return nettoyer(sortie)


# =========================================================================== choix multiples

def choix_multiples(items: pd.DataFrame, groupe: pd.Series | None = None, *, ic: float = 0.95,
                    simulation: int = 10000, graine: int = 0) -> dict:
    """Question à réponses multiples : une colonne booléenne par item (coché / non coché).

    Champ : les individus dont tous les items sont manquants sont exclus (question non posée
    ou non atteinte). Un item manquant chez un individu ayant répondu à au moins un autre
    item est compté « non coché » (et signalé).

    Deux pourcentages par item, à ne pas confondre :
      - `pct_repondants` : part des répondants qui ont coché l'item (la somme dépasse 100 %) ;
      - `pct_reponses` : part de l'item dans l'ensemble des coches (la somme fait 100 %).

    Avec `groupe` : pour chaque item, part de chaque groupe l'ayant coché, et un test
    d'association item × groupe (chi² si les effectifs théoriques le permettent, sinon
    Fisher exact en 2×2 ou p simulée) avec V de Cramér. Comme il y a autant de tests que
    d'items, les p sont aussi données après ajustement (Holm et Benjamini-Hochberg).
    """
    if not isinstance(items, pd.DataFrame):
        items = pd.DataFrame(items)
    items = items.reset_index(drop=True)
    B = pd.DataFrame({c: items[c].astype("boolean") for c in items.columns})
    concerne = B.notna().any(axis=1)
    n_exclus = int((~concerne).sum())
    n_partiels = int((B[concerne].isna().any(axis=1)).sum())
    M = B[concerne].fillna(False).astype(bool)
    n = int(len(M))
    avertissements: list[str] = []
    if n_partiels:
        avertissements.append(f"{n_partiels} répondant(s) avec des items manquants : ces items ont été comptés « non coché ».")

    total_coches = int(M.to_numpy().sum())
    lignes = []
    for c in M.columns:
        k = int(M[c].sum())
        bas, haut = ic_wilson(k, n, ic)
        lignes.append({
            "item": c, "n": k,
            "pct_repondants": 100 * k / n if n else None,
            "ic_bas": None if bas is None else 100 * bas, "ic_haut": None if haut is None else 100 * haut,
            "pct_reponses": 100 * k / total_coches if total_coches else None,
        })
    nb = M.sum(axis=1) if n else pd.Series(dtype=float)
    sortie: dict = {
        "n_repondants": n, "n_exclus": n_exclus, "n_reponses": total_coches,
        "nb_moyen_reponses": float(nb.mean()) if n else None,
        "nb_median_reponses": float(nb.median()) if n else None,
        "n_aucun_coche": int((nb == 0).sum()) if n else 0,
        "items": lignes, "par_groupe": None, "niveau_ic": ic,
    }
    methode = {
        "nom": "Question à réponses multiples",
        "champ": "individus ayant au moins un item renseigné",
        "intervalle_confiance": f"Wilson à {100 * ic:g} % sur la part des répondants",
    }

    if groupe is not None and n:
        if not isinstance(groupe, pd.Series):
            groupe = pd.Series(groupe, name="groupe")
        g = en_categorie(groupe.reset_index(drop=True))[concerne]
        ok = g.notna()
        n_sans_groupe = int((~ok).sum())
        g = g[ok].cat.remove_unused_categories()
        Mg = M[ok.to_numpy()]
        noms_groupes = list(g.cat.categories)
        n_groupes = [int((g == m).sum()) for m in noms_groupes]
        effectifs, pct, tests = [], [], []
        for c in Mg.columns:
            coche = [int(Mg[c][(g == m).to_numpy()].sum()) for m in noms_groupes]
            effectifs.append(coche)
            pct.append([100 * k / t if t else None for k, t in zip(coche, n_groupes)])
            obs = np.array([coche, [t - k for k, t in zip(coche, n_groupes)]], dtype=float)
            test: dict = {"item": c, "test": None, "p": None, "chi2": None, "ddl": None, "p_chi2": None,
                          "p_exacte": None, "v_cramer": None, "v_cramer_corrige": None, "min_theorique": None, "fragile": True}
            if len(noms_groupes) >= 2 and (obs.sum(axis=1) > 0).all():
                chi2, ddl, p, theo = _chi2(obs)
                cond = _conditions_chi2(theo)
                vc = v_cramer(obs, ic)
                test.update({"chi2": chi2, "ddl": int(ddl), "p_chi2": p, "v_cramer": vc["v"], "v_cramer_corrige": vc["v_corrige"],
                             "min_theorique": cond["min_theorique"], "fragile": not cond["respectees"]})
                if cond["respectees"]:
                    test.update({"test": "chi²", "p": p})
                elif obs.shape == (2, 2):
                    pe = float(stats.fisher_exact(obs.astype(int)).pvalue)
                    test.update({"test": "Fisher exact", "p": pe, "p_exacte": pe})
                elif simulation:
                    pe = _simulation(obs, int(simulation), graine)["p_chi2"]
                    test.update({"test": f"chi² à p simulée ({int(simulation)} tirages)", "p": pe, "p_exacte": pe})
                else:
                    test.update({"test": "chi² (conditions non réunies)", "p": p})
            else:
                test["test"] = "non calculable (item coché par tous ou par personne, ou un seul groupe)"
            tests.append(test)
        for t, ph, pb in zip(tests, ajuster_p([t["p"] for t in tests], "holm"), ajuster_p([t["p"] for t in tests], "bh")):
            t["p_holm"], t["p_bh"] = ph, pb
        n_tests = sum(t["p"] is not None for t in tests)
        sortie["par_groupe"] = {
            "nom_groupe": groupe.name, "groupes": noms_groupes, "n_groupes": n_groupes, "n_sans_groupe": n_sans_groupe,
            "effectifs": effectifs, "pct": pct, "tests": tests, "n_tests": n_tests,
            "note": (f"{n_tests} tests ont été réalisés (un par item). Les p ajustées (Holm : risque d'au moins un faux positif ; "
                     "BH : taux de fausses découvertes) tiennent compte de cette multiplicité ; les p brutes non."),
        }
        methode["tests"] = ("par item : chi² de Pearson si la règle de Cochran est respectée, sinon Fisher exact (2×2) "
                            "ou p simulée à marges fixées ; ajustements de Holm et de Benjamini-Hochberg")
        if n_sans_groupe:
            avertissements.append(f"{n_sans_groupe} répondant(s) sans groupe renseigné, exclu(s) de la comparaison.")
        if any(t < 5 for t in n_groupes):
            avertissements.append("Au moins un groupe compte moins de 5 répondants : ses pourcentages sont très instables.")
        if n_tests > 1:
            avertissements.append(f"Comparaisons multiples : {n_tests} tests. Se fier aux p ajustées et, surtout, à l'ampleur des écarts de pourcentages.")

    if n == 0:
        avertissements.append("Aucun répondant concerné par cette question.")
    sortie.update({"methode": methode, "avertissements": avertissements})
    return nettoyer(sortie)
