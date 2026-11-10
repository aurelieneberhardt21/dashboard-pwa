"""Exploration d'associations : une variable « cible » face à un ensemble de variables candidates.

Ce module ne cherche pas des résultats « significatifs ». Il dresse un tableau de bord honnête :
pour chaque candidate, l'effectif réellement utilisé, une taille d'effet (avec intervalle de confiance
quand il existe), la p-valeur brute ET les p-valeurs ajustées pour le nombre de tests effectués, et un
drapeau « fragile » quand les effectifs sont insuffisants pour conclure quoi que ce soit.

Mesures selon la nature du couple :
  quali × quali   : V de Cramér corrigé du biais (Bergsma 2013) ; test du chi²
  quali × quanti  : rapport de corrélation eta² (part de variance expliquée par les groupes) ; ANOVA
                    (le test de Kruskal-Wallis est donné en complément, moins sensible aux valeurs extrêmes)
  quanti × quanti : rho de Spearman (rangs : robuste aux distributions asymétriques)

Pour pouvoir comparer des mesures de natures différentes, ``intensite`` ramène tout à l'échelle d'une
corrélation (0 = aucune liaison, 1 = liaison parfaite) : V corrigé, eta = racine de eta², |rho|.
Le tri se fait sur cette intensité, jamais sur la p-valeur.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .correlation import correlation_paire
from .croise import comparer_groupes, tableau_croise
from .univarie import ajuster_p, est_quanti, nettoyer

AVERTISSEMENT = (
    "Lecture exploratoire. {n} tests ont été calculés : avec autant de comparaisons, quelques p-valeurs "
    "brutes inférieures à 0,05 sont attendues par le seul hasard (environ {attendu} ici si aucune liaison "
    "n'existait). Fiez-vous d'abord à l'intensité, à son intervalle de confiance et aux effectifs ; les "
    "p-valeurs ajustées (Holm : contrôle strict du risque d'au moins une fausse alerte ; Benjamini-Hochberg : "
    "contrôle de la proportion de fausses alertes) tiennent compte du nombre de tests. Une liaison repérée "
    "ici est une piste à examiner (tableau croisé, contrôle par d'autres variables), pas un résultat."
)


def _quali_quali(cible: pd.Series, cand: pd.Series, seuil: int) -> dict:
    t = tableau_croise(cible, cand, simulation=0)
    cond = t["conditions_chi2"]
    raisons = []
    if cond["part_theoriques_inf_5"] > 0.2 or cond["min_theorique"] < 1:
        raisons.append(f"{round(100 * cond['part_theoriques_inf_5'])} % des cellules ont un effectif théorique < 5")
    petites = [m for m in t["marge_colonnes"] + t["marge_lignes"] if m < seuil]
    if petites:
        raisons.append(f"{len(petites)} modalité(s) de moins de {seuil} individus")
    return {"type_couple": "quali × quali", "mesure": "V de Cramér corrigé", "effet": t["v_cramer"]["v_corrige"],
            "intensite": t["v_cramer"]["v_corrige"], "ic_bas": t["v_cramer"]["ic_bas"], "ic_haut": t["v_cramer"]["ic_haut"],
            "n": t["n"], "n_exclus": t["n_exclus"], "test": "chi²", "p": t["chi2"]["p"], "p_complement": None,
            "part_theoriques_inf_5": cond["part_theoriques_inf_5"], "raisons_fragilite": raisons,
            "detail": f"chi² = {t['chi2']['statistique']:.2f}, ddl = {t['chi2']['ddl']}"}


def _quali_quanti(quanti: pd.Series, groupe: pd.Series, seuil: int) -> dict:
    g = comparer_groupes(quanti, groupe)
    raisons = []
    petits = [x for x in g["groupes"] if x["n"] < seuil]
    if petits:
        raisons.append(f"{len(petits)} groupe(s) de moins de {seuil} individus")
    eta2 = g["anova"]["eta2"]
    return {"type_couple": "quali × quanti", "mesure": "eta²", "effet": eta2,
            "intensite": None if eta2 is None else float(np.sqrt(max(eta2, 0.0))), "ic_bas": None, "ic_haut": None,
            "n": g["n"], "n_exclus": g["n_exclus"], "test": "ANOVA", "p": g["anova"]["p"],
            "p_complement": {"test": "Kruskal-Wallis", "p": g["kruskal"]["p"]},
            "part_theoriques_inf_5": None, "raisons_fragilite": raisons,
            "detail": f"F = {g['anova']['f']:.2f} ; Kruskal-Wallis p = {g['kruskal']['p']:.3g}"
            if g["anova"]["f"] is not None and g["kruskal"]["p"] is not None else ""}


def _quanti_quanti(a: pd.Series, b: pd.Series, seuil: int) -> dict:
    ok = a.notna() & b.notna()
    c = correlation_paire(a[ok].to_numpy(dtype=float), b[ok].to_numpy(dtype=float), "spearman")
    return {"type_couple": "quanti × quanti", "mesure": "rho de Spearman", "effet": c["r"],
            "intensite": None if c["r"] is None else abs(c["r"]), "ic_bas": c.get("ic_bas"), "ic_haut": c.get("ic_haut"),
            "n": int(ok.sum()), "n_exclus": int((~ok).sum()), "test": "Spearman", "p": c["p"], "p_complement": None,
            "part_theoriques_inf_5": None, "raisons_fragilite": [], "detail": ""}


def associations(cible: pd.Series, candidates: pd.DataFrame, *, ajustement: str = "bh", seuil_effectif: int = 5,
                 n_min: int = 30) -> dict:
    """Mesure la liaison entre ``cible`` et chaque colonne de ``candidates`` (voir la documentation du module)."""
    cible = cible.reset_index(drop=True)
    candidates = candidates.reset_index(drop=True)
    cible_quanti = est_quanti(cible)
    lignes, echecs = [], []
    for nom in candidates.columns:
        cand = candidates[nom]
        try:
            if cible_quanti and est_quanti(cand):
                res = _quanti_quanti(cible, cand, seuil_effectif)
            elif cible_quanti:
                res = _quali_quanti(cible, cand, seuil_effectif)
            elif est_quanti(cand):
                res = _quali_quanti(cand, cible, seuil_effectif)
            else:
                res = _quali_quali(cible, cand, seuil_effectif)
        except (ValueError, ZeroDivisionError) as e:
            echecs.append({"variable": str(nom), "raison": str(e)})
            continue
        if res["n"] < n_min:
            res["raisons_fragilite"].append(f"seulement {res['n']} individus avec les deux variables renseignées")
        res["fragile"] = bool(res["raisons_fragilite"])
        lignes.append({"variable": str(nom), **res})
    p = [l["p"] for l in lignes]
    for l, ph, pb in zip(lignes, ajuster_p(p, "holm"), ajuster_p(p, "bh")):
        l["p_holm"], l["p_bh"] = ph, pb
        l["p_ajustee"] = pb if ajustement == "bh" else (ph if ajustement == "holm" else l["p"])
    lignes.sort(key=lambda l: -(l["intensite"] if l["intensite"] is not None else -1))
    n = len(lignes)
    return nettoyer({
        "cible": cible.name, "cible_type": "quanti" if cible_quanti else "quali", "n_tests": n,
        "ajustement": ajustement, "associations": lignes, "non_calculees": echecs,
        "avertissement": AVERTISSEMENT.format(n=n, attendu=f"{0.05 * n:.1f}".replace(".", ",")),
        "methode": {
            "nom": "Exploration d'associations (une cible × n candidates)",
            "mesures": "quali×quali : V de Cramér corrigé (Bergsma 2013) + chi² ; quali×quanti : eta² + ANOVA "
                       "(Kruskal-Wallis en complément) ; quanti×quanti : rho de Spearman",
            "intensite": "V corrigé, racine de eta², |rho| : même échelle 0-1, sert au tri",
            "valeurs_manquantes": "exclusion par paire (l'effectif n varie d'une ligne à l'autre)",
            "ajustement": "Holm et Benjamini-Hochberg calculés sur l'ensemble des tests du tableau",
            "fragilite": f"drapeau si > 20 % de cellules théoriques < 5, modalité ou groupe < {seuil_effectif}, "
                         f"ou n < {n_min}",
        },
        "avertissements": [f"{len(echecs)} variable(s) n'ont pas pu être analysées (voir « non_calculees »)."] if echecs else [],
    })
