"""Classification ascendante hiérarchique (Ward) sur coordonnées factorielles, et description des classes.

Démarche (celle de ``FactoMineR::HCPC`` ; Lebart, Morineau & Piron ; Husson, Lê & Pagès)
---------------------------------------------------------------------------------
1. On part des coordonnées des individus sur les premiers axes d'une analyse
   factorielle (ne retenir que les premiers axes « débruite » la classification).
2. CAH avec le critère de Ward : à chaque étape on fusionne les deux classes dont
   la réunion fait le moins baisser l'inertie inter-classes. La perte d'inertie
   inter causée par la fusion de A et B vaut

       Δ(A, B) = p_A p_B / (p_A + p_B) · ||g_A − g_B||²

   (p = poids relatif de la classe, g = son centre de gravité). La somme de toutes
   les pertes est l'inertie totale du nuage : chaque palier de l'arbre se lit donc
   comme une part d'inertie.
3. Choix du nombre de classes : l'utilisateur décide. Une suggestion est fournie,
   avec la règle de HCPC : parmi k = 3 … k_max, retenir le k qui minimise
   W(k) / W(k − 1), W(k) étant l'inertie intra-classes de la partition en k classes
   (on s'arrête là où ajouter une classe a le plus réduit, relativement, l'inertie
   intra). Ce n'est qu'un repère : le diagramme des gains et l'interprétabilité
   des classes priment.
4. Consolidation facultative par k-means (centres mobiles) initialisé sur les
   centres des classes de la CAH : les individus sont réaffectés au centre le
   plus proche jusqu'à stabilité (itérations de Lloyd), puis on vérifie qu'aucun
   transfert individuel n'améliore encore le critère (étape de type
   Hartigan-Wong). La partition consolidée a une inertie inter au moins égale,
   mais ne correspond plus exactement à une coupure de l'arbre.

Les classes sont numérotées de 1 à k par ordre croissant de leur centre sur le
premier axe (convention de HCPC), ce qui rend la numérotation reproductible.

Moteur : ``scipy.cluster.hierarchy.linkage(method="ward")`` quand les individus
ont tous le même poids ; avec des poids inégaux (que SciPy ne gère pas), la même
récurrence de Lance-Williams est appliquée par ``_ward_pondere`` (validée contre
SciPy à poids égaux et contre HCPC à poids inégaux).

Différence connue avec HCPC : sa consolidation appelle ``kmeans`` (algorithme de
Hartigan-Wong, 10 itérations, **sans** les poids des individus). La nôtre tient
compte des poids et itère jusqu'à convergence ; à poids égaux les partitions
obtenues sont en pratique identiques (testé), sans garantie théorique.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from scipy.cluster import hierarchy
from scipy.special import ndtri_exp

from .geometrique import _df, _modalites, _numerique, _poids, _propre

__all__ = ["cah", "decrire_classes"]


# --------------------------------------------------------------------------
# Arbre de Ward
# --------------------------------------------------------------------------

def _ward_pondere(X: np.ndarray, p: np.ndarray) -> np.ndarray:
    """CAH de Ward avec poids. Renvoie une matrice de fusions au format SciPy
    (n−1 lignes : identifiants des deux classes fusionnées, perte d'inertie inter Δ,
    nombre d'individus de la nouvelle classe).

    Récurrence de Lance-Williams sur Δ : pour la classe k et la fusion (i, j),
        Δ(k, i∪j) = [(p_i + p_k) Δ(k, i) + (p_j + p_k) Δ(k, j) − p_k Δ(i, j)] / (p_i + p_j + p_k).
    On tient à jour le plus proche voisin de chaque classe pour ne pas reparcourir
    toute la matrice à chaque étape.
    """
    n = X.shape[0]
    carres = (X**2).sum(axis=1)
    D2 = np.maximum(carres[:, None] + carres[None, :] - 2 * X @ X.T, 0.0)
    D = D2 * (p[:, None] * p[None, :]) / (p[:, None] + p[None, :])
    np.fill_diagonal(D, np.inf)

    actif = np.ones(n, dtype=bool)
    poids = p.astype(float).copy()
    taille = np.ones(n, dtype=int)
    ident = np.arange(n)                     # identifiant SciPy de la classe portée par chaque ligne
    voisin = D.argmin(axis=1)
    dmin = D[np.arange(n), voisin]
    fusions = np.zeros((n - 1, 4))

    for etape in range(n - 1):
        a = int(np.argmin(dmin))
        b = int(voisin[a])
        delta = float(dmin[a])
        if a > b:
            a, b = b, a
        # Mise à jour de Lance-Williams : la classe fusionnée occupe la ligne a, la ligne b disparaît.
        autres = actif.copy()
        autres[[a, b]] = False
        nouveau = np.full(n, np.inf)
        nouveau[autres] = (
            (poids[a] + poids[autres]) * D[a, autres] + (poids[b] + poids[autres]) * D[b, autres]
            - poids[autres] * delta
        ) / (poids[a] + poids[b] + poids[autres])
        fusions[etape] = (min(ident[a], ident[b]), max(ident[a], ident[b]), delta, taille[a] + taille[b])
        D[a, :] = nouveau
        D[:, a] = nouveau
        D[b, :] = np.inf
        D[:, b] = np.inf
        actif[b] = False
        poids[a] += poids[b]
        taille[a] += taille[b]
        ident[a] = n + etape
        dmin[b] = np.inf
        if etape == n - 2:
            break
        # Plus proches voisins : la ligne a est recalculée ; celles qui pointaient vers a ou b aussi ;
        # les autres n'ont qu'à comparer leur minimum courant à la nouvelle distance.
        voisin[a] = int(np.argmin(nouveau))
        dmin[a] = nouveau[voisin[a]]
        a_refaire = np.where(autres & ((voisin == a) | (voisin == b)))[0]
        if len(a_refaire):
            voisin[a_refaire] = D[a_refaire].argmin(axis=1)
            dmin[a_refaire] = D[a_refaire, voisin[a_refaire]]
        mieux = autres & (nouveau < dmin)
        voisin[mieux] = a
        dmin[mieux] = nouveau[mieux]
    return fusions


def _arbre_ward(X: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Matrice de fusions (format SciPy) dont la 3ᵉ colonne est la perte d'inertie inter Δ."""
    n = X.shape[0]
    if np.allclose(p, 1 / n):
        Z = hierarchy.linkage(X, method="ward")
        # SciPy renvoie d = sqrt(2 n_A n_B / (n_A + n_B)) ||g_A − g_B|| ; avec p = 1/n, Δ = d² / (2n).
        Z[:, 2] = Z[:, 2] ** 2 / (2 * n)
        return Z
    return _ward_pondere(X, p)


# --------------------------------------------------------------------------
# Inerties et consolidation
# --------------------------------------------------------------------------

def _centres(X: np.ndarray, p: np.ndarray, labels: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Centres de gravité (k × d) et poids relatifs des classes, labels dans 0..k−1."""
    masses = np.bincount(labels, weights=p, minlength=k)
    sommes = np.zeros((k, X.shape[1]))
    np.add.at(sommes, labels, X * p[:, None])
    with np.errstate(divide="ignore", invalid="ignore"):
        return sommes / masses[:, None], masses


def _inertie_inter(X: np.ndarray, p: np.ndarray, labels: np.ndarray, k: int) -> float:
    g = p @ X
    centres, masses = _centres(X, p, labels, k)
    return float((masses * ((centres - g) ** 2).sum(axis=1)).sum())


def _consolider(X: np.ndarray, p: np.ndarray, labels: np.ndarray, k: int, iter_max: int = 100) -> tuple[np.ndarray, int]:
    """k-means pondéré partant de la partition fournie. Renvoie (labels, nombre d'itérations)."""
    labels = labels.copy()
    n = X.shape[0]
    iterations = 0
    for iterations in range(1, iter_max + 1):
        # (a) Itérations de Lloyd : réaffectation au centre le plus proche.
        centres, _ = _centres(X, p, labels, k)
        d2 = ((X[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
        nouveaux = d2.argmin(axis=1)
        # On n'accepte pas de vider une classe : l'individu concerné reste où il est.
        for c in range(k):
            if not (nouveaux == c).any():
                nouveaux[labels == c] = c
        change = bool((nouveaux != labels).any())
        labels = nouveaux
        if change:
            continue
        # (b) Transferts individuels (Hartigan-Wong) : déplacer i de A vers B si
        #     p_B/(p_B + p_i)·d²(i, g_B) < p_A/(p_A − p_i)·d²(i, g_A).
        transfert = False
        centres, masses = _centres(X, p, labels, k)
        for i in range(n):
            a = labels[i]
            if masses[a] - p[i] <= 1e-15 or (labels == a).sum() <= 1:
                continue
            d2i = ((centres - X[i]) ** 2).sum(axis=1)
            cout = masses / (masses + p[i]) * d2i
            cout[a] = np.inf
            b = int(np.argmin(cout))
            if cout[b] < masses[a] / (masses[a] - p[i]) * d2i[a] * (1 - 1e-12):
                centres[a] = (masses[a] * centres[a] - p[i] * X[i]) / (masses[a] - p[i])
                centres[b] = (masses[b] * centres[b] + p[i] * X[i]) / (masses[b] + p[i])
                masses[a] -= p[i]
                masses[b] += p[i]
                labels[i] = b
                transfert = True
        if not transfert:
            break
    return labels, iterations


def _numeroter(X: np.ndarray, p: np.ndarray, labels: np.ndarray, k: int) -> np.ndarray:
    """Renumérote 0..k−1 par ordre croissant du centre sur le premier axe."""
    centres, _ = _centres(X, p, labels, k)
    rang = np.empty(k, dtype=int)
    rang[np.argsort(centres[:, 0], kind="stable")] = np.arange(k)
    return rang[labels]


# --------------------------------------------------------------------------
# CAH
# --------------------------------------------------------------------------

def cah(coord, *, poids=None, k: int | None = None, k_max: int = 10,
        consolidation: bool = True, graine: int = 0) -> dict:
    """Classification ascendante hiérarchique de Ward sur des coordonnées factorielles.

    Paramètres
    ----------
    coord : DataFrame individus × axes retenus (coordonnées d'une ACP/ACM/AFDM).
    poids : poids des individus (facultatif ; normalisés à somme n).
    k : nombre de classes. None → on applique la suggestion (voir le module).
    k_max : plus grand nombre de classes examiné pour la suggestion et le diagramme des gains.
    consolidation : consolider la partition par k-means (voir le module).
    graine : sans effet sur le résultat (l'algorithme est entièrement déterministe :
        la consolidation part des centres de la CAH, sans tirage aléatoire) ;
        conservé dans les paramètres pour la traçabilité.

    Résultat : voir les clés du dictionnaire renvoyé ; ``partition`` est alignée sur
    ``ids`` (l'index de ``coord``) ; les inerties sont celles du nuage des individus
    dans l'espace des axes fournis (somme des variances des axes).
    """
    avert: list[str] = []
    C = _df(coord, "coord")
    X = _numerique(C, "coord")
    n, d = X.shape
    if n < 3:
        raise ValueError("Il faut au moins 3 individus pour une classification.")
    w, p = _poids(poids, n)

    Z = _arbre_ward(X, p)
    gains_desc = Z[::-1, 2]                    # gains_desc[q−1] = gain d'inertie inter en passant de q à q+1 classes
    inertie_totale = float(gains_desc.sum())
    if inertie_totale <= 0:
        raise ValueError("Tous les individus ont les mêmes coordonnées : rien à classer.")
    # intra[q−1] = inertie intra-classes de la partition en q classes.
    intra = np.concatenate([np.cumsum(gains_desc[::-1])[::-1], [0.0]])

    # Suggestion du nombre de classes (règle de HCPC).
    k_haut = int(max(2, min(k_max, round(n / 2), n - 1)))
    rapports = []
    if k_haut >= 3:
        for q in range(3, k_haut + 1):
            rapports.append({"k": q, "rapport": float(intra[q - 1] / intra[q - 2]) if intra[q - 2] > 0 else None})
        valides = [r for r in rapports if r["rapport"] is not None]
        k_suggere = min(valides, key=lambda r: r["rapport"])["k"] if valides else 2
    else:
        k_suggere = 2
    if k is None:
        k_eff = k_suggere
    else:
        k_eff = int(k)
        if not 2 <= k_eff <= n - 1:
            raise ValueError(f"Le nombre de classes doit être compris entre 2 et {n - 1}.")

    # Coupure de l'arbre.
    labels_cah = hierarchy.fcluster(Z, t=k_eff, criterion="maxclust") - 1
    k_obtenu = int(labels_cah.max()) + 1
    if k_obtenu != k_eff:
        avert.append(
            f"Des fusions de même hauteur empêchent de couper l'arbre en exactement {k_eff} classes : "
            f"{k_obtenu} classes obtenues."
        )
        k_eff = k_obtenu
    labels_cah = _numeroter(X, p, labels_cah, k_eff)
    inter_avant = _inertie_inter(X, p, labels_cah, k_eff)

    labels = labels_cah
    info_consol: dict[str, Any] = {"effectuee": False}
    if consolidation:
        labels, iterations = _consolider(X, p, labels_cah, k_eff)
        labels = _numeroter(X, p, labels, k_eff)
        inter_apres = _inertie_inter(X, p, labels, k_eff)
        # Individus dont la classe a changé : on apparie les classes avant/après par recouvrement maximal.
        croise = pd.crosstab(labels_cah, labels).to_numpy()
        deplaces = int(n - croise.max(axis=1).sum())
        info_consol = {"effectuee": True, "iterations": int(iterations), "deplaces": deplaces,
                       "inertie_inter_avant": inter_avant, "inertie_inter_apres": inter_apres}
    inter = _inertie_inter(X, p, labels, k_eff)

    # Description géométrique des classes.
    centres, masses = _centres(X, p, labels, k_eff)
    ids = [str(i) for i in C.index]
    classes = []
    for c in range(k_eff):
        membres = np.where(labels == c)[0]
        d2 = ((X[membres] - centres[c]) ** 2).sum(axis=1)
        ordre = np.argsort(d2, kind="stable")[:5]
        classes.append({
            "classe": c + 1, "n": int(len(membres)), "poids": float(w[membres].sum()),
            "pct": float(100 * masses[c]), "centre": centres[c],
            "inertie_intra": float(p[membres] @ d2),
            "parangons": [{"id": ids[membres[i]], "distance": float(math.sqrt(d2[i]))} for i in ordre],
        })

    # Diagramme des gains d'inertie (pour choisir k).
    n_gains = int(min(n - 1, max(3 * k_max, 30)))
    gains = [
        {"k": q + 1, "gain": float(gains_desc[q - 1]), "pct_gain": float(100 * gains_desc[q - 1] / inertie_totale),
         "inertie_intra": float(intra[q]), "pct_inter": float(100 * (1 - intra[q] / inertie_totale))}
        for q in range(1, n_gains + 1)
    ]

    # Dendrogramme tronqué aux derniers nœuds (hauteurs = gains d'inertie).
    m = int(min(n, max(3 * k_max, 30, k_eff)))
    dendro = hierarchy.dendrogram(Z, p=m, truncate_mode="lastp", no_plot=True)
    noeuds = hierarchy.to_tree(Z, rd=True)[1]
    feuilles = []
    for noeud in dendro["leaves"]:
        if noeud < n:
            membres = [noeud]
        else:
            membres = noeuds[noeud].pre_order(lambda x: x.id)
        feuilles.append({"n": len(membres), "classe_cah": int(labels_cah[membres[0]]) + 1,
                         "id": ids[membres[0]] if len(membres) == 1 else None})
    # Hauteur de coupe : à mi-chemin entre le dernier palier conservé et le premier coupé.
    haut = float(gains_desc[k_eff - 2])
    bas = float(gains_desc[k_eff - 1]) if k_eff - 1 < len(gains_desc) else 0.0
    dendrogramme = {
        # Segments en « U » : pour chaque nœud, 4 abscisses (positions 5, 15, 25… des feuilles) et 4 hauteurs.
        "x": dendro["icoord"], "y": dendro["dcoord"], "feuilles": feuilles,
        "hauteur_coupe": (haut + bas) / 2, "tronque": m < n, "n_feuilles": m,
    }

    if min(c["n"] for c in classes) < max(5, 0.02 * n):
        petites = [f"classe {c['classe']} (n = {c['n']})" for c in classes if c["n"] < max(5, 0.02 * n)]
        avert.append(
            "Classe(s) de très petit effectif : " + ", ".join(petites) + ". Une telle classe isole souvent "
            "quelques individus atypiques ; vérifiez-la avant de l'interpréter."
        )

    return _propre({
        "methode": "cah_ward",
        "n": n,
        "k": k_eff,
        "k_suggere": k_suggere,
        "suggestion": {
            "k": k_suggere, "rapports": rapports,
            "critere": (
                "Règle de HCPC : parmi k = 3 à k_max, le k qui minimise W(k)/W(k−1), W étant l'inertie "
                "intra-classes. Simple repère : confrontez-le au diagramme des gains et au sens des classes."
            ),
        },
        "ids": ids,
        "partition": (labels + 1).tolist(),
        "partition_cah": (labels_cah + 1).tolist(),
        "classes": classes,
        "inertie_totale": inertie_totale,
        "inertie_inter": inter,
        "inertie_intra": inertie_totale - inter,
        "pct_inter": 100 * inter / inertie_totale,
        "gains": gains,
        "consolidation": info_consol,
        "dendrogramme": dendrogramme,
        "parametres": {"k_demande": k, "k_max": k_max, "consolidation": bool(consolidation), "graine": graine,
                       "pondere": poids is not None, "axes": list(C.columns), "n_axes": d},
        "avertissements": avert,
    })


# --------------------------------------------------------------------------
# Description des classes (catdes)
# --------------------------------------------------------------------------

def _p_hypergeometrique(x: int, n_classe: int, n_total: int, n_modalite: int) -> tuple[float, float]:
    """Test de sur/sous-représentation d'une modalité dans une classe.

    Sous l'hypothèse d'un tirage au hasard, sans remise, des n_classe individus de la
    classe parmi les n_total, le nombre X de porteurs de la modalité suit une loi
    hypergéométrique. p bilatérale « mid-p doublée » de FactoMineR::catdes :
        p = min( 2·P(X < x) + P(X = x),  2·P(X > x) + P(X = x) ).
    Renvoie (p, |v-test|) où le v-test est le quantile normal correspondant, |v| = −Φ⁻¹(p/2).
    """
    loi = stats.hypergeom(n_total, n_classe, n_modalite)
    pt = loi.pmf(x)
    p = min(2 * loi.cdf(x - 1) + pt, 2 * loi.sf(x) + pt)
    p = min(max(p, 0.0), 1.0)
    if p > 1e-290:
        v = -stats.norm.ppf(p / 2)
    else:
        # Probabilités trop petites pour les flottants : on passe par les logarithmes.
        with np.errstate(divide="ignore"):
            lp = min(
                np.logaddexp(math.log(2) + loi.logcdf(x - 1), loi.logpmf(x)),
                np.logaddexp(math.log(2) + loi.logsf(x), loi.logpmf(x)),
            )
        v = -float(ndtri_exp(lp - math.log(2)))
    return float(p), float(max(v, 0.0))


def decrire_classes(partition, quali=None, quanti=None, *, poids=None) -> dict:
    """Décrit les classes d'une partition par des variables (équivalent ``FactoMineR::catdes``).

    partition : labels de classe (liste ou Series), alignés sur ``quali`` / ``quanti``.
    quali : DataFrame de variables qualitatives ; une valeur manquante est traitée
        comme une modalité « (manquant) » (comme catdes), ce qui permet de voir si la
        non-réponse caractérise une classe.
    quanti : DataFrame de variables quantitatives (valeurs manquantes ignorées variable par variable).
    poids : poids des individus (facultatif). Comme catdes, les effectifs pondérés
        sont arrondis à l'entier pour le test hypergéométrique.

    Pour chaque classe et chaque modalité :
      cla_mod = % des porteurs de la modalité qui sont dans la classe ;
      mod_cla = % des membres de la classe qui portent la modalité ;
      global  = % de la modalité dans l'ensemble ;
      p, vtest : test hypergéométrique (v-test > 0 : modalité sur-représentée).
    Pour chaque variable quantitative : moyenne dans la classe contre moyenne générale,
      vtest = (m_classe − m) / sqrt( s² / n_classe · (n − n_classe)/(n − 1) ).
    Liaison globale variable × partition : χ² (sans correction) et V de Cramér ; eta² et test F.

    Attention : chaque ligne est un test. Sur des dizaines de modalités, des
    |v-test| > 2 apparaissent par hasard ; les valeurs-tests servent à ordonner les
    modalités caractéristiques, pas à « prouver » chaque écart.
    """
    avert: list[str] = []
    part = pd.Series(partition).reset_index(drop=True)
    if part.isna().any():
        raise ValueError("La partition contient des valeurs manquantes.")
    n = len(part)
    etiquettes = _modalites(part)
    if len(etiquettes) < 2:
        raise ValueError("La partition ne compte qu'une classe.")
    w_brut = np.ones(n) if poids is None else np.asarray(poids, dtype=float).reshape(-1)
    if len(w_brut) != n:
        raise ValueError("Les poids n'ont pas la même longueur que la partition.")
    part_np = part.to_numpy(dtype=object)
    appart = {c: part_np == c for c in etiquettes}
    par_classe = {c: {"classe": _propre(c), "n": int(appart[c].sum()), "poids": float(w_brut[appart[c]].sum()),
                      "modalites": [], "quanti": []} for c in etiquettes}
    n_tests = 0

    variables_quali = []
    if quali is not None and quali.shape[1]:
        L = _df(quali, "quali").reset_index(drop=True)
        if len(L) != n:
            raise ValueError("« quali » n'a pas le même nombre de lignes que la partition.")
        for nom in L.columns:
            s = L[nom]
            mods = [str(m) for m in _modalites(s)]
            valeurs = np.array([None if pd.isna(v) else str(v) for v in s.to_numpy(dtype=object)], dtype=object)
            if s.isna().any():
                valeurs = np.array(["(manquant)" if v is None else v for v in valeurs], dtype=object)
                mods = mods + ["(manquant)"]
            # Tableau croisé classes × modalités (pondéré).
            T = np.array([[w_brut[appart[c] & (valeurs == m)].sum() for m in mods] for c in etiquettes])
            lig, col, tot = T.sum(axis=1), T.sum(axis=0), T.sum()
            attendu = np.outer(lig, col) / tot
            with np.errstate(divide="ignore", invalid="ignore"):
                khi2 = float(np.nansum(np.where(attendu > 0, (T - attendu) ** 2 / attendu, 0.0)))
            ddl = (len(etiquettes) - 1) * (len(mods) - 1)
            variables_quali.append({
                "variable": nom, "khi2": khi2, "ddl": ddl,
                "p": float(stats.chi2.sf(khi2, ddl)) if ddl > 0 else None,
                "v_cramer": math.sqrt(khi2 / (tot * min(len(etiquettes) - 1, len(mods) - 1))) if ddl > 0 else None,
                "n": float(tot), "pct_attendus_inf_5": float(100 * (attendu < 5).mean()),
            })
            Tr, ligr, colr, totr = np.round(T), np.round(lig), np.round(col), int(round(tot))
            for i, c in enumerate(etiquettes):
                for j, m in enumerate(mods):
                    if col[j] <= 0 or lig[i] <= 0:
                        continue
                    mod_cla, glob = T[i, j] / lig[i], col[j] / tot
                    p_val, v_abs = _p_hypergeometrique(int(Tr[i, j]), int(ligr[i]), totr, int(colr[j]))
                    n_tests += 1
                    par_classe[c]["modalites"].append({
                        "variable": nom, "modalite": m, "n": float(T[i, j]),
                        "cla_mod": 100 * T[i, j] / col[j], "mod_cla": 100 * mod_cla, "global": 100 * glob,
                        "p": p_val, "vtest": v_abs if mod_cla > glob else -v_abs,
                    })
        variables_quali.sort(key=lambda v: (v["p"] is None, v["p"]))

    variables_quanti = []
    if quanti is not None and quanti.shape[1]:
        Qd = _df(quanti, "quanti").reset_index(drop=True)
        if len(Qd) != n:
            raise ValueError("« quanti » n'a pas le même nombre de lignes que la partition.")
        A = _numerique(Qd, "quanti", manquants_permis=True)
        for j, nom in enumerate(Qd.columns):
            x = A[:, j]
            ok = ~np.isnan(x)
            if ok.sum() < 3:
                avert.append(f"« {nom} » : moins de 3 valeurs renseignées, variable ignorée.")
                continue
            wk, xk = w_brut[ok], x[ok]
            N = wk.sum()
            moy = (wk @ xk) / N
            et = math.sqrt((wk @ (xk - moy) ** 2) / N)
            sc_inter, sc_intra, lignes = 0.0, 0.0, []
            for c in etiquettes:
                sel = appart[c][ok]
                n_c = wk[sel].sum()
                if n_c <= 0:
                    continue
                m_c = (wk[sel] @ xk[sel]) / n_c
                et_c = math.sqrt((wk[sel] @ (xk[sel] - m_c) ** 2) / n_c)
                sc_inter += n_c * (m_c - moy) ** 2
                sc_intra += wk[sel] @ (xk[sel] - m_c) ** 2
                lignes.append((c, n_c, m_c, et_c))
            k_obs = len(lignes)
            n_obs = int(ok.sum())
            eta2 = sc_inter / (sc_inter + sc_intra) if sc_inter + sc_intra > 0 else float("nan")
            if k_obs > 1 and n_obs > k_obs and sc_intra > 0:
                f_stat = (sc_inter / (k_obs - 1)) / (sc_intra / (n_obs - k_obs))
                p_f = float(stats.f.sf(f_stat, k_obs - 1, n_obs - k_obs))
            else:
                p_f = None
            variables_quanti.append({"variable": nom, "eta2": eta2, "p": p_f, "n": n_obs})
            for c, n_c, m_c, et_c in lignes:
                if et <= 0 or N - n_c <= 0:
                    continue
                v = (m_c - moy) / et * math.sqrt(n_c) / math.sqrt((N - n_c) / (N - 1))
                n_tests += 1
                par_classe[c]["quanti"].append({
                    "variable": nom, "vtest": v, "moyenne_classe": m_c, "moyenne_globale": moy,
                    "ecart_type_classe": et_c, "ecart_type_global": et, "p": float(2 * stats.norm.sf(abs(v))),
                })
        variables_quanti.sort(key=lambda v: (v["p"] is None, v["p"]))

    for c in etiquettes:
        par_classe[c]["modalites"].sort(key=lambda r: -r["vtest"])
        par_classe[c]["quanti"].sort(key=lambda r: -r["vtest"])
    if n_tests > 20:
        avert.append(
            f"{n_tests} tests ont été calculés : au seuil de 5 %, on en attend environ {round(0.05 * n_tests)} "
            "« significatifs » par le seul hasard. Lisez les valeurs-tests comme un classement des traits "
            "caractéristiques, non comme autant de preuves."
        )
    return _propre({
        "n": n,
        "classes": etiquettes,
        "variables_quali": variables_quali,
        "variables_quanti": variables_quanti,
        "par_classe": [par_classe[c] for c in etiquettes],
        "parametres": {"pondere": poids is not None, "n_tests": n_tests},
        "avertissements": avert,
    })
