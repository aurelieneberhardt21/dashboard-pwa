"""Exécution des analyses : de la spécification (ce que l'utilisateur a choisi) au résultat documenté.

Chaque analyse est décrite par une *spécification* JSON (type, variables, population, options). Ce module
  1. prépare les données correspondantes (population, traitement des non-réponses) ;
  2. appelle le moteur statistique (modules ``stats.*``, validés contre R) ;
  3. accompagne le résultat d'une *fiche de calcul* : quelles données, quelles exclusions, quels paramètres,
     quelle méthode, quels avertissements — pour que rien ne soit implicite.
"""
from __future__ import annotations

import hashlib
import json
import re

import numpy as np
import pandas as pd

from .recette import TYPES_ETAPES
from .stats import classification, correlation, croise, exploration, geometrique, regression, univarie
from .table import (ABANDON, EXCLU, FILTRE, NR, NSP, STATUTS, TYPES_CATEGORIELS, VALIDE, VIDE, Table, _court,
                    decompte_statuts, decrire, evaluer)

TYPES_ANALYSES = {
    "tri": "Tri à plat", "croise": "Croisement de deux variables", "multiples": "Question à réponses multiples",
    "correlation": "Corrélations", "regression": "Régression", "acm": "Analyse des correspondances multiples",
    "acp": "Analyse en composantes principales", "afc": "Analyse factorielle des correspondances",
    "afdm": "Analyse factorielle de données mixtes", "cah": "Classification ascendante hiérarchique",
    "exploration": "Exploration d'associations",
}
NON_REPONSE = "Non-réponse"


class ErreurAnalyse(ValueError):
    pass


# ----------------------------------------------------------------------------
# Contexte commun
# ----------------------------------------------------------------------------

class Contexte:
    def __init__(self, projet, spec: dict):
        self.projet, self.spec = projet, spec
        self.table: Table = projet.table()
        self.meta = self.table.meta
        self.base = self.table.masque_base()
        self.population = next((p for p in projet.etat["populations"] if p["id"] == spec.get("population")), None)
        if spec.get("population") and self.population is None:
            raise ErreurAnalyse("La population choisie n'existe plus.")
        self.masque = self.base & (evaluer(self.population["condition"], self.table) if self.population else True)
        self.avertissements: list[str] = []
        self.variables: list[str] = []
        self.exclusions: list[dict] = []
        self.nsp = spec.get("nsp", "exclure")
        self.export: pd.DataFrame | None = None     # données telles qu'analysées (pour l'export reproductible)
        self.roles_export: dict = {}

    def exiger(self, vid: str | None, *types: str, role: str = "") -> str:
        if not vid:
            raise ErreurAnalyse(f"Choisissez une variable{(' ' + role) if role else ''}.")
        if vid not in self.meta:
            raise ErreurAnalyse(f"La variable « {vid} » n'existe pas (ou plus) dans le projet.")
        t = self.meta[vid]["type"]
        if types and t not in types:
            noms = {"quali": "qualitative", "ordinale": "ordinale", "multi": "à cocher", "quanti": "numérique",
                    "texte": "textuelle"}
            raise ErreurAnalyse(f"« {self.nom(vid)} » est {noms.get(t, t)} : cette analyse attend une variable "
                                f"{' ou '.join(noms.get(x, x) for x in types)}.")
        if vid not in self.variables:
            self.variables.append(vid)
        return vid

    def nom(self, vid: str) -> str:
        m = self.meta.get(vid, {})
        if m.get("nom") and m["nom"] != vid:
            return m["nom"]
        # item d'une matrice ou d'une question à choix multiples : l'intitulé de l'item est le plus parlant
        return _court(m.get("sous_libelle") or m.get("libelle", vid), 60)

    def serie(self, vid: str, **kw) -> pd.Series:
        kw.setdefault("nsp", self.nsp)
        s = self.table.serie(vid, **kw)
        s.index = self.table.index
        return s

    def cadre(self, vids: list[str], **kw) -> pd.DataFrame:
        return pd.DataFrame({v: self.serie(v, **kw) for v in vids}, index=self.table.index)

    def humaniser(self, texte: str) -> str:
        """Remplace les identifiants de variables par leur nom dans un message."""
        if not isinstance(texte, str):
            return texte
        for vid in sorted(self.variables, key=len, reverse=True):
            texte = texte.replace(f"« {vid} »", f"« {self.nom(vid)} »")
            texte = re.sub(rf"(?<![\w«]){re.escape(vid)}(?![\w»])", f"« {self.nom(vid)} »", texte)
        return texte

    def fiche(self, n_analyses: int, parametres: dict, methode, lecture: str | None = None,
              avertissements: list[str] | None = None) -> dict:
        e, t = self.projet.etat, self.table
        etapes = {x["id"]: x for x in e["recette"]}
        variables = []
        for vid in self.variables:
            m = self.meta[vid]
            ligne = {"id": vid, "nom": self.nom(vid), "libelle": m.get("libelle"), "sous_libelle": m.get("sous_libelle"),
                     "type": m["type"], "statuts": decompte_statuts(t, vid, self.masque)}
            if m.get("derive"):
                et = etapes.get(m["derive"], {})
                ligne["derive"] = {"etape": m["derive"], "type": TYPES_ETAPES.get(et.get("type"), et.get("type")),
                                   "sources": [self.nom(s) if s in self.meta else s for s in m.get("sources", [])],
                                   "note": et.get("note")}
            if m.get("champ") and not m["champ"].get("tous"):
                ligne["champ"] = decrire(m["champ"], self.meta)
            variables.append(ligne)
        av = [self.humaniser(a) for a in (self.avertissements + (avertissements or []))]
        return {
            "donnees": {
                "sources": [{"fichier": s["fichier"], "sha256": s["sha256"][:12], "importe": s["importe"],
                             "n_lignes": s["n_lignes"]} for s in e["sources"]],
                "n_total": t.n,
                "exclusions_globales": [{"motif": x["motif"], "n": x["n"]} for x in t.motifs_exclusion],
                "n_base": int(self.base.sum()),
                "population": ({"id": self.population["id"], "nom": self.population["nom"],
                                "description": decrire(self.population["condition"], self.meta)}
                               if self.population else None),
                "n_population": int(self.masque.sum()),
                "n_analyses": int(n_analyses),
                "exclusions": self.exclusions,
            },
            "variables": variables, "parametres": parametres, "methode": methode,
            "avertissements": list(dict.fromkeys(av)), "lecture": lecture,
            "version_projet": e.get("version"), "fictif": e.get("fictif", False),
        }

    def noter_exclusions(self, vids: list[str], garde: np.ndarray, quoi: str = "valeur manquante") -> None:
        """Décompte, variable par variable et par motif, les individus de la population écartés de l'analyse."""
        for vid in vids:
            st = self.table.statuts[vid][self.masque & ~garde]
            if self.nsp == "garder":
                st = st[st != NSP]
            st = st[st != VALIDE]
            if len(st):
                comptes = np.bincount(st, minlength=len(STATUTS))
                self.exclusions.append({"variable": vid, "nom": self.nom(vid), "n": int(len(st)),
                                        "motifs": {STATUTS[k][1]: int(c) for k, c in enumerate(comptes) if c}})


def _pct(x: float) -> str:
    return f"{x:.1f}".replace(".", ",") + " %"


# ----------------------------------------------------------------------------
# Analyses descriptives
# ----------------------------------------------------------------------------

def _tri(ctx: Contexte) -> tuple[dict, dict]:
    vid = ctx.exiger(ctx.spec.get("variable"))
    m = ctx.meta[vid]
    if m["type"] == "texte":
        s = ctx.serie(vid)[ctx.masque].dropna()
        comptes = s.value_counts()
        res = {"type": "texte", "n": int(len(s)), "n_distinctes": int(len(comptes)),
               "reponses": [{"texte": k, "n": int(v)} for k, v in comptes.head(500).items()],
               "avertissements": [], "methode": {"nom": "Liste des réponses textuelles (les plus fréquentes d'abord)"}}
        return res, ctx.fiche(len(s), {}, res["methode"])
    s = ctx.serie(vid)[ctx.masque]
    ctx.export = pd.DataFrame({vid: s})
    statuts = decompte_statuts(ctx.table, vid, ctx.masque)
    if m["type"] == "quanti":
        res = univarie.resume_quanti(s, classes=ctx.spec.get("classes"))
        lecture = (f"Lecture : parmi les {res['n']} réponses valides, la moyenne est de "
                   f"{res['moyenne']:.2f} et la médiane de {res['mediane']:.2f}.".replace(".", ",", 2)
                   if res.get("n") else None)
    else:
        res = univarie.tri_a_plat(s)
        lecture = None
        if res["modalites"] and res["n"]:
            top = max(res["modalites"], key=lambda x: x["n"])
            lecture = (f"Lecture : sur {res['n']} réponses valides, {top['n']} ({_pct(top['pct'])}) sont "
                       f"« {top['modalite']} ». Les pourcentages sont calculés sur les réponses valides ; "
                       f"l'intervalle de confiance (Wilson, 95 %) n'a de sens que si les répondants peuvent "
                       f"être vus comme un échantillon d'une population plus large.")
        petites = [x for x in res["modalites"] if 0 < x["n"] < 5]
        if petites:
            ctx.avertissements.append(f"{len(petites)} modalité(s) comptent moins de 5 individus : à regrouper avant "
                                      "tout croisement, et à ne pas publier telles quelles (risque de réidentification).")
    res["statuts"] = statuts
    res["n_population"] = int(ctx.masque.sum())
    if statuts["vide"]:
        ctx.avertissements.append(
            f"{statuts['vide']} cellules vides dont on ne sait pas si la question était posée : documentez le champ "
            "de la question (fiche de la variable) pour distinguer « non concerné » et « non-réponse ».")
    return res, ctx.fiche(res.get("n", 0), {"nsp": ctx.nsp}, res.get("methode"), lecture, res.get("avertissements"))


def _croise(ctx: Contexte) -> tuple[dict, dict]:
    x = ctx.exiger(ctx.spec.get("ligne"), "quali", "ordinale", "multi", "quanti", role="en lignes")
    y = ctx.exiger(ctx.spec.get("colonne"), "quali", "ordinale", "multi", "quanti", role="en colonnes")
    if x == y:
        raise ErreurAnalyse("Choisissez deux variables différentes.")
    sx, sy = ctx.serie(x)[ctx.masque], ctx.serie(y)[ctx.masque]
    garde = np.zeros(ctx.table.n, dtype=bool)
    garde[ctx.masque] = (sx.notna() & sy.notna()).to_numpy()
    ctx.noter_exclusions([x, y], garde)
    qx, qy = ctx.meta[x]["type"] == "quanti", ctx.meta[y]["type"] == "quanti"
    ctx.export = pd.DataFrame({x: sx, y: sy})[(sx.notna() & sy.notna())]
    params = {"ligne": x, "colonne": y, "nsp": ctx.nsp}
    if qx and qy:
        res = correlation.matrice_correlation(pd.DataFrame({x: sx, y: sy}), methode=ctx.spec.get("methode", "spearman"),
                                              ajustement="aucun")
        res["forme"] = "correlation"
        res["points"] = _nuage(sx, sy)
        return res, ctx.fiche(int(garde.sum()), params, res["methode"], None, res["avertissements"])
    if qx or qy:
        quanti, groupe = (sx, sy) if qx else (sy, sx)
        res = croise.comparer_groupes(quanti, groupe.cat.remove_unused_categories())
        res["forme"] = "groupes"
        res["quanti"], res["groupe"] = (x, y) if qx else (y, x)
        g = [k for k in res["groupes"] if k["n"]]
        lecture = None
        if len(g) >= 2:
            a, b = max(g, key=lambda k: k["moyenne"]), min(g, key=lambda k: k["moyenne"])
            lecture = (f"Lecture : la moyenne va de {b['moyenne']:.2f} (« {b['groupe']} », n = {b['n']}) à "
                       f"{a['moyenne']:.2f} (« {a['groupe']} », n = {a['n']}) ; l'appartenance au groupe rend compte "
                       f"de {_pct(100 * (res['anova']['eta2'] or 0))} de la variance (eta²).")
        return res, ctx.fiche(res["n"], params, res["methode"], lecture, res["avertissements"])
    res = croise.tableau_croise(sx, sy, simulation=int(ctx.spec.get("simulation", 5000)))
    res["forme"] = "tableau"
    lecture = None
    if res["n"] and res["lignes"] and res["colonnes"]:
        # cellule la plus sur-représentée (plus fort résidu ajusté positif) pour illustrer la lecture en ligne
        ra = np.array([[v if v is not None else -np.inf for v in l] for l in res["residus_ajustes"]], dtype=float)
        i, j = np.unravel_index(np.argmax(ra), ra.shape)
        lecture = (f"Lecture : parmi les {res['marge_lignes'][i]} individus « {res['lignes'][i]} », "
                   f"{res['effectifs'][i][j]} ({_pct(res['pct_ligne'][i][j])}) sont « {res['colonnes'][j]} », "
                   f"contre {_pct(res['pct_marge_colonnes'][j])} dans l'ensemble.")
    petites = int(sum(1 for l in res["effectifs"] for v in l if 0 < v < 5))
    if petites:
        ctx.avertissements.append(f"{petites} cellule(s) comptent entre 1 et 4 individus : pourcentages très instables, "
                                  "et risque de réidentification en cas de publication du tableau détaillé.")
    return res, ctx.fiche(res["n"], params, res["methode"], lecture, res["avertissements"])


def _nuage(sx: pd.Series, sy: pd.Series, maxi: int = 3000) -> list[list[float]]:
    d = pd.DataFrame({"x": sx, "y": sy}).dropna()
    if len(d) > maxi:
        d = d.sample(maxi, random_state=0)
    return [[float(a), float(b)] for a, b in zip(d["x"], d["y"])]


def _multiples(ctx: Contexte) -> tuple[dict, dict]:
    items = [ctx.exiger(v, "multi", "quali") for v in ctx.spec.get("variables", [])]
    if len(items) < 2:
        raise ErreurAnalyse("Choisissez les items (au moins deux) d'une question à réponses multiples.")
    coche = ctx.spec.get("valeur_cochee", "Oui")
    cadre = {}
    for v in items:
        s = ctx.serie(v, etiquettes=False)[ctx.masque]
        cadre[v] = s.map(lambda val: np.nan if pd.isna(val) else (val == coche)).astype(object)
    df = pd.DataFrame(cadre)
    groupe = None
    if ctx.spec.get("groupe"):
        g = ctx.exiger(ctx.spec["groupe"], "quali", "ordinale", "multi", role="de comparaison")
        groupe = ctx.serie(g)[ctx.masque].cat.remove_unused_categories()
    ctx.export = df.assign(**({ctx.spec['groupe']: groupe} if groupe is not None else {}))
    res = croise.choix_multiples(df, groupe)
    for it in res.get("items", []):
        vid = it.get("item")
        if vid in ctx.meta:
            it["libelle"] = ctx.meta[vid].get("sous_libelle") or ctx.nom(vid)
    return res, ctx.fiche(res.get("n_repondants", 0), {"items": items, "groupe": ctx.spec.get("groupe"), "valeur_cochee": coche},
                          res.get("methode"), None, res.get("avertissements"))


def _correlation(ctx: Contexte) -> tuple[dict, dict]:
    vids = [ctx.exiger(v, "quanti", "ordinale") for v in ctx.spec.get("variables", [])]
    if len(vids) < 2:
        raise ErreurAnalyse("Choisissez au moins deux variables numériques ou ordinales.")
    methode = ctx.spec.get("methode", "spearman")
    cadre = {}
    for v in vids:
        s = ctx.serie(v)[ctx.masque]
        if ctx.meta[v]["type"] == "ordinale":
            if methode == "pearson":
                raise ErreurAnalyse("Le coefficient de Pearson suppose des variables numériques : avec une variable "
                                    "ordinale, choisissez Spearman ou Kendall (corrélations de rangs).")
            s = pd.Series(np.where(s.isna(), np.nan, s.cat.codes.astype(float)), index=s.index)
        cadre[v] = s
    ctx.export = pd.DataFrame(cadre)
    res = correlation.matrice_correlation(pd.DataFrame(cadre), methode=methode,
                                          ajustement=ctx.spec.get("ajustement", "holm"))
    return res, ctx.fiche(int(pd.DataFrame(cadre).notna().all(axis=1).sum()),
                          {"methode": methode, "ajustement": ctx.spec.get("ajustement", "holm")}, res["methode"], None,
                          res["avertissements"] + ["Les effectifs varient d'une paire à l'autre (exclusion par paire) : "
                                                   "voir la colonne n."])


def _regression(ctx: Contexte) -> tuple[dict, dict]:
    y = ctx.exiger(ctx.spec.get("y"), "quanti", "quali", "ordinale", "multi", role="à expliquer")
    xs = [ctx.exiger(v, "quanti", "quali", "ordinale", "multi") for v in ctx.spec.get("x", []) if v != y]
    if not xs:
        raise ErreurAnalyse("Choisissez au moins une variable explicative.")
    sy = ctx.serie(y)[ctx.masque]
    X = ctx.cadre(xs)[ctx.masque]
    for v in xs:
        if ctx.meta[v]["type"] != "quanti":
            X[v] = X[v].cat.remove_unused_categories().cat.as_unordered()
    garde = np.zeros(ctx.table.n, dtype=bool)
    garde[ctx.masque] = (sy.notna() & X.notna().all(axis=1)).to_numpy()
    ctx.noter_exclusions([y] + xs, garde)
    ctx.export = X.assign(**{y: sy})[[y] + xs]
    refs = {k: v for k, v in (ctx.spec.get("references") or {}).items() if k in xs}
    inter = [tuple(i) for i in ctx.spec.get("interactions", []) if all(v in xs for v in i)]
    type_y = ctx.meta[y]["type"]
    modele = ctx.spec.get("modele") or ("lineaire" if type_y == "quanti" else "logistique")
    params = {"y": y, "x": xs, "modele": modele, "references": refs, "interactions": inter}
    if modele == "lineaire":
        if type_y != "quanti":
            raise ErreurAnalyse("La régression linéaire attend une variable à expliquer numérique.")
        res = regression.regression_lineaire(sy, X, references=refs, robuste=ctx.spec.get("robuste"), interactions=inter)
        params["robuste"] = ctx.spec.get("robuste")
    elif modele == "logistique":
        if type_y == "quanti":
            raise ErreurAnalyse("La régression logistique attend une variable à expliquer qualitative à deux modalités "
                                "(ou une modalité cible à opposer aux autres).")
        sy = sy.cat.remove_unused_categories()
        cible = ctx.spec.get("modalite_cible")
        if cible is None:
            if len(sy.cat.categories) != 2:
                raise ErreurAnalyse("La variable à expliquer a plus de deux modalités : choisissez la modalité cible "
                                    "(elle sera opposée à toutes les autres), ou un modèle multinomial.")
            cible = "Oui" if "Oui" in list(sy.cat.categories) else sy.cat.categories[-1]
        params["modalite_cible"] = cible
        res = regression.regression_logistique(sy, X, modalite_cible=cible, references=refs, interactions=inter)
    else:
        sy = sy.cat.remove_unused_categories().cat.as_unordered()
        res = regression.regression_multinomiale(sy, X, reference_y=ctx.spec.get("reference_y"), references=refs)
        params["reference_y"] = res.get("y", {}).get("modalite_reference")
    res["modele"] = modele
    av = list(res.get("avertissements", []))
    av.append("Un coefficient mesure une association « toutes choses égales par ailleurs » parmi les variables du "
              "modèle, pas un effet causal ; il dépend des variables incluses et de la modalité de référence choisie.")
    return res, ctx.fiche(res.get("n", 0), params, res.get("methode"), None, av)


# ----------------------------------------------------------------------------
# Analyses géométriques
# ----------------------------------------------------------------------------

def _individus_sup(ctx: Contexte) -> np.ndarray:
    pid = ctx.spec.get("ind_sup")
    if not pid:
        return np.zeros(ctx.table.n, dtype=bool)
    pop = next((p for p in ctx.projet.etat["populations"] if p["id"] == pid), None)
    if pop is None:
        raise ErreurAnalyse("La population d'individus supplémentaires n'existe plus.")
    return ctx.base & evaluer(pop["condition"], ctx.table) & ~ctx.masque


def _sup(ctx: Contexte, garde: np.ndarray, actives: list[str]) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    quali = [ctx.exiger(v, *TYPES_CATEGORIELS) for v in ctx.spec.get("sup_quali", []) if v not in actives]
    quanti = [ctx.exiger(v, "quanti") for v in ctx.spec.get("sup_quanti", []) if v not in actives]
    dq = ctx.cadre(quali)[garde] if quali else None
    if dq is not None:
        for v in quali:
            dq[v] = dq[v].cat.remove_unused_categories()
    return dq, (ctx.cadre(quanti)[garde] if quanti else None)


def _hors_champ(ctx: Contexte, vids: list[str]) -> np.ndarray:
    """Individus de la population qui ne sont pas concernés par (ou n'ont pas atteint) une variable active."""
    hors = np.zeros(ctx.table.n, dtype=bool)
    for v in vids:
        hors |= np.isin(ctx.table.statuts[v], (FILTRE, ABANDON))
    return hors


def _acm(ctx: Contexte) -> tuple[dict, dict]:
    spec = ctx.spec
    actives = [ctx.exiger(v, *TYPES_CATEGORIELS, role="active") for v in spec.get("actives", [])]
    if len(actives) < 2:
        raise ErreurAnalyse("Une ACM demande au moins deux variables actives qualitatives.")
    manquants = spec.get("manquants", "passive")        # passive | active | exclure
    nsp = spec.get("nsp_acm", "passive")                # passive | active | manquant
    garder_nsp = "garder" if nsp in ("passive", "active") else "exclure"
    X = pd.DataFrame({v: ctx.table.serie(v, nsp=garder_nsp, manquants="exclure" if manquants == "exclure" else "modalite")
                      for v in actives})
    X.index = ctx.table.index
    hors = _hors_champ(ctx, actives)
    complet = X.notna().all(axis=1).to_numpy()
    garde = ctx.masque & complet
    sup_masque = _individus_sup(ctx) & complet
    n_hors = int((ctx.masque & hors).sum())
    if n_hors:
        ctx.avertissements.append(
            f"{n_hors} individus de la population ne sont pas concernés par (ou n'ont pas atteint) au moins une "
            "variable active : ils sont écartés de l'analyse. Si ce nombre est élevé, restreignez la population au "
            "champ commun des variables actives, ou retirez la variable en cause (détail dans les exclusions).")
    ctx.noter_exclusions(actives, garde)
    if garde.sum() < 10:
        raise ErreurAnalyse(f"Il ne reste que {int(garde.sum())} individus avec toutes les variables actives "
                            "disponibles : vérifiez la population et le champ des questions choisies.")
    Xa = X[garde].copy()
    passives: list[tuple[str, str]] = []
    for v in actives:
        Xa[v] = Xa[v].cat.remove_unused_categories().cat.as_unordered()
        cats = list(Xa[v].cat.categories)
        if len(cats) < 2:
            raise ErreurAnalyse(f"« {ctx.nom(v)} » n'a qu'une seule modalité dans cette population : retirez-la.")
        if manquants == "passive" and NON_REPONSE in cats:
            passives.append((v, NON_REPONSE))
        if nsp == "passive":
            etq = ctx.table.etiquettes(v)
            passives += [(v, etq[m["valeur"]]) for m in ctx.meta[v].get("modalites", [])
                         if m.get("nr") and etq[m["valeur"]] in cats]
    for v, m in spec.get("passives", []):
        if v in actives and m in list(Xa[v].cat.categories) and (v, m) not in passives:
            passives.append((v, m))
    ind_sup = None
    if sup_masque.any():
        ind_sup = X[sup_masque].copy()
        for v in actives:      # un individu supplémentaire ne peut porter que des modalités connues des actifs
            ind_sup[v] = pd.Categorical(ind_sup[v].astype(object), categories=list(Xa[v].cat.categories))
        ind_sup = ind_sup.dropna()
    quali_sup, quanti_sup = _sup(ctx, garde, actives)
    ctx.export = pd.concat([Xa, quali_sup, quanti_sup], axis=1)
    ctx.roles_export = {"passives": passives}
    res = geometrique.acm(Xa, passives=passives, n_axes=int(spec.get("n_axes", 5)), ind_sup=ind_sup,
                          quali_sup=quali_sup, quanti_sup=quanti_sup)
    n = int(garde.sum())
    rares = [m for m in res["modalites"] if not m.get("passive") and m["n"] < max(5, 0.05 * n)]
    params = {"actives": actives, "manquants": manquants, "nsp_acm": nsp, "passives": [list(p) for p in passives],
              "sup_quali": spec.get("sup_quali", []), "sup_quanti": spec.get("sup_quanti", []),
              "ind_sup": spec.get("ind_sup"), "n_axes": int(spec.get("n_axes", 5))}
    res["modalites_rares"] = [m["id"] for m in rares]
    return res, ctx.fiche(n, params, _methode_geo(res), None, res.get("avertissements"))


def _methode_geo(res: dict) -> dict:
    noms = {"acm": "Analyse des correspondances multiples (ACM)",
            "acm_specifique": "ACM spécifique (modalités passives ; Le Roux & Rouanet)",
            "acp": "Analyse en composantes principales (ACP)", "afc": "Analyse factorielle des correspondances (AFC)",
            "afdm": "Analyse factorielle de données mixtes (AFDM / FAMD)"}
    return {"nom": noms.get(res.get("methode"), res.get("methode")),
            "moteur": "décomposition en valeurs singulières (numpy) ; formules validées contre FactoMineR 2.9 "
                      "et GDAtools 2.3 (voir tests/test_geometrique.py)",
            "conventions": "contributions en % (somme 100 par axe) ; cos² en proportion ; signe des axes arbitraire"}


def _acp(ctx: Contexte) -> tuple[dict, dict]:
    spec = ctx.spec
    actives = [ctx.exiger(v, "quanti", role="active") for v in spec.get("actives", [])]
    if len(actives) < 2:
        raise ErreurAnalyse("Une ACP demande au moins deux variables actives numériques.")
    X = ctx.cadre(actives)
    complet = X.notna().all(axis=1).to_numpy()
    garde = ctx.masque & complet
    ctx.noter_exclusions(actives, garde)
    if garde.sum() < 5:
        raise ErreurAnalyse("Trop peu d'individus avec toutes les variables actives renseignées.")
    sup_masque = _individus_sup(ctx) & complet
    quali_sup, quanti_sup = _sup(ctx, garde, actives)
    ctx.export = pd.concat([X[garde], quali_sup, quanti_sup], axis=1)
    res = geometrique.acp(X[garde], reduire=bool(spec.get("reduire", True)), n_axes=int(spec.get("n_axes", 5)),
                          ind_sup=X[sup_masque] if sup_masque.any() else None, quanti_sup=quanti_sup, quali_sup=quali_sup)
    params = {"actives": actives, "reduire": bool(spec.get("reduire", True)), "sup_quali": spec.get("sup_quali", []),
              "sup_quanti": spec.get("sup_quanti", []), "ind_sup": spec.get("ind_sup"), "n_axes": int(spec.get("n_axes", 5))}
    ctx.avertissements.append("Les individus ayant au moins une valeur manquante sur les variables actives sont écartés "
                              "(aucune imputation n'est faite).")
    return res, ctx.fiche(int(garde.sum()), params, _methode_geo(res), None, res.get("avertissements"))


def _afdm(ctx: Contexte) -> tuple[dict, dict]:
    spec = ctx.spec
    actives = [ctx.exiger(v, "quanti", *TYPES_CATEGORIELS, role="active") for v in spec.get("actives", [])]
    types = {ctx.meta[v]["type"] == "quanti" for v in actives}
    if len(actives) < 2 or len(types) < 2:
        raise ErreurAnalyse("L'AFDM mêle des variables actives numériques ET qualitatives (au moins une de chaque). "
                            "Avec un seul type, utilisez l'ACP ou l'ACM.")
    X = ctx.cadre(actives)
    complet = X.notna().all(axis=1).to_numpy()
    garde = ctx.masque & complet
    ctx.noter_exclusions(actives, garde)
    if garde.sum() < 10:
        raise ErreurAnalyse("Trop peu d'individus avec toutes les variables actives renseignées.")
    Xa = X[garde].copy()
    for v in actives:
        if ctx.meta[v]["type"] != "quanti":
            Xa[v] = Xa[v].cat.remove_unused_categories().cat.as_unordered()
    quali_sup, quanti_sup = _sup(ctx, garde, actives)
    ctx.export = pd.concat([Xa, quali_sup, quanti_sup], axis=1)
    res = geometrique.afdm(Xa, n_axes=int(spec.get("n_axes", 5)), quali_sup=quali_sup, quanti_sup=quanti_sup)
    params = {"actives": actives, "sup_quali": spec.get("sup_quali", []), "sup_quanti": spec.get("sup_quanti", []),
              "n_axes": int(spec.get("n_axes", 5))}
    return res, ctx.fiche(int(garde.sum()), params, _methode_geo(res), None, res.get("avertissements"))


def _afc(ctx: Contexte) -> tuple[dict, dict]:
    spec = ctx.spec
    x = ctx.exiger(spec.get("ligne"), *TYPES_CATEGORIELS, role="en lignes")
    y = ctx.exiger(spec.get("colonne"), *TYPES_CATEGORIELS, role="en colonnes")
    sx, sy = ctx.serie(x)[ctx.masque], ctx.serie(y)[ctx.masque]
    ok = sx.notna() & sy.notna()
    garde = np.zeros(ctx.table.n, dtype=bool)
    garde[ctx.masque] = ok.to_numpy()
    ctx.noter_exclusions([x, y], garde)
    ctx.export = pd.DataFrame({x: sx[ok], y: sy[ok]})
    N = pd.crosstab(sx[ok].cat.remove_unused_categories(), sy[ok].cat.remove_unused_categories())
    if N.shape[0] < 3 or N.shape[1] < 3:
        raise ErreurAnalyse("L'AFC n'a d'intérêt que pour un tableau d'au moins 3 lignes et 3 colonnes : pour un "
                            "tableau plus petit, lisez directement le tableau croisé et ses résidus.")
    ls = [m for m in spec.get("lignes_sup", []) if m in N.index]
    cs = [m for m in spec.get("colonnes_sup", []) if m in N.columns]
    actif = N.drop(index=ls, columns=cs)
    res = geometrique.afc(actif, n_axes=int(spec.get("n_axes", 5)),
                          lignes_sup=N.loc[ls, actif.columns] if ls else None,
                          colonnes_sup=N.loc[actif.index, cs] if cs else None)
    res["tableau"] = {"lignes": [str(i) for i in N.index], "colonnes": [str(c) for c in N.columns],
                      "effectifs": N.to_numpy().tolist()}
    params = {"ligne": x, "colonne": y, "lignes_sup": ls, "colonnes_sup": cs, "n_axes": int(spec.get("n_axes", 5))}
    return res, ctx.fiche(int(N.to_numpy().sum()), params, _methode_geo(res), None, res.get("avertissements"))


FACTORIELLES = {"acm": _acm, "acp": _acp, "afdm": _afdm}


def _cah(ctx: Contexte) -> tuple[dict, dict]:
    spec = ctx.spec
    base = spec.get("base")
    if isinstance(base, str):       # identifiant d'une analyse enregistrée
        a = next((a for a in ctx.projet.etat["analyses"] if a["id"] == base), None)
        if a is None:
            raise ErreurAnalyse("L'analyse factorielle de départ n'existe plus.")
        base = a["spec"]
    if not base or base.get("type") not in FACTORIELLES:
        raise ErreurAnalyse("La classification part d'une ACM, d'une ACP ou d'une AFDM : choisissez l'analyse de départ.")
    n_axes = int(spec.get("n_axes_cah", 5))
    sous = Contexte(ctx.projet, {**base, "n_axes": max(n_axes, int(base.get("n_axes", 5)))})
    fact, fiche_fact = FACTORIELLES[base["type"]](sous)
    ctx.variables, ctx.exclusions, ctx.masque, ctx.population = sous.variables, sous.exclusions, sous.masque, sous.population
    ctx.export, ctx.roles_export = sous.export, sous.roles_export
    ids = fact["individus"]["ids"]
    n_axes = min(n_axes, len(fact["individus"]["coord"][0]))
    coord = pd.DataFrame([c[:n_axes] for c in fact["individus"]["coord"]], index=ids)
    res = classification.cah(coord, k=spec.get("k"), k_max=int(spec.get("k_max", 10)),
                             consolidation=bool(spec.get("consolidation", True)))
    partition = pd.Series(res["partition"], index=res["ids"])
    position = {i: k for k, i in enumerate(ctx.table.index)}
    lignes = [position[i] for i in ids]
    decrire_vars = list(dict.fromkeys(list(base.get("actives", [])) + list(base.get("sup_quali", [])) +
                                      list(base.get("sup_quanti", [])) + list(spec.get("decrire", []))))
    decrire_vars = [v for v in decrire_vars if v in ctx.meta]
    for v in decrire_vars:
        if v not in ctx.variables:
            ctx.variables.append(v)
    quali = [v for v in decrire_vars if ctx.meta[v]["type"] in TYPES_CATEGORIELS]
    quanti = [v for v in decrire_vars if ctx.meta[v]["type"] == "quanti"]
    dq = pd.DataFrame({v: ctx.serie(v).iloc[lignes].to_numpy() for v in quali}, index=ids) if quali else None
    if dq is not None:
        for v in quali:
            dq[v] = pd.Categorical(dq[v]).remove_unused_categories()
    dn = pd.DataFrame({v: ctx.serie(v).iloc[lignes].to_numpy() for v in quanti}, index=ids) if quanti else None
    res["description"] = classification.decrire_classes(partition.loc[ids].tolist(), quali=dq, quanti=dn)
    res["factorielle"] = {"type": base["type"], "axes": fact["axes"][:10], "n_axes_utilises": n_axes,
                          "pct_inertie_utilisee": sum(a["pct"] for a in fact["axes"][:n_axes]),
                          "individus": {"ids": ids, "coord": [c[:min(3, n_axes)] for c in fact["individus"]["coord"]]}}
    params = {"base": base, "n_axes_cah": n_axes, "k": res["k"], "k_suggere": res.get("k_suggere"),
              "consolidation": bool(spec.get("consolidation", True))}
    av = list(res.get("avertissements", [])) + fiche_fact["avertissements"] + [
        "Une classification produit toujours des classes, même sans structure nette : regardez la part d'inertie "
        "inter-classes, la stabilité quand on change le nombre d'axes ou de classes, et ce que décrivent les classes."]
    methode = {"nom": "Classification ascendante hiérarchique (critère de Ward) sur les coordonnées factorielles",
               "moteur": "scipy.cluster.hierarchy ; consolidation par centres mobiles ; description des classes par "
                         "valeurs-tests (équivalent FactoMineR::HCPC et catdes, validé à 1e-8)",
               "axes": f"{n_axes} premiers axes, soit {res['factorielle']['pct_inertie_utilisee']:.1f} % de l'inertie"}
    return res, ctx.fiche(len(ids), params, methode, None, av)


def partition_analyse(projet, etape: dict, table: Table) -> None:
    """Étape « partition » de la recette : ajoute comme variable les classes d'une classification enregistrée."""
    a = next((a for a in projet.etat["analyses"] if a["id"] == etape["params"].get("analyse")), None)
    if a is None or a["spec"].get("type") != "cah":
        raise ValueError("La classification d'origine a été supprimée.")
    # la classification est recalculée sur les variables brutes et dérivées déjà présentes dans la table
    ancien = projet._table
    projet._table, projet._cle_table = table, projet.cle_donnees()
    try:
        res, _ = _cah(Contexte(projet, a["spec"]))
    finally:
        projet._table = ancien if ancien is not None else table
    classes = dict(zip(res["ids"], res["partition"]))
    vals = pd.Series([f"Classe {classes[i]}" if i in classes else None for i in table.index], dtype=object)
    st = np.where(vals.notna().to_numpy(), VALIDE, EXCLU).astype(np.int8)
    cible = etape["params"]["cible"]
    table.ajouter({"id": cible["id"], "nom": cible.get("nom") or cible["id"],
                   "libelle": cible.get("libelle") or f"Classes — {a.get('titre', '')}", "sous_libelle": None,
                   "question": None, "type": "quali", "role": "analyse", "ordonnee": False,
                   "modalites": [{"valeur": f"Classe {k}"} for k in sorted(set(classes.values()))],
                   "derive": etape["id"], "sources": [], "champ": None}, vals, st)


def _exploration(ctx: Contexte) -> tuple[dict, dict]:
    spec = ctx.spec
    cible = ctx.exiger(spec.get("cible"), "quanti", *TYPES_CATEGORIELS, role="cible")
    candidates = [v for v in spec.get("candidates", []) if v != cible and v in ctx.meta
                  and ctx.meta[v]["type"] in ("quanti",) + TYPES_CATEGORIELS and ctx.meta[v].get("role") == "analyse"]
    if not candidates:
        raise ErreurAnalyse("Choisissez les variables à confronter à la variable cible.")
    for v in candidates:
        ctx.exiger(v)
    sc = ctx.serie(cible)[ctx.masque]
    if ctx.meta[cible]["type"] != "quanti":
        sc = sc.cat.remove_unused_categories()
    cadre = ctx.cadre(candidates)[ctx.masque]
    for v in candidates:
        if ctx.meta[v]["type"] != "quanti":
            cadre[v] = cadre[v].cat.remove_unused_categories()
    ctx.export = cadre.assign(**{cible: sc})
    res = exploration.associations(sc.rename(cible), cadre, ajustement=spec.get("ajustement", "bh"))
    ctx.variables = [cible]          # la fiche ne détaille que la cible ; les candidates sont dans le tableau
    for a in res["associations"]:
        a["nom"] = ctx.nom(a["variable"])
    return res, ctx.fiche(int(sc.notna().sum()), {"cible": cible, "n_candidates": len(candidates),
                                                 "ajustement": spec.get("ajustement", "bh")}, res["methode"],
                          None, [res["avertissement"]] + res["avertissements"])


EXECUTEURS = {"tri": _tri, "croise": _croise, "multiples": _multiples, "correlation": _correlation,
              "regression": _regression, "acm": _acm, "acp": _acp, "afdm": _afdm, "afc": _afc, "cah": _cah,
              "exploration": _exploration}


def empreinte(projet, spec: dict) -> str:
    brut = json.dumps([projet.cle_donnees(), projet.etat["populations"], spec], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(brut.encode()).hexdigest()[:16]


def contexte_execute(projet, spec: dict) -> tuple[Contexte, dict, dict]:
    """Recalcule une analyse et renvoie aussi son contexte (données préparées) — utilisé par les exports."""
    if spec.get("type") not in EXECUTEURS:
        raise ErreurAnalyse(f"Type d'analyse inconnu : {spec.get('type')}")
    ctx = Contexte(projet, spec)
    resultat, fiche = EXECUTEURS[spec["type"]](ctx)
    return ctx, resultat, fiche


def executer(projet, spec: dict) -> dict:
    """Calcule une analyse (ou la retrouve en cache) et renvoie {type, resultat, fiche, empreinte}."""
    type_ = spec.get("type")
    if type_ not in EXECUTEURS:
        raise ErreurAnalyse(f"Type d'analyse inconnu : {type_}")
    projet.table()          # garantit que le cache correspond à l'état courant
    cle = empreinte(projet, spec)
    if cle in projet.cache_resultats:
        return projet.cache_resultats[cle]
    try:
        ctx = Contexte(projet, spec)
        resultat, fiche = EXECUTEURS[type_](ctx)
    except KeyError as e:
        raise ErreurAnalyse(str(e).strip("'\"")) from e
    except ValueError as e:
        if isinstance(e, ErreurAnalyse):
            raise
        raise ErreurAnalyse(str(e)) from e
    if isinstance(resultat.get("avertissements"), list):
        resultat["avertissements"] = [ctx.humaniser(a) for a in resultat["avertissements"]]
    sortie = univarie.nettoyer({"type": type_, "resultat": resultat, "fiche": fiche, "empreinte": cle})
    if len(projet.cache_resultats) > 60:
        projet.cache_resultats.pop(next(iter(projet.cache_resultats)))
    projet.cache_resultats[cle] = sortie
    return sortie
