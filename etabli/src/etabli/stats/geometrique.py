"""Analyse géométrique des données : ACP, AFC, ACM (standard et spécifique), AFDM.

Principe commun
---------------
Toutes ces méthodes sont une même opération d'algèbre linéaire : la décomposition
en valeurs singulières (SVD) d'un tableau transformé, les lignes et les colonnes
étant munies de poids. Si ``T`` est le tableau transformé, ``r`` les poids des
lignes (somme 1) et ``c`` les poids des colonnes, on décompose

    S = diag(sqrt(r)) · T · diag(sqrt(c)) = U · diag(s) · Vᵗ

Les valeurs propres (inertie portée par chaque axe) sont ``λ = s²`` ; les
coordonnées principales des lignes sont ``F = diag(1/sqrt(r)) · U · diag(s)`` et
celles des colonnes ``G = diag(1/sqrt(c)) · V · diag(s)``. Seul le tableau ``T``
et les poids changent d'une méthode à l'autre :

* ACP   : T = variables centrées (et réduites) ; r = poids des individus ; c = 1.
* AFC   : T = f_ij / (f_i. f_.j) − 1 ; r = f_i. ; c = f_.j.
* ACM   : AFC du tableau disjonctif complet, c'est-à-dire
          T_ik = (z_ik − f_k) / f_k ; r = p_i ; c = f_k / Q
          (ACM spécifique : on retire de T les colonnes des modalités passives,
          sans rien changer d'autre — Le Roux & Rouanet 2004, 2010).
* AFDM  : ACP du tableau juxtaposant les variables quantitatives centrées-réduites
          et les indicatrices transformées (z_ik − f_k) / sqrt(f_k) (Pagès 2004).

La seule brique numérique est ``numpy.linalg.svd`` ; tout le reste est écrit
explicitement ci-dessous pour pouvoir être relu.

Conventions
-----------
* Poids des individus (``poids``) : facultatifs. Ils sont **normalisés pour que
  leur somme soit égale au nombre d'individus actifs** ; les effectifs ``n`` des
  modalités sont donc des effectifs pondérés comparables à des effectifs bruts et
  les valeurs-tests ne dépendent pas de l'échelle arbitraire des poids
  (convention de GDAtools ; FactoMineR donne les mêmes résultats quand on lui
  fournit des poids de somme n).
* Contributions en % (somme = 100 par axe) ; cos² en proportion (0-1).
* Signe des axes : arbitraire en soi. Pour que les résultats soient
  reproductibles d'une machine à l'autre et superposables à ceux de FactoMineR, on
  applique sa convention : chaque axe est orienté de sorte que la somme des
  composantes du vecteur singulier droit (colonnes) soit positive.
* Valeur-test d'une modalité : coordonnée de son point moyen rapportée à
  l'écart-type qu'aurait la moyenne de n_k individus tirés au hasard sans remise,
  ``v = (barycentre / sqrt(λ)) · sqrt(n_k (n − 1) / (n − n_k))`` (Lebart, Morineau
  & Piron). |v| > 2 signale un écart à l'origine notable au seuil usuel de 5 %.
* Les variables **actives** ne doivent contenir aucune valeur manquante (sinon
  ``ValueError``). Les variables **supplémentaires** peuvent en contenir : les
  individus concernés sont alors ignorés pour cette variable (signalé dans
  ``avertissements``).
* Les sorties sont des ``dict`` entièrement sérialisables en JSON.

Validation
----------
``tests/test_geometrique.py`` compare ces fonctions à FactoMineR 2.9 (PCA, CA,
MCA, FAMD) et GDAtools 2.3.1 (speMCA, supvar, modif.rate), à 1e-8 près en
relatif. Divergences connues et assumées :

1. *Individus supplémentaires en ACM spécifique.* On applique la formule de
   transition exacte, ``y_i = [Σ_{k actives} (z_ik − f_k) y_k] / (Q sqrt(λ))``,
   qui redonne exactement ses coordonnées à un individu actif replacé en
   supplémentaire. ``GDAtools::supind`` omet le terme de centrage ``Σ f_k y_k``
   (nul en ACM standard, non nul dès qu'il y a des modalités passives) et
   ``FactoMineR::MCA(excl=)`` fait intervenir les modalités passives ; leurs
   résultats diffèrent donc des nôtres (et entre eux) dans ce seul cas.
2. *eta² des variables en ACM spécifique.* On calcule le vrai rapport de
   corrélation entre l'axe et la variable (toutes modalités, passives comprises,
   comme GDAtools) ; FactoMineR renvoie Q·λ·(somme des contributions des
   modalités actives), qui n'est plus un rapport de corrélation dans ce cas.
3. *Taux modifiés en ACM spécifique* : formule de Benzécri appliquée avec le
   seuil 1/Q (convention de GDAtools) ; le taux de Greenacre n'est pas défini.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np
import pandas as pd

__all__ = ["acp", "afc", "acm", "afdm"]

# Une valeur propre est considérée comme nulle en dessous de ce seuil relatif.
_EPS_AXE = 1e-12
# Seuil d'effectif relatif en dessous duquel une modalité active est signalée.
_SEUIL_MODALITE_RARE = 0.05


# --------------------------------------------------------------------------
# Utilitaires généraux
# --------------------------------------------------------------------------

def _propre(obj: Any) -> Any:
    """Convertit récursivement en types Python natifs ; NaN et ±inf deviennent None."""
    if isinstance(obj, dict):
        return {str(k): _propre(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_propre(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _propre(obj.tolist())
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if obj is pd.NA or obj is pd.NaT:
        return None
    return obj


def _poids(poids, n: int, nom: str = "poids") -> tuple[np.ndarray, np.ndarray]:
    """Renvoie (w, p) : poids normalisés de somme n, et poids relatifs de somme 1."""
    if poids is None:
        w = np.ones(n, dtype=float)
    else:
        w = np.asarray(poids, dtype=float).reshape(-1)
        if w.shape[0] != n:
            raise ValueError(
                f"Le vecteur « {nom} » compte {w.shape[0]} valeurs pour {n} individus actifs."
            )
        if not np.all(np.isfinite(w)) or np.any(w < 0):
            raise ValueError("Les poids doivent être des nombres finis et positifs ou nuls.")
        if w.sum() <= 0:
            raise ValueError("La somme des poids est nulle.")
        w = w * n / w.sum()
    return w, w / n


def _svd_ponderee(T: np.ndarray, r: np.ndarray, c: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """SVD généralisée de T pour les poids de lignes r et de colonnes c.

    Renvoie (U, s, V) tels que T = U·diag(s)·Vᵗ, avec Uᵗ·diag(r)·U = I et
    Vᵗ·diag(c)·V = I. Seuls les axes d'inertie non nulle sont conservés.
    """
    S = np.sqrt(r)[:, None] * T * np.sqrt(c)[None, :]
    U, s, Vt = np.linalg.svd(S, full_matrices=False)
    V = Vt.T
    # Orientation déterministe des axes (convention FactoMineR).
    signe = np.sign(V.sum(axis=0))
    signe[signe == 0] = 1.0
    U, V = U * signe, V * signe
    # On écarte les axes d'inertie numériquement nulle.
    lam = s**2
    garde = lam > _EPS_AXE * max(lam.sum(), 1e-300)
    U, s, V = U[:, garde], s[garde], V[:, garde]
    return U / np.sqrt(r)[:, None], s, V / np.sqrt(c)[None, :]


def _table_axes(lam: np.ndarray) -> list[dict]:
    pct = 100 * lam / lam.sum()
    cumul = np.cumsum(pct)
    return [
        {"axe": i + 1, "valeur_propre": float(lam[i]), "pct": float(pct[i]), "pct_cumule": float(cumul[i])}
        for i in range(len(lam))
    ]


def _n_axes(n_axes: int, disponibles: int, avertissements: list[str]) -> int:
    n_axes = int(n_axes)
    if n_axes < 1:
        raise ValueError("Le nombre d'axes demandé doit être au moins 1.")
    if disponibles < 1:
        raise ValueError("Le tableau n'a aucune inertie : toutes les variables sont constantes.")
    if n_axes > disponibles:
        avertissements.append(
            f"{n_axes} axes demandés, mais le tableau n'en compte que {disponibles} d'inertie non nulle : "
            f"{disponibles} axes sont restitués."
        )
        n_axes = disponibles
    return n_axes


def _ids(index: Iterable) -> list[str]:
    return [str(i) for i in index]


def _df(X, nom: str) -> pd.DataFrame:
    if isinstance(X, pd.Series):
        X = X.to_frame()
    if not isinstance(X, pd.DataFrame):
        X = pd.DataFrame(X)
    if X.shape[1] == 0:
        raise ValueError(f"« {nom} » ne contient aucune variable.")
    X = X.copy()
    X.columns = [str(c) for c in X.columns]
    if len(set(X.columns)) != X.shape[1]:
        raise ValueError(f"« {nom} » contient des noms de variables en double.")
    return X


def _numerique(X: pd.DataFrame, nom: str, manquants_permis: bool = False) -> np.ndarray:
    try:
        A = X.to_numpy(dtype=float, na_value=np.nan)
    except (TypeError, ValueError) as e:
        raise ValueError(f"« {nom} » doit ne contenir que des variables quantitatives ({e}).") from None
    if not manquants_permis and np.isnan(A).any():
        fautives = [c for c, m in zip(X.columns, np.isnan(A).any(axis=0)) if m]
        raise ValueError(
            "Valeurs manquantes dans des variables actives : " + ", ".join(fautives) + ". "
            "Les variables actives doivent être complètes : restreignez la population, retirez la variable "
            "ou traitez la non-réponse avant l'analyse."
        )
    return A


def _aligner(sup: pd.DataFrame, index: pd.Index, nom: str) -> pd.DataFrame:
    """Vérifie qu'un tableau de variables supplémentaires porte sur les individus actifs."""
    if len(sup) != len(index):
        raise ValueError(
            f"« {nom} » compte {len(sup)} lignes alors que l'analyse porte sur {len(index)} individus actifs."
        )
    if not sup.index.equals(index):
        if sup.index.is_unique and index.is_unique and set(sup.index) == set(index):
            sup = sup.loc[index]
        else:
            raise ValueError(f"L'index de « {nom} » ne correspond pas à celui des individus actifs.")
    return sup


# --------------------------------------------------------------------------
# Variables qualitatives : modalités et tableau disjonctif
# --------------------------------------------------------------------------

def _modalites(serie: pd.Series) -> list:
    """Modalités observées, dans l'ordre des catégories si la variable est catégorielle."""
    if isinstance(serie.dtype, pd.CategoricalDtype):
        presentes = set(serie.dropna().unique())
        return [c for c in serie.cat.categories if c in presentes]
    vues = pd.unique(serie.dropna())
    try:
        return sorted(vues)
    except TypeError:
        return sorted(vues, key=str)


def _disjonctif(X: pd.DataFrame) -> tuple[np.ndarray, list[tuple[str, Any]], list[int]]:
    """Tableau disjonctif complet Z (n × K), liste des (variable, modalité), index de variable par colonne.

    Une valeur manquante donne une ligne de zéros pour la variable concernée.
    """
    blocs, cats, var_idx = [], [], []
    for j, col in enumerate(X.columns):
        s = X[col]
        mods = _modalites(s)
        valeurs = s.to_numpy(dtype=object)
        for m in mods:
            blocs.append((valeurs == m).astype(float))
            cats.append((col, m))
            var_idx.append(j)
    if not blocs:
        return np.zeros((len(X), 0)), [], []
    return np.column_stack(blocs), cats, var_idx


def _id_modalite(variable: str, modalite: Any) -> str:
    return f"{variable}::{modalite}"


# --------------------------------------------------------------------------
# Éléments supplémentaires communs
# --------------------------------------------------------------------------

def _eta2(F: np.ndarray, valeurs: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Rapport de corrélation eta² entre chaque axe (colonnes de F) et une variable qualitative.

    eta² = variance inter-modalités des coordonnées / variance totale, calculé sur
    les individus pour lesquels la variable est renseignée.
    """
    ok = ~pd.isna(valeurs)
    if ok.sum() == 0:
        return np.full(F.shape[1], np.nan)
    Fk, pk, vk = F[ok], p[ok] / p[ok].sum(), valeurs[ok]
    moy = pk @ Fk
    totale = pk @ (Fk - moy) ** 2
    inter = np.zeros(F.shape[1])
    for m in pd.unique(vk):
        sel = vk == m
        poids_m = pk[sel].sum()
        if poids_m > 0:
            inter += poids_m * ((pk[sel] @ Fk[sel]) / poids_m - moy) ** 2
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(totale > 0, inter / totale, np.nan)


def _quanti_sup(Q: pd.DataFrame, F: np.ndarray, p: np.ndarray, reduire: bool, avert: list[str]) -> list[dict]:
    """Variables quantitatives supplémentaires : corrélation (pondérée) avec chaque axe.

    ``coord`` est la corrélation si ``reduire`` (cas général), sinon la covariance
    avec la composante normée (ACP non réduite, comme FactoMineR) ; ``cor`` est
    toujours la corrélation et ``cos2`` son carré.
    """
    A = _numerique(Q, "quanti_sup", manquants_permis=True)
    sortie = []
    for j, nom in enumerate(Q.columns):
        x = A[:, j]
        ok = ~np.isnan(x)
        if ok.sum() < 2:
            avert.append(f"Variable supplémentaire « {nom} » : moins de 2 valeurs renseignées, non projetée.")
            continue
        if not ok.all():
            avert.append(
                f"Variable supplémentaire « {nom} » : {int((~ok).sum())} valeur(s) manquante(s), "
                "corrélations calculées sur les individus renseignés."
            )
        pk = p[ok] / p[ok].sum()
        xc = x[ok] - pk @ x[ok]
        sd_x = math.sqrt(pk @ xc**2)
        Fc = F[ok] - pk @ F[ok]
        sd_F = np.sqrt(pk @ Fc**2)
        with np.errstate(divide="ignore", invalid="ignore"):
            cov = (pk * xc) @ Fc / sd_F          # covariance avec la composante normée
            cor = cov / sd_x if sd_x > 0 else np.full_like(cov, np.nan)
        if sd_x == 0:
            avert.append(f"Variable supplémentaire « {nom} » constante : corrélations non définies.")
        sortie.append({
            "id": nom, "type": "quanti", "n": int(ok.sum()),
            "coord": cor if reduire else cov, "cor": cor, "cos2": cor**2,
        })
    return sortie


def _quali_sup_barycentres(
    S: pd.DataFrame, F: np.ndarray, lam: np.ndarray, w: np.ndarray, *,
    mode: str, Z_espace: np.ndarray | None = None, poids_col: np.ndarray | None = None,
    avert: list[str],
) -> tuple[list[dict], list[dict]]:
    """Modalités supplémentaires : points moyens des individus qui les portent.

    mode = "acp"  : coord = barycentre des coordonnées des individus ;
                    cos² = coord² / d², d² = distance² du barycentre à l'origine dans
                    l'espace complet (``Z_espace``, tableau transformé, métrique ``poids_col``).
    mode = "acm"  : coord = barycentre / sqrt(λ) (coordonnée principale d'une colonne
                    supplémentaire en AFC) ; cos² = coord² / (1/f_k − 1).
    Dans les deux cas : v-test = (barycentre / sqrt(λ)) · sqrt(n_k (n − 1) / (n − n_k)).
    """
    n = len(w)
    p = w / n
    mods_out, vars_out = [], []
    for nom in S.columns:
        valeurs = S[nom].to_numpy(dtype=object)
        ok = ~pd.isna(valeurs)
        n_manq = int((~ok).sum())
        if n_manq:
            avert.append(
                f"Variable supplémentaire « {nom} » : {n_manq} individu(s) sans réponse, ignoré(s) pour cette variable."
            )
        for m in _modalites(S[nom]):
            sel = valeurs == m
            n_k = float(w[sel].sum())
            if n_k <= 0:
                continue
            bary = (w[sel] @ F[sel]) / n_k
            with np.errstate(divide="ignore", invalid="ignore"):
                coef_vtest = math.sqrt(n_k * (n - 1) / (n - n_k)) if n - n_k > 1e-9 else float("nan")
                vtest = bary / np.sqrt(lam) * coef_vtest
                if mode == "acm":
                    coord = bary / np.sqrt(lam)
                    f_k = n_k / n
                    cos2 = coord**2 / (1 / f_k - 1) if f_k < 1 else np.full_like(coord, np.nan)
                else:
                    coord = bary
                    g = (w[sel] @ Z_espace[sel]) / n_k
                    d2 = float((g**2 * poids_col).sum())
                    cos2 = coord**2 / d2 if d2 > 0 else np.full_like(coord, np.nan)
            mods_out.append({
                "id": _id_modalite(nom, m), "variable": nom, "modalite": str(m), "n": n_k,
                "coord": coord, "cos2": cos2, "vtest": vtest,
            })
        vars_out.append({"id": nom, "type": "quali", "n": int(ok.sum()), "eta2": _eta2(F, valeurs, p)})
    return mods_out, vars_out


# --------------------------------------------------------------------------
# ACP
# --------------------------------------------------------------------------

def acp(X, *, reduire: bool = True, poids=None, n_axes: int = 5,
        ind_sup=None, quanti_sup=None, quali_sup=None) -> dict:
    """Analyse en composantes principales (équivalent de ``FactoMineR::PCA``).

    Paramètres
    ----------
    X : DataFrame individus × variables quantitatives actives (sans valeur manquante).
    reduire : True = ACP normée (variables centrées-réduites, chacune pèse 1 dans
        l'inertie) ; False = ACP sur covariances (les variables de forte variance
        dominent : à réserver à des variables de même unité).
    poids : poids des individus (facultatif).
    ind_sup : DataFrame d'individus supplémentaires (mêmes colonnes que X).
    quanti_sup, quali_sup : DataFrames de variables supplémentaires, alignés sur X.

    Calcul : SVD du tableau centré(-réduit) Z avec les poids p_i des individus.
    Individus : F = U·s. Variables : G = V·s (= corrélations variable-axe si
    ``reduire``). contrib_i = 100·p_i·F_i²/λ ; cos²_i = F_i² / ||z_i||².
    """
    avert: list[str] = []
    X = _df(X, "X")
    A = _numerique(X, "X")
    n, k = A.shape
    if n < 2:
        raise ValueError("Il faut au moins 2 individus actifs.")
    w, p = _poids(poids, n)

    # 1. Centrage (moyennes pondérées) et réduction (écarts-types pondérés, dénominateur n).
    moy = p @ A
    Zc = A - moy
    ecart = np.sqrt(p @ Zc**2)
    if reduire:
        constantes = [c for c, e in zip(X.columns, ecart) if e < 1e-12]
        if constantes:
            raise ValueError("Variable(s) constante(s), impossible(s) à réduire : " + ", ".join(constantes) + ".")
        diviseur = ecart
    else:
        diviseur = np.ones(k)
    Z = Zc / diviseur

    # 2. SVD pondérée (colonnes de poids 1).
    U, s, V = _svd_ponderee(Z, p, np.ones(k))
    lam_tous = s**2
    q = _n_axes(n_axes, len(s), avert)
    U, V, lam = U[:, :q], V[:, :q], lam_tous[:q]

    # 3. Individus.
    F = U * np.sqrt(lam)
    d2_ind = (Z**2).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        cos2_ind = np.where(d2_ind[:, None] > 0, F**2 / d2_ind[:, None], np.nan)
    contrib_ind = 100 * p[:, None] * F**2 / lam

    # 4. Variables.
    G = V * np.sqrt(lam)
    d2_var = p @ Z**2                       # = 1 si réduite, = variance sinon
    cor = G / np.sqrt(d2_var)[:, None]
    variables = [
        {"id": nom, "type": "quanti", "coord": G[j], "cor": cor[j], "contrib": 100 * V[j] ** 2,
         "cos2": cor[j] ** 2, "moyenne": moy[j], "ecart_type": ecart[j]}
        for j, nom in enumerate(X.columns)
    ]

    sup: dict[str, Any] = {}
    # 5. Individus supplémentaires : même transformation (moyennes et écarts-types des actifs), puis projection.
    if ind_sup is not None and len(ind_sup):
        IS = _df(ind_sup, "ind_sup")
        manquantes = [c for c in X.columns if c not in IS.columns]
        if manquantes:
            raise ValueError("Variables absentes des individus supplémentaires : " + ", ".join(manquantes) + ".")
        Zs = (_numerique(IS[list(X.columns)], "ind_sup") - moy) / diviseur
        Fs = Zs @ V
        d2s = (Zs**2).sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            sup["individus"] = {"ids": _ids(IS.index), "coord": Fs,
                                "cos2": np.where(d2s[:, None] > 0, Fs**2 / d2s[:, None], np.nan)}
    # 6. Variables supplémentaires.
    sup_vars: list[dict] = []
    if quanti_sup is not None:
        QS = _aligner(_df(quanti_sup, "quanti_sup"), X.index, "quanti_sup")
        sup_vars += _quanti_sup(QS, F, p, reduire, avert)
    if quali_sup is not None:
        LS = _aligner(_df(quali_sup, "quali_sup"), X.index, "quali_sup")
        mods, vs = _quali_sup_barycentres(LS, F, lam, w, mode="acp", Z_espace=Z, poids_col=np.ones(k), avert=avert)
        sup["modalites"] = mods
        sup_vars += vs
    if sup_vars:
        sup["variables"] = sup_vars

    return _propre({
        "methode": "acp",
        "n": n,
        "axes": _table_axes(lam_tous),
        "inertie_totale": float(lam_tous.sum()),
        "individus": {"ids": _ids(X.index), "coord": F, "contrib": contrib_ind, "cos2": cos2_ind},
        "variables": variables,
        "sup": sup,
        "parametres": {"reduire": bool(reduire), "n_axes": q, "pondere": poids is not None,
                       "variables_actives": list(X.columns), "n_ind_sup": 0 if ind_sup is None else len(ind_sup)},
        "avertissements": avert,
    })


# --------------------------------------------------------------------------
# AFC
# --------------------------------------------------------------------------

def afc(N, *, n_axes: int = 5, lignes_sup=None, colonnes_sup=None) -> dict:
    """Analyse factorielle des correspondances d'un tableau de contingence (``FactoMineR::CA``).

    N : DataFrame d'effectifs (lignes × colonnes actives), valeurs ≥ 0.
    lignes_sup : DataFrame de lignes supplémentaires (mêmes colonnes que N).
    colonnes_sup : DataFrame de colonnes supplémentaires (mêmes lignes que N).

    Calcul : fréquences f_ij = n_ij / n ; marges r_i (lignes) et c_j (colonnes) ;
    T_ij = f_ij / (r_i c_j) − 1 (écart relatif à l'indépendance) ; SVD de T avec les
    poids r et c. L'inertie totale vaut φ² = χ² / n. Un élément supplémentaire est
    placé au barycentre de son profil (formules de transition).
    """
    from scipy import stats

    avert: list[str] = []
    N = _df(N, "N")
    N.index = [str(i) for i in N.index]
    A = _numerique(N, "N")
    if (A < 0).any():
        raise ValueError("Un tableau de contingence ne peut pas contenir d'effectifs négatifs.")
    lig_ok, col_ok = A.sum(axis=1) > 0, A.sum(axis=0) > 0
    if not lig_ok.all():
        avert.append("Lignes de total nul retirées : " + ", ".join(N.index[~lig_ok]) + ".")
    if not col_ok.all():
        avert.append("Colonnes de total nul retirées : " + ", ".join(N.columns[~col_ok]) + ".")
    N = N.loc[lig_ok, col_ok]
    A = A[np.ix_(lig_ok, col_ok)]
    I, J = A.shape
    if I < 2 or J < 2:
        raise ValueError("L'AFC demande au moins 2 lignes et 2 colonnes d'effectif non nul.")

    total = A.sum()
    P = A / total
    r, c = P.sum(axis=1), P.sum(axis=0)
    T = P / np.outer(r, c) - 1

    U, s, V = _svd_ponderee(T, r, c)
    lam_tous = s**2
    q = _n_axes(n_axes, len(s), avert)
    U, V, lam = U[:, :q], V[:, :q], lam_tous[:q]

    F, G = U * np.sqrt(lam), V * np.sqrt(lam)
    d2_lig = (T**2 * c).sum(axis=1)          # distance du χ² du profil-ligne au profil moyen
    d2_col = (T**2 * r[:, None]).sum(axis=0)

    def points(noms, coord, masse, d2, effectifs):
        return [
            {"id": str(nom), "n": float(effectifs[i]), "masse": float(masse[i]), "coord": coord[i],
             "contrib": 100 * masse[i] * coord[i] ** 2 / lam, "cos2": coord[i] ** 2 / d2[i],
             "inertie": float(masse[i] * d2[i])}
            for i, nom in enumerate(noms)
        ]

    sup: dict[str, Any] = {}
    if lignes_sup is not None and len(lignes_sup):
        LS = _df(lignes_sup, "lignes_sup")
        manquantes = [col for col in N.columns if col not in LS.columns]
        if manquantes:
            raise ValueError("Colonnes absentes des lignes supplémentaires : " + ", ".join(manquantes) + ".")
        B = _numerique(LS[list(N.columns)], "lignes_sup")
        tot = B.sum(axis=1)
        if (tot <= 0).any():
            raise ValueError("Une ligne supplémentaire a un total nul.")
        prof = B / tot[:, None]
        coord = prof @ V                      # transition : barycentre des colonnes / sqrt(λ)
        d2 = ((prof - c) ** 2 / c).sum(axis=1)
        sup["lignes"] = [{"id": str(nom), "n": float(tot[i]), "coord": coord[i], "cos2": coord[i] ** 2 / d2[i]}
                         for i, nom in enumerate(LS.index)]
    if colonnes_sup is not None and colonnes_sup.shape[1]:
        CS = _df(colonnes_sup, "colonnes_sup")
        CS.index = [str(i) for i in CS.index]
        manquantes = [i for i in N.index if i not in CS.index]
        if manquantes:
            raise ValueError("Lignes absentes des colonnes supplémentaires : " + ", ".join(manquantes) + ".")
        B = _numerique(CS.loc[list(N.index)], "colonnes_sup")
        tot = B.sum(axis=0)
        if (tot <= 0).any():
            raise ValueError("Une colonne supplémentaire a un total nul.")
        prof = B / tot
        coord = prof.T @ U
        d2 = ((prof - r[:, None]) ** 2 / r[:, None]).sum(axis=0)
        sup["colonnes"] = [{"id": str(nom), "n": float(tot[j]), "coord": coord[j], "cos2": coord[j] ** 2 / d2[j]}
                           for j, nom in enumerate(CS.columns)]

    khi2 = float(total * lam_tous.sum())
    ddl = (I - 1) * (J - 1)
    attendus = np.outer(r, c) * total
    if (attendus < 5).mean() > 0.2:
        avert.append(
            f"{int((attendus < 5).sum())} case(s) sur {I * J} ont un effectif théorique inférieur à 5 : "
            "le test du χ² est approximatif et les modalités rares peuvent dominer les axes."
        )
    return _propre({
        "methode": "afc",
        "n": float(total),
        "axes": _table_axes(lam_tous),
        "inertie_totale": float(lam_tous.sum()),
        "khi2": {"valeur": khi2, "ddl": ddl, "p": float(stats.chi2.sf(khi2, ddl)),
                 "phi2": float(lam_tous.sum()),
                 "v_cramer": math.sqrt(lam_tous.sum() / min(I - 1, J - 1))},
        "lignes": points(N.index, F, r, d2_lig, A.sum(axis=1)),
        "colonnes": points(N.columns, G, c, d2_col, A.sum(axis=0)),
        "sup": sup,
        "parametres": {"n_axes": q, "n_lignes": I, "n_colonnes": J},
        "avertissements": avert,
    })


# --------------------------------------------------------------------------
# ACM (standard et spécifique)
# --------------------------------------------------------------------------

def _verifier_quali(X: pd.DataFrame, nom: str) -> None:
    manq = [c for c in X.columns if X[c].isna().any()]
    if manq:
        raise ValueError(
            "Valeurs manquantes dans des variables actives : " + ", ".join(manq) + ". "
            "En ACM, une variable active doit être renseignée pour tous les individus : restreignez la population, "
            "ou codez la non-réponse comme une modalité à part entière et déclarez-la passive (ACM spécifique)."
        )


def acm(X, *, passives=None, n_axes: int = 5, poids=None,
        ind_sup=None, quali_sup=None, quanti_sup=None) -> dict:
    """Analyse des correspondances multiples, standard ou spécifique.

    Paramètres
    ----------
    X : DataFrame individus × variables qualitatives actives (sans valeur manquante).
    passives : liste de couples (variable, modalité) à traiter en **modalités
        passives** → ACM spécifique (Le Roux & Rouanet ; ``GDAtools::speMCA`` ;
        ``FactoMineR::MCA(excl=)``). Les individus restent tous dans l'analyse, mais
        ces modalités (non-réponse, « autre », modalités rares…) ne participent
        plus à la définition des distances ni des axes.
    poids : poids des individus (facultatif).
    ind_sup : DataFrame d'individus supplémentaires (mêmes variables que X).
    quali_sup, quanti_sup : variables supplémentaires alignées sur X.

    Calcul (n individus, Q variables, K modalités, f_k fréquence de la modalité k) :
    SVD de H, H_ik = sqrt(p_i) · (z_ik − f_k) / sqrt(Q f_k), restreinte aux colonnes
    des modalités actives non passives.
      individus  y_i = U_i·s / sqrt(p_i)          (variance de l'axe = λ)
      modalités  y_k = V_k·s · sqrt(Q / f_k)      (= point moyen des individus / sqrt(λ))
      contrib_k = 100 · (f_k / Q) · y_k² / λ ;  cos²_k = y_k² / (1/f_k − 1).
    Inertie totale : K/Q − 1 en ACM standard.

    Taux modifiés. En ACM les taux d'inertie bruts sous-estiment systématiquement
    l'importance des premiers axes. Benzécri : pour les axes tels que λ > 1/Q,
    λ' = [Q/(Q−1)]² (λ − 1/Q)², taux = λ' / Σλ' (``pct_modifie``). Greenacre : même
    λ', rapporté à l'inertie hors-diagonale moyenne du tableau de Burt,
    Q/(Q−1) · (Σλ² − (K−Q)/Q²) (``pct_greenacre``, plus prudent, ne somme pas à 100).
    """
    avert: list[str] = []
    X = _df(X, "X")
    _verifier_quali(X, "X")
    n, Q = X.shape
    if n < 2:
        raise ValueError("Il faut au moins 2 individus actifs.")
    w, p = _poids(poids, n)

    # 1. Tableau disjonctif complet et fréquences des modalités.
    Z, cats, var_idx = _disjonctif(X)
    var_idx = np.array(var_idx)
    K = Z.shape[1]
    n_k = w @ Z                      # effectifs pondérés
    f = n_k / n                      # fréquences
    constantes = [col for j, col in enumerate(X.columns) if (var_idx == j).sum() < 2]
    if constantes:
        raise ValueError("Variable(s) active(s) à une seule modalité : " + ", ".join(constantes) + ".")

    # 2. Modalités passives (ACM spécifique).
    passive = np.zeros(K, dtype=bool)
    paires = [(str(v), str(m)) for v, m in (passives or [])]
    index_cat = {(v, str(m)): i for i, (v, m) in enumerate(cats)}
    inconnues = [f"{v} = {m}" for v, m in paires if (v, m) not in index_cat]
    if inconnues:
        raise ValueError("Modalité(s) passive(s) introuvable(s) dans les variables actives : " + " ; ".join(inconnues) + ".")
    for v, m in paires:
        passive[index_cat[(v, m)]] = True
    specifique = bool(passive.any())
    for j, col in enumerate(X.columns):
        if (~passive[var_idx == j]).sum() == 0:
            raise ValueError(f"Toutes les modalités de « {col} » sont passives : retirez plutôt la variable des actives.")
    act = ~passive

    # 3. SVD pondérée du tableau T_ik = (z_ik − f_k) / f_k, poids p_i et f_k / Q.
    T = (Z[:, act] - f[act]) / f[act]
    U, s, V = _svd_ponderee(T, p, f[act] / Q)
    lam_tous = s**2
    q = _n_axes(n_axes, len(s), avert)
    U, V, lam = U[:, :q], V[:, :q], lam_tous[:q]

    # 4. Individus.
    F = U * np.sqrt(lam)
    d2_ind = (T**2 * (f[act] / Q)).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        cos2_ind = np.where(d2_ind[:, None] > 0, F**2 / d2_ind[:, None], np.nan)
    contrib_ind = 100 * p[:, None] * F**2 / lam

    # 5. Modalités actives (coordonnées principales), puis passives (placées en supplémentaires).
    G = np.full((K, q), np.nan)
    G[act] = V * np.sqrt(lam)
    contrib = np.zeros((K, q))
    contrib[act] = 100 * (f[act] / Q)[:, None] * G[act] ** 2 / lam
    for k in np.where(passive)[0]:
        sel = Z[:, k] > 0
        G[k] = (w[sel] @ F[sel]) / n_k[k] / np.sqrt(lam)
    with np.errstate(divide="ignore", invalid="ignore"):
        cos2 = G**2 / (1 / f - 1)[:, None]
        vtest = G * np.sqrt(n_k * (n - 1) / (n - n_k))[:, None]
    modalites = [
        {"id": _id_modalite(v, m), "variable": v, "modalite": str(m), "n": float(n_k[k]),
         "pct": float(100 * f[k]), "coord": G[k],
         "contrib": None if passive[k] else contrib[k], "cos2": cos2[k], "vtest": vtest[k],
         "passive": bool(passive[k])}
        for k, (v, m) in enumerate(cats)
    ]

    # 6. Variables : contribution cumulée de leurs modalités, et rapport de corrélation eta².
    variables = []
    for j, col in enumerate(X.columns):
        cols = var_idx == j
        variables.append({
            "id": col, "type": "quali",
            "contrib": contrib[cols].sum(axis=0),
            "eta2": _eta2(F, X[col].to_numpy(dtype=object), p),
            "n_modalites": int(cols.sum()), "n_passives": int(passive[cols].sum()),
        })

    # 7. Taux d'inertie modifiés.
    axes = _table_axes(lam_tous)
    if Q > 1:
        seuil = 1 / Q
        retenus = lam_tous > seuil + 1e-12
        pseudo = np.where(retenus, (Q / (Q - 1) * (lam_tous - seuil)) ** 2, 0.0)
        if pseudo.sum() > 0:
            benz = 100 * pseudo / pseudo.sum()
            cumul = np.cumsum(benz)
            green = None
            if not specifique:
                denom = Q / (Q - 1) * ((lam_tous**2).sum() - (K - Q) / Q**2)
                green = 100 * pseudo / denom if denom > 0 else None
            for i, a in enumerate(axes):
                a["pct_modifie"] = float(benz[i]) if retenus[i] else None
                a["pct_modifie_cumule"] = float(cumul[i]) if retenus[i] else None
                a["pct_greenacre"] = float(green[i]) if (green is not None and retenus[i]) else None

    # 8. Avertissements de méthode.
    rares = [f"{v} = {m} ({100 * f[k]:.1f} %)" for k, (v, m) in enumerate(cats)
             if act[k] and f[k] < _SEUIL_MODALITE_RARE]
    if rares:
        avert.append(
            f"{len(rares)} modalité(s) active(s) concernent moins de {int(100 * _SEUIL_MODALITE_RARE)} % des individus : "
            + " ; ".join(rares[:12]) + (" ; …" if len(rares) > 12 else "") + ". "
            "Une modalité rare est très éloignée du centre et peut créer un axe à elle seule : "
            "regroupez-la avec une modalité voisine ou déclarez-la passive."
        )
    nb_mod = np.array([(var_idx == j).sum() for j in range(Q)])
    if nb_mod.max() >= 2 * max(nb_mod.min(), 1) and nb_mod.max() - nb_mod.min() >= 3:
        avert.append(
            f"Les variables actives ont des nombres de modalités très inégaux ({nb_mod.min()} à {nb_mod.max()}) : "
            "la contribution d'une variable à l'inertie croît avec son nombre de modalités."
        )

    sup: dict[str, Any] = {}
    # 9. Individus supplémentaires : formule de transition exacte (voir docstring du module, divergence 1).
    if ind_sup is not None and len(ind_sup):
        IS = _df(ind_sup, "ind_sup")
        manquantes = [c for c in X.columns if c not in IS.columns]
        if manquantes:
            raise ValueError("Variables absentes des individus supplémentaires : " + ", ".join(manquantes) + ".")
        Zs = np.zeros((len(IS), K))
        n_hors = 0
        for j, col in enumerate(X.columns):
            vals = IS[col].to_numpy(dtype=object)
            connues = {str(m): k for k, (v, m) in enumerate(cats) if v == col}
            for i, val in enumerate(vals):
                k = None if pd.isna(val) else connues.get(str(val))
                if k is None:
                    n_hors += 1
                else:
                    Zs[i, k] = 1.0
        if n_hors:
            avert.append(
                f"Individus supplémentaires : {n_hors} réponse(s) manquante(s) ou de modalité inconnue des actifs ; "
                "elles sont traitées comme une modalité passive (aucune contribution à la position)."
            )
        Ts = (Zs[:, act] - f[act]) / f[act]
        Fs = (Ts * (f[act] / Q)) @ V
        d2s = (Ts**2 * (f[act] / Q)).sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            sup["individus"] = {"ids": _ids(IS.index), "coord": Fs,
                                "cos2": np.where(d2s[:, None] > 0, Fs**2 / d2s[:, None], np.nan)}
    # 10. Variables supplémentaires.
    sup_vars: list[dict] = []
    if quali_sup is not None:
        LS = _aligner(_df(quali_sup, "quali_sup"), X.index, "quali_sup")
        mods, vs = _quali_sup_barycentres(LS, F, lam, w, mode="acm", avert=avert)
        sup["modalites"] = mods
        sup_vars += vs
    if quanti_sup is not None:
        QS = _aligner(_df(quanti_sup, "quanti_sup"), X.index, "quanti_sup")
        sup_vars += _quanti_sup(QS, F, p, True, avert)
    if sup_vars:
        sup["variables"] = sup_vars

    return _propre({
        "methode": "acm_specifique" if specifique else "acm",
        "n": n,
        "axes": axes,
        "inertie_totale": float(lam_tous.sum()),
        "individus": {"ids": _ids(X.index), "coord": F, "contrib": contrib_ind, "cos2": cos2_ind},
        "modalites": modalites,
        "variables": variables,
        "sup": sup,
        "parametres": {
            "n_axes": q, "pondere": poids is not None, "variables_actives": list(X.columns),
            "n_variables": Q, "n_modalites": K, "n_modalites_actives": int(act.sum()),
            "passives": [[v, m] for v, m in paires],
            "seuil_valeur_propre": 1 / Q,
            "n_ind_sup": 0 if ind_sup is None else len(ind_sup),
        },
        "avertissements": avert,
    })


# --------------------------------------------------------------------------
# AFDM (analyse factorielle de données mixtes)
# --------------------------------------------------------------------------

def _est_quanti(s: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(s.dtype) and not pd.api.types.is_bool_dtype(s.dtype)


def afdm(X, *, n_axes: int = 5, poids=None, ind_sup=None, quali_sup=None, quanti_sup=None) -> dict:
    """Analyse factorielle de données mixtes (``FactoMineR::FAMD`` ; Pagès 2004).

    X : DataFrame mêlant variables quantitatives (dtype numérique) et qualitatives
    (catégorielles ou texte), sans valeur manquante.

    Calcul : chaque variable quantitative est centrée-réduite (comme en ACP normée) ;
    chaque modalité k devient une colonne (z_ik − f_k) / sqrt(f_k) (comme en ACM) ;
    on réalise l'ACP non réduite du tableau juxtaposé. Chaque variable, quantitative
    ou qualitative, est ainsi « équilibrée » : son inertie projetée sur un axe vaut
    r² (quantitative) ou eta² (qualitative), au plus 1 dans les deux cas — c'est la
    valeur ``liaison`` renvoyée pour chaque variable.
    """
    avert: list[str] = []
    X = _df(X, "X")
    n = len(X)
    if n < 2:
        raise ValueError("Il faut au moins 2 individus actifs.")
    quanti = [c for c in X.columns if _est_quanti(X[c])]
    quali = [c for c in X.columns if c not in quanti]
    if not quanti or not quali:
        raise ValueError(
            "L'AFDM demande au moins une variable quantitative et une variable qualitative actives "
            "(sinon, utilisez l'ACP ou l'ACM)."
        )
    w, p = _poids(poids, n)

    # 1. Bloc quantitatif : centrage-réduction.
    A = _numerique(X[quanti], "X")
    moy = p @ A
    ecart = np.sqrt(p @ (A - moy) ** 2)
    constantes = [c for c, e in zip(quanti, ecart) if e < 1e-12]
    if constantes:
        raise ValueError("Variable(s) quantitative(s) constante(s) : " + ", ".join(constantes) + ".")
    Zq = (A - moy) / ecart

    # 2. Bloc qualitatif : indicatrices centrées, divisées par sqrt(f_k).
    _verifier_quali(X[quali], "X")
    D, cats, var_idx = _disjonctif(X[quali])
    var_idx = np.array(var_idx)
    constantes = [c for j, c in enumerate(quali) if (var_idx == j).sum() < 2]
    if constantes:
        raise ValueError("Variable(s) qualitative(s) à une seule modalité : " + ", ".join(constantes) + ".")
    n_k = w @ D
    f = n_k / n
    Zl = (D - f) / np.sqrt(f)

    # 3. ACP non réduite du tableau juxtaposé.
    Zt = np.hstack([Zq, Zl])
    nq = len(quanti)
    U, s, V = _svd_ponderee(Zt, p, np.ones(Zt.shape[1]))
    lam_tous = s**2
    q = _n_axes(n_axes, len(s), avert)
    U, V, lam = U[:, :q], V[:, :q], lam_tous[:q]

    F = U * np.sqrt(lam)
    d2_ind = (Zt**2).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        cos2_ind = np.where(d2_ind[:, None] > 0, F**2 / d2_ind[:, None], np.nan)
    contrib_ind = 100 * p[:, None] * F**2 / lam
    Gv = V * np.sqrt(lam)                      # coordonnées des colonnes du tableau juxtaposé
    contrib_col = 100 * V**2

    variables = []
    for j, nom in enumerate(quanti):
        cor = Gv[j]                            # variable réduite : coordonnée = corrélation
        variables.append({"id": nom, "type": "quanti", "coord": cor, "cor": cor, "contrib": contrib_col[j],
                          "cos2": cor**2, "liaison": cor**2, "moyenne": moy[j], "ecart_type": ecart[j]})
    # Modalités : point moyen des individus qui les portent.
    modalites = []
    for k, (v, m) in enumerate(cats):
        sel = D[:, k] > 0
        bary = (w[sel] @ F[sel]) / n_k[k]
        g = (w[sel] @ Zt[sel]) / n_k[k]
        d2 = float((g**2).sum())
        with np.errstate(divide="ignore", invalid="ignore"):
            vt = bary / np.sqrt(lam) * (math.sqrt(n_k[k] * (n - 1) / (n - n_k[k])) if n - n_k[k] > 1e-9 else float("nan"))
        modalites.append({
            "id": _id_modalite(v, m), "variable": v, "modalite": str(m), "n": float(n_k[k]),
            "pct": float(100 * f[k]), "coord": bary, "contrib": contrib_col[nq + k],
            "cos2": bary**2 / d2 if d2 > 0 else np.full(q, np.nan), "vtest": vt, "passive": False,
        })
    for j, nom in enumerate(quali):
        cols = np.where(var_idx == j)[0]
        eta2 = _eta2(F, X[nom].to_numpy(dtype=object), p)
        variables.append({
            "id": nom, "type": "quali", "coord": None, "contrib": contrib_col[nq + cols].sum(axis=0),
            "eta2": eta2, "cos2": eta2**2 / (len(cols) - 1), "liaison": eta2, "n_modalites": int(len(cols)),
        })

    rares = [f"{v} = {m} ({100 * f[k]:.1f} %)" for k, (v, m) in enumerate(cats) if f[k] < _SEUIL_MODALITE_RARE]
    if rares:
        avert.append(
            f"{len(rares)} modalité(s) concernent moins de {int(100 * _SEUIL_MODALITE_RARE)} % des individus : "
            + " ; ".join(rares[:12]) + (" ; …" if len(rares) > 12 else "")
            + ". Les modalités rares pèsent fortement sur les axes : envisagez un regroupement."
        )

    sup: dict[str, Any] = {}
    if ind_sup is not None and len(ind_sup):
        IS = _df(ind_sup, "ind_sup")
        manquantes = [c for c in X.columns if c not in IS.columns]
        if manquantes:
            raise ValueError("Variables absentes des individus supplémentaires : " + ", ".join(manquantes) + ".")
        Zqs = (_numerique(IS[quanti], "ind_sup") - moy) / ecart
        Ds = np.zeros((len(IS), len(cats)))
        for k, (v, m) in enumerate(cats):
            Ds[:, k] = (IS[v].to_numpy(dtype=object) == m).astype(float)
        hors = int(len(IS) * len(quali) - Ds.sum())
        if hors:
            avert.append(
                f"Individus supplémentaires : {hors} réponse(s) manquante(s) ou de modalité inconnue des actifs "
                "(aucune indicatrice activée pour la variable concernée)."
            )
        Zs = np.hstack([Zqs, (Ds - f) / np.sqrt(f)])
        Fs = Zs @ V
        d2s = (Zs**2).sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            sup["individus"] = {"ids": _ids(IS.index), "coord": Fs,
                                "cos2": np.where(d2s[:, None] > 0, Fs**2 / d2s[:, None], np.nan)}
    sup_vars: list[dict] = []
    if quanti_sup is not None:
        QS = _aligner(_df(quanti_sup, "quanti_sup"), X.index, "quanti_sup")
        qs = _quanti_sup(QS, F, p, True, avert)
        for v in qs:
            v["liaison"] = v["cos2"]
        sup_vars += qs
    if quali_sup is not None:
        LS = _aligner(_df(quali_sup, "quali_sup"), X.index, "quali_sup")
        mods, vs = _quali_sup_barycentres(LS, F, lam, w, mode="acp", Z_espace=Zt,
                                          poids_col=np.ones(Zt.shape[1]), avert=avert)
        for v in vs:
            v["liaison"] = v["eta2"]
        sup["modalites"] = mods
        sup_vars += vs
    if sup_vars:
        sup["variables"] = sup_vars

    return _propre({
        "methode": "afdm",
        "n": n,
        "axes": _table_axes(lam_tous),
        "inertie_totale": float(lam_tous.sum()),
        "individus": {"ids": _ids(X.index), "coord": F, "contrib": contrib_ind, "cos2": cos2_ind},
        "modalites": modalites,
        "variables": variables,
        "sup": sup,
        "parametres": {"n_axes": q, "pondere": poids is not None, "variables_quanti": quanti,
                       "variables_quali": quali, "n_modalites": len(cats),
                       "n_ind_sup": 0 if ind_sup is None else len(ind_sup)},
        "avertissements": avert,
    })
