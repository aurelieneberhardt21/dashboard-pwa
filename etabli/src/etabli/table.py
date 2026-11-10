"""Table de travail : valeurs typées + statut de chaque cellule.

La table est toujours *recalculée* à partir des fichiers sources (jamais modifiés), du dictionnaire
et de la recette de préparation. Chaque cellule porte un statut qui distingue les différentes
raisons pour lesquelles une réponse peut manquer :

  0 VALIDE   réponse exploitable
  1 FILTRE   non concerné : la question n'a pas été présentée (parcours conditionnel)
  2 ABANDON  non atteint : le répondant a quitté le questionnaire avant cette question
  3 NR       non-réponse : la question était posée, le répondant n'a pas répondu
  4 VIDE     cellule vide dont on ne sait pas dire si la question était posée (champ non documenté)
  5 EXCLU    mis en manquant par une étape de préparation (recodage, règle…)
  6 NSP      modalité déclarée « de non-réponse » (refus, ne sait pas) : la valeur est conservée
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .importer import NON, NON_PRESENTE, OUI, _norm

VALIDE, FILTRE, ABANDON, NR, VIDE, EXCLU, NSP = range(7)
STATUTS = {
    VALIDE: ("valide", "Réponse valide"),
    FILTRE: ("filtre", "Non concerné (question non présentée)"),
    ABANDON: ("abandon", "Non atteint (abandon du questionnaire)"),
    NR: ("nr", "Non-réponse"),
    VIDE: ("vide", "Vide (champ de la question non documenté)"),
    EXCLU: ("exclu", "Mis en manquant par la préparation"),
    NSP: ("nsp", "Modalité de non-réponse déclarée"),
}
CODES_STATUT = {v[0]: k for k, v in STATUTS.items()}
TYPES_CATEGORIELS = ("quali", "ordinale", "multi")


def _nombre(v: str) -> float:
    try:
        return float(v.replace(",", ".").replace(" ", ""))
    except (ValueError, AttributeError):
        return np.nan


class Table:
    """Valeurs et statuts de toutes les variables (brutes puis dérivées)."""

    def __init__(self, n: int, index: list[str]):
        self.n = n
        self.index = index
        self.valeurs: dict[str, pd.Series] = {}
        self.statuts: dict[str, np.ndarray] = {}
        self.meta: dict[str, dict] = {}
        self.exclus = np.zeros(n, dtype=bool)          # exclusions globales (étapes « exclure »)
        self.motifs_exclusion: list[dict] = []
        self.complet = np.ones(n, dtype=bool)
        self.source = np.array([""] * n, dtype=object)

    # -- accès ------------------------------------------------------------
    def ajouter(self, meta: dict, valeurs: pd.Series, statuts: np.ndarray) -> None:
        vid = meta["id"]
        self.meta[vid] = meta
        self.valeurs[vid] = valeurs.reset_index(drop=True)
        self.statuts[vid] = np.asarray(statuts, dtype=np.int8)

    def existe(self, vid: str) -> bool:
        return vid in self.valeurs

    def exiger(self, vid: str) -> None:
        if vid not in self.valeurs:
            raise KeyError(f"La variable « {vid} » est introuvable (colonne absente de l'export ou étape désactivée).")

    def etiquettes(self, vid: str) -> dict[str, str]:
        """valeur brute → libellé affiché (unique)."""
        vus: dict[str, int] = {}
        sortie = {}
        for m in self.meta[vid].get("modalites", []):
            lib = (m.get("libelle") or m["valeur"]).strip() or m["valeur"]
            if lib in vus:
                vus[lib] += 1
                lib = f"{lib} ({vus[lib]})"
            else:
                vus[lib] = 1
            sortie[m["valeur"]] = lib
        return sortie

    def serie(self, vid: str, *, nsp: str = "exclure", manquants: str = "exclure",
              etiquettes: bool = True) -> pd.Series:
        """Série prête pour l'analyse.

        nsp       : « exclure » (les modalités de non-réponse déclarées deviennent manquantes) ou « garder ».
        manquants : « exclure » (NaN) ou « modalite » (une modalité par type de non-réponse, variables
                    catégorielles seulement — utile en ACM où l'on peut ensuite les rendre passives).
        """
        self.exiger(vid)
        meta, s, st = self.meta[vid], self.valeurs[vid], self.statuts[vid]
        if meta["type"] in TYPES_CATEGORIELS:
            cats = [m["valeur"] for m in meta.get("modalites", [])]
            if nsp == "exclure":
                cats = [m["valeur"] for m in meta.get("modalites", []) if not m.get("nr")]
            brut = s.astype(object).where(st == VALIDE if nsp == "exclure" else np.isin(st, (VALIDE, NSP)))
            etq = self.etiquettes(vid) if etiquettes else {c: c for c in cats}
            noms = [etq.get(c, c) for c in cats]
            brut = brut.map(lambda v: etq.get(v, v) if isinstance(v, str) else v)
            if manquants == "modalite":
                masque_nr = np.isin(st, (NR, VIDE, EXCLU)) | ((st == NSP) & (nsp == "exclure"))
                if masque_nr.any():
                    brut = brut.where(~masque_nr, "Non-réponse")
                    noms = noms + ["Non-réponse"]
            return pd.Series(pd.Categorical(brut, categories=noms, ordered=bool(meta.get("ordonnee"))), name=vid)
        if meta["type"] == "quanti":
            return pd.Series(pd.to_numeric(s, errors="coerce").where(st == VALIDE), name=vid, dtype=float)
        return pd.Series(s.where(st == VALIDE), name=vid)

    def masque_base(self) -> np.ndarray:
        return ~self.exclus


# ----------------------------------------------------------------------------
# Conditions (filtres, champs des questions, populations, règles)
# ----------------------------------------------------------------------------

OPERATEURS_NUM = {">=": np.greater_equal, ">": np.greater, "<=": np.less_equal, "<": np.less, "=": np.equal}


def evaluer(condition: dict | None, table: Table) -> np.ndarray:
    """Évalue une condition sur la table → vecteur booléen. ``None`` ou {"tous": true} = tout le monde."""
    if not condition or condition.get("tous"):
        return np.ones(table.n, dtype=bool)
    if "regles" in condition:
        parties = [evaluer(r, table) for r in condition["regles"]] or [np.ones(table.n, dtype=bool)]
        res = np.logical_or.reduce(parties) if condition.get("op") == "ou" else np.logical_and.reduce(parties)
        return ~res if condition.get("non") else res
    vid, test = condition["var"], condition.get("test", "dans")
    table.exiger(vid)
    s, st = table.valeurs[vid], table.statuts[vid]
    present = np.isin(st, (VALIDE, NSP))
    if test == "dans":
        return present & s.astype(object).isin(condition.get("valeurs", [])).to_numpy()
    if test == "hors":
        return present & ~s.astype(object).isin(condition.get("valeurs", [])).to_numpy()
    if test == "renseigne":
        return st == VALIDE
    if test == "manquant":
        return st != VALIDE
    if test == "statut":
        return np.isin(st, [CODES_STATUT[c] for c in condition.get("valeurs", [])])
    num = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
    if test == "entre":
        a, b = condition["valeurs"]
        return present & (num >= float(a)) & (num <= float(b))
    if test in OPERATEURS_NUM:
        with np.errstate(invalid="ignore"):
            return present & OPERATEURS_NUM[test](num, float(condition["valeur"]))
    raise ValueError(f"Test inconnu dans une condition : {test}")


def variables_condition(condition: dict | None) -> set[str]:
    if not condition or condition.get("tous"):
        return set()
    if "regles" in condition:
        return set().union(*[variables_condition(r) for r in condition["regles"]]) if condition["regles"] else set()
    return {condition["var"]}


def decrire(condition: dict | None, meta: dict[str, dict]) -> str:
    """Phrase lisible décrivant une condition."""
    if not condition or condition.get("tous"):
        return "tous les répondants"
    if "regles" in condition:
        liant = " OU " if condition.get("op") == "ou" else " ET "
        parties = [decrire(r, meta) for r in condition["regles"]]
        parties = [f"({p})" if ("regles" in r and len(r["regles"]) > 1) else p
                   for p, r in zip(parties, condition["regles"])]
        txt = liant.join(parties) or "tous les répondants"
        return f"NON ({txt})" if condition.get("non") else txt
    m = meta.get(condition["var"], {})
    nom = m.get("nom") if m.get("nom") and m.get("nom") != m.get("id") else None
    nom = nom or _court(m.get("libelle", condition["var"]) + (f" [{m['sous_libelle']}]" if m.get("sous_libelle") else ""))
    etq = {x["valeur"]: (x.get("libelle") or x["valeur"]) for x in m.get("modalites", [])}
    test = condition.get("test", "dans")
    vals = " ; ".join(f"« {_court(etq.get(v, str(v)), 60)} »" for v in condition.get("valeurs", []))
    if test == "dans":
        return f"{nom} = {vals}"
    if test == "hors":
        return f"{nom} ≠ {vals}"
    if test == "renseigne":
        return f"{nom} est renseigné"
    if test == "manquant":
        return f"{nom} est manquant"
    if test == "statut":
        return f"{nom} a le statut {', '.join(STATUTS[CODES_STATUT[c]][1].lower() for c in condition.get('valeurs', []))}"
    if test == "entre":
        return f"{nom} entre {condition['valeurs'][0]} et {condition['valeurs'][1]}"
    return f"{nom} {test} {condition.get('valeur')}"


def _court(texte: str, n: int = 70) -> str:
    texte = re.sub(r"\s+", " ", texte or "").strip()
    return texte if len(texte) <= n else texte[: n - 1].rstrip() + "…"


# ----------------------------------------------------------------------------
# Construction à partir des sources
# ----------------------------------------------------------------------------

def construire_table(sources: list[tuple[str, pd.DataFrame]], variables: dict[str, dict],
                     questions: dict[str, dict]) -> Table:
    """Assemble la table de travail à partir des tableaux bruts (un par source, empilés)."""
    tailles = [len(t) for _, t in sources]
    n = sum(tailles)
    debuts = np.cumsum([0] + tailles)
    index: list[str] = []
    table = Table(n, index)
    par_source: dict[str | None, list[dict]] = {}
    for v in variables.values():
        if not v.get("absente"):
            par_source.setdefault(v.get("source") or None, []).append(v)

    brut: dict[str, np.ndarray] = {}        # valeurs brutes (chaînes), '' hors de la source
    na_export: dict[str, np.ndarray] = {}
    rang: dict[str, int] = {}
    dernier = np.full(n, -1, dtype=int)
    table.complet[:] = True
    for k, (alias, t) in enumerate(sources):
        a, b = debuts[k], debuts[k + 1]
        table.source[a:b] = alias or ""
        vars_src = sorted(par_source.get(alias or None, []), key=lambda v: v["colonne"])
        ident = next((v for v in vars_src if v.get("para") == "id"), None)
        ids = t[ident["colonne"]].tolist() if ident is not None else [str(i + 1) for i in range(len(t))]
        index.extend([f"{alias}:{i}" if alias and len(sources) > 1 else str(i) for i in ids])
        soumis = next((v for v in vars_src if v.get("para") == "date_soumission"), None)
        if soumis is not None:
            table.complet[a:b] = (t[soumis["colonne"]] != "").to_numpy()
        for pos, v in enumerate(vars_src):
            col = t[v["colonne"]].to_numpy(dtype=object)
            plein = np.full(n, "", dtype=object)
            plein[a:b] = col
            norm = pd.Series(col).map(_norm)
            est_na = np.zeros(n, dtype=bool)
            est_na[a:b] = norm.isin(NON_PRESENTE).to_numpy()
            if v["type"] == "multi":
                canon = norm.map(lambda x: "Oui" if x in OUI else ("Non" if x in NON else ""))
                plein[a:b] = canon.to_numpy(dtype=object)
            else:
                plein[est_na] = ""
            brut[v["id"]], na_export[v["id"]], rang[v["id"]] = plein, est_na, pos
            if v["role"] == "analyse":
                substantiel = np.zeros(n, dtype=bool)
                substantiel[a:b] = (plein[a:b] != "")
                dernier = np.where(substantiel, np.maximum(dernier, pos), dernier)

    # Règle LimeSurvey : dans une question à choix multiples, un « N/A » sur un item alors qu'un autre item
    # de la même question est renseigné signifie « non coché » (cas des options exclusives du type « Aucun »).
    for q in questions.values():
        if q["genre"] != "multiple":
            continue
        items = [v for v in q["variables"] if v in brut and variables[v]["type"] == "multi"]
        if not items:
            continue
        presentee = np.logical_or.reduce([brut[v] != "" for v in items])
        for v in items:
            a_corriger = presentee & (brut[v] == "")
            brut[v] = np.where(a_corriger, "Non", brut[v])
            na_export[v] = na_export[v] & ~presentee

    # 1re passe : valeurs ; statut provisoire (valide / vide)
    for v in variables.values():
        vid = v["id"]
        if vid not in brut:
            continue
        col = pd.Series(brut[vid], dtype=object)
        rempli = (col != "").to_numpy()
        if v["type"] in TYPES_CATEGORIELS:
            connues = {m["valeur"] for m in v.get("modalites", [])}
            valeurs = col.where(rempli)
            inconnues = sorted(set(valeurs.dropna().unique()) - connues)
            if inconnues:   # modalités apparues depuis l'import (nouvel export)
                v.setdefault("modalites", []).extend({"valeur": x, "nouvelle": True} for x in inconnues)
        elif v["type"] == "quanti":
            valeurs = col.map(_nombre).astype(float)
            rempli = rempli & ~np.isnan(valeurs.to_numpy())
        else:
            valeurs = col.where(rempli)
        table.ajouter(v, valeurs, np.where(rempli, VALIDE, VIDE))

    # 2e passe : statut des cellules vides
    for v in variables.values():
        vid = v["id"]
        if vid not in brut:
            continue
        st = table.statuts[vid].copy()
        vide = st == VIDE
        if v["role"] != "analyse":
            table.statuts[vid] = np.where(vide, NR, st).astype(np.int8)
            continue
        champ = v.get("champ")
        dans_champ = None
        if champ and not champ.get("tous"):
            try:
                dans_champ = evaluer(champ, table)
            except KeyError:
                dans_champ = None
        abandon = (~table.complet) & (rang[vid] > dernier)
        nouveau = np.full(n, VIDE, dtype=np.int8)
        if champ:
            nouveau[:] = NR
        nouveau[na_export[vid]] = FILTRE
        nouveau[abandon] = ABANDON
        if dans_champ is not None:
            nouveau[~dans_champ] = FILTRE
        # hors de sa source, une variable est « non concernée » par construction
        if len(sources) > 1:
            nouveau[table.source != (v.get("source") or "")] = FILTRE
        st = np.where(vide, nouveau, st)
        # modalités de non-réponse déclarées
        nr_mods = [m["valeur"] for m in v.get("modalites", []) if m.get("nr")]
        if nr_mods:
            st = np.where((st == VALIDE) & table.valeurs[vid].isin(nr_mods).to_numpy(), NSP, st)
        table.statuts[vid] = st.astype(np.int8)
    table.rang = rang
    table.dernier = dernier
    return table


def decompte_statuts(table: Table, vid: str, masque: np.ndarray | None = None) -> dict[str, int]:
    st = table.statuts[vid]
    if masque is not None:
        st = st[masque]
    comptes = np.bincount(st, minlength=len(STATUTS))
    return {STATUTS[k][0]: int(comptes[k]) for k in STATUTS}


# ----------------------------------------------------------------------------
# Propositions de « champ » (à qui la question a-t-elle été posée ?)
# ----------------------------------------------------------------------------

def proposer_champs(table: Table, variables: dict[str, dict], questions: dict[str, dict]) -> list[dict]:
    """Pour chaque question au champ non documenté, cherche ce qui explique le mieux qui a répondu.
    Ce sont des *propositions* : rien n'est appliqué sans validation.

    Méthode : parmi les répondants ayant atteint la question (hors abandons), on compare « a répondu » aux
    modalités de chaque variable catégorielle placée avant dans le questionnaire. Pour une variable P, on
    retient l'ensemble S de ses modalités dont au moins la moitié des porteurs ont répondu, et on mesure
      - le rappel    : part des réponses observées qui viennent de S (exigé ≥ 97 %) ;
      - la précision : part des porteurs de S qui ont répondu (exigée ≥ 80 %).
    On préfère une règle *sélective* (S ne contient pas toutes les modalités de P) et, à qualité égale, la
    variable la plus en amont (la cause plutôt qu'une question voisine posée aux mêmes personnes).
    À défaut, on essaie la conjonction de deux règles ; à défaut encore, on reprend le champ de la question
    antérieure à laquelle répondent exactement les mêmes personnes.
    """
    propositions: list[dict] = []
    base = table.masque_base()
    predicteurs = []
    for v in variables.values():
        if v["id"] in table.valeurs and v["role"] == "analyse" and v["type"] in TYPES_CATEGORIELS \
                and 1 <= len(v.get("modalites", [])) <= 15:
            cats = [m["valeur"] for m in v["modalites"]]
            present = np.isin(table.statuts[v["id"]], (VALIDE, NSP))
            codes = pd.Categorical(table.valeurs[v["id"]].astype(object).where(present), categories=cats).codes
            predicteurs.append((v, cats, codes.astype(int)))
    champs_resolus: dict[str, dict | None] = {}     # champ proposé ou documenté, par question

    for q in questions.values():
        if q["genre"] == "technique" or q.get("precision_de"):
            continue
        membres = [variables[v] for v in q["variables"] if v in table.valeurs and variables[v]["role"] == "analyse"
                   and variables[v]["type"] != "vide"]
        coeur = [v for v in membres if v["type"] != "texte"] or membres
        if not coeur:
            continue
        if all(v.get("champ") for v in coeur):
            champs_resolus[q["id"]] = coeur[0]["champ"]
            continue
        repondu = np.logical_or.reduce([np.isin(table.statuts[v["id"]], (VALIDE, NSP)) for v in coeur])
        atteint = base & np.logical_or.reduce([table.statuts[v["id"]] != ABANDON for v in coeur])
        repondu = repondu & atteint
        n_att, n_rep = int(atteint.sum()), int(repondu.sum())
        if n_att == 0 or n_rep == 0:
            continue
        ids = [v["id"] for v in membres]
        prop = {"question": q["id"], "variables": ids, "n_repondants": n_rep, "n_atteints": n_att,
                "connu_par_export": q["genre"] == "multiple"}
        if n_rep / n_att >= 0.9:
            champs_resolus[q["id"]] = {"tous": True}
            propositions.append({**prop, "champ": {"tous": True}, "precision": n_rep / n_att, "rappel": 1.0,
                                 "explication": f"{n_rep} des {n_att} répondants ayant atteint la question y ont répondu."})
            continue
        rang_q = min(table.rang[v["id"]] for v in coeur)
        candidats = []          # (precision, rappel, selectif, rang, variable, S, masque)
        larges = []             # variante « large » de S (modalités compatibles avec une réponse) pour les conjonctions
        purs = []               # modalités dont presque tous les porteurs ont répondu, pour les unions
        for p, cats, codes in predicteurs:
            if (p.get("source") or None) != (coeur[0].get("source") or None) or table.rang[p["id"]] >= rang_q \
                    or p["question"] == q["id"]:
                continue
            k = len(cats)
            ok = atteint & (codes >= 0)
            tot = np.bincount(codes[ok], minlength=k)
            oui = np.bincount(codes[ok & repondu], minlength=k)
            taux_mod = oui / np.maximum(tot, 1)
            n_obs = int((tot > 0).sum())
            for seuil, cible in ((0.5, candidats), (0.1, larges), (0.8, purs)):
                S_idx = np.flatnonzero((tot > 0) & (taux_mod >= seuil))
                if len(S_idx) == 0 or (cible is not candidats and len(S_idx) == n_obs):
                    continue
                rappel = oui[S_idx].sum() / n_rep
                if (cible is purs and oui[S_idx].sum() < 3) or (cible is not purs and rappel < 0.97):
                    continue
                cible.append((float(oui[S_idx].sum() / tot[S_idx].sum()), float(rappel), len(S_idx) < n_obs,
                              table.rang[p["id"]], p, [cats[i] for i in S_idx], atteint & np.isin(codes, S_idx)))
        bons = [c for c in candidats if c[0] >= 0.8]
        selectifs = [c for c in bons if c[2]]
        regle = lambda c: {"var": c[4]["id"], "test": "dans", "valeurs": c[5]}
        champ, precision, rappel, mode = None, None, None, None
        if selectifs:
            # qualité par tranches de 5 points, puis la variable la plus en amont
            c = max(selectifs, key=lambda c: (int(c[0] * c[1] * 20), -c[3]))
            champ, precision, rappel, mode = regle(c), c[0], c[1], "regle"
        if champ is None:
            # conjonction de deux règles (ex. « DES commencé après 2022 » ET « phase ≠ socle »)
            sel = sorted(larges, key=lambda c: -c[0])[:12]
            meilleur = None
            for i in range(len(sel)):
                for j in range(i + 1, len(sel)):
                    if sel[i][4]["id"] == sel[j][4]["id"]:
                        continue
                    m = sel[i][6] & sel[j][6]
                    if m.sum() == 0:
                        continue
                    pr, ra = (m & repondu).sum() / m.sum(), (m & repondu).sum() / n_rep
                    if pr >= 0.9 and ra >= 0.97 and (meilleur is None or pr * ra > meilleur[0] + 1e-9):
                        meilleur = (pr * ra, pr, ra, sel[i], sel[j])
            if meilleur:
                _, precision, rappel, c1, c2 = meilleur
                precision, rappel, mode = float(precision), float(rappel), "regle"
                champ = {"op": "et", "regles": [regle(c1), regle(c2)]}
        if champ is None and purs:
            # union de règles (ex. orientation déclarée dans l'une OU l'autre de deux questions parallèles)
            couvert = np.zeros(table.n, dtype=bool)
            choisis = []
            while len(choisis) < 4:
                gain = lambda c: int((c[6] & repondu & ~couvert).sum())
                reste = [c for c in purs if gain(c) >= 2 and c[4]["id"] not in [x[4]["id"] for x in choisis]]
                if not reste:
                    break
                c = max(reste, key=lambda c: (gain(c), c[0]))
                choisis.append(c)
                couvert |= c[6]
                if (couvert & repondu).sum() / n_rep >= 0.97:
                    break
            if len(choisis) >= 2 and couvert.sum():
                pr, ra = (couvert & repondu).sum() / couvert.sum(), (couvert & repondu).sum() / n_rep
                if pr >= 0.9 and ra >= 0.97:
                    champ = {"op": "ou", "regles": [regle(c) for c in sorted(choisis, key=lambda c: c[3])]}
                    precision, rappel, mode = float(pr), float(ra), "regle"
        if champ is None and bons:
            # mêmes répondants qu'une question antérieure : on reprend son champ
            c = max(bons, key=lambda c: (round(c[0] * c[1], 2), c[3]))
            herite = champs_resolus.get(c[4]["question"])
            if herite and not herite.get("tous"):
                champ, precision, rappel, mode = herite, c[0], c[1], "herite"
        champs_resolus[q["id"]] = champ
        if champ:
            n_S = int((evaluer(champ, table) & atteint).sum())
            explication = (f"{round(100 * rappel)} % des {n_rep} réponses viennent des {n_S} répondants pour qui "
                           f"{decrire(champ, table.meta)} ; {round(100 * precision)} % d'entre eux ont répondu.")
            if mode == "herite":
                explication += " (Champ repris d'une question antérieure à laquelle répondent les mêmes personnes.)"
            propositions.append({**prop, "champ": champ, "precision": precision, "rappel": rappel,
                                 "explication": explication})
        else:
            propositions.append({**prop, "champ": None, "precision": None, "rappel": None,
                                 "explication": (f"{n_rep} des {n_att} répondants ayant atteint la question y ont répondu, "
                                                 "sans qu'une ou deux variables antérieures l'expliquent : champ à "
                                                 "documenter à la main (ou non-réponse élevée).")})
    return propositions
