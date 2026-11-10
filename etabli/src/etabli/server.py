"""Serveur local d'Établi. N'écoute que sur 127.0.0.1 : rien ne sort de la machine."""
from __future__ import annotations

import copy
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import analyses, demo, export
from .projet import Projet, dossier_travail
from .recette import TYPES_ETAPES, appliquer_recette, sorties_etape, sources_etape
from .stats import univarie
from .table import (STATUTS, TYPES_CATEGORIELS, VALIDE, NSP, construire_table, decompte_statuts, decrire, evaluer,
                    proposer_champs)

WEB = Path(__file__).parent / "web"
app = FastAPI(title="Établi", docs_url=None, redoc_url=None)
_projets: dict[str, Projet] = {}


def P(pid: str) -> Projet:
    if pid not in _projets:
        dossier = dossier_travail() / pid
        if not (dossier / "projet.json").exists():
            raise HTTPException(404, "Projet introuvable.")
        p = Projet(dossier)
        p.partitions = lambda etape, table, p=p: analyses.partition_analyse(p, etape, table)
        _projets[pid] = p
    return _projets[pid]


@app.exception_handler(analyses.ErreurAnalyse)
async def _erreur_analyse(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=422)


@app.exception_handler(ValueError)
async def _erreur_valeur(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=422)


@app.exception_handler(KeyError)
async def _erreur_cle(_, exc):
    return JSONResponse({"detail": str(exc).strip("'\"")}, status_code=422)


# ---------------------------------------------------------------- projets

@app.get("/api/projets")
def lister_projets():
    return {"projets": Projet.lister(), "dossier": str(dossier_travail())}


def _televerser(fichier: UploadFile) -> Path:
    suffixe = Path(fichier.filename or "export.csv").suffix or ".csv"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffixe)
    shutil.copyfileobj(fichier.file, tmp)
    tmp.close()
    return Path(tmp.name)


@app.post("/api/projets")
def creer_projet(nom: str = Form(...), fichier: UploadFile = File(...)):
    tmp = _televerser(fichier)
    try:
        p = Projet.creer(nom.strip() or "Projet", tmp, nom_fichier=fichier.filename)
    finally:
        tmp.unlink(missing_ok=True)
    return {"id": p.etat["id"]}


@app.post("/api/projets/demo")
def creer_demo():
    with tempfile.TemporaryDirectory() as d:
        chemin = demo.ecrire_export(Path(d) / "export_fictif_limesurvey.csv")
        p = Projet.creer("Démonstration (données fictives)", chemin, fictif=True)
    return {"id": p.etat["id"]}


@app.delete("/api/projets/{pid}")
def supprimer_projet(pid: str):
    P(pid)
    corbeille = dossier_travail() / ".corbeille"
    corbeille.mkdir(exist_ok=True)
    shutil.move(str(dossier_travail() / pid), str(corbeille / f"{pid}-{datetime.now():%Y%m%d-%H%M%S}"))
    _projets.pop(pid, None)
    return {"ok": True, "corbeille": str(corbeille)}


# ---------------------------------------------------------------- état

def _etat(p: Projet) -> dict:
    e = p.etat
    table = p.table()
    base = table.masque_base()
    variables = {}
    for vid, m in table.meta.items():
        v = {k: val for k, val in m.items() if not k.startswith("_")}
        st = table.statuts[vid][base]
        v["n_valide"] = int(np.isin(st, (VALIDE, NSP)).sum())
        if m.get("champ") and not m["champ"].get("tous"):
            v["champ_texte"] = decrire(m["champ"], table.meta)
        variables[vid] = v
    for vid, m in e["variables"].items():      # colonnes absentes du dernier export
        if vid not in variables:
            variables[vid] = {**m, "n_valide": 0}
    rapports = {r["id"]: r for r in p.rapports_recette()}
    recette = []
    for et in e["recette"]:
        recette.append({**et, "rapport": rapports.get(et["id"]), "sources": sorted(sources_etape(et)),
                        "sorties": sorties_etape(et), "type_libelle": TYPES_ETAPES.get(et["type"], et["type"])})
    populations = []
    for pop in e["populations"]:
        try:
            n = int((base & evaluer(pop["condition"], table)).sum())
            populations.append({**pop, "n": n, "description": decrire(pop["condition"], table.meta)})
        except KeyError as ex:
            populations.append({**pop, "n": None, "description": "", "erreur": str(ex).strip("'\"")})
    h = p.historique()
    return {
        "projet": {"id": e["id"], "nom": e["nom"], "fictif": e.get("fictif", False), "cree": e["cree"],
                   "modifie": e["modifie"], "version": e.get("version"), "dossier": str(p.dossier)},
        "sources": e["sources"], "n_total": table.n, "n_base": int(base.sum()), "n_complets": int((table.complet & base).sum()),
        "exclusions": table.motifs_exclusion,
        "variables": variables, "questions": e["questions"], "sections": e.get("sections", []),
        "recette": recette, "populations": populations, "analyses": e["analyses"], "carnet": e.get("carnet", []),
        "historique": {"peut_annuler": h["peut_annuler"], "peut_retablir": h["peut_retablir"], "version": h["version"]},
        "statuts": {v[0]: v[1] for v in STATUTS.values()},
        "types_analyses": analyses.TYPES_ANALYSES, "types_etapes": TYPES_ETAPES,
    }


@app.get("/api/p/{pid}")
def etat(pid: str):
    return univarie.nettoyer(_etat(P(pid)))


def _ok(p: Projet, **extra):
    return univarie.nettoyer({"etat": _etat(p), **extra})


@app.patch("/api/p/{pid}")
def renommer(pid: str, corps: dict = Body(...)):
    p = P(pid)
    p.modifier(f"Projet renommé « {corps['nom']} »", lambda e: e.update(nom=corps["nom"]))
    return _ok(p)


# ---------------------------------------------------------------- dictionnaire

CHAMPS_VARIABLE = {"nom", "libelle", "sous_libelle", "type", "role", "ordonnee", "champ", "modalites", "note"}


@app.patch("/api/p/{pid}/variables")
def modifier_variables(pid: str, corps: dict = Body(...)):
    """corps : {description, modifications: [{id, ...champs}]} — modifie des variables brutes."""
    p = P(pid)
    modifs = corps.get("modifications", [])

    def f(e):
        for m in modifs:
            v = e["variables"].get(m["id"])
            if v is None:
                raise ValueError(f"« {m['id']} » est une variable dérivée : modifiez l'étape de préparation qui la crée.")
            for k, val in m.items():
                if k in CHAMPS_VARIABLE:
                    v[k] = val
            if "ordonnee" in m and v["type"] in ("quali", "ordinale"):
                v["type"] = "ordinale" if m["ordonnee"] else "quali"
            if m.get("type") in ("quali", "ordinale"):
                v["ordonnee"] = m["type"] == "ordinale"
                if not v.get("modalites"):
                    v["modalites"] = _modalites_observees(p, v)
            for mod in v.get("modalites", []):
                mod.pop("nouvelle", None) if "modalites" in m else None
    p.modifier(corps.get("description") or f"Dictionnaire : {len(modifs)} variable(s) modifiée(s)", f, categorie="dictionnaire")
    return _ok(p)


def _modalites_observees(p: Projet, v: dict) -> list[dict]:
    src = next(s for s in p.etat["sources"] if (s["alias"] or None) == (v.get("source") or None))
    col = p._brut(src)[v["colonne"]]
    comptes = col[col != ""].value_counts()
    return [{"valeur": k} for k in comptes.index[:200]]


@app.get("/api/p/{pid}/variable/{vid}")
def fiche_variable(pid: str, vid: str, population: str | None = None):
    p = P(pid)
    ctx = analyses.Contexte(p, {"population": population, "nsp": "garder"})
    if vid not in ctx.meta:
        raise HTTPException(404, "Variable introuvable.")
    m = ctx.meta[vid]
    s = ctx.serie(vid)[ctx.masque]
    sortie: dict = {"id": vid, "statuts": decompte_statuts(ctx.table, vid, ctx.masque), "n_population": int(ctx.masque.sum()),
                    "dependants": p.dependants(vid)}
    if m["type"] in TYPES_CATEGORIELS:
        comptes = s.value_counts(sort=False)
        etq = ctx.table.etiquettes(vid)
        sortie["modalites"] = [{"valeur": mod["valeur"], "libelle": etq[mod["valeur"]], "nr": bool(mod.get("nr")),
                                "nouvelle": bool(mod.get("nouvelle")), "n": int(comptes.get(etq[mod["valeur"]], 0))}
                               for mod in m.get("modalites", [])]
    elif m["type"] == "quanti":
        sortie["resume"] = univarie.resume_quanti(s) if s.notna().any() else None
    else:
        vc = s.dropna().value_counts()
        masquer = m.get("role") == "sensible"
        sortie["textes"] = {"n": int(s.notna().sum()), "n_distinctes": int(len(vc)), "masque": masquer,
                            "reponses": [] if masquer else [{"texte": k, "n": int(c)} for k, c in vc.head(300).items()]}
    if m.get("derive"):
        et = next((x for x in p.etat["recette"] if x["id"] == m["derive"]), None)
        sortie["etape"] = et
    return univarie.nettoyer(sortie)


@app.get("/api/p/{pid}/champs/propositions")
def propositions_champs(pid: str):
    p = P(pid)
    table = p.table()
    props = proposer_champs(table, p.etat["variables"], p.etat["questions"])
    for pr in props:
        pr["champ_texte"] = decrire(pr["champ"], table.meta) if pr["champ"] else None
    return univarie.nettoyer({"propositions": props})


# ---------------------------------------------------------------- recette

def _nouvelle_etape(p: Projet, e: dict, corps: dict) -> dict:
    etape = {"id": p.nouvel_id(e, "e"), "type": corps["type"], "params": corps.get("params", {}),
             "note": corps.get("note", ""), "actif": True, "cree": datetime.now().isoformat(timespec="seconds")}
    if corps["type"] != "exclure":
        cible = etape["params"].setdefault("cible", {})
        cible["id"] = p.nouvel_id(e, "d")
        cible.setdefault("nom", cible["id"])
        cible.setdefault("libelle", cible["nom"])
    return etape


@app.post("/api/p/{pid}/recette")
def ajouter_etape(pid: str, corps: dict = Body(...)):
    p = P(pid)
    if corps.get("type") not in TYPES_ETAPES:
        raise HTTPException(422, "Type d'étape inconnu.")
    cree = {}

    def f(e):
        etape = _nouvelle_etape(p, e, corps)
        e["recette"].append(etape)
        cree.update(etape)
    cible = corps.get("params", {}).get("cible", {})
    p.modifier(f"Préparation : {TYPES_ETAPES[corps['type']].lower()}" + (f" « {cible.get('nom')} »" if cible.get("nom") else ""),
               f, categorie="recette")
    return _ok(p, etape=cree)


@app.put("/api/p/{pid}/recette/{eid}")
def modifier_etape(pid: str, eid: str, corps: dict = Body(...)):
    p = P(pid)

    def f(e):
        et = next((x for x in e["recette"] if x["id"] == eid), None)
        if et is None:
            raise ValueError("Étape introuvable.")
        if "params" in corps:
            ancien_cible = et["params"].get("cible", {})
            et["params"] = corps["params"]
            if ancien_cible:
                et["params"].setdefault("cible", {})
                et["params"]["cible"]["id"] = ancien_cible["id"]
                et["params"]["cible"].setdefault("nom", ancien_cible.get("nom"))
                et["params"]["cible"].setdefault("libelle", ancien_cible.get("libelle"))
        for k in ("note", "actif"):
            if k in corps:
                et[k] = corps[k]
    p.modifier(corps.get("description") or "Préparation : étape modifiée", f, categorie="recette")
    return _ok(p)


@app.delete("/api/p/{pid}/recette/{eid}")
def supprimer_etape(pid: str, eid: str):
    p = P(pid)
    p.modifier("Préparation : étape supprimée", lambda e: e.update(recette=[x for x in e["recette"] if x["id"] != eid]),
               categorie="recette")
    return _ok(p)


@app.post("/api/p/{pid}/recette/ordre")
def ordonner_etapes(pid: str, corps: dict = Body(...)):
    p = P(pid)
    ordre = corps["ordre"]
    p.modifier("Préparation : ordre des étapes modifié",
               lambda e: e.update(recette=sorted(e["recette"], key=lambda x: ordre.index(x["id"]) if x["id"] in ordre else 1e9)),
               categorie="recette")
    return _ok(p)


@app.post("/api/p/{pid}/recette/apercu")
def apercu_etape(pid: str, corps: dict = Body(...)):
    """Applique une étape (nouvelle ou modifiée) sans rien enregistrer et montre ce qu'elle produirait."""
    p = P(pid)
    e = copy.deepcopy(p.etat)
    eid = corps.get("id")
    if eid:
        et = copy.deepcopy(next(x for x in e["recette"] if x["id"] == eid))
        cible_id = et["params"].get("cible", {}).get("id")
        et["params"] = corps.get("params", et["params"])
        if cible_id:
            et["params"].setdefault("cible", {})["id"] = cible_id
        e["recette"] = [et if x["id"] == eid else x for x in e["recette"]]
    else:
        et = {"id": "apercu", "type": corps["type"], "params": copy.deepcopy(corps.get("params", {})), "actif": True}
        if et["type"] != "exclure":
            et["params"].setdefault("cible", {})["id"] = "_apercu"
        e["recette"].append(et)
    table = construire_table([(s["alias"], p._brut(s)) for s in e["sources"]], copy.deepcopy(e["variables"]), e["questions"])
    avant_exclus = None
    rapports = []
    for x in e["recette"]:
        if x["id"] == et["id"]:
            avant_exclus = int(table.exclus.sum())
        rapports += appliquer_recette(table, [x], p.partitions)
    rapport = next(r for r in rapports if r["id"] == et["id"])
    sortie: dict = {"rapport": rapport}
    base = table.masque_base()
    if et["type"] == "exclure":
        sortie["n_exclus"] = int(table.exclus.sum()) - (avant_exclus or 0)
        sortie["n_restants"] = int(base.sum())
    for vid in sorties_etape(et):
        if not table.existe(vid):
            continue
        m = table.meta[vid]
        s = table.serie(vid, nsp="garder")[base]
        sortie["statuts"] = decompte_statuts(table, vid, base)
        sortie["type"] = m["type"]
        if m["type"] in TYPES_CATEGORIELS:
            vc = s.value_counts(sort=False)
            sortie["modalites"] = [{"valeur": k, "n": int(c)} for k, c in vc.items()]
            srcs = [x for x in sources_etape(et) if table.existe(x) and table.meta[x]["type"] in TYPES_CATEGORIELS]
            if len(srcs) == 1 and et["type"] in ("recoder", "decouper"):
                src = table.serie(srcs[0], nsp="garder")[base]
                croise = pd.crosstab(src, s, dropna=False)
                sortie["controle"] = {"source": srcs[0], "lignes": [str(i) for i in croise.index],
                                      "colonnes": [str(c) for c in croise.columns], "effectifs": croise.to_numpy().tolist()}
        elif m["type"] == "quanti" and s.notna().any():
            sortie["resume"] = univarie.resume_quanti(s)
    return univarie.nettoyer(sortie)


# ---------------------------------------------------------------- populations

@app.post("/api/p/{pid}/populations/apercu")
def apercu_population(pid: str, corps: dict = Body(...)):
    p = P(pid)
    table = p.table()
    m = table.masque_base() & evaluer(corps.get("condition"), table)
    return {"n": int(m.sum()), "n_base": int(table.masque_base().sum()), "description": decrire(corps.get("condition"), table.meta)}


@app.post("/api/p/{pid}/populations")
def ajouter_population(pid: str, corps: dict = Body(...)):
    p = P(pid)
    evaluer(corps["condition"], p.table())

    def f(e):
        e["populations"].append({"id": p.nouvel_id(e, "p"), "nom": corps["nom"], "condition": corps["condition"],
                                 "note": corps.get("note", "")})
    p.modifier(f"Population « {corps['nom']} » créée", f, categorie="population")
    return _ok(p)


@app.put("/api/p/{pid}/populations/{popid}")
def modifier_population(pid: str, popid: str, corps: dict = Body(...)):
    p = P(pid)
    if "condition" in corps:
        evaluer(corps["condition"], p.table())

    def f(e):
        pop = next(x for x in e["populations"] if x["id"] == popid)
        pop.update({k: corps[k] for k in ("nom", "condition", "note") if k in corps})
    p.modifier(f"Population « {corps.get('nom', popid)} » modifiée", f, categorie="population")
    return _ok(p)


@app.delete("/api/p/{pid}/populations/{popid}")
def supprimer_population(pid: str, popid: str):
    p = P(pid)
    p.modifier("Population supprimée", lambda e: e.update(populations=[x for x in e["populations"] if x["id"] != popid]),
               categorie="population")
    return _ok(p)


# ---------------------------------------------------------------- analyses

@app.post("/api/p/{pid}/calcul")
def calculer(pid: str, spec: dict = Body(...)):
    return analyses.executer(P(pid), spec)


@app.post("/api/p/{pid}/analyses")
def enregistrer_analyse(pid: str, corps: dict = Body(...)):
    p = P(pid)
    cree = {}

    def f(e):
        a = {"id": p.nouvel_id(e, "a"), "titre": corps.get("titre") or analyses.TYPES_ANALYSES.get(corps["spec"]["type"]),
             "spec": corps["spec"], "notes": corps.get("notes", ""), "cree": datetime.now().isoformat(timespec="seconds"),
             "modifie": datetime.now().isoformat(timespec="seconds"), "dossier": corps.get("dossier", "")}
        e["analyses"].append(a)
        cree.update(a)
    p.modifier(f"Analyse « {corps.get('titre') or corps['spec']['type']} » enregistrée", f, categorie="analyse")
    return _ok(p, analyse=cree)


@app.put("/api/p/{pid}/analyses/{aid}")
def modifier_analyse(pid: str, aid: str, corps: dict = Body(...)):
    p = P(pid)

    def f(e):
        a = next(x for x in e["analyses"] if x["id"] == aid)
        a.update({k: corps[k] for k in ("titre", "spec", "notes", "dossier") if k in corps})
        a["modifie"] = datetime.now().isoformat(timespec="seconds")
    p.modifier(f"Analyse « {corps.get('titre', aid)} » mise à jour", f, categorie="analyse")
    return _ok(p)


@app.delete("/api/p/{pid}/analyses/{aid}")
def supprimer_analyse(pid: str, aid: str):
    p = P(pid)
    liees = [et["id"] for et in p.etat["recette"] if et["type"] == "partition" and et["params"].get("analyse") == aid]
    if liees:
        raise HTTPException(422, "Cette classification alimente une variable de la recette : supprimez d'abord l'étape correspondante.")
    p.modifier("Analyse supprimée", lambda e: e.update(analyses=[x for x in e["analyses"] if x["id"] != aid]), categorie="analyse")
    return _ok(p)


@app.get("/api/p/{pid}/valeurs")
def valeurs(pid: str, variable: str):
    """Valeurs d'une variable pour tous les individus (coloration des nuages d'individus)."""
    p = P(pid)
    ctx = analyses.Contexte(p, {})
    if variable not in ctx.meta or ctx.meta[variable].get("role") == "sensible" or ctx.meta[variable]["type"] == "texte":
        raise HTTPException(422, "Variable non disponible pour l'affichage.")
    s = ctx.serie(variable)
    vals = [None if pd.isna(v) else (float(v) if ctx.meta[variable]["type"] == "quanti" else str(v)) for v in s]
    return {"ids": list(ctx.table.index), "valeurs": vals, "type": ctx.meta[variable]["type"],
            "modalites": list(s.cat.categories) if hasattr(s, "cat") else None}


@app.get("/api/p/{pid}/donnees")
def donnees(pid: str, variables: str, population: str | None = None, debut: int = 0, n: int = 100):
    p = P(pid)
    ctx = analyses.Contexte(p, {"population": population, "nsp": "garder"})
    vids = [v for v in variables.split(",") if v in ctx.meta][:40]
    idx = np.flatnonzero(ctx.masque)[debut:debut + n]
    lignes = []
    for i in idx:
        ligne = {"id": ctx.table.index[i]}
        for v in vids:
            m = ctx.meta[v]
            st = int(ctx.table.statuts[v][i])
            val = ctx.table.valeurs[v].iloc[i]
            if m.get("role") == "sensible":
                val = "•••" if st == VALIDE else None
            ligne[v] = {"v": None if pd.isna(val) else (float(val) if m["type"] == "quanti" else str(val)), "s": STATUTS[st][0]}
        lignes.append(ligne)
    return univarie.nettoyer({"lignes": lignes, "total": int(ctx.masque.sum())})


# ---------------------------------------------------------------- historique, carnet

@app.get("/api/p/{pid}/historique")
def historique(pid: str):
    return P(pid).historique()


@app.post("/api/p/{pid}/annuler")
def annuler(pid: str):
    p = P(pid)
    return _ok(p, annule=p.annuler())


@app.post("/api/p/{pid}/retablir")
def retablir(pid: str):
    p = P(pid)
    return _ok(p, retabli=p.retablir())


@app.post("/api/p/{pid}/jalons")
def jalon(pid: str, corps: dict = Body(...)):
    p = P(pid)
    return {"jalon": p.poser_jalon(corps["nom"], corps.get("note", "")), "historique": p.historique()}


@app.post("/api/p/{pid}/restaurer/{n}")
def restaurer(pid: str, n: int):
    p = P(pid)
    p.restaurer(n)
    return _ok(p)


@app.put("/api/p/{pid}/carnet")
def carnet(pid: str, corps: dict = Body(...)):
    p = P(pid)
    p.modifier("Carnet de recherche mis à jour", lambda e: e.update(carnet=corps["carnet"]), categorie="carnet")
    return _ok(p)


@app.put("/api/p/{pid}/sections")
def sections(pid: str, corps: dict = Body(...)):
    p = P(pid)
    p.modifier("Sections du questionnaire modifiées", lambda e: e.update(sections=corps["sections"]), categorie="dictionnaire")
    return _ok(p)


@app.post("/api/p/{pid}/sources")
def reimporter(pid: str, fichier: UploadFile = File(...), alias: str = Form("")):
    p = P(pid)
    tmp = _televerser(fichier)
    try:
        rapport = p.importer_source(tmp, alias=alias, nom_fichier=fichier.filename)
    finally:
        tmp.unlink(missing_ok=True)
    return _ok(p, rapport=rapport)


# ---------------------------------------------------------------- exports

@app.post("/api/p/{pid}/export/xlsx")
def export_xlsx(pid: str, corps: dict = Body(...)):
    p = P(pid)
    contenu = export.classeur_excel(corps.get("tableaux", []), fictif=p.etat.get("fictif", False))
    return Response(contenu, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="tableaux.xlsx"'})


@app.post("/api/p/{pid}/export/reproduction")
def export_reproduction(pid: str, corps: dict = Body(...)):
    contenu = export.archive_reproduction(P(pid), corps["spec"], corps.get("titre", ""))
    return Response(contenu, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="reproduction.zip"'})


@app.post("/api/p/{pid}/export/script")
def export_script(pid: str, corps: dict = Body(...)):
    script, _ = export.script_r(P(pid), corps["spec"], corps.get("titre", ""))
    return {"script": script}


@app.get("/api/p/{pid}/export/journal")
def export_journal(pid: str):
    return Response(export.journal_markdown(P(pid)), media_type="text/markdown; charset=utf-8")


@app.get("/api/p/{pid}/export/donnees")
def export_donnees(pid: str, variables: str = "", population: str | None = None):
    p = P(pid)
    meta = p.table().meta
    vids = [v for v in variables.split(",") if v in meta] or [v for v, m in meta.items() if m.get("role") == "analyse"]
    return Response(export.donnees_csv(p, vids, population), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="donnees_preparees.csv"'})


# ---------------------------------------------------------------- interface

@app.middleware("http")
async def _sans_cache(request, call_next):
    reponse = await call_next(request)
    if not request.url.path.startswith("/api"):
        reponse.headers["Cache-Control"] = "no-cache"
    return reponse


@app.get("/")
def accueil():
    return FileResponse(WEB / "index.html")


app.mount("/", StaticFiles(directory=WEB), name="web")
