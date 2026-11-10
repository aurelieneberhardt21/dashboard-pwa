"""Validation du moteur géométrique contre R (FactoMineR 2.9, GDAtools 2.3.1, ca).

Les références (tests/reference/geometrique/*.json) et les jeux de données
(tests/reference/donnees/*.csv) sont produits par tests/reference/geometrique.R
et versionnés : ces tests ne demandent pas R.

Le signe d'un axe factoriel est arbitraire : les coordonnées sont comparées au
signe près, axe par axe (le signe étant fixé une fois par analyse sur les
coordonnées des individus ou des lignes, puis imposé à tous les autres tableaux).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.cluster import hierarchy

from etabli.stats.classification import _arbre_ward, _ward_pondere, cah, decrire_classes
from etabli.stats.geometrique import acm, acp, afc, afdm

REF = Path(__file__).parent / "reference"
RTOL = 1e-8
ATOL = 1e-9


# ------------------------------------------------------------------ outils

def ref(nom: str) -> dict:
    return json.loads((REF / "geometrique" / f"{nom}.json").read_text())


def donnees(nom: str) -> pd.DataFrame:
    return pd.read_csv(REF / "donnees" / f"{nom}.csv", index_col=0, keep_default_na=False)


def M(bloc) -> np.ndarray:
    """Matrice d'un bloc de référence {lignes, donnees} (null → nan)."""
    return np.array([[np.nan if v is None else v for v in ligne] for ligne in bloc["donnees"]], dtype=float)


def A(x) -> np.ndarray:
    return np.array([[np.nan if v is None else v for v in ligne] for ligne in x], dtype=float)


def signes(nous: np.ndarray, r: np.ndarray) -> np.ndarray:
    """Signe relatif de chaque axe entre nos coordonnées et celles de R."""
    s = np.sign((nous * r).sum(axis=0))
    s[s == 0] = 1
    return s


def proche(nous, attendu, *, rtol=RTOL, atol=ATOL, quoi=""):
    np.testing.assert_allclose(np.asarray(nous, dtype=float), np.asarray(attendu, dtype=float),
                               rtol=rtol, atol=atol, err_msg=quoi, equal_nan=True)


def tableau(liste, cle) -> np.ndarray:
    return A([e[cle] for e in liste])


def valeurs_propres(res) -> np.ndarray:
    return np.array([a["valeur_propre"] for a in res["axes"]])


def verifier_json(res):
    """Le résultat doit être sérialisable tel quel, sans NaN ni type numpy."""
    json.dumps(res, allow_nan=False)


def meme_ordre_modalites(res_mods, niveaux: dict) -> None:
    """Nos modalités suivent l'ordre « variables × niveaux » de R (une fois les catégories ordonnées)."""
    attendu = [(v, str(m)) for v, mods in niveaux.items() for m in mods]
    assert [(m["variable"], m["modalite"]) for m in res_mods] == attendu


def categoriel(df: pd.DataFrame, niveaux: dict) -> pd.DataFrame:
    """Reconstitue les facteurs R (ordre des niveaux compris)."""
    out = df.copy()
    for col, mods in niveaux.items():
        out[col] = pd.Categorical(df[col].astype(str), categories=[str(m) for m in mods])
    return out


# ------------------------------------------------------------------ ACP

def _comparer_acp(res, r, *, reduite=True):
    verifier_json(res)
    q = len(res["individus"]["coord"][0])
    proche(valeurs_propres(res), r["eig"], quoi="valeurs propres")
    F = A(res["individus"]["coord"])
    s = signes(F, M(r["ind"]["coord"])[:, :q])
    proche(F * s, M(r["ind"]["coord"]), quoi="coord individus")
    proche(A(res["individus"]["contrib"]), M(r["ind"]["contrib"]), quoi="contrib individus")
    proche(A(res["individus"]["cos2"]), M(r["ind"]["cos2"]), quoi="cos2 individus")
    assert [v["id"] for v in res["variables"]] == r["var"]["coord"]["lignes"]
    proche(tableau(res["variables"], "coord") * s, M(r["var"]["coord"]), quoi="coord variables")
    proche(tableau(res["variables"], "cor") * s, M(r["var"]["cor"]), quoi="cor variables")
    proche(tableau(res["variables"], "contrib"), M(r["var"]["contrib"]), quoi="contrib variables")
    proche(tableau(res["variables"], "cos2"), M(r["var"]["cos2"]), quoi="cos2 variables")
    if r.get("ind_sup"):
        assert res["sup"]["individus"]["ids"] == r["ind_sup"]["coord"]["lignes"]
        proche(A(res["sup"]["individus"]["coord"]) * s, M(r["ind_sup"]["coord"]), quoi="coord ind sup")
        proche(A(res["sup"]["individus"]["cos2"]), M(r["ind_sup"]["cos2"]), quoi="cos2 ind sup")
    quanti = [v for v in res["sup"]["variables"] if v["type"] == "quanti"]
    proche(tableau(quanti, "coord") * s, M(r["quanti_sup"]["coord"]), quoi="coord quanti sup")
    proche(tableau(quanti, "cor") * s, M(r["quanti_sup"]["cor"]), quoi="cor quanti sup")
    proche(tableau(quanti, "cos2"), M(r["quanti_sup"]["cos2"]), quoi="cos2 quanti sup")
    mods = res["sup"]["modalites"]
    assert [m["modalite"] for m in mods] == r["quali_sup"]["coord"]["lignes"]
    proche(tableau(mods, "coord") * s, M(r["quali_sup"]["coord"]), quoi="coord quali sup")
    proche(tableau(mods, "cos2"), M(r["quali_sup"]["cos2"]), quoi="cos2 quali sup")
    proche(tableau(mods, "vtest") * s, M(r["quali_sup"]["vtest"]), quoi="vtest quali sup")
    quali = [v for v in res["sup"]["variables"] if v["type"] == "quali"]
    proche(tableau(quali, "eta2"), M(r["quali_sup"]["eta2"]), quoi="eta2 quali sup")
    for axe in range(q):
        assert math.isclose(sum(l[axe] for l in res["individus"]["contrib"]), 100, rel_tol=1e-9)
        assert math.isclose(sum(v["contrib"][axe] for v in res["variables"]), 100, rel_tol=1e-9)


def test_acp_reduite_avec_supplementaires():
    d = donnees("decathlon")
    act = d.iloc[:36]
    res = acp(act.iloc[:, :10], ind_sup=d.iloc[36:, :10], quanti_sup=act.iloc[:, 10:12], quali_sup=act.iloc[:, [12]])
    _comparer_acp(res, ref("acp_reduite_sup"))
    assert res["methode"] == "acp" and res["n"] == 36
    assert math.isclose(res["inertie_totale"], 10, rel_tol=1e-12)     # ACP normée : inertie = nombre de variables


def test_acp_non_reduite():
    d = donnees("decathlon")
    res = acp(d.iloc[:, :10], reduire=False, quanti_sup=d.iloc[:, 10:12], quali_sup=d.iloc[:, [12]])
    _comparer_acp(res, ref("acp_non_reduite"), reduite=False)


def test_acp_ponderee():
    d = donnees("decathlon")
    r = ref("acp_ponderee")
    res = acp(d.iloc[:, :10], poids=r["poids"], quanti_sup=d.iloc[:, 10:12], quali_sup=d.iloc[:, [12]])
    _comparer_acp(res, r)
    # L'échelle des poids est indifférente (normalisation interne à somme n).
    res2 = acp(d.iloc[:, :10], poids=[7.3 * x for x in r["poids"]], quali_sup=d.iloc[:, [12]])
    proche(tableau(res2["sup"]["modalites"], "vtest"), tableau(res["sup"]["modalites"], "vtest"))


def test_acp_erreurs():
    d = donnees("decathlon").iloc[:, :4].copy()
    d.iloc[0, 0] = np.nan
    with pytest.raises(ValueError, match="manquantes"):
        acp(d)
    d = donnees("decathlon").iloc[:, :4].copy()
    d["constante"] = 1.0
    with pytest.raises(ValueError, match="constante"):
        acp(d)


# ------------------------------------------------------------------ AFC

def _comparer_afc(res, r):
    verifier_json(res)
    q = len(res["lignes"][0]["coord"])
    proche(valeurs_propres(res), r["eig"], quoi="valeurs propres")
    F = tableau(res["lignes"], "coord")
    s = signes(F, M(r["row"]["coord"])[:, :q])
    for nous, cle in ((res["lignes"], "row"), (res["colonnes"], "col")):
        assert [e["id"] for e in nous] == r[cle]["coord"]["lignes"]
        proche(tableau(nous, "coord") * s, M(r[cle]["coord"]), quoi=f"coord {cle}")
        proche(tableau(nous, "contrib"), M(r[cle]["contrib"]), quoi=f"contrib {cle}")
        proche(tableau(nous, "cos2"), M(r[cle]["cos2"]), quoi=f"cos2 {cle}")
        for axe in range(q):
            assert math.isclose(sum(e["contrib"][axe] for e in nous), 100, rel_tol=1e-9)
    return s


def test_afc_avec_supplementaires():
    d = donnees("children")
    res = afc(d.iloc[:14, :5], n_axes=4, lignes_sup=d.iloc[14:, :5], colonnes_sup=d.iloc[:14, 5:])
    r = ref("afc_children_sup")
    s = _comparer_afc(res, r)
    for nous, cle in ((res["sup"]["lignes"], "row_sup"), (res["sup"]["colonnes"], "col_sup")):
        assert [e["id"] for e in nous] == r[cle]["coord"]["lignes"]
        proche(tableau(nous, "coord") * s, M(r[cle]["coord"]), quoi=f"coord {cle}")
        proche(tableau(nous, "cos2"), M(r[cle]["cos2"]), quoi=f"cos2 {cle}")


def test_afc_simple_et_khi2():
    from scipy.stats import chi2_contingency

    d = donnees("children").iloc[:14, :5]
    res = afc(d, n_axes=4)
    _comparer_afc(res, ref("afc_children_simple"))
    khi2, p, ddl, _ = chi2_contingency(d.to_numpy(), correction=False)
    assert math.isclose(res["khi2"]["valeur"], khi2, rel_tol=1e-10)
    assert res["khi2"]["ddl"] == ddl
    assert math.isclose(res["inertie_totale"], khi2 / d.to_numpy().sum(), rel_tol=1e-10)   # φ² = χ²/n


# ------------------------------------------------------------------ ACM

def _comparer_acm(res, r, *, exclues=()):
    """Compare à FactoMineR::MCA. `exclues` : identifiants des modalités passives (absentes de la référence)."""
    verifier_json(res)
    q = len(res["individus"]["coord"][0])
    proche(valeurs_propres(res), r["eig"], quoi="valeurs propres")
    F = A(res["individus"]["coord"])
    s = signes(F, M(r["ind"]["coord"])[:, :q])
    proche(F * s, M(r["ind"]["coord"]), quoi="coord individus")
    proche(A(res["individus"]["contrib"]), M(r["ind"]["contrib"]), quoi="contrib individus")
    proche(A(res["individus"]["cos2"]), M(r["ind"]["cos2"]), quoi="cos2 individus")
    meme_ordre_modalites(res["modalites"], r["niveaux_actives"])
    actives = [m for m in res["modalites"] if m["id"] not in exclues]
    assert len(actives) == len(r["var"]["coord"]["lignes"])
    proche(tableau(actives, "coord") * s, M(r["var"]["coord"]), quoi="coord modalités")
    proche(tableau(actives, "contrib"), M(r["var"]["contrib"]), quoi="contrib modalités")
    proche(tableau(actives, "cos2"), M(r["var"]["cos2"]), quoi="cos2 modalités")
    proche(tableau(actives, "vtest") * s, M(r["var"]["vtest"]), quoi="vtest modalités")
    if r.get("quali_sup"):
        mods = res["sup"]["modalites"]
        meme_ordre_modalites(mods, r["niveaux_sup"])
        proche(tableau(mods, "coord") * s, M(r["quali_sup"]["coord"]), quoi="coord quali sup")
        proche(tableau(mods, "cos2"), M(r["quali_sup"]["cos2"]), quoi="cos2 quali sup")
        proche(tableau(mods, "vtest") * s, M(r["quali_sup"]["vtest"]), quoi="vtest quali sup")
        quali = [v for v in res["sup"]["variables"] if v["type"] == "quali"]
        proche(tableau(quali, "eta2"), M(r["quali_sup"]["eta2"]), quoi="eta2 quali sup")
    if r.get("quanti_sup"):
        quanti = [v for v in res["sup"]["variables"] if v["type"] == "quanti"]
        proche(tableau(quanti, "coord") * s, M(r["quanti_sup"]["coord"]), quoi="cor quanti sup")
    for axe in range(q):
        assert math.isclose(sum(l[axe] for l in res["individus"]["contrib"]), 100, rel_tol=1e-9)
        assert math.isclose(sum(m["contrib"][axe] for m in actives), 100, rel_tol=1e-9)
        assert math.isclose(sum(v["contrib"][axe] for v in res["variables"]), 100, rel_tol=1e-9)
    return s


def test_acm_tea_avec_supplementaires():
    r = ref("acm_tea_sup")
    d = donnees("tea")
    act = d.iloc[:290]
    X = categoriel(act.iloc[:, :18], r["niveaux_actives"])
    res = acm(X, ind_sup=d.iloc[290:, :18], quali_sup=categoriel(act.iloc[:, 19:36], r["niveaux_sup"]),
              quanti_sup=act.iloc[:, [18]].astype(float))
    s = _comparer_acm(res, r)
    assert res["methode"] == "acm"
    # eta² des variables actives (FactoMineR : Q·λ·Σcontrib ; ici vrai rapport de corrélation : identiques en ACM standard)
    proche(tableau(res["variables"], "eta2"), M(r["var"]["eta2"]), quoi="eta2 actives")
    # Individus supplémentaires
    assert res["sup"]["individus"]["ids"] == r["ind_sup"]["coord"]["lignes"]
    proche(A(res["sup"]["individus"]["coord"]) * s, M(r["ind_sup"]["coord"]), quoi="coord ind sup")
    proche(A(res["sup"]["individus"]["cos2"]), M(r["ind_sup"]["cos2"]), quoi="cos2 ind sup")
    # Propriété : inertie totale = K/Q − 1
    K, Q = res["parametres"]["n_modalites"], res["parametres"]["n_variables"]
    assert math.isclose(res["inertie_totale"], K / Q - 1, rel_tol=1e-10)
    assert len(res["axes"]) == K - Q


def test_acm_tea_ponderee():
    r = ref("acm_tea_ponderee")
    d = donnees("tea")
    X = categoriel(d.iloc[:, :18], r["niveaux_actives"])
    res = acm(X, poids=r["poids"], quali_sup=categoriel(d.iloc[:, 19:22], r["niveaux_sup"]),
              quanti_sup=d.iloc[:, [18]].astype(float))
    _comparer_acm(res, r)
    proche(tableau(res["variables"], "eta2"), M(r["var"]["eta2"]), quoi="eta2 actives")


def test_acm_poison():
    r = ref("acm_poison")
    d = donnees("poison")
    X = categoriel(d.iloc[:, 4:15], r["niveaux_actives"])
    res = acm(X, quali_sup=categoriel(d.iloc[:, 2:4], r["niveaux_sup"]), quanti_sup=d.iloc[:, :2].astype(float))
    _comparer_acm(res, r)
    proche(tableau(res["variables"], "eta2"), M(r["var"]["eta2"]), quoi="eta2 actives")


def test_acm_taux_modifies():
    """Benzécri : GDAtools::modif.rate ; Greenacre : ca::mjca(lambda = "adjusted")."""
    r = ref("acm_tea_taux_modifies")
    res = acm(donnees("tea").iloc[:, :18])
    proche(valeurs_propres(res), r["eig"])
    nb = len(r["benzecri"])
    proche([a["pct_modifie"] for a in res["axes"][:nb]], r["benzecri"], quoi="Benzécri")
    proche([a["pct_modifie_cumule"] for a in res["axes"][:nb]], r["benzecri_cumule"], quoi="Benzécri cumulé")
    assert all(a["pct_modifie"] is None for a in res["axes"][nb:])       # axes où λ ≤ 1/Q
    ng = len(r["greenacre_pct"])
    assert ng == nb
    proche([a["pct_greenacre"] for a in res["axes"][:ng]], r["greenacre_pct"], rtol=1e-7, quoi="Greenacre")


def _passives(r):
    return [tuple(p) for p in r["passives"]]


def test_acm_specifique_contre_factominer():
    """FactoMineR::MCA(excl=) : mêmes axes, individus et modalités actives."""
    r = ref("acm_specifique_factominer")
    d = donnees("tea")
    X = categoriel(d.iloc[:, :18], r["niveaux_actives"])
    res = acm(X, passives=_passives(r), quali_sup=categoriel(d.iloc[:, 19:36], r["niveaux_sup"]),
              quanti_sup=d.iloc[:, [18]].astype(float))
    assert res["methode"] == "acm_specifique"
    exclues = {f"{v}::{m}" for v, m in _passives(r)}
    # FactoMineR ne restitue que les axes en nombre « min(n−1, K−Q) » : on compare ce préfixe commun.
    lam = valeurs_propres(res)
    nb = min(len(lam), len(r["eig"]))
    proche(lam[:nb], r["eig"][:nb], quoi="valeurs propres")
    r["eig"] = lam.tolist()
    _comparer_acm(res, r, exclues=exclues)
    passives = [m for m in res["modalites"] if m["passive"]]
    assert {m["id"] for m in passives} == exclues
    assert all(m["contrib"] is None for m in passives)


@pytest.mark.parametrize("nom", ["acm_specifique_gdatools", "acm_specifique_gdatools_ponderee"])
def test_acm_specifique_contre_gdatools(nom):
    """GDAtools::speMCA, supvar et modif.rate (GDAtools arrondit certaines sorties à 6 décimales)."""
    r = ref(nom)
    d = donnees("tea")
    X = categoriel(d.iloc[:, :18], r["niveaux_actives"])
    sup_noms = [v["variable"] for v in r["quali_sup"]]
    sup = categoriel(d[sup_noms], {v["variable"]: v["niveaux"] for v in r["quali_sup"]})
    res = acm(X, passives=_passives(r), poids=r.get("poids"), quali_sup=sup)
    verifier_json(res)
    q = 5
    lam = valeurs_propres(res)
    proche(lam, r["eig"][: len(lam)], quoi="valeurs propres")
    assert np.all(np.abs(r["eig"][len(lam):]) < 1e-12)                  # axes d'inertie nulle écartés chez nous
    proche([a["pct"] for a in res["axes"]], r["pct"][: len(lam)], quoi="taux bruts")
    nb = len(r["benzecri"])
    proche([a["pct_modifie"] for a in res["axes"][:nb]], r["benzecri"], quoi="Benzécri (convention GDAtools)")
    assert all(a["pct_greenacre"] is None for a in res["axes"])
    F = A(res["individus"]["coord"])
    s = signes(F, M(r["ind"]["coord"])[:, :q])
    proche(F * s, M(r["ind"]["coord"]), quoi="coord individus")
    arrondi = dict(rtol=0, atol=6e-7)                                    # sorties arrondies à 6 décimales
    proche(A(res["individus"]["contrib"]), M(r["ind"]["contrib"]), quoi="contrib individus", **arrondi)
    proche(A(res["individus"]["cos2"]), M(r["ind"]["cos2"]), quoi="cos2 individus", **arrondi)
    actives = [m for m in res["modalites"] if not m["passive"]]
    assert [f"{m['variable']}.{m['modalite']}" for m in actives] == r["categories"]
    proche(tableau(actives, "coord") * s, M(r["var"]["coord"]), quoi="coord modalités")
    proche(tableau(actives, "contrib"), M(r["var"]["contrib"]), quoi="contrib modalités", **arrondi)
    proche(tableau(actives, "cos2"), M(r["var"]["cos2"]), quoi="cos2 modalités", **arrondi)
    proche(tableau(actives, "vtest") * s, M(r["var"]["vtest"]), quoi="vtest modalités", rtol=0, atol=2e-6)
    proche([m["n"] for m in actives], r["var"]["poids"], rtol=0, atol=0.051, quoi="effectifs (arrondis à 0,1)")
    # Variables : contributions cumulées et eta² (vrai rapport de corrélation, modalités passives comprises)
    proche(tableau(res["variables"], "contrib"), M(r["var"]["contrib_variable"]), quoi="contrib variables", **arrondi)
    proche(tableau(res["variables"], "eta2"), M(r["var"]["eta2"]), quoi="eta2 variables", **arrondi)
    # Variables supplémentaires (supvar)
    for v in r["quali_sup"]:
        mods = [m for m in res["sup"]["modalites"] if m["variable"] == v["variable"]]
        assert [m["modalite"] for m in mods] == v["niveaux"]
        proche(tableau(mods, "coord") * s, M(v["coord"]), quoi="coord sup", **arrondi)
        proche(tableau(mods, "cos2"), M(v["cos2"]), quoi="cos2 sup", **arrondi)
        proche(tableau(mods, "vtest") * s, M(v["typic"]), quoi="typicalité sup", rtol=0, atol=2e-5)
        eta = next(x for x in res["sup"]["variables"] if x["id"] == v["variable"])["eta2"]
        proche(eta, v["eta2"], quoi="eta2 sup", **arrondi)


def test_acm_specifique_proprietes():
    d = donnees("tea").iloc[:, :18]
    passives = [("Tea", "green"), ("price", "p_unknown")]
    res = acm(d, passives=passives, n_axes=4)
    Q = 18
    # Inertie du nuage spécifique : (1/Q) Σ_{k actives} (1 − f_k)
    act = [m for m in res["modalites"] if not m["passive"]]
    assert math.isclose(res["inertie_totale"], sum(1 - m["n"] / 300 for m in act) / Q, rel_tol=1e-10)
    # Une modalité passive garde une coordonnée (point moyen de ses individus), mais ne contribue pas.
    F = A(res["individus"]["coord"])
    lam = valeurs_propres(res)[:4]
    green = next(m for m in res["modalites"] if m["id"] == "Tea::green")
    bary = F[(d["Tea"] == "green").to_numpy()].mean(axis=0)
    proche(green["coord"], bary / np.sqrt(lam))
    # Transition exacte : un individu actif replacé en supplémentaire retrouve ses coordonnées et ses cos².
    res2 = acm(d, passives=passives, n_axes=4, ind_sup=d.iloc[:25])
    proche(A(res2["sup"]["individus"]["coord"]), F[:25], quoi="transition individus")
    proche(A(res2["sup"]["individus"]["cos2"]), A(res["individus"]["cos2"])[:25])
    # Sans modalité passive, on retombe exactement sur l'ACM standard.
    proche(valeurs_propres(acm(d, passives=[])), valeurs_propres(acm(d)))


def test_acm_erreurs_et_avertissements():
    d = donnees("poison").iloc[:, 4:9].astype(object)
    d2 = d.copy()
    d2.iloc[0, 0] = np.nan
    with pytest.raises(ValueError, match="manquantes"):
        acm(d2)
    with pytest.raises(ValueError, match="introuvable"):
        acm(d, passives=[("Nausea", "inexistante")])
    with pytest.raises(ValueError, match="Toutes les modalités"):
        acm(d, passives=[("Nausea", "Nausea_n"), ("Nausea", "Nausea_y")])
    # Variables supplémentaires incomplètes : acceptées, individus ignorés pour la variable concernée.
    sup = donnees("poison").iloc[:, [2]].astype(object)
    sup.iloc[:5, 0] = np.nan
    res = acm(d, quali_sup=sup)
    assert any("sans réponse" in a for a in res["avertissements"])
    assert math.isclose(sum(m["n"] for m in res["sup"]["modalites"]), 50)
    verifier_json(res)


# ------------------------------------------------------------------ AFDM

def _comparer_afdm(res, r, quanti, quali):
    verifier_json(res)
    q = len(res["individus"]["coord"][0])
    proche(valeurs_propres(res)[:q], r["eig"], quoi="valeurs propres")
    F = A(res["individus"]["coord"])
    s = signes(F, M(r["ind"]["coord"]))
    proche(F * s, M(r["ind"]["coord"]), quoi="coord individus")
    proche(A(res["individus"]["contrib"]), M(r["ind"]["contrib"]), quoi="contrib individus")
    proche(A(res["individus"]["cos2"]), M(r["ind"]["cos2"]), quoi="cos2 individus")
    vq = [v for v in res["variables"] if v["type"] == "quanti"]
    assert [v["id"] for v in vq] == r["quanti"]["coord"]["lignes"]
    proche(tableau(vq, "coord") * s, M(r["quanti"]["coord"]), quoi="coord quanti")
    proche(tableau(vq, "contrib"), M(r["quanti"]["contrib"]), quoi="contrib quanti")
    proche(tableau(vq, "cos2"), M(r["quanti"]["cos2"]), quoi="cos2 quanti")
    mods = res["modalites"]
    assert [m["modalite"] for m in mods] == r["quali"]["coord"]["lignes"]
    proche(tableau(mods, "coord") * s, M(r["quali"]["coord"]), quoi="coord modalités")
    proche(tableau(mods, "contrib"), M(r["quali"]["contrib"]), quoi="contrib modalités")
    proche(tableau(mods, "cos2"), M(r["quali"]["cos2"]), quoi="cos2 modalités")
    proche(tableau(mods, "vtest") * s, M(r["quali"]["vtest"]), quoi="vtest modalités")
    # Tableau « var » de FactoMineR : r² (quanti) puis eta² (quali) ; contributions ; cos².
    ordre = quanti + quali
    assert r["var"]["coord"]["lignes"] == ordre
    par_id = {v["id"]: v for v in res["variables"]}
    proche(A([par_id[v]["liaison"] for v in ordre]), M(r["var"]["coord"]), quoi="liaisons")
    proche(A([par_id[v]["contrib"] for v in ordre]), M(r["var"]["contrib"]), quoi="contrib variables")
    proche(A([par_id[v]["cos2"] if par_id[v]["type"] == "quali" else np.array(par_id[v]["cos2"]) ** 2
              for v in ordre]), M(r["var"]["cos2"]), quoi="cos2 variables (convention FactoMineR)")
    for axe in range(q):
        assert math.isclose(sum(v["contrib"][axe] for v in res["variables"]), 100, rel_tol=1e-9)
    return s


def test_afdm_avec_supplementaires():
    r = ref("afdm_wine_sup")
    wine = donnees("wine")
    wn = wine.iloc[:, [1] + list(range(2, 12)) + [0, 12, 13]]
    assert list(wn.columns) == r["colonnes"]
    act = wn.iloc[2:]
    X = act.iloc[:, :11].copy()
    X["Soil"] = pd.Categorical(X["Soil"], categories=r["niveaux"]["Soil"])
    quali_sup = pd.DataFrame({"Label": pd.Categorical(act["Label"], categories=r["niveaux"]["Label"])}, index=act.index)
    res = afdm(X, ind_sup=wn.iloc[:2, :11], quali_sup=quali_sup, quanti_sup=act.iloc[:, 12:14])
    quanti = list(wn.columns[1:11])
    s = _comparer_afdm(res, r, quanti, ["Soil"])
    assert res["sup"]["individus"]["ids"] == r["ind_sup"]["coord"]["lignes"]
    proche(A(res["sup"]["individus"]["coord"]) * s, M(r["ind_sup"]["coord"]), quoi="coord ind sup")
    proche(A(res["sup"]["individus"]["cos2"]), M(r["ind_sup"]["cos2"]), quoi="cos2 ind sup")
    qs = [v for v in res["sup"]["variables"] if v["type"] == "quanti"]
    proche(tableau(qs, "coord") * s, M(r["quanti_sup"]["coord"]), quoi="cor quanti sup")
    ms = res["sup"]["modalites"]
    assert [m["modalite"] for m in ms] == r["quali_sup"]["coord"]["lignes"]
    proche(tableau(ms, "coord") * s, M(r["quali_sup"]["coord"]), quoi="coord quali sup")
    proche(tableau(ms, "cos2"), M(r["quali_sup"]["cos2"]), quoi="cos2 quali sup")
    proche(tableau(ms, "vtest") * s, M(r["quali_sup"]["vtest"]), quoi="vtest quali sup")
    ls = [v for v in res["sup"]["variables"] if v["type"] == "quali"]
    proche(tableau(ls, "eta2"), M(r["quali_sup"]["eta2"]), quoi="eta2 quali sup")
    # « coord.sup » de FactoMineR : r² des quantitatives supplémentaires puis eta² des qualitatives.
    proche(A([v["liaison"] for v in qs + ls]), M(r["var"]["coord_sup"]), quoi="liaisons sup")


def test_afdm_ponderee():
    r = ref("afdm_wine_ponderee")
    wine = donnees("wine").iloc[:, :10].copy()
    for col in ("Label", "Soil"):
        wine[col] = pd.Categorical(wine[col], categories=r["niveaux"][col])
    res = afdm(wine, poids=r["poids"])
    _comparer_afdm(res, r, list(wine.columns[2:]), ["Label", "Soil"])


def test_afdm_proprietes_et_erreurs():
    wine = donnees("wine").iloc[:, :8]
    res = afdm(wine)
    # Inertie totale = nb de quantitatives + (nb de modalités − nb de qualitatives)
    assert math.isclose(res["inertie_totale"], 6 + (res["parametres"]["n_modalites"] - 2), rel_tol=1e-10)
    # La coordonnée d'une modalité est le point moyen des individus qui la portent.
    F = A(res["individus"]["coord"])
    m = next(m for m in res["modalites"] if m["id"] == "Soil::Env1")
    proche(m["coord"], F[(wine["Soil"] == "Env1").to_numpy()].mean(axis=0))
    with pytest.raises(ValueError, match="quantitative et une variable qualitative"):
        afdm(wine.iloc[:, 2:])


# ------------------------------------------------------------------ CAH

def _rand_ajuste(a, b) -> float:
    t = pd.crosstab(pd.Series(a), pd.Series(b)).to_numpy().astype(float)
    comb = lambda x: x * (x - 1) / 2
    s_ij, s_a, s_b, tot = comb(t).sum(), comb(t.sum(axis=1)).sum(), comb(t.sum(axis=0)).sum(), comb(t.sum())
    attendu = s_a * s_b / tot
    return float((s_ij - attendu) / ((s_a + s_b) / 2 - attendu))


def _coord_acp_decathlon(poids=None):
    d = donnees("decathlon").iloc[:, :10]
    res = acp(d, poids=poids)
    return pd.DataFrame(res["individus"]["coord"], index=res["individus"]["ids"])


def _comparer_cah(res, r, *, consol):
    verifier_json(res)
    nb = len(r["gains"])
    proche([g["gain"] for g in res["gains"]][:nb], r["gains"][: len(res["gains"])], quoi="gains d'inertie")
    proche(res["inertie_totale"], r["intra"][0], quoi="inertie totale")
    proche([g["inertie_intra"] for g in res["gains"]][: len(r["intra"]) - 1],
           r["intra"][1: len(res["gains"]) + 1], quoi="inerties intra")
    partition = pd.Series(res["partition"], index=res["ids"]).loc[r["individus"]].tolist()
    assert partition == r["partition"]                      # même numérotation (ordre des centres sur l'axe 1)
    proche(res["inertie_inter"], r["bw_apres"] if consol else r["bw_avant"], quoi="inertie inter")
    if consol:
        proche(res["consolidation"]["inertie_inter_avant"], r["bw_avant"])
    for c, par in zip(res["classes"], r["parangons"]):
        assert [p["id"] for p in c["parangons"]] == par["noms"]
        proche([p["distance"] for p in c["parangons"]], par["distances"], quoi="distances des parangons")


def test_cah_suggestion_du_nombre_de_classes():
    r = ref("cah_decathlon_auto")
    res = cah(_coord_acp_decathlon(), consolidation=False)
    assert res["k"] == res["k_suggere"] == r["nb_classes"]
    proche([x["rapport"] for x in res["suggestion"]["rapports"]], r["quot"], quoi="rapports W(k)/W(k−1)")
    _comparer_cah(res, r, consol=False)


def test_cah_consolidation():
    r = ref("cah_decathlon_auto_consol")
    res = cah(_coord_acp_decathlon(), consolidation=True)
    _comparer_cah(res, r, consol=True)
    assert res["consolidation"]["inertie_inter_apres"] >= res["consolidation"]["inertie_inter_avant"] - 1e-12


def test_cah_k_impose():
    res = cah(_coord_acp_decathlon(), k=4, consolidation=False)
    assert res["k"] == 4 and len(res["classes"]) == 4
    _comparer_cah(res, ref("cah_decathlon_k4"), consol=False)
    assert math.isclose(res["inertie_inter"] + res["inertie_intra"], res["inertie_totale"], rel_tol=1e-12)
    assert math.isclose(sum(c["inertie_intra"] for c in res["classes"]), res["inertie_intra"], rel_tol=1e-9)
    assert sum(f["n"] for f in res["dendrogramme"]["feuilles"]) == res["n"]


def test_cah_ponderee():
    r = ref("cah_decathlon_ponderee")
    coord = _coord_acp_decathlon(poids=r["poids"])
    s = signes(coord.to_numpy(), M(r["coord"]))
    proche(coord.to_numpy() * s, M(r["coord"]))
    res = cah(coord, poids=r["poids"], k=3, consolidation=False)
    _comparer_cah(res, r, consol=False)


def test_cah_tea():
    coord_res = acm(donnees("tea").iloc[:, :18])
    coord = pd.DataFrame(coord_res["individus"]["coord"], index=coord_res["individus"]["ids"])
    _comparer_cah(cah(coord, k=3, consolidation=False), ref("cah_tea_k3"), consol=False)
    r = ref("cah_tea_k3_consol")
    res = cah(coord, k=3, consolidation=True)
    partition = pd.Series(res["partition"], index=res["ids"]).loc[r["individus"]].tolist()
    # HCPC consolide par Hartigan-Wong limité à 10 itérations : on exige une partition quasi identique
    # et une inertie inter au moins aussi bonne.
    assert _rand_ajuste(partition, r["partition"]) > 0.95
    assert res["inertie_inter"] >= r["bw_apres"] * (1 - 1e-9)


def test_ward_pondere_equivaut_a_scipy_a_poids_egaux():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(60, 3))
    p = np.full(60, 1 / 60)
    Z_scipy = _arbre_ward(X, p)
    Z_nous = _ward_pondere(X, p)
    proche(Z_nous[:, 2], Z_scipy[:, 2], quoi="hauteurs")
    for k in (2, 3, 5, 8):
        a = hierarchy.fcluster(Z_scipy, k, "maxclust")
        b = hierarchy.fcluster(Z_nous, k, "maxclust")
        assert math.isclose(_rand_ajuste(a, b), 1.0)


def test_cah_erreurs():
    with pytest.raises(ValueError, match="entre 2 et"):
        cah(_coord_acp_decathlon(), k=1)
    with pytest.raises(ValueError, match="mêmes coordonnées"):
        cah(pd.DataFrame(np.ones((6, 2))))


# ------------------------------------------------------------------ description des classes

def _comparer_catdes(res, r):
    verifier_json(res)
    # Liaisons globales : p du χ² (catdes ne garde que p et ddl) et eta² / p de l'analyse de variance.
    chi = {nom: ligne for nom, ligne in zip(r["chi2"]["lignes"], r["chi2"]["donnees"])}
    for v in res["variables_quali"]:
        proche([v["p"], v["ddl"]], chi[v["variable"]], quoi=f"χ² {v['variable']}")
    qv = {nom: ligne for nom, ligne in zip(r["quanti_var"]["lignes"], r["quanti_var"]["donnees"])}
    for v in res["variables_quanti"]:
        proche([v["eta2"], v["p"]], qv[v["variable"]], quoi=f"eta² {v['variable']}")
    for classe in res["par_classe"]:
        attendu = r["categories"][str(classe["classe"])]
        nous = {f"{m['variable']}={m['modalite']}": m for m in classe["modalites"]}
        assert set(nous) == set(attendu["lignes"])
        for nom, ligne in zip(attendu["lignes"], attendu["donnees"]):
            m = nous[nom]
            # p proche de 1 : la somme 2·P(X<x)+P(X=x) perd des chiffres ; d'où la tolérance absolue.
            proche([m["cla_mod"], m["mod_cla"], m["global"], m["p"], m["vtest"]], ligne,
                   rtol=1e-7, atol=1e-9, quoi=f"classe {classe['classe']} {nom}")
        att_q = r["quanti"][str(classe["classe"])]
        for q in classe["quanti"]:
            ligne = att_q["donnees"][att_q["lignes"].index(q["variable"])]
            proche([q["vtest"], q["moyenne_classe"], q["moyenne_globale"], q["ecart_type_classe"],
                    q["ecart_type_global"], q["p"]], ligne, quoi=f"quanti classe {classe['classe']}")


@pytest.mark.parametrize("nom", ["catdes_tea", "catdes_tea_ponderee"])
def test_decrire_classes(nom):
    r = ref(nom)
    d = donnees("tea")
    res = decrire_classes(r["partition"], quali=d[["Tea", "How", "sex", "SPC", "age_Q"]],
                          quanti=d[["age"]].astype(float), poids=r.get("poids"))
    _comparer_catdes(res, r)
    assert res["classes"] == [1, 2, 3]
    # Chaque classe : modalités triées par v-test décroissant.
    for c in res["par_classe"]:
        v = [m["vtest"] for m in c["modalites"]]
        assert v == sorted(v, reverse=True)


def test_decrire_classes_manquants_et_extremes():
    part = [1] * 50 + [2] * 50
    quali = pd.DataFrame({"a": ["x"] * 50 + ["y"] * 50, "b": ["u", None] * 50})
    res = decrire_classes(part, quali=quali)
    verifier_json(res)
    c1 = res["par_classe"][0]
    x = next(m for m in c1["modalites"] if m["modalite"] == "x")
    assert x["vtest"] > 9 and x["cla_mod"] == 100 and x["mod_cla"] == 100      # association parfaite : v-test fini
    assert any(m["modalite"] == "(manquant)" for m in c1["modalites"])
    a = next(v for v in res["variables_quali"] if v["variable"] == "a")
    assert math.isclose(a["v_cramer"], 1.0)
