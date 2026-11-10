"""Recette de préparation : liste ordonnée d'étapes déclaratives appliquées aux données brutes.

Chaque étape est un petit objet JSON (type + paramètres + note de justification). Aucune étape ne modifie
une variable existante : elle *ajoute* une ou plusieurs variables dérivées (ou marque des individus comme
exclus). On peut donc toujours modifier, désactiver ou supprimer une étape, et rejouer la recette entière
sur un nouvel export.

Types d'étapes :
  recoder    regrouper / renommer les modalités d'une variable (y compris coder une question ouverte)
  decouper   découper une variable numérique en classes
  score      compter des réponses ou additionner / moyenner des items (indicateur synthétique)
  regle      construire une variable par règles « si … alors … » (la première règle vraie l'emporte)
  fusionner  réunir plusieurs questions comparables en une seule variable (harmonisation documentée)
  convertir  transformer une variable catégorielle ou textuelle en nombre
  croiser    combiner les modalités de deux variables
  exclure    écarter des individus de toutes les analyses (ils restent dans les données brutes)
  partition  classes issues d'une classification enregistrée
"""
from __future__ import annotations

import re
from typing import Callable

import numpy as np
import pandas as pd

from .table import (ABANDON, EXCLU, FILTRE, NR, NSP, VALIDE, VIDE, Table, evaluer, variables_condition)

TYPES_ETAPES = {
    "recoder": "Recodage", "decouper": "Découpage en classes", "score": "Score / indicateur",
    "regle": "Variable par règles", "fusionner": "Fusion de questions comparables",
    "convertir": "Conversion en nombre", "croiser": "Croisement de deux variables",
    "exclure": "Exclusion d'individus", "partition": "Classes d'une classification",
}
RE_NOMBRE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


class ErreurEtape(ValueError):
    pass


def sources_etape(etape: dict) -> set[str]:
    """Variables lues par une étape."""
    p = etape.get("params", {})
    t = etape["type"]
    if t in ("recoder", "decouper", "convertir"):
        return {p["source"]}
    if t in ("score", "croiser"):
        return set(p.get("sources", []))
    if t == "fusionner":
        return {s["var"] for s in p.get("sources", [])}
    if t == "regle":
        return set().union(*[variables_condition(c.get("si")) for c in p.get("cas", [])]) if p.get("cas") else set()
    if t == "exclure":
        return variables_condition(p.get("si"))
    return set()


def sorties_etape(etape: dict) -> list[str]:
    cible = etape.get("params", {}).get("cible")
    return [cible["id"]] if cible else []


def _statut_combine(statuts: list[np.ndarray]) -> np.ndarray:
    """Statut d'une variable construite à partir de plusieurs sources, là où aucune valeur n'a pu être calculée :
    non concerné si toutes les sources le sont, non atteint si toutes sont non concernées ou non atteintes,
    non-réponse sinon."""
    pile = np.vstack(statuts)
    tous_filtre = (pile == FILTRE).all(axis=0)
    tous_hors = np.isin(pile, (FILTRE, ABANDON)).all(axis=0)
    un_vide = (pile == VIDE).any(axis=0) & ~np.isin(pile, (NR, EXCLU, NSP)).any(axis=0)
    return np.where(tous_filtre, FILTRE, np.where(tous_hors, ABANDON, np.where(un_vide, VIDE, NR))).astype(np.int8)


def _meta(etape: dict, type_: str, modalites: list[str] | None, sources: list[str], ordonnee: bool = False,
          nr: set[str] | None = None) -> dict:
    cible = etape["params"]["cible"]
    return {
        "id": cible["id"], "nom": cible.get("nom") or cible["id"], "libelle": cible.get("libelle") or cible["id"],
        "sous_libelle": None, "question": None, "type": type_, "role": "analyse", "ordonnee": ordonnee,
        "modalites": [{"valeur": m, **({"nr": True} if nr and m in nr else {})} for m in (modalites or [])],
        "derive": etape["id"], "sources": sources, "champ": None,
    }


def _ordre(params: dict, vus: list[str]) -> list[str]:
    ordre = [m for m in params.get("ordre", []) if m in vus]
    return ordre + [m for m in vus if m not in ordre]


# -- étapes ------------------------------------------------------------------

def _recoder(etape, table: Table, rapport):
    p = etape["params"]
    src = p["source"]
    table.exiger(src)
    meta_src = table.meta[src]
    corr = p.get("correspondance", {})
    s = table.valeurs[src].astype(object)
    if meta_src["type"] == "quanti":
        s = s.map(lambda v: None if pd.isna(v) else (str(int(v)) if float(v).is_integer() else str(v)))
    st = table.statuts[src].copy()
    present = np.isin(st, (VALIDE, NSP))
    connues = [m["valeur"] for m in meta_src.get("modalites", [])] or sorted(set(s[present].dropna()))
    autres = p.get("autres", "conserver")
    non_prevues = [m for m in connues if m not in corr]
    if non_prevues and autres == "conserver" and corr:
        rapport["avertissements"].append(
            f"{len(non_prevues)} modalité(s) de la source ne figurent pas dans le recodage et sont conservées telles "
            f"quelles : {', '.join('« ' + m[:40] + ' »' for m in non_prevues[:5])}{'…' if len(non_prevues) > 5 else ''}")

    def cible(v):
        if v in corr:
            return corr[v]
        return v if autres == "conserver" else None

    nouvelles = s.where(present).map(lambda v: cible(v) if isinstance(v, str) else None)
    mis_manquant = present & nouvelles.isna().to_numpy()
    nr_src = {m["valeur"] for m in meta_src.get("modalites", []) if m.get("nr")}
    nr_cible = {cible(m) for m in nr_src if m not in corr and cible(m)}
    # une modalité de non-réponse explicitement recodée devient une réponse valide
    st = np.where(present & ~mis_manquant, np.where(nouvelles.isin(nr_cible), NSP, VALIDE), st)
    st = np.where(mis_manquant, EXCLU, st)
    vus = []
    for m in connues:
        c = cible(m)
        if c is not None and c not in vus:
            vus.append(c)
    for c in nouvelles.dropna().unique():
        if c not in vus:
            vus.append(c)
    meta = _meta(etape, "ordinale" if p.get("ordonnee") else "quali", _ordre(p, vus), [src], bool(p.get("ordonnee")),
                 nr=nr_cible)
    table.ajouter(meta, nouvelles, st)


def _decouper(etape, table: Table, rapport):
    p = etape["params"]
    src = p["source"]
    table.exiger(src)
    x = pd.to_numeric(table.valeurs[src], errors="coerce").to_numpy(dtype=float)
    st = table.statuts[src].copy()
    bornes = sorted(float(b) for b in p.get("bornes", []))
    if not bornes:
        raise ErreurEtape("Indiquez au moins une borne de découpage.")
    f = lambda b: str(int(b)) if float(b).is_integer() else str(b).replace(".", ",")
    auto = [f"Moins de {f(bornes[0])}"] + [f"{f(a)} à moins de {f(b)}" for a, b in zip(bornes, bornes[1:])] + \
           [f"{f(bornes[-1])} ou plus"]
    if p.get("droite"):
        auto = [f"{f(bornes[0])} ou moins"] + [f"Plus de {f(a)} à {f(b)}" for a, b in zip(bornes, bornes[1:])] + \
               [f"Plus de {f(bornes[-1])}"]
    etiquettes = p.get("etiquettes") or auto
    if len(etiquettes) != len(bornes) + 1 or len(set(etiquettes)) != len(etiquettes):
        etiquettes = auto
    idx = np.searchsorted(bornes, x, side="left" if p.get("droite") else "right")
    valide = (st == VALIDE) & ~np.isnan(x)
    vals = pd.Series(np.where(valide, np.array(etiquettes, dtype=object)[np.clip(idx, 0, len(bornes))], None), dtype=object)
    table.ajouter(_meta(etape, "ordinale", etiquettes, [src], True), vals, st)


def _points(table: Table, vid: str, points: dict | None) -> np.ndarray:
    meta = table.meta[vid]
    if meta["type"] == "quanti":
        return pd.to_numeric(table.valeurs[vid], errors="coerce").to_numpy(dtype=float)
    if not points:
        raise ErreurEtape("Indiquez le nombre de points attribué à chaque modalité.")
    return table.valeurs[vid].astype(object).map(lambda v: points.get(v, np.nan) if isinstance(v, str) else np.nan) \
        .to_numpy(dtype=float)


def _score(etape, table: Table, rapport):
    p = etape["params"]
    srcs = p.get("sources", [])
    if not srcs:
        raise ErreurEtape("Choisissez au moins une variable.")
    for v in srcs:
        table.exiger(v)
    mode = p.get("mode", "compter")
    statuts = [table.statuts[v] for v in srcs]
    valides = np.vstack([s == VALIDE for s in statuts])
    if mode == "compter":
        cibles = set(p.get("valeurs", ["Oui"]))
        mat = np.vstack([table.valeurs[v].astype(object).isin(cibles).to_numpy() & (table.statuts[v] == VALIDE)
                         for v in srcs]).astype(float)
    else:
        mat = np.vstack([_points(table, v, p.get("points")) for v in srcs])
        valides = valides & ~np.isnan(mat)
        mat = np.where(valides, mat, 0.0)
    n_val = valides.sum(axis=0)
    defaut = len(srcs) if mode != "moyenne" else max(1, (len(srcs) + 1) // 2)
    mini = int(p.get("min_valides") or defaut)
    total = mat.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        valeur = total / n_val if mode == "moyenne" else total
    ok = n_val >= mini
    st = np.where(ok, VALIDE, _statut_combine(statuts))
    partiels = int((ok & (n_val < len(srcs))).sum())
    if partiels:
        rapport["avertissements"].append(
            f"{partiels} individu(s) ont un score calculé sur une partie seulement des {len(srcs)} items "
            f"(minimum exigé : {mini}).")
    table.ajouter(_meta(etape, "quanti", None, srcs), pd.Series(np.where(ok, valeur, np.nan), dtype=float), st)


def _regle(etape, table: Table, rapport):
    p = etape["params"]
    cas = p.get("cas", [])
    if not cas:
        raise ErreurEtape("Ajoutez au moins une règle.")
    vals = np.full(table.n, None, dtype=object)
    libre = np.ones(table.n, dtype=bool)
    for c in cas:
        m = evaluer(c.get("si"), table) & libre
        vals[m] = c.get("alors")
        libre &= ~m
    if p.get("sinon"):
        vals[libre] = p["sinon"]
    srcs = sorted(sources_etape(etape))
    st = np.where(pd.isna(pd.Series(vals, dtype=object)).to_numpy(), EXCLU, VALIDE).astype(np.int8)
    # là où aucune règle ne s'applique et où toutes les sources manquent, on garde la raison du manque
    if srcs:
        comb = _statut_combine([table.statuts[v] for v in srcs])
        toutes_manquantes = np.vstack([table.statuts[v] != VALIDE for v in srcs]).all(axis=0)
        st = np.where((st == EXCLU) & libre & toutes_manquantes, comb, st)
    vus = [c["alors"] for c in cas if c.get("alors")] + ([p["sinon"]] if p.get("sinon") else [])
    vus = list(dict.fromkeys(vus))
    non_classes = int(((st == EXCLU) & libre).sum())
    if non_classes:
        rapport["avertissements"].append(f"{non_classes} individu(s) ne correspondent à aucune règle (mis en manquant).")
    table.ajouter(_meta(etape, "ordinale" if p.get("ordonnee") else "quali", _ordre(p, vus), srcs,
                        bool(p.get("ordonnee"))), pd.Series(vals, dtype=object), st)


def _fusionner(etape, table: Table, rapport):
    p = etape["params"]
    srcs = p.get("sources", [])
    if len(srcs) < 2:
        raise ErreurEtape("Une fusion réunit au moins deux variables.")
    for s in srcs:
        table.exiger(s["var"])
    numerique = all(table.meta[s["var"]]["type"] == "quanti" for s in srcs)
    vals = np.full(table.n, np.nan if numerique else None, dtype=float if numerique else object)
    pris = np.zeros(table.n, dtype=bool)
    conflits = 0
    vus: list[str] = []
    for s in srcs:
        vid, corr = s["var"], s.get("correspondance") or {}
        valide = table.statuts[vid] == VALIDE
        if numerique:
            x = pd.to_numeric(table.valeurs[vid], errors="coerce").to_numpy(dtype=float)
        else:
            serie = table.valeurs[vid].astype(object).map(lambda v: corr.get(v, v) if isinstance(v, str) else None)
            x = serie.to_numpy(dtype=object)
            valide = valide & ~pd.isna(serie).to_numpy()
            for m in table.meta[vid].get("modalites", []):
                c = corr.get(m["valeur"], m["valeur"])
                if c is not None and c not in vus and not m.get("nr"):
                    vus.append(c)
        with np.errstate(invalid="ignore"):
            conflits += int((valide & pris & (pd.Series(x).astype(object) != pd.Series(vals).astype(object)).to_numpy()).sum())
        nouveau = valide & ~pris
        vals[nouveau] = x[nouveau]
        pris |= valide
    if conflits:
        rapport["avertissements"].append(
            f"{conflits} individu(s) ont une réponse valide différente dans plusieurs sources : la première source "
            "de la liste l'emporte.")
    st = np.where(pris, VALIDE, _statut_combine([table.statuts[s["var"]] for s in srcs]))
    ids = [s["var"] for s in srcs]
    if numerique:
        table.ajouter(_meta(etape, "quanti", None, ids), pd.Series(vals, dtype=float), st)
    else:
        table.ajouter(_meta(etape, "ordinale" if p.get("ordonnee") else "quali", _ordre(p, vus), ids,
                            bool(p.get("ordonnee"))), pd.Series(vals, dtype=object), st)


def _convertir(etape, table: Table, rapport):
    p = etape["params"]
    src = p["source"]
    table.exiger(src)
    corr = p.get("valeurs") or {}

    def nombre(v):
        if not isinstance(v, str):
            return np.nan
        if v in corr:
            return float(corr[v]) if corr[v] is not None else np.nan
        m = RE_NOMBRE.search(v)
        return float(m.group().replace(",", ".")) if m else np.nan

    x = table.valeurs[src].astype(object).map(nombre).to_numpy(dtype=float)
    st = table.statuts[src].copy()
    rate = (st == VALIDE) & np.isnan(x)
    if rate.any():
        rapport["avertissements"].append(f"{int(rate.sum())} réponse(s) sans nombre reconnaissable (mises en manquant).")
    st = np.where(rate, EXCLU, st)
    table.ajouter(_meta(etape, "quanti", None, [src]), pd.Series(np.where(st == VALIDE, x, np.nan), dtype=float), st)


def _croiser(etape, table: Table, rapport):
    p = etape["params"]
    a, b = p["sources"]
    table.exiger(a), table.exiger(b)
    sep = p.get("separateur", " × ")
    ea, eb = table.etiquettes(a), table.etiquettes(b)
    va = table.valeurs[a].astype(object).map(lambda v: ea.get(v, v) if isinstance(v, str) else None)
    vb = table.valeurs[b].astype(object).map(lambda v: eb.get(v, v) if isinstance(v, str) else None)
    ok = (table.statuts[a] == VALIDE) & (table.statuts[b] == VALIDE)
    vals = pd.Series(np.where(ok, va.astype(str) + sep + vb.astype(str), None), dtype=object)
    ordre = [ea[m["valeur"]] + sep + eb[n["valeur"]] for m in table.meta[a]["modalites"] if not m.get("nr")
             for n in table.meta[b]["modalites"] if not n.get("nr")]
    presents = set(vals.dropna())
    st = np.where(ok, VALIDE, _statut_combine([table.statuts[a], table.statuts[b]]))
    table.ajouter(_meta(etape, "quali", [m for m in ordre if m in presents], [a, b]), vals, st)


def _exclure(etape, table: Table, rapport):
    p = etape["params"]
    m = evaluer(p.get("si"), table) & ~table.exclus
    table.exclus |= m
    table.motifs_exclusion.append({"etape": etape["id"], "motif": p.get("motif") or "", "n": int(m.sum())})
    rapport["n_exclus"] = int(m.sum())


APPLICATEURS: dict[str, Callable] = {
    "recoder": _recoder, "decouper": _decouper, "score": _score, "regle": _regle, "fusionner": _fusionner,
    "convertir": _convertir, "croiser": _croiser, "exclure": _exclure,
}


def appliquer_recette(table: Table, etapes: list[dict], partitions: Callable[[dict, Table], None] | None = None) -> list[dict]:
    """Applique les étapes actives dans l'ordre. Une étape en erreur n'arrête pas la recette :
    elle est signalée et ses variables de sortie sont simplement absentes."""
    rapports = []
    for etape in etapes:
        rapport = {"id": etape["id"], "ok": True, "erreur": None, "avertissements": [], "sorties": sorties_etape(etape)}
        if not etape.get("actif", True):
            rapport.update(ok=False, erreur="Étape désactivée")
            rapports.append(rapport)
            continue
        try:
            if etape["type"] == "partition":
                if partitions is None:
                    raise ErreurEtape("Classification indisponible.")
                partitions(etape, table)
            else:
                APPLICATEURS[etape["type"]](etape, table, rapport)
            for vid in rapport["sorties"]:
                if table.existe(vid):
                    st = table.statuts[vid]
                    rapport["n_valides"] = int(((st == VALIDE) & ~table.exclus).sum())
        except (ErreurEtape, KeyError, ValueError, TypeError) as e:
            rapport.update(ok=False, erreur=str(e).strip("'\""))
        rapports.append(rapport)
    return rapports
