"""Projet Établi : un dossier sur le disque qui contient tout le travail.

    <dossier du projet>/
        projet.json            état courant (dictionnaire, recette, populations, analyses, carnet…)
        sources/<alias>/…      copies des fichiers importés — jamais modifiées
        historique/index.jsonl une ligne par modification (date, description, version parente)
        historique/000042.json.gz   instantané complet de l'état après la modification n° 42
        historique/jalons.json versions nommées par l'utilisateur

Rien n'est jamais effacé de l'historique : « annuler » déplace simplement le pointeur de version, et
toute modification crée un nouvel instantané. Le projet ne contient aucune donnée dérivée : la table de
travail est recalculée à partir des sources et de la recette.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path

from . import importer
from .recette import appliquer_recette, sorties_etape, sources_etape
from .table import Table, construire_table, variables_condition

FORMAT = 1


def dossier_travail() -> Path:
    d = Path(os.environ.get("ETABLI_DOSSIER") or Path.home() / "Etabli")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _slug(nom: str) -> str:
    t = unicodedata.normalize("NFKD", nom)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:50] or "projet"


def _empreinte(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


class Projet:
    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)
        self.etat: dict = json.loads((self.dossier / "projet.json").read_text(encoding="utf-8"))
        self._table: Table | None = None
        self._cle_table: str | None = None
        self._rapports: list[dict] = []
        self._bruts: dict[str, tuple] = {}
        self.cache_resultats: dict[str, dict] = {}
        self.partitions = None      # crochet fourni par le module d'analyses (étapes « partition »)

    # -- création / liste --------------------------------------------------
    @staticmethod
    def lister() -> list[dict]:
        projets = []
        for f in sorted(dossier_travail().glob("*/projet.json")):
            try:
                e = json.loads(f.read_text(encoding="utf-8"))
                projets.append({"id": f.parent.name, "nom": e["nom"], "fictif": e.get("fictif", False),
                                "modifie": e.get("modifie"), "cree": e.get("cree"),
                                "n_variables": len(e.get("variables", {})), "n_analyses": len(e.get("analyses", [])),
                                "sources": [{"fichier": s["fichier"], "n_lignes": s["n_lignes"]} for s in e.get("sources", [])]})
            except (json.JSONDecodeError, KeyError, OSError):
                continue
        return sorted(projets, key=lambda p: p.get("modifie") or "", reverse=True)

    @staticmethod
    def creer(nom: str, fichier: Path, *, nom_fichier: str | None = None, fictif: bool = False) -> "Projet":
        base, k = _slug(nom), 2
        ident = base
        while (dossier_travail() / ident).exists():
            ident, k = f"{base}-{k}", k + 1
        dossier = dossier_travail() / ident
        (dossier / "historique").mkdir(parents=True)
        etat = {"format": FORMAT, "id": ident, "nom": nom, "fictif": fictif, "cree": _maintenant(),
                "modifie": _maintenant(), "version": 0, "sources": [], "variables": {}, "questions": {},
                "sections": [], "recette": [], "populations": [], "analyses": [], "carnet": [],
                "compteurs": {}}
        (dossier / "projet.json").write_text(json.dumps(etat, ensure_ascii=False), encoding="utf-8")
        projet = Projet(dossier)
        try:
            projet.importer_source(fichier, alias="", nom_fichier=nom_fichier)
        except Exception:
            shutil.rmtree(dossier, ignore_errors=True)
            raise
        return projet

    # -- persistance et historique -----------------------------------------
    def _index(self) -> list[dict]:
        f = self.dossier / "historique" / "index.jsonl"
        if not f.exists():
            return []
        return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]

    def _instantane(self, n: int) -> dict:
        with gzip.open(self.dossier / "historique" / f"{n:06d}.json.gz", "rt", encoding="utf-8") as f:
            return json.load(f)

    def _ecrire_etat(self) -> None:
        tmp = self.dossier / "projet.json.tmp"
        tmp.write_text(json.dumps(self.etat, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.dossier / "projet.json")

    def modifier(self, description: str, fonction, *, categorie: str = "autre"):
        """Applique ``fonction(etat)`` puis enregistre un nouvel instantané décrit par ``description``."""
        avant = copy.deepcopy(self.etat)
        try:
            retour = fonction(self.etat)
        except Exception:
            self.etat = avant
            raise
        index = self._index()
        n = (index[-1]["n"] if index else 0) + 1
        parent = self.etat.get("version", 0)
        self.etat["version"] = n
        self.etat["modifie"] = _maintenant()
        with gzip.open(self.dossier / "historique" / f"{n:06d}.json.gz", "wt", encoding="utf-8") as f:
            json.dump(self.etat, f, ensure_ascii=False)
        with open(self.dossier / "historique" / "index.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"n": n, "parent": parent, "date": self.etat["modifie"], "description": description,
                                "categorie": categorie}, ensure_ascii=False) + "\n")
        self._ecrire_etat()
        return retour

    def historique(self) -> dict:
        index = self._index()
        courant = self.etat.get("version", 0)
        par_n = {e["n"]: e for e in index}
        parent = par_n.get(courant, {}).get("parent")
        enfants = [e["n"] for e in index if e["parent"] == courant]
        jalons = self._jalons()
        return {"version": courant, "entrees": index[-400:], "peut_annuler": bool(parent),
                "peut_retablir": bool(enfants), "jalons": jalons}

    def _aller_a(self, n: int) -> None:
        self.etat = self._instantane(n)
        self.etat["version"] = n
        self._ecrire_etat()

    def annuler(self) -> str | None:
        par_n = {e["n"]: e for e in self._index()}
        entree = par_n.get(self.etat.get("version", 0))
        if not entree or not entree["parent"]:
            return None
        self._aller_a(entree["parent"])
        return entree["description"]

    def retablir(self) -> str | None:
        enfants = [e for e in self._index() if e["parent"] == self.etat.get("version", 0)]
        if not enfants:
            return None
        self._aller_a(enfants[-1]["n"])
        return enfants[-1]["description"]

    def _jalons(self) -> list[dict]:
        f = self.dossier / "historique" / "jalons.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []

    def poser_jalon(self, nom: str, note: str = "") -> dict:
        jalons = self._jalons()
        j = {"n": self.etat.get("version", 0), "nom": nom, "note": note, "date": _maintenant()}
        jalons.append(j)
        (self.dossier / "historique" / "jalons.json").write_text(json.dumps(jalons, ensure_ascii=False), encoding="utf-8")
        return j

    def restaurer(self, n: int) -> None:
        """Revient à l'état de la version ``n`` en créant une nouvelle entrée d'historique (donc annulable)."""
        ancien = self._instantane(n)
        entree = next((e for e in self._index() if e["n"] == n), {})
        jalon = next((j for j in self._jalons() if j["n"] == n), None)
        nom = f"« {jalon['nom']} »" if jalon else f"n° {n} ({entree.get('date', '')[:16].replace('T', ' ')})"

        def f(etat):
            for cle in list(etat):
                if cle not in ("version",):
                    etat.pop(cle)
            etat.update({k: v for k, v in ancien.items() if k != "version"})
        self.modifier(f"Restauration de la version {nom}", f, categorie="version")

    def nouvel_id(self, etat: dict, prefixe: str) -> str:
        c = etat.setdefault("compteurs", {})
        c[prefixe] = c.get(prefixe, 0) + 1
        return f"{prefixe}{c[prefixe]:03d}"

    # -- sources -------------------------------------------------------------
    def importer_source(self, fichier: Path, *, alias: str = "", nom_fichier: str | None = None) -> dict:
        """Importe (ou ré-importe) un export. Les identifiants des colonnes déjà connues sont conservés,
        ainsi que toutes les annotations (libellés, types, ordre des modalités, champs)."""
        fichier = Path(fichier)
        nom_fichier = nom_fichier or fichier.name
        tableau, infos = importer.lire_tableau(fichier)
        existante = next((s for s in self.etat["sources"] if s["alias"] == alias), None)
        horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest_dir = self.dossier / "sources" / (alias or "principal")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{horodatage}_{re.sub(r'[^A-Za-z0-9._-]+', '_', nom_fichier)}"
        shutil.copy2(fichier, dest)
        anciennes = importer.cles_anciennes(self.etat["variables"], alias) if existante else None
        dico = importer.construire_dictionnaire(tableau, infos["entetes"], alias=alias, anciennes=anciennes)
        rapport = {"style_entetes": dico["style"], "decisions": dico["decisions"],
                   "lecture": {k: v for k, v in infos.items() if k != "entetes"}}

        def f(etat):
            if existante:
                rapport["reimport"] = self._fusionner_dictionnaire(etat, dico, alias)
            else:
                etat["variables"].update(dico["variables"])
                etat["questions"].update(dico["questions"])
            src = {"alias": alias, "fichier": nom_fichier, "chemin": str(dest.relative_to(self.dossier)),
                   "sha256": importer.sha256_fichier(dest), "importe": _maintenant(), "n_lignes": infos["n_lignes"],
                   "n_colonnes": infos["n_colonnes"], "rapport": rapport}
            if existante:
                src["precedents"] = existante.get("precedents", []) + [
                    {k: existante[k] for k in ("fichier", "chemin", "sha256", "importe", "n_lignes")}]
                etat["sources"] = [src if s["alias"] == alias else s for s in etat["sources"]]
            else:
                etat["sources"].append(src)

        self.modifier(("Nouvel export pour la source" if existante else "Import de") + f" « {nom_fichier} »", f,
                      categorie="source")
        return rapport

    @staticmethod
    def _fusionner_dictionnaire(etat: dict, dico: dict, alias: str) -> dict:
        anciens = {vid: v for vid, v in etat["variables"].items() if (v.get("source") or "") == alias}
        nouvelles, modalites_nouvelles = [], []
        for vid, nv in dico["variables"].items():
            av = anciens.get(vid)
            if av is None:
                etat["variables"][vid] = nv
                nouvelles.append(vid)
                continue
            av.update(colonne=nv["colonne"], n_brut=nv["n_brut"], na_export=nv["na_export"])
            av.pop("absente", None)
            connues = {m["valeur"] for m in av.get("modalites", [])}
            for m in nv.get("modalites", []):
                if m["valeur"] not in connues and av["type"] in ("quali", "ordinale"):
                    av["modalites"].append({**m, "nouvelle": True})
                    modalites_nouvelles.append({"variable": vid, "modalite": m["valeur"]})
        disparues = [vid for vid in anciens if vid not in dico["variables"]]
        for vid in disparues:
            etat["variables"][vid]["absente"] = True
        # questions : on garde l'identifiant de l'ancienne question quand sa première variable est retrouvée
        ancienne_q = {v["id"]: v["question"] for v in anciens.values()}
        for q in [q for q in etat["questions"].values() if (q.get("source") or "") == alias]:
            etat["questions"].pop(q["id"])
        pris = set(etat["questions"])
        renommage = {}
        for qid, q in dico["questions"].items():
            cible = ancienne_q.get(q["variables"][0])
            if cible is None or cible in pris:
                cible, k = qid, 2
                while cible in pris:
                    cible, k = f"{qid}_{k}", k + 1
            pris.add(cible)
            renommage[qid] = cible
        for qid, q in dico["questions"].items():
            q = {**q, "id": renommage[qid]}
            if q.get("precision_de"):
                q["precision_de"] = renommage.get(q["precision_de"], q["precision_de"])
            etat["questions"][q["id"]] = q
            for vid in q["variables"]:
                etat["variables"][vid]["question"] = q["id"]
                if q.get("precision_de"):
                    etat["variables"][vid]["precision_de"] = q["precision_de"]
        return {"nouvelles_colonnes": nouvelles, "colonnes_disparues": disparues,
                "modalites_nouvelles": modalites_nouvelles}

    def _brut(self, src: dict):
        chemin = self.dossier / src["chemin"]
        cle = (src["chemin"], src["sha256"])
        if self._bruts.get(src["alias"], (None,))[0] != cle:
            self._bruts[src["alias"]] = (cle, importer.lire_tableau(chemin)[0])
        return self._bruts[src["alias"]][1]

    # -- table de travail ------------------------------------------------------
    def cle_donnees(self) -> str:
        e = self.etat
        analyses_liees = [a for a in e["analyses"] if any(
            et["type"] == "partition" and et["params"].get("analyse") == a["id"] for et in e["recette"])]
        return _empreinte([[(s["alias"], s["sha256"]) for s in e["sources"]], e["variables"], e["questions"],
                           e["recette"], analyses_liees])

    def table(self) -> Table:
        cle = self.cle_donnees()
        if self._table is None or cle != self._cle_table:
            variables = copy.deepcopy(self.etat["variables"])
            table = construire_table([(s["alias"], self._brut(s)) for s in self.etat["sources"]], variables,
                                     self.etat["questions"])
            self._rapports = appliquer_recette(table, self.etat["recette"], self.partitions)
            self._table, self._cle_table = table, cle
            self.cache_resultats.clear()
        return self._table

    def rapports_recette(self) -> list[dict]:
        self.table()
        return self._rapports

    def dictionnaire(self) -> dict[str, dict]:
        """Toutes les variables (brutes + dérivées) telles que la table les connaît."""
        return self.table().meta

    def dependants(self, vid: str) -> dict:
        """Où une variable est-elle utilisée ? (étapes, populations, analyses, champs)"""
        e = self.etat
        return {
            "etapes": [et["id"] for et in e["recette"] if vid in sources_etape(et)],
            "populations": [p["id"] for p in e["populations"] if vid in variables_condition(p.get("condition"))],
            "analyses": [a["id"] for a in e["analyses"] if vid in json.dumps(a.get("spec", {}))],
            "champs": [v["id"] for v in e["variables"].values() if vid in variables_condition(v.get("champ"))],
        }

    def variables_etape(self, etape_id: str) -> list[str]:
        et = next((x for x in self.etat["recette"] if x["id"] == etape_id), None)
        return sorties_etape(et) if et else []
