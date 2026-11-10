"""Validation des statistiques uni/bivariées, corrélations et régressions contre R.

Les valeurs de référence (tests/reference/bivarie/*.json) sont produites par tests/reference/bivarie.R
(R 4.3.3 : chisq.test, fisher.test, t.test, oneway.test, aov, kruskal.test, wilcox.test, cor.test,
p.adjust, lm, glm, car::Anova, car::vif, sandwich::vcovHC, nnet::multinom). Les tests n'exigent pas R.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from etabli.stats import correlation, croise, exploration, regression, univarie

REF = Path(__file__).parent / "reference"


def ref(nom):
    return json.loads((REF / "bivarie" / f"{nom}.json").read_text())


def donnees(nom, **kw):
    # « None » est une modalité (survey$Exer), pas une valeur manquante : seules les cellules vides le sont
    return pd.read_csv(REF / "donnees" / f"{nom}.csv", keep_default_na=False, na_values=[""], **kw)


def proche(a, b, rtol=1e-8, atol=1e-10):
    np.testing.assert_allclose(np.asarray(a, dtype=float), np.asarray(b, dtype=float), rtol=rtol, atol=atol)


def individus(table, lignes, colonnes):
    """Reconstitue des données individuelles (deux séries catégorielles) à partir d'un tableau d'effectifs."""
    x, y = [], []
    for i, l in enumerate(lignes):
        for j, c in enumerate(colonnes):
            x += [l] * int(table[i][j])
            y += [c] * int(table[i][j])
    return (pd.Series(pd.Categorical(x, categories=lignes), name="x"),
            pd.Series(pd.Categorical(y, categories=colonnes), name="y"))


def survey():
    d = donnees("survey")
    d["Smoke"] = pd.Categorical(d["Smoke"], categories=["Never", "Occas", "Regul", "Heavy"], ordered=True)
    d["Exer"] = pd.Categorical(d["Exer"], categories=["None", "Some", "Freq"], ordered=True)
    d["Sex"] = pd.Categorical(d["Sex"], categories=["Female", "Male"])
    return d


def birthwt():
    bw = donnees("birthwt")
    for c, lv in [("race", ["white", "black", "other"]), ("smoke", ["non", "oui"]), ("ht", ["non", "oui"]),
                  ("ui", ["non", "oui"])]:
        bw[c] = pd.Categorical(bw[c], categories=lv)
    return bw


# ---------------------------------------------------------------- univarié

def test_tri_a_plat_et_wilson():
    r = ref("univarie")
    d = survey()
    res = univarie.tri_a_plat(d["Smoke"])
    assert res["n"] == r["fume"]["n"] and res["n_manquants"] == r["fume"]["n_manquants"]
    for m in res["modalites"]:
        assert m["n"] == r["fume"]["effectifs"][m["modalite"]]
    for w in r["wilson"]:
        bas, haut = univarie.ic_wilson(w["k"], w["n"], w.get("niveau", 0.95))
        proche([bas, haut], w["ic"])


def test_resume_quanti():
    r = ref("univarie")["height"]
    res = univarie.resume_quanti(survey()["Height"], classes=10)
    assert res["n"] == r["n"] and res["n_manquants"] == r["n_manquants"]
    proche([res["moyenne"], res["ecart_type"], res["variance"], res["mediane"], res["min"], res["max"]],
           [r["moyenne"], r["ecart_type"], r["variance"], r["mediane"], r["min"], r["max"]])
    proche([res["q1"], res["q3"]], r["quartiles"])
    proche([res["d1"], res["d9"]], r["deciles"])
    proche([res["ic_bas"], res["ic_haut"]], r["ic_moyenne"])
    proche(res["asymetrie"], r["asymetrie"])
    proche(res["histogramme"]["bornes"], r["hist10"]["bornes"])
    assert res["histogramme"]["effectifs"] == r["hist10"]["effectifs"]


def test_ajustement_p():
    r = ref("correlation")["p_adjust"]
    proche(univarie.ajuster_p(r["p"], "holm"), r["holm"])
    proche(univarie.ajuster_p(r["p"], "bh"), r["bh"])


# ---------------------------------------------------------------- tableaux croisés

@pytest.mark.parametrize("nom", ["cheveux_yeux", "titanic", "the", "emploi", "fume_sport"])
def test_tableau_croise(nom):
    r = ref("croise")[nom]
    x, y = individus(r["table"], r["lignes"], r["colonnes"])
    if nom in ("emploi", "fume_sport"):
        x, y = x.cat.as_ordered(), y.cat.as_ordered()
    res = croise.tableau_croise(x, y, simulation=20000, graine=1)
    assert res["n"] == r["n"]
    assert res["effectifs"] == r["table"]
    proche(res["chi2"]["statistique"], r["chi2"])
    assert res["chi2"]["ddl"] == r["ddl"]
    proche(res["chi2"]["p"], r["p"], rtol=1e-7, atol=1e-300)
    proche(res["theoriques"], r["theoriques"])
    proche(res["residus"], r["residus"])
    proche(res["residus_ajustes"], r["residus_ajustes"])
    proche(np.asarray(res["contributions_chi2"]) / 100, np.asarray(r["contributions"]) / np.sum(r["contributions"]),
           rtol=1e-7)
    proche(res["v_cramer"]["v"], r["v"])
    proche(res["v_cramer"]["v_corrige"], r["v_corrige"], atol=1e-9)
    if r["v_ic"][0] is not None:
        # la formule brute peut dépasser 1 sur un très petit tableau : nous bornons l'intervalle à [0, 1]
        proche([res["v_cramer"]["ic_bas"], res["v_cramer"]["ic_haut"]], np.clip(r["v_ic"], 0, 1), rtol=1e-4, atol=1e-5)
    # p simulée (Monte-Carlo) : ordre de grandeur seulement, les générateurs aléatoires diffèrent
    assert abs(res["simulation"]["p_chi2"] - r["p_simulee"]) < 0.02
    if r["fisher_exact"] and res["fisher"] and "exact" in res["fisher"]["methode"].lower():
        proche(res["fisher"]["p"], r["fisher_p"], rtol=1e-6, atol=1e-12)
    elif res["fisher"]:
        assert abs(res["fisher"]["p"] - r["fisher_p"]) < 0.02
    if "yates" in r:
        dd = res["deux_par_deux"]
        proche(dd["phi"], r["phi"])
        proche(dd["odds_ratio"]["valeur"], r["or"])
        proche([dd["odds_ratio"]["ic_bas"], dd["odds_ratio"]["ic_haut"]], r["or_ic"])
        ya = res["chi2"]["yates"]
        proche([ya["statistique"], ya["p"]], [r["yates"]["chi2"], r["yates"]["p"]], atol=1e-300)
    if "gamma" in r:
        proche(res["ordinal"]["gamma"]["valeur"], r["gamma"])
        proche(res["ordinal"]["tau_b"]["valeur"], r["tau_b"])
        proche(res["ordinal"]["tau_b"]["p"], r["tau_b_p"], rtol=1e-6)
    if "pem_local" in r:
        proche(res["pem"], r["pem_local"], rtol=1e-6, atol=1e-6)
        proche(res["pem_global"], r["pem_global"], rtol=1e-6, atol=1e-6)


def test_pem_exemple_a_la_main():
    """PEM (Cibois) calculé à la main sur un tableau 2×2 : effectifs [[30, 10], [20, 40]].

    Marges : lignes 40 / 60, colonnes 50 / 50, n = 100. Théorique de la cellule (1,1) : 40 × 50 / 100 = 20.
    Écart observé : 30 − 20 = +10. Maximum possible compte tenu des marges : min(40, 50) = 40, soit un écart
    maximal de 40 − 20 = 20. PEM = 10 / 20 = +50 %. Cellule (1,2) : théorique 20, observé 10, écart −10 ;
    minimum possible max(0, 40 + 50 − 100) = 0, écart maximal (en valeur absolue) 20 → PEM = −50 %.
    """
    x, y = individus([[30, 10], [20, 40]], ["a", "b"], ["x", "y"])
    res = croise.tableau_croise(x, y, simulation=0)
    proche(res["pem"][0][0], 50.0)
    proche(res["pem"][0][1], -50.0)


def test_croise_valeurs_manquantes():
    d = survey()
    r = ref("croise")["fume_sport"]
    res = croise.tableau_croise(d["Smoke"], d["Exer"], simulation=0)
    assert res["n"] == r["n"] and res["n_exclus"] == r["n_exclus"]


# ---------------------------------------------------------------- comparaison de groupes

@pytest.mark.parametrize("nom,y,g", [("height_sexe", "Height", "Sex"), ("pulse_exer", "Pulse", "Exer"),
                                     ("age_fume", "Age", "Smoke")])
def test_comparer_groupes(nom, y, g):
    r = ref("groupes")[nom]
    d = survey()
    res = croise.comparer_groupes(d[y], d[g])
    assert res["n"] == r["n"] and res["n_exclus"] == r["n_exclus"]
    for nous, eux in zip(res["groupes"], r["groupes"]):
        assert nous["groupe"] == eux["groupe"] and nous["n"] == eux["n"]
        proche([nous["moyenne"], nous["ecart_type"], nous["mediane"]], [eux["moyenne"], eux["ecart_type"], eux["mediane"]])
    for bloc, cles in (("anova", ["f", "p", "eta2", "omega2"]), ("welch", ["f", "ddl2", "p"]),
                       ("kruskal", ["h", "p", "epsilon2"]), ("levene", ["w", "p"])):
        proche([res[bloc][c] for c in cles], [r[bloc][c] for c in cles], rtol=1e-7, atol=1e-300)
    if "deux" in r:
        dg = res["deux_groupes"]
        proche([abs(dg["t_welch"]["t"]), dg["t_welch"]["ddl"], dg["t_welch"]["p"]],
               [abs(r["deux"]["t"]), r["deux"]["ddl"], r["deux"]["p"]], rtol=1e-7, atol=1e-300)
        proche(abs(dg["d_cohen"]["d"]), abs(r["deux"]["d"]))
        proche(abs(dg["d_cohen"]["g_hedges"]), abs(r["deux"]["g"]), rtol=1e-6)
        proche(dg["mann_whitney"]["p"], r["deux"]["p_mw"], rtol=1e-6, atol=1e-300)
        proche(abs(dg["mann_whitney"]["r_biseriale"]), abs(r["deux"]["r_biseriale"]), rtol=1e-7)


# ---------------------------------------------------------------- corrélations

@pytest.mark.parametrize("jeu,colonnes", [("mtcars", ["mpg", "hp", "wt", "qsec", "drat"]),
                                          ("survey", ["Height", "Pulse", "Age", "Wr.Hnd", "NW.Hnd"])])
@pytest.mark.parametrize("methode", ["pearson", "spearman", "kendall"])
def test_correlations(jeu, colonnes, methode):
    r = ref("correlation")[jeu][methode]
    d = donnees(jeu)[colonnes]
    for ajust, cle in (("holm", "p_holm"), ("bh", "p_bh")):
        res = correlation.matrice_correlation(d, methode=methode, ajustement=ajust)
        assert res["n_tests"] == len(r["paires"])
        par_cle = {(p["x"], p["y"]): p for p in res["paires"]}
        for eux, p_aj in zip(r["paires"], r[cle]):
            nous = par_cle[(eux["x"], eux["y"])]
            assert nous["n"] == eux["n"]
            proche(nous["r"], eux["r"])
            proche(nous["p"], eux["p"], rtol=1e-6, atol=1e-300)
            proche(nous["p_ajustee"], p_aj, rtol=1e-6, atol=1e-300)
            if eux["ic"][0] is not None:
                proche([nous["ic_bas"], nous["ic_haut"]], eux["ic"], rtol=1e-7)


# ---------------------------------------------------------------- régressions

def _termes(res):
    return {(t["variable"], t.get("modalite")): t for t in res["termes"] if not t.get("reference")}


def _nom_r(terme_r, facteurs):
    """« raceblack » (R) → ("race", "black") ; « age » → ("age", None) ; « (Intercept) » → constante."""
    for f, niveaux in facteurs.items():
        for n in niveaux:
            if terme_r == f + n:
                return (f, n)
    return (terme_r, None)


FACTEURS = {"race": ["white", "black", "other"], "smoke": ["non", "oui"], "ht": ["non", "oui"], "ui": ["non", "oui"]}


def test_regression_lineaire():
    r = ref("regression")["lineaire"]
    bw = birthwt()
    res = regression.regression_lineaire(bw["bwt"], bw[["age", "lwt", "race", "smoke", "ht"]])
    assert res["n"] == r["n"]
    nous = _termes(res)
    for eux, ic in zip(r["termes"], r["ic_t"]):
        if eux["terme"] == "(Intercept)":
            t = next(t for t in res["termes"] if t["variable"] in ("(constante)", "constante", "Constante", None)
                     or "onstante" in t["terme"])
        else:
            t = nous[_nom_r(eux["terme"], FACTEURS)]
        proche([t["coef"], t["se"], t["stat"], t["p"]], [eux["coef"], eux["se"], eux["stat"], eux["p"]], rtol=1e-7,
               atol=1e-300)
        proche([t["ic_bas"], t["ic_haut"]], ic, rtol=1e-7)
    a = res["ajustement"]
    proche([a["r2"], a["r2_ajuste"], a["f"], a["p_f"], a["sigma"], a["aic"], a["bic"], a["log_vraisemblance"]],
           [r["r2"], r["r2_ajuste"], r["f"], r["p_f"], r["sigma"], r["aic"], r["bic"], r["logvrais"]], rtol=1e-7,
           atol=1e-300)
    par_terme = {t["terme"]: t for t in res["tests_variables"]}
    for eux in r["anova2"]:
        proche([par_terme[eux["terme"]]["stat"], par_terme[eux["terme"]]["p"]], [eux["stat"], eux["p"]], rtol=1e-6)
    vif = {v["terme"]: v for v in res["diagnostics"]["vif"]}
    for eux in r["vif"]:
        proche(vif[eux["terme"]]["gvif"], eux["gvif"], rtol=1e-6)
    # erreurs types robustes HC3 (sandwich::vcovHC)
    rob = _termes(regression.regression_lineaire(bw["bwt"], bw[["age", "lwt", "race", "smoke", "ht"]], robuste="HC3"))
    for eux in r["termes"]:
        if eux["terme"] != "(Intercept)":
            proche(rob[_nom_r(eux["terme"], FACTEURS)]["se"], eux["se_robuste"], rtol=1e-7)


def test_regression_logistique():
    r = ref("regression")["logistique"]
    bw = birthwt()
    res = regression.regression_logistique(bw["low"], bw[["age", "lwt", "race", "smoke", "ht", "ui"]], modalite_cible=1)
    assert res["n"] == r["n"]
    nous = _termes(res)
    for eux in r["termes"]:
        if eux["terme"] == "(Intercept)":
            continue
        t = nous[_nom_r(eux["terme"], FACTEURS)]
        # glm() de R s'arrête à une tolérance de 1e-8 sur la déviance : ses erreurs types ne sont exactes
        # qu'à ~1e-5 près en relatif (statsmodels converge plus loin). D'où la tolérance de 2e-4.
        proche(t["coef"], eux["coef"], rtol=1e-5)
        proche([t["se"], t["stat"], t["p"]], [eux["se"], eux["stat"], eux["p"]], rtol=2e-4)
        proche([t["ic_bas"], t["ic_haut"]], eux["ic"], rtol=2e-4)
        proche(t["odds_ratio"], np.exp(eux["coef"]), rtol=1e-5)
    a = res["ajustement"]
    proche([a["deviance"], a["deviance_nulle"], a["aic"], a["bic"], a["log_vraisemblance"], a["pseudo_r2_mcfadden"],
            a["pseudo_r2_nagelkerke"], a["lr_chi2"], a["lr_p"]],
           [r["deviance"], r["deviance_nulle"], r["aic"], r["bic"], r["logvrais"], r["mcfadden"], r["nagelkerke"],
            r["lr"]["chi2"], r["lr"]["p"]], rtol=1e-6)
    proche([res["classement"]["auc"], res["classement"]["taux_bons_classements"]], [r["auc"], r["bons_classements"]],
           rtol=1e-6)
    par_terme = {t["terme"]: t for t in res["tests_variables"]}
    for eux in r["anova2"]:
        proche([par_terme[eux["terme"]]["stat"], par_terme[eux["terme"]]["p"]], [eux["stat"], eux["p"]], rtol=1e-5)
    ame = {(e["variable"], e.get("modalite")): e["effet"] for e in res["effets_marginaux"]}
    proche([ame[("age", None)], ame[("lwt", None)], ame[("smoke", "oui")], ame[("ht", "oui")], ame[("race", "black")],
            ame[("race", "other")]],
           [r["ame"][k] for k in ("age", "lwt", "smoke_oui", "ht_oui", "race_black", "race_other")], rtol=1e-5)


def test_regression_logistique_separation():
    """Séparation parfaite : pas de plantage, un avertissement explicite."""
    y = pd.Series([0] * 10 + [1] * 10)
    X = pd.DataFrame({"x": list(range(20))}, dtype=float)
    res = regression.regression_logistique(y, X, modalite_cible=1)
    assert res["diagnostics"]["separation"] is True
    assert any("séparation" in a.lower() for a in res["avertissements"])


def test_regression_multinomiale():
    r = ref("regression")["multinomiale"]
    bw = birthwt()
    res = regression.regression_multinomiale(bw["race"], bw[["age", "lwt", "smoke"]], reference_y="white")
    assert res["n"] == r["n"]
    proche(res["ajustement"]["log_vraisemblance"], r["logvrais"], rtol=1e-6)
    proche(res["ajustement"]["aic"], r["aic"], rtol=1e-6)
    for i, mod in enumerate(r["modalites"]):
        for j, nom in enumerate(r["termes_noms"]):
            if nom == "(Intercept)":
                continue
            cle = _nom_r(nom, FACTEURS)
            t = next(t for t in res["termes"] if t.get("modalite_y") == mod and (t["variable"], t.get("modalite")) == cle
                     and not t.get("reference"))
            proche(t["coef"], r["coef"][i][j], rtol=2e-3, atol=1e-5)     # optimiseurs différents (BFGS vs Newton)
            proche(t["se"], r["se"][i][j], rtol=2e-3, atol=1e-5)


# ---------------------------------------------------------------- exploration

def test_associations():
    d = survey()
    cand = d[["Exer", "Sex", "Height", "Pulse", "Age"]]
    res = exploration.associations(d["Smoke"], cand)
    assert res["n_tests"] == 5
    par_var = {a["variable"]: a for a in res["associations"]}
    # mêmes chiffres que les fonctions bivariées appelées directement
    direct = croise.tableau_croise(d["Smoke"], d["Exer"], simulation=0)
    proche(par_var["Exer"]["effet"], direct["v_cramer"]["v_corrige"])
    proche(par_var["Exer"]["p"], direct["chi2"]["p"])
    g = croise.comparer_groupes(d["Height"], d["Smoke"])
    proche(par_var["Height"]["effet"], g["anova"]["eta2"])
    # p ajustées cohérentes avec p.adjust
    p = [a["p"] for a in res["associations"]]
    proche([a["p_holm"] for a in res["associations"]], univarie.ajuster_p(p, "holm"))
    proche([a["p_bh"] for a in res["associations"]], univarie.ajuster_p(p, "bh"))
    # tri par taille d'effet décroissante à l'intérieur de chaque famille de mesure
    assert res["avertissement"]
    json.dumps(res)
