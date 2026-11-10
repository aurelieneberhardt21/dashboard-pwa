"""Import d'exports de questionnaires (LimeSurvey en priorité, CSV/Excel génériques sinon).

Principe : l'import ne modifie jamais le fichier source. Il produit
  1. un tableau brut de chaînes de caractères (une ligne par réponse, '' = cellule vide) ;
  2. un *dictionnaire* décrivant chaque colonne (question, sous-question, type, modalités…) ;
  3. un *rapport d'import* listant toutes les décisions prises automatiquement,
     pour que chacune puisse être relue et corrigée dans l'interface.

Les trois styles d'en-têtes de LimeSurvey sont reconnus :
  - « codes »        : ``Q5`` / ``Q5[SQ001]`` / ``Q5[other]``
  - « code + texte » : ``Q5[SQ001]. Texte de la question [Sous-question]``
  - « texte complet »: ``Texte de la question [Sous-question]`` (pas de code : on en fabrique)
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd

# ----------------------------------------------------------------------------
# Lecture brute
# ----------------------------------------------------------------------------

ENCODAGES = ("utf-8-sig", "utf-16", "cp1252", "latin-1")


def sha256_fichier(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _decoder(octets: bytes) -> tuple[str, str]:
    for enc in ENCODAGES:
        try:
            return octets.decode(enc), enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return octets.decode("utf-8", errors="replace"), "utf-8 (caractères invalides remplacés)"


def _detecter_separateur(texte: str) -> str:
    """Choisit le séparateur qui donne le plus de colonnes avec un nombre de champs constant."""
    echantillon = texte[:400_000]
    meilleur, score_max = ",", -1.0
    for sep in (",", ";", "\t", "|"):
        try:
            lignes = []
            for i, ligne in enumerate(csv.reader(io.StringIO(echantillon), delimiter=sep)):
                lignes.append(len(ligne))
                if i >= 60:
                    break
        except csv.Error:
            continue
        if len(lignes) < 2 or lignes[0] < 2:
            continue
        # la dernière ligne de l'échantillon peut être tronquée : on l'ignore
        corps = lignes[:-1] if len(lignes) > 2 else lignes
        constance = sum(1 for n in corps if n == lignes[0]) / len(corps)
        score = constance * lignes[0]
        if score > score_max:
            meilleur, score_max = sep, score
    return meilleur


def lire_tableau(chemin: Path) -> tuple[pd.DataFrame, dict]:
    """Lit un CSV ou un classeur Excel et renvoie (tableau de chaînes, informations de lecture).

    Les colonnes du tableau sont numérotées 0..p-1 ; les en-têtes d'origine sont dans
    ``infos["entetes"]`` (ils peuvent être dupliqués, ce qui est fréquent avec LimeSurvey).
    """
    chemin = Path(chemin)
    suffixe = chemin.suffix.lower()
    infos: dict = {"fichier": chemin.name, "format": suffixe.lstrip(".")}
    if suffixe in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook

        classeur = load_workbook(chemin, read_only=True, data_only=True)
        feuille = classeur.worksheets[0]
        lignes = [["" if c is None else str(c) for c in ligne] for ligne in feuille.iter_rows(values_only=True)]
        infos["feuille"] = feuille.title
        classeur.close()
    else:
        texte, enc = _decoder(chemin.read_bytes())
        sep = "\t" if suffixe in (".tsv", ".tab") else _detecter_separateur(texte)
        lignes = [l for l in csv.reader(io.StringIO(texte), delimiter=sep)]
        infos.update(encodage=enc, separateur={"\t": "tabulation"}.get(sep, sep))
    lignes = [l for l in lignes if any(c.strip() for c in l)]
    if len(lignes) < 2:
        raise ValueError("Le fichier ne contient pas de ligne de données sous la ligne d'en-têtes.")
    entetes = [e.strip() for e in lignes[0]]
    p = len(entetes)
    irregulieres = sum(1 for l in lignes[1:] if len(l) != p)
    corps = [(l + [""] * p)[:p] for l in lignes[1:]]
    tableau = pd.DataFrame(corps, columns=range(p), dtype=object)
    tableau = tableau.map(lambda v: v.strip() if isinstance(v, str) else v)
    infos.update(entetes=entetes, n_lignes=len(corps), n_colonnes=p, lignes_irregulieres=irregulieres)
    return tableau, infos


# ----------------------------------------------------------------------------
# Reconnaissance de la structure du questionnaire
# ----------------------------------------------------------------------------

def _norm(texte: str) -> str:
    """Minuscules sans accents ni ponctuation : sert aux comparaisons tolérantes."""
    t = unicodedata.normalize("NFKD", texte.replace("’", "'"))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", t)).strip()


# Colonnes techniques (« paradonnées ») ajoutées par LimeSurvey, en français et en anglais.
PARADONNEES = {
    "id": "id", "id de la reponse": "id", "response id": "id", "identifiant de la reponse": "id",
    "submitdate": "date_soumission", "date de soumission": "date_soumission", "date submitted": "date_soumission",
    "lastpage": "derniere_page", "derniere page": "derniere_page", "last page": "derniere_page",
    "startlanguage": "langue", "langue de depart": "langue", "start language": "langue",
    "seed": "graine", "tete de serie": "graine",
    "token": "jeton", "code d'acces": "jeton", "access code": "jeton", "invitation": "jeton",
    "startdate": "date_debut", "date de lancement": "date_debut", "date started": "date_debut",
    "datestamp": "date_action", "date de la derniere action": "date_action", "date last action": "date_action",
    "ipaddr": "ip", "adresse ip": "ip", "ip address": "ip",
    "refurl": "url_referente", "url referente": "url_referente", "referrer url": "url_referente",
    "interviewtime": "duree", "temps total": "duree", "total time": "duree",
}
LIBELLES_PARADONNEES = {
    "id": "Identifiant de la réponse", "date_soumission": "Date de soumission", "derniere_page": "Dernière page atteinte",
    "langue": "Langue de passation", "graine": "Graine aléatoire (technique)", "jeton": "Code d'accès (jeton)",
    "date_debut": "Date de début", "date_action": "Date de la dernière action", "ip": "Adresse IP",
    "url_referente": "URL référente", "duree": "Durée de passation",
}
PARADONNEES_SENSIBLES = {"jeton", "ip", "url_referente"}

RE_CODE = re.compile(r"^([A-Za-z][A-Za-z0-9_]{0,40})((?:\[[^\[\]]{1,60}\])*)$")
RE_CODE_TEXTE = re.compile(r"^([A-Za-z][A-Za-z0-9_]{0,40})((?:\[[^\[\]]{1,60}\])*)\.\s+(.+)$", re.S)
RE_CROCHETS_FIN = re.compile(r"^(.*?)\s*((?:\[[^\[\]]*\]\s*)+)$", re.S)
RE_CROCHET = re.compile(r"\[([^\[\]]*)\]")
RE_PRECISION = re.compile(
    r"^(si autre|si oui|merci de preciser|precisez|veuillez preciser|autre[, ]+(merci de )?precise|"
    r"lequel|laquelle|lesquels|lesquelles|if other|please specify|other[, ]+please)", re.I)
RE_TEMPS = re.compile(r"^(grouptime\d+|.*time|temps (du groupe|de la question).*)$", re.I)
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")
RE_TELEPHONE = re.compile(r"(?<!\d)(?:\+?\d[\s.\-]?){10,14}(?!\d)")
RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$|^\d{2}/\d{2}/\d{4}( \d{2}:\d{2}(:\d{2})?)?$")
RE_NOMBRE = re.compile(r"^[+-]?\d+([.,]\d+)?$")

OUI = {"oui", "yes", "y"}
NON = {"non", "no", "n"}
NON_PRESENTE = {"n/a", "na", "n a"}   # LimeSurvey : question non présentée au répondant


def detecter_style(entetes: list[str]) -> str:
    """« codes », « code_texte » ou « texte » selon la forme majoritaire des en-têtes."""
    utiles = [e for e in entetes if _norm(e) not in PARADONNEES and e]
    if not utiles:
        return "texte"
    n_code = sum(1 for e in utiles if RE_CODE.match(e))
    n_code_texte = sum(1 for e in utiles if RE_CODE_TEXTE.match(e))
    if n_code >= 0.8 * len(utiles):
        return "codes"
    if n_code_texte >= 0.8 * len(utiles):
        return "code_texte"
    return "texte"


def _decomposer_entete(entete: str, style: str) -> dict:
    """Sépare code, texte de la question et sous-question(s) entre crochets."""
    code, texte, sous = None, entete, []
    if style == "codes":
        m = RE_CODE.match(entete)
        if m:
            code, sous = m.group(1), RE_CROCHET.findall(m.group(2))
            texte = code
    elif style == "code_texte":
        m = RE_CODE_TEXTE.match(entete)
        if m:
            code = m.group(1)
            codes_sous = RE_CROCHET.findall(m.group(2))
            texte = m.group(3).strip()
            m2 = RE_CROCHETS_FIN.match(texte)
            if m2 and codes_sous:
                texte, sous = m2.group(1).strip(), [s.strip() for s in RE_CROCHET.findall(m2.group(2))]
            elif codes_sous:
                sous = codes_sous
            code = code + "".join(f"_{c}" for c in codes_sous)
            return {"code": code, "texte": texte, "sous": sous, "code_question": m.group(1)}
    else:
        m = RE_CROCHETS_FIN.match(entete)
        if m and m.group(1).strip():
            texte, sous = m.group(1).strip(), [s.strip() for s in RE_CROCHET.findall(m.group(2))]
    if code and sous:
        return {"code": code + "".join(f"_{s}" for s in sous), "texte": texte, "sous": sous, "code_question": code}
    return {"code": code, "texte": texte, "sous": sous, "code_question": code}


def _identifiant_propre(code: str, pris: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", code).strip("_") or "v"
    if base[0].isdigit():
        base = "v" + base
    cand, k = base, 2
    while cand.lower() in pris:
        cand, k = f"{base}_{k}", k + 1
    pris.add(cand.lower())
    return cand


# ----------------------------------------------------------------------------
# Typage des colonnes et ordre des modalités
# ----------------------------------------------------------------------------

# Échelles usuelles, du « moins » vers le « plus ». Une variable dont les modalités
# appartiennent toutes à une même échelle est proposée comme ordinale, dans cet ordre.
ECHELLES = [
    ["jamais", "jamais ou presque", "presque jamais", "tres rarement", "rarement", "parfois", "de temps en temps",
     "occasionnellement", "assez souvent", "regulierement", "souvent", "tres souvent", "presque toujours",
     "toujours ou presque", "toujours"],
    ["jamais", "jamais ou presque", "moins d'une fois par mois", "une a trois fois par mois", "environ une fois par mois",
     "plusieurs fois par mois", "environ une fois par semaine", "une fois par semaine", "plusieurs fois par semaine",
     "tous les jours ou presque", "tous les jours", "plusieurs fois par jour"],
    ["pas du tout d'accord", "pas d'accord", "plutot pas d'accord", "ni d'accord ni pas d'accord",
     "ni en accord ni en desaccord", "plutot d'accord", "d'accord", "tout a fait d'accord"],
    ["tres eloigne", "plutot eloigne", "ni proche ni eloigne", "plutot proche", "tres proche"],
    ["pas du tout", "tres peu", "peu", "un peu", "moyennement", "assez", "plutot", "beaucoup", "enormement", "tout a fait"],
    ["pas du tout important", "peu important", "moyennement important", "assez important", "important", "tres important"],
    ["tres insatisfait", "plutot insatisfait", "insatisfait", "ni satisfait ni insatisfait", "satisfait",
     "plutot satisfait", "tres satisfait"],
    ["tres negativement", "plutot negativement", "negativement", "ni positivement ni negativement",
     "positivement", "plutot positivement", "tres positivement"],
    ["tres mauvais", "mauvais", "plutot mauvais", "moyen", "plutot bon", "bon", "tres bon", "excellent"],
    ["tres faible", "faible", "plutot faible", "moyen", "plutot eleve", "eleve", "tres eleve"],
    ["non", "non pas du tout", "non plutot pas", "oui mais brievement", "oui en partie", "oui occasionnellement",
     "oui plutot", "oui serieusement", "oui principalement", "oui regulierement", "oui tout a fait", "oui"],
    ["never", "rarely", "sometimes", "often", "very often", "always"],
    ["strongly disagree", "disagree", "somewhat disagree", "neither agree nor disagree", "somewhat agree", "agree",
     "strongly agree"],
    ["not at all", "slightly", "a little", "moderately", "somewhat", "quite a bit", "very", "very much", "extremely"],
]
# Modalités « hors échelle » : placées en fin de liste, jamais dans l'ordre.
RE_REFUS = re.compile(r"^(prefere ne pas repondre|ne souhaite pas repondre|je ne souhaite pas repondre|sans reponse|"
                      r"pas de reponse|refus|prefer not to (say|answer)|no answer)$")
RE_HORS_ECHELLE = re.compile(r"^(je ne sais pas.*|ne sait pas|nsp|sans opinion|non concerne.*|ne s'applique pas|"
                             r"ne se prononce pas|.*pour me prononcer|.*trop peu.*|"
                             r"autre.*|aucun.*|don't know|not applicable|other.*|none.*)$")
RE_BORNE = re.compile(r"\d+(?:[.,]\d+)?")


def _rang_numerique(modalite: str) -> float | None:
    """Rang d'une tranche (« Moins de 25 ans », « 25-27 ans », « 35 ans ou plus ») d'après sa première borne."""
    nombres = RE_BORNE.findall(modalite)
    if not nombres:
        return None
    val = float(nombres[0].replace(",", "."))
    n = _norm(modalite)
    if re.match(r"^(moins|avant|inferieur|less|under|below|<)", n):
        val -= 0.5
    elif re.search(r"(ou plus|et plus|or more|\+)$", n) or re.match(r"^(plus de|apres|superieur|more than|over|>)", n):
        val += 0.5
    return val


def proposer_ordre(modalites: list[str]) -> tuple[list[str], bool, str]:
    """Propose un ordre des modalités. Renvoie (ordre, ordonnée ?, justification)."""
    hors = [m for m in modalites if RE_REFUS.match(_norm(m)) or RE_HORS_ECHELLE.match(_norm(m))]
    coeur = [m for m in modalites if m not in hors]
    if len(coeur) >= 3:
        normes = {m: _norm(m).replace(",", "") for m in coeur}
        for echelle in ECHELLES:
            if all(n in echelle for n in normes.values()) and len(set(normes.values())) == len(coeur):
                return sorted(coeur, key=lambda m: echelle.index(normes[m])) + hors, True, "échelle reconnue"
        rangs = {m: _rang_numerique(m) for m in coeur}
        if all(r is not None for r in rangs.values()) and len(set(rangs.values())) == len(coeur):
            return sorted(coeur, key=lambda m: rangs[m]) + hors, True, "tranches numériques"
    return list(coeur) + hors, False, "ordre de fréquence"


def _typer_colonne(valeurs: pd.Series, dans_famille: bool, est_precision: bool) -> dict:
    """Devine le type d'une colonne à partir de ses valeurs non vides."""
    remplies = valeurs[valeurs != ""]
    normes = remplies.map(_norm)
    substantielles = remplies[~normes.isin(NON_PRESENTE)]
    n = len(substantielles)
    comptes = Counter(substantielles)
    nd = len(comptes)
    infos: dict = {"n": n, "n_distinctes": nd, "na_export": int((normes.isin(NON_PRESENTE)).sum())}
    if n == 0:
        infos["type"] = "multi" if (dans_famille and infos["na_export"]) else "vide"
        return infos
    ens = set(substantielles.map(_norm))
    if ens <= (OUI | NON) and (dans_famille or infos["na_export"] > 0):
        infos["type"] = "multi"
        return infos
    if est_precision and (n < 4 or nd / n > 0.5):
        infos["type"] = "texte"
        return infos
    if all(RE_DATE.match(v) for v in comptes):
        infos["type"] = "date"
        return infos
    if all(RE_NOMBRE.match(v) for v in comptes):
        infos["type"] = "quanti"
        return infos
    longueur_moy = sum(len(v) * c for v, c in comptes.items()) / n
    if any("\n" in v for v in comptes) or (n >= 4 and nd / n > 0.7 and longueur_moy > 12) or nd > 40 or \
            (nd > 20 and nd / n > 0.25):
        infos["type"] = "texte"
        return infos
    infos["type"] = "quali"
    return infos


# ----------------------------------------------------------------------------
# Construction du dictionnaire
# ----------------------------------------------------------------------------

def construire_dictionnaire(tableau: pd.DataFrame, entetes: list[str], *, alias: str = "",
                            anciennes: dict | None = None) -> dict:
    """Construit le dictionnaire des variables et des questions d'une source.

    ``anciennes`` : dictionnaire {(entête, occurrence): identifiant} issu d'un import précédent,
    pour que les mêmes colonnes retrouvent les mêmes identifiants lors d'un ré-import.
    """
    style = detecter_style(entetes)
    prefixe = f"{alias}_" if alias else ""
    pris: set[str] = set(v.lower() for v in (anciennes or {}).values())
    occurrences: Counter = Counter()
    colonnes = []
    for j, entete in enumerate(entetes):
        occ = occurrences[entete]
        occurrences[entete] += 1
        role_para = PARADONNEES.get(_norm(entete))
        if role_para is None and RE_TEMPS.match(entete.strip()) and style != "texte":
            role_para = "duree"
        d = _decomposer_entete(entete, style) if role_para is None else \
            {"code": None, "texte": LIBELLES_PARADONNEES[role_para], "sous": [], "code_question": None}
        colonnes.append({"j": j, "entete": entete, "occ": occ, "para": role_para, **d})

    # Familles : colonnes consécutives partageant le même texte de question et portant une sous-question.
    familles: list[list[int]] = []
    for c in colonnes:
        if c["para"] is None and c["sous"] and familles and colonnes[familles[-1][-1]]["j"] == c["j"] - 1 \
                and colonnes[familles[-1][-1]]["sous"] and colonnes[familles[-1][-1]]["para"] is None \
                and (c["code_question"] or c["texte"]) == (colonnes[familles[-1][-1]]["code_question"]
                                                           or colonnes[familles[-1][-1]]["texte"]):
            familles[-1].append(c["j"])
        else:
            familles.append([c["j"]])

    variables: dict[str, dict] = {}
    questions: dict[str, dict] = {}
    decisions: list[dict] = []
    largeur = max(3, len(str(len(entetes))))
    derniere_question: str | None = None

    for num_q, famille in enumerate(familles, start=1):
        qid = f"{prefixe}q{num_q:0{largeur}d}"
        cols = [colonnes[j] for j in famille]
        tete = cols[0]
        en_famille = len(cols) > 1 or bool(tete["sous"])
        est_precision = (not en_famille and tete["para"] is None and bool(RE_PRECISION.match(_norm(tete["texte"]))))
        ids = []
        for c in cols:
            cle = (c["entete"], c["occ"])
            if anciennes and cle in anciennes:
                vid = anciennes[cle]
            elif c["code"]:
                vid = _identifiant_propre(prefixe + c["code"], pris)
            else:
                vid = _identifiant_propre(f"{prefixe}v{c['j'] + 1:0{largeur}d}", pris)
            serie = tableau[c["j"]]
            t = _typer_colonne(serie, en_famille, est_precision)
            var = {
                "id": vid, "nom": vid, "libelle": c["texte"], "sous_libelle": " — ".join(c["sous"]) or None,
                "question": qid, "source": alias or None, "colonne": c["j"], "entete": c["entete"], "occ": c["occ"],
                "type": t["type"], "role": "analyse", "modalites": [], "ordonnee": False, "champ": None,
                "n_brut": t["n"], "na_export": t["na_export"],
            }
            if c["para"]:
                var.update(role="sensible" if c["para"] in PARADONNEES_SENSIBLES else "technique", para=c["para"],
                           type={"id": "identifiant", "date_soumission": "date", "date_debut": "date",
                                 "date_action": "date", "derniere_page": "quanti", "duree": "quanti"}.get(c["para"], "texte")
                           if t["type"] != "vide" else "vide")
            variables[vid] = var
            ids.append(vid)

        # Cohérence de famille : une matrice ou une question à choix multiples partage type et modalités.
        types = [variables[v]["type"] for v in ids]
        genre = "simple"
        if tete["para"]:
            genre = "technique"
        elif en_famille:
            coeur = [t for t in types if t not in ("texte", "vide")]
            if coeur and sum(t == "multi" for t in coeur) >= max(2, 0.6 * len(coeur)):
                genre = "multiple"   # les colonnes non binaires (« Autre : précisez ») sont du texte libre
                for v in ids:
                    if variables[v]["type"] not in ("multi", "vide"):
                        variables[v]["type"] = "texte"
            elif coeur and all(t in ("quali",) for t in coeur):
                genre = "matrice"
            elif coeur and all(t == "quanti" for t in coeur):
                genre = "matrice_num"
            else:
                genre = "groupe"
        question = {"id": qid, "libelle": tete["texte"], "genre": genre, "variables": ids, "source": alias or None,
                    "code": tete.get("code_question")}
        if est_precision and derniere_question:
            question["precision_de"] = derniere_question
            for v in ids:
                variables[v]["precision_de"] = derniere_question
        questions[qid] = question
        if not tete["para"] and not est_precision:
            derniere_question = qid

        # Modalités
        if genre == "multiple":
            for v in ids:
                if variables[v]["type"] in ("multi", "vide"):
                    variables[v]["type"] = "multi"
                    variables[v]["modalites"] = [{"valeur": "Oui"}, {"valeur": "Non"}]
        communs: Counter = Counter()
        for v in ids:
            if variables[v]["type"] == "quali":
                s = tableau[variables[v]["colonne"]]
                s = s[(s != "") & ~s.map(_norm).isin(NON_PRESENTE)]
                variables[v]["_comptes"] = Counter(s)
                communs.update(variables[v]["_comptes"])
        for v in ids:
            var = variables[v]
            if var["type"] != "quali":
                continue
            comptes = communs if genre == "matrice" else var.pop("_comptes")
            var.pop("_comptes", None)
            par_frequence = [m for m, _ in sorted(comptes.items(), key=lambda kv: (-kv[1], kv[0]))]
            ordre, ordonnee, pourquoi = proposer_ordre(par_frequence)
            var["ordonnee"] = ordonnee
            if ordonnee:
                var["type"] = "ordinale"
            mods = []
            for m in ordre:
                mod = {"valeur": m}
                if RE_REFUS.match(_norm(m)):
                    mod["nr"] = True
                    decisions.append({"genre": "refus", "variable": v, "modalite": m})
                elif ordonnee and RE_HORS_ECHELLE.match(_norm(m)):
                    decisions.append({"genre": "hors_echelle", "variable": v, "modalite": m})
                mods.append(mod)
            var["modalites"] = mods
            if ordonnee:
                decisions.append({"genre": "ordre", "variable": v, "raison": pourquoi})

    # Colonnes potentiellement identifiantes (courriels, téléphones) : rôle « sensible ».
    for var in variables.values():
        if var["type"] in ("texte", "quali") and var["role"] == "analyse":
            s = tableau[var["colonne"]]
            s = s[s != ""]
            n_id = int(s.map(lambda x: bool(RE_EMAIL.search(x) or RE_TELEPHONE.search(x))).sum())
            if n_id:
                var["role"] = "sensible"
                var["type"] = "texte"
                var["modalites"] = []
                decisions.append({"genre": "sensible", "variable": var["id"], "n": n_id})
    for var in variables.values():
        if var["type"] == "vide":
            decisions.append({"genre": "colonne_vide", "variable": var["id"]})

    return {"style": style, "variables": variables, "questions": questions, "decisions": decisions}


def cles_anciennes(variables: dict, alias: str | None) -> dict:
    """Table (entête, occurrence) → identifiant, pour ré-apparier les colonnes d'un nouvel export."""
    return {(v["entete"], v.get("occ", 0)): v["id"] for v in variables.values()
            if v.get("entete") is not None and (v.get("source") or None) == (alias or None)}
