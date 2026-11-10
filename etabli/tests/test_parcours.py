"""Tests fonctionnels de bout en bout sur l'export FICTIF : import → dictionnaire → recette → analyses → exports."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    os.environ["ETABLI_DOSSIER"] = str(tmp_path_factory.mktemp("etabli"))
    from etabli import server
    server._projets.clear()
    return TestClient(server.app)


@pytest.fixture(scope="module")
def pid(client):
    r = client.post("/api/projets/demo")
    assert r.status_code == 200, r.text
    return r.json()["id"]


def var(etat, debut, sous=None):
    """Identifiant de la variable dont le libellé commence par ``debut`` (et l'item par ``sous``)."""
    for v in etat["variables"].values():
        if v["libelle"].startswith(debut) and (sous is None or (v.get("sous_libelle") or "").startswith(sous)):
            return v["id"]
    raise AssertionError(f"variable introuvable : {debut} {sous}")


def test_import_et_dictionnaire(client, pid):
    e = client.get(f"/api/p/{pid}").json()
    assert e["projet"]["fictif"] is True
    assert e["n_total"] == 420 and 0 < e["n_complets"] < 420
    types = {v["type"] for v in e["variables"].values()}
    assert {"quali", "ordinale", "multi", "quanti", "texte"} <= types
    genres = {q["genre"] for q in e["questions"].values()}
    assert {"simple", "multiple", "matrice", "technique"} <= genres
    # la colonne de courriels est repérée comme sensible, et son contenu n'est jamais renvoyé
    contact = var(e, "Si vous acceptez")
    assert e["variables"][contact]["role"] == "sensible"
    f = client.get(f"/api/p/{pid}/variable/{contact}").json()
    assert f["textes"]["masque"] and f["textes"]["reponses"] == []
    # échelle reconnue et ordonnée ; refus déclaré comme modalité de non-réponse
    freq = e["variables"][var(e, "À quelle fréquence lisez-vous", "Romans")]
    assert freq["type"] == "ordinale" and [m["valeur"] for m in freq["modalites"]][0] == "Jamais"
    rec = e["variables"][var(e, "Diriez-vous")]
    assert any(m.get("nr") for m in rec["modalites"])


def test_non_reponses_et_champs(client, pid):
    e = client.get(f"/api/p/{pid}").json()
    props = client.get(f"/api/p/{pid}/champs/propositions").json()["propositions"]
    annee = var(e, "En quelle année")
    prop = next(p for p in props if annee in p["variables"])
    situation = var(e, "Quelle est votre situation")
    assert prop["champ"]["var"] == situation and len(prop["champ"]["valeurs"]) == 1
    # avant validation : cellules « vides » ; après : « non concerné » / « non-réponse »
    avant = client.get(f"/api/p/{pid}/variable/{annee}").json()["statuts"]
    assert avant["vide"] > 0 and avant["filtre"] == 0 and avant["abandon"] > 0
    modifs = [{"id": v, "champ": p["champ"]} for p in props if p["champ"] for v in p["variables"]]
    r = client.patch(f"/api/p/{pid}/variables", json={"description": "Champs acceptés", "modifications": modifs})
    assert r.status_code == 200, r.text
    apres = client.get(f"/api/p/{pid}/variable/{annee}").json()["statuts"]
    assert apres["vide"] == 0 and apres["filtre"] > 0
    assert sum(apres.values()) == sum(avant.values())
    # option exclusive « Aucune » : les autres items passent de N/A à « Non » (question présentée)
    accueil = client.get(f"/api/p/{pid}/variable/{var(e, 'Quelles tâches', 'Accueil')}").json()
    aucune = client.get(f"/api/p/{pid}/variable/{var(e, 'Quelles tâches', 'Aucune')}").json()
    assert accueil["statuts"]["valide"] == aucune["statuts"]["valide"]


def test_recette_population_analyses_exports(client, pid):
    e = client.get(f"/api/p/{pid}").json()
    situation, age, genre = var(e, "Quelle est votre situation"), var(e, "Quel âge"), var(e, "Quel est votre genre")
    livres, dipl = var(e, "Combien de livres"), var(e, "Quel est le diplôme")
    genres = [v["id"] for v in e["variables"].values() if v["libelle"].startswith("À quelle fréquence lisez-vous")]
    # recodage (aperçu puis enregistrement)
    params = {"source": age, "correspondance": {"Moins de 25 ans": "Moins de 35 ans", "25-34 ans": "Moins de 35 ans",
                                                "35-44 ans": "35-54 ans", "45-54 ans": "35-54 ans"},
              "ordonnee": True, "cible": {"nom": "age3", "libelle": "Âge en trois classes"}}
    ap = client.post(f"/api/p/{pid}/recette/apercu", json={"type": "recoder", "params": params}).json()
    assert {m["valeur"] for m in ap["modalites"]} == {"Moins de 35 ans", "35-54 ans", "55 ans ou plus"}
    assert sum(sum(l) for l in ap["controle"]["effectifs"]) > 0
    r = client.post(f"/api/p/{pid}/recette", json={"type": "recoder", "params": params, "note": "Effectifs trop faibles aux extrêmes"})
    age3 = r.json()["etape"]["params"]["cible"]["id"]
    assert age3 in r.json()["etat"]["variables"]
    # score, découpage, exclusion
    r = client.post(f"/api/p/{pid}/recette", json={"type": "score", "params": {
        "sources": genres, "mode": "moyenne", "points": {"Jamais": 0, "Rarement": 1, "Parfois": 2, "Souvent": 3, "Très souvent": 4},
        "cible": {"nom": "intensite_lecture", "libelle": "Intensité de lecture (0-4)"}}})
    score = r.json()["etape"]["params"]["cible"]["id"]
    assert r.json()["etat"]["variables"][score]["type"] == "quanti"
    r = client.post(f"/api/p/{pid}/recette", json={"type": "exclure", "params": {
        "si": {"var": situation, "test": "manquant"}, "motif": "Aucune réponse au-delà de la première page"}})
    etat = r.json()["etat"]
    assert etat["n_base"] < etat["n_total"]
    # population
    en_poste = e["variables"][situation]["modalites"]
    valeur = next(m["valeur"] for m in en_poste if "poste" in m["valeur"])
    r = client.post(f"/api/p/{pid}/populations", json={"nom": "En poste", "condition": {"var": situation, "test": "dans", "valeurs": [valeur]}})
    pop = r.json()["etat"]["populations"][0]
    assert 0 < pop["n"] < etat["n_base"]
    # analyses
    specs = [
        {"type": "tri", "variable": age3},
        {"type": "croise", "ligne": genre, "colonne": age3},
        {"type": "croise", "ligne": livres, "colonne": genre},
        {"type": "multiples", "variables": [v["id"] for v in e["variables"].values() if v["libelle"].startswith("Par quels moyens")], "groupe": genre},
        {"type": "correlation", "variables": [livres, score] + genres[:2]},
        {"type": "regression", "y": livres, "x": [genre, age3, dipl]},
        {"type": "regression", "y": genre, "x": [age3, livres], "modalite_cible": "Femme"},
        {"type": "acm", "actives": genres, "sup_quali": [genre, age3, situation], "sup_quanti": [livres]},
        {"type": "acp", "actives": [livres, score], "sup_quali": [genre]},
        {"type": "afc", "ligne": dipl, "colonne": genres[1]},
        {"type": "afdm", "actives": genres[:3] + [livres]},
        {"type": "cah", "base": {"type": "acm", "actives": genres, "sup_quali": [genre]}, "n_axes_cah": 3},
        {"type": "exploration", "cible": genres[1], "candidates": [genre, age3, dipl, livres, situation]},
    ]
    for spec in specs:
        r = client.post(f"/api/p/{pid}/calcul", json=spec)
        assert r.status_code == 200, (spec["type"], r.text)
        f = r.json()["fiche"]
        assert f["fictif"] is True and f["donnees"]["n_analyses"] > 0 and f["methode"]
        # export reproductible : script R + données analysées
        z = client.post(f"/api/p/{pid}/export/reproduction", json={"spec": spec, "titre": "essai"})
        assert z.status_code == 200, (spec["type"], z.text)
        noms = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
        assert {"analyse.R", "donnees.csv", "fiche_de_calcul.json"} <= set(noms)
    # ACM : inertie et modalités passives (non-réponses) → ACM spécifique
    acm = client.post(f"/api/p/{pid}/calcul", json=specs[7]).json()
    assert acm["resultat"]["methode"] in ("acm", "acm_specifique")
    assert abs(sum(a["pct"] for a in acm["resultat"]["axes"]) - 100) < 1e-6
    # la même analyse restreinte à une population donne un autre effectif, tracé dans la fiche
    acm_pop = client.post(f"/api/p/{pid}/calcul", json={**specs[7], "population": pop["id"]}).json()
    assert acm_pop["fiche"]["donnees"]["n_population"] == pop["n"]
    # enregistrement, classes comme variable, journal, Excel, données
    r = client.post(f"/api/p/{pid}/analyses", json={"titre": "Typologie des lectures", "spec": specs[11], "notes": "Hypothèse fictive."})
    aid = r.json()["analyse"]["id"]
    r = client.post(f"/api/p/{pid}/recette", json={"type": "partition", "params": {"analyse": aid, "cible": {"nom": "classe_lecture", "libelle": "Classes de lecture"}}})
    classe = r.json()["etape"]["params"]["cible"]["id"]
    assert r.json()["etat"]["variables"][classe]["n_valide"] > 0
    assert client.delete(f"/api/p/{pid}/analyses/{aid}").status_code == 422      # protégée : alimente la recette
    journal = client.get(f"/api/p/{pid}/export/journal").text
    assert "DONNÉES FICTIVES" in journal and "Typologie des lectures" in journal and "Âge en trois classes" in journal
    x = client.post(f"/api/p/{pid}/export/xlsx", json={"tableaux": [{"titre": "T1", "entetes": ["a", "b"], "lignes": [["x", 1.5]], "notes": ["n"]}]})
    assert x.status_code == 200 and x.content[:2] == b"PK"
    csv = client.get(f"/api/p/{pid}/export/donnees").text
    assert "exemple.invalid" not in csv            # la variable sensible n'est jamais exportée


def test_historique_annuler_retablir_restaurer(client, pid):
    e = client.get(f"/api/p/{pid}").json()
    n_etapes = len(e["recette"])
    j = client.post(f"/api/p/{pid}/jalons", json={"nom": "Avant essai"}).json()["jalon"]
    genre = var(e, "Quel est votre genre")
    client.post(f"/api/p/{pid}/recette", json={"type": "recoder", "params": {"source": genre, "correspondance": {"Non-binaire ou autre": None}, "cible": {"nom": "genre2"}}})
    assert len(client.get(f"/api/p/{pid}").json()["recette"]) == n_etapes + 1
    r = client.post(f"/api/p/{pid}/annuler").json()
    assert len(r["etat"]["recette"]) == n_etapes and r["etat"]["historique"]["peut_retablir"]
    r = client.post(f"/api/p/{pid}/retablir").json()
    assert len(r["etat"]["recette"]) == n_etapes + 1
    r = client.post(f"/api/p/{pid}/restaurer/{j['n']}").json()
    assert len(r["etat"]["recette"]) == n_etapes
    h = client.get(f"/api/p/{pid}/historique").json()
    assert h["entrees"][-1]["description"].startswith("Restauration") and h["jalons"][0]["nom"] == "Avant essai"


def test_reimport_conserve_le_travail(client, pid, tmp_path):
    """Un nouvel export (plus de réponses) : les annotations, la recette et les identifiants sont conservés."""
    from etabli import demo
    avant = client.get(f"/api/p/{pid}").json()
    chemin = demo.ecrire_export(tmp_path / "nouvel_export.csv", n=460)
    with open(chemin, "rb") as f:
        r = client.post(f"/api/p/{pid}/sources", files={"fichier": ("nouvel_export.csv", f, "text/csv")}, data={"alias": ""})
    assert r.status_code == 200, r.text
    apres = r.json()["etat"]
    assert apres["n_total"] == 460
    assert set(avant["variables"]) == set(apres["variables"])
    assert [x["id"] for x in avant["recette"]] == [x["id"] for x in apres["recette"]]
    assert all(x["rapport"]["ok"] for x in apres["recette"])
    annee = var(apres, "En quelle année")
    assert apres["variables"][annee]["champ"]          # champ documenté conservé
    assert r.json()["rapport"]["reimport"]["colonnes_disparues"] == []
