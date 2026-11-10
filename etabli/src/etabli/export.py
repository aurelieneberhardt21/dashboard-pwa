"""Exports : tableaux Excel, données préparées, script R de reproduction, journal méthodologique.

Le script R ne sert pas à faire tourner Établi : il permet à n'importe qui de *refaire le calcul* avec des
logiciels de référence (R, FactoMineR, GDAtools) à partir des données préparées exportées à côté.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime

import pandas as pd

from . import analyses
from .recette import TYPES_ETAPES, sources_etape
from .table import STATUTS, decrire

MENTION_FICTIF = "DONNÉES FICTIVES — démonstration, aucun résultat d'enquête réel"


def classeur_excel(tableaux: list[dict], *, fictif: bool = False) -> bytes:
    """tableaux : [{titre, entetes: [...], lignes: [[...]], notes: [...]}] → un onglet par tableau."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, Side

    wb = Workbook()
    wb.remove(wb.active)
    for k, t in enumerate(tableaux, start=1):
        ws = wb.create_sheet(re.sub(r"[\[\]:*?/\\]", " ", t.get("titre") or f"Tableau {k}")[:31] or f"Tableau {k}")
        ligne = 1
        ws.cell(ligne, 1, t.get("titre") or "").font = Font(bold=True, size=12)
        ligne += 1
        if fictif:
            ws.cell(ligne, 1, MENTION_FICTIF).font = Font(bold=True, color="B00020")
            ligne += 1
        ligne += 1
        trait = Side(style="thin", color="000000")
        for j, e in enumerate(t.get("entetes", []), start=1):
            c = ws.cell(ligne, j, e)
            c.font = Font(bold=True)
            c.border = Border(top=trait, bottom=trait)
            c.alignment = Alignment(wrap_text=True, vertical="bottom", horizontal="left" if j == 1 else "right")
        for l in t.get("lignes", []):
            ligne += 1
            for j, v in enumerate(l, start=1):
                c = ws.cell(ligne, j, v)
                if isinstance(v, float):
                    c.number_format = "0.0" if abs(v) >= 1 else "0.000"
        for j in range(1, len(t.get("entetes", [])) + 1):
            ws.cell(ligne, j).border = Border(bottom=trait)
        ligne += 1
        for note in t.get("notes", []):
            ligne += 1
            ws.cell(ligne, 1, note).font = Font(italic=True, size=9)
        ws.column_dimensions["A"].width = 44
        for j in range(2, len(t.get("entetes", [])) + 1):
            ws.column_dimensions[ws.cell(1, j).column_letter].width = 14
    if not wb.worksheets:
        wb.create_sheet("Vide")
    tampon = io.BytesIO()
    wb.save(tampon)
    return tampon.getvalue()


def donnees_csv(projet, variables: list[str], population: str | None = None, *, textes: bool = False) -> str:
    """Données préparées (libellés en clair, NA = manquant). Les variables sensibles ne sont jamais exportées ;
    les réponses textuelles ne le sont que sur demande explicite."""
    ctx = analyses.Contexte(projet, {"population": population})
    cols = {}
    for v in variables:
        m = ctx.meta.get(v)
        if not m or m.get("role") == "sensible" or (m["type"] == "texte" and not textes):
            continue
        cols[v] = ctx.serie(v)[ctx.masque]
    return pd.DataFrame(cols).to_csv(index=True, index_label="id", na_rep="NA")


# ----------------------------------------------------------------------------
# Script R
# ----------------------------------------------------------------------------

def _r(texte) -> str:
    return '"' + str(texte).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _vec(valeurs) -> str:
    return "c(" + ", ".join(_r(v) for v in valeurs) + ")"


def script_r(projet, spec: dict, titre: str = "") -> tuple[str, str]:
    """Renvoie (script R, CSV des données analysées)."""
    ctx, res, fiche = analyses.contexte_execute(projet, spec)
    df = ctx.export if ctx.export is not None else pd.DataFrame()
    csv = df.to_csv(index=True, index_label="id", na_rep="NA")
    t = spec["type"]
    L = [f"# {titre or analyses.TYPES_ANALYSES.get(t, t)}",
         f"# Script de reproduction généré par Établi le {datetime.now():%Y-%m-%d %H:%M}",
         "# Les données lues ci-dessous sont celles réellement analysées (population et exclusions déjà appliquées).",
         f"# Population : {fiche['donnees']['population']['nom'] + ' — ' + fiche['donnees']['population']['description'] if fiche['donnees']['population'] else 'tous les répondants'}",
         f"# Individus analysés : {fiche['donnees']['n_analyses']}"]
    if projet.etat.get("fictif"):
        L.append(f"# {MENTION_FICTIF}")
    L += ["", 'd <- read.csv("donnees.csv", row.names = 1, na.strings = "NA", check.names = FALSE, '
              'stringsAsFactors = FALSE, encoding = "UTF-8")', "", "# Variables :"]
    for v in df.columns:
        m = ctx.meta.get(v, {})
        L.append(f"#   {v} : {ctx.nom(v)}")
        if m.get("type") in ("quali", "ordinale", "multi") and str(df[v].dtype) == "category":
            L.append(f"d[[{_r(v)}]] <- factor(d[[{_r(v)}]], levels = {_vec(df[v].cat.categories)}"
                     f"{', ordered = TRUE' if m.get('ordonnee') and t in ('croise', 'tri') else ''})")
    L.append("")
    p = fiche["parametres"]
    if t == "tri":
        v = spec["variable"]
        if ctx.meta[v]["type"] == "quanti":
            L += [f"summary(d[[{_r(v)}]]); sd(d[[{_r(v)}]], na.rm = TRUE)", f"hist(d[[{_r(v)}]])"]
        else:
            L += [f"eff <- table(d[[{_r(v)}]])", "cbind(n = eff, pct = round(100 * prop.table(eff), 1))"]
    elif t == "croise":
        x, y = spec["ligne"], spec["colonne"]
        forme = res.get("forme")
        if forme == "tableau":
            L += [f"tab <- table(d[[{_r(x)}]], d[[{_r(y)}]])", "tab", "round(100 * prop.table(tab, 1), 1)   # % en ligne",
                  "test <- chisq.test(tab, correct = FALSE)", "test; test$expected; test$stdres   # résidus ajustés",
                  "sqrt(test$statistic / (sum(tab) * (min(dim(tab)) - 1)))   # V de Cramér",
                  "chisq.test(tab, simulate.p.value = TRUE, B = 10000)   # si effectifs théoriques faibles",
                  "# PEM de Cibois : GDAtools::pem(d[[1]], d[[2]])"]
        elif forme == "groupes":
            q, g = res["quanti"], res["groupe"]
            L += [f"aggregate(d[[{_r(q)}]], list(groupe = d[[{_r(g)}]]), function(v) c(n = length(v), moyenne = mean(v), sd = sd(v)))",
                  f"summary(aov(d[[{_r(q)}]] ~ d[[{_r(g)}]]))", f"oneway.test(d[[{_r(q)}]] ~ d[[{_r(g)}]], var.equal = FALSE)",
                  f"kruskal.test(d[[{_r(q)}]] ~ d[[{_r(g)}]])"]
        else:
            L += [f"cor.test(d[[{_r(x)}]], d[[{_r(y)}]], method = \"spearman\", exact = FALSE)"]
    elif t == "multiples":
        items = p["items"]
        L += [f"items <- sapply(d[, {_vec(items)}], function(x) ifelse(is.na(x), NA, as.character(x) %in% c(\"True\", \"TRUE\")))",
              "repondants <- rowSums(!is.na(items)) > 0", "items[is.na(items)] <- FALSE",
              "round(100 * colMeans(items[repondants, ]), 1)   # % des répondants ayant coché chaque item"]
        if p.get("groupe"):
            L += [f"g <- d[[{_r(p['groupe'])}]][repondants]",
                  "sapply(as.data.frame(items[repondants, ]), function(x) round(100 * tapply(x, g, mean), 1))"]
    elif t == "correlation":
        L += ["# variables ordinales : remplacées par leur rang de modalité",
              "num <- as.data.frame(lapply(d, function(x) if (is.factor(x)) as.numeric(x) else as.numeric(x)))",
              f"round(cor(num, method = {_r(p['methode'])}, use = \"pairwise.complete.obs\"), 3)",
              f"# test d'une paire : cor.test(num[[1]], num[[2]], method = {_r(p['methode'])}, exact = FALSE)",
              f"# ajustement des p : p.adjust(p, method = {_r({'bh': 'BH', 'holm': 'holm'}.get(p['ajustement'], 'none'))})"]
    elif t == "regression":
        y, xs = p["y"], p["x"]
        for v, ref in (res.get("references") or {}).items():
            L.append(f"d[[{_r(v)}]] <- relevel(factor(d[[{_r(v)}]], ordered = FALSE), ref = {_r(ref)})")
        droite = " + ".join(f"`{v}`" for v in xs) + "".join(f" + `{a}`:`{b}`" for a, b in p.get("interactions", []))
        if p["modele"] == "lineaire":
            L += [f"m <- lm(`{y}` ~ {droite}, data = d)", "summary(m); confint(m)", "car::Anova(m, type = 2); car::vif(m)"]
            if p.get("robuste"):
                L.append(f"lmtest::coeftest(m, vcov = sandwich::vcovHC(m, type = {_r(p['robuste'])}))")
        elif p["modele"] == "logistique":
            L += [f"d$cible <- as.integer(d[[{_r(y)}]] == {_r(p['modalite_cible'])})",
                  f"m <- glm(cible ~ {droite}, data = d, family = binomial)", "summary(m)",
                  "exp(cbind(OR = coef(m), confint.default(m)))   # odds ratios et IC de Wald",
                  "car::Anova(m, type = 2, test.statistic = \"LR\"); car::vif(m)",
                  "# effets marginaux moyens : marginaleffects::avg_slopes(m)"]
        else:
            L += [f"d[[{_r(y)}]] <- relevel(factor(d[[{_r(y)}]], ordered = FALSE), ref = {_r(p.get('reference_y'))})",
                  f"m <- nnet::multinom(`{y}` ~ {droite}, data = d, Hess = TRUE)", "summary(m); exp(coef(m))"]
    elif t in ("acm", "acp", "afdm", "cah"):
        base = spec["base"] if t == "cah" else spec
        if isinstance(base, str):
            base = next(a["spec"] for a in projet.etat["analyses"] if a["id"] == base)
        bp = p["base"] if t == "cah" else p
        actives = [v for v in base.get("actives", []) if v in df.columns]
        sq = [v for v in base.get("sup_quali", []) if v in df.columns]
        sn = [v for v in base.get("sup_quanti", []) if v in df.columns]
        ordre = actives + sq + sn
        L += ["library(FactoMineR)", f"x <- d[, {_vec(ordre)}]"]
        iq = f"quali.sup = {len(actives) + 1}:{len(actives) + len(sq)}" if sq else ""
        inn = f"quanti.sup = {len(actives) + len(sq) + 1}:{len(ordre)}" if sn else ""
        sup = "".join(", " + s for s in (iq, inn) if s)
        n_axes = max(int(base.get("n_axes", 5)), int(spec.get("n_axes_cah", 0)))
        if base["type"] == "acm":
            passives = ctx.roles_export.get("passives", [])
            L += ["for (v in " + _vec(actives) + ") x[[v]] <- factor(x[[v]], ordered = FALSE)"]
            if passives:
                L += ["# ACM spécifique : modalités passives (non-réponses, modalités écartées)",
                      "passives <- " + _vec(f"{v}_{m}" for v, m in passives),
                      f"res <- MCA(x, ncp = {n_axes}, excl = passives, graph = FALSE{sup})",
                      "# équivalent : GDAtools::speMCA(x[, 1:" + str(len(actives)) + "], excl = GDAtools::getindexcat(x[, 1:"
                      + str(len(actives)) + "])[...])"]
            else:
                L += [f"res <- MCA(x, ncp = {n_axes}, graph = FALSE{sup})"]
            L += ["res$eig", "res$var$coord; res$var$contrib; res$var$cos2", "# taux modifiés de Benzécri : GDAtools::modif.rate(res)"]
        elif base["type"] == "acp":
            L += [f"res <- PCA(x, scale.unit = {'TRUE' if bp.get('reduire', True) else 'FALSE'}, ncp = {n_axes}, graph = FALSE{sup})",
                  "res$eig; res$var$coord; res$var$contrib; res$var$cos2"]
        else:
            L += [f"res <- FAMD(x, ncp = {n_axes}, graph = FALSE" + (f", sup.var = {len(actives) + 1}:{len(ordre)}" if sq or sn else "") + ")",
                  "res$eig; res$var$coord; res$var$contrib"]
        L += ["plot(res, invisible = \"ind\")   # carte des modalités / variables"]
        if t == "cah":
            L += ["", f"# CAH de Ward sur les {p['n_axes_cah']} premiers axes, {p['k']} classes",
                  f"res$ind$coord <- res$ind$coord[, 1:{p['n_axes_cah']}, drop = FALSE]   # ne garder que les axes retenus",
                  f"cl <- HCPC(res, nb.clust = {p['k']}, consol = {'TRUE' if p['consolidation'] else 'FALSE'}, graph = FALSE)",
                  "table(cl$data.clust$clust)", "cl$desc.var   # description des classes (v-tests)"]
    elif t == "afc":
        L += ["library(FactoMineR)", f"tab <- table(d[[{_r(spec['ligne'])}]], d[[{_r(spec['colonne'])}]])",
              "tab <- unclass(tab)"]
        ls, cs = p.get("lignes_sup", []), p.get("colonnes_sup", [])
        args = ""
        if ls:
            args += f", row.sup = which(rownames(tab) %in% {_vec(ls)})"
        if cs:
            args += f", col.sup = which(colnames(tab) %in% {_vec(cs)})"
        L += [f"res <- CA(tab, ncp = {p['n_axes']}, graph = FALSE{args})", "res$eig; res$row$coord; res$col$coord; res$row$contrib; res$col$contrib"]
    elif t == "exploration":
        c = spec["cible"]
        L += ["# Une ligne par variable candidate ; ici le principe pour les couples qualitatifs :",
              f"cible <- d[[{_r(c)}]]",
              f"res <- lapply(setdiff(names(d), {_r(c)}), function(v) {{",
              "  if (is.numeric(d[[v]]) || is.numeric(cible)) return(NULL)",
              "  tab <- table(cible, d[[v]]); tab <- tab[rowSums(tab) > 0, colSums(tab) > 0, drop = FALSE]",
              "  if (min(dim(tab)) < 2) return(NULL)",
              "  k <- suppressWarnings(chisq.test(tab, correct = FALSE))",
              "  data.frame(variable = v, n = sum(tab), V = sqrt(k$statistic / (sum(tab) * (min(dim(tab)) - 1))), p = k$p.value)",
              "})", "res <- do.call(rbind, res)",
              "res$p_holm <- p.adjust(res$p, \"holm\"); res$p_bh <- p.adjust(res$p, \"BH\")", "res[order(-res$V), ]"]
    L += ["", "# Paramètres enregistrés par Établi :", "# " + json.dumps(p, ensure_ascii=False, default=str)]
    return "\n".join(L) + "\n", csv


def archive_reproduction(projet, spec: dict, titre: str = "") -> bytes:
    script, csv = script_r(projet, spec, titre)
    ctx, res, fiche = analyses.contexte_execute(projet, spec)
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("analyse.R", script)
        z.writestr("donnees.csv", csv)
        z.writestr("fiche_de_calcul.json", json.dumps({"titre": titre, "specification": spec, "fiche": fiche},
                                                        ensure_ascii=False, indent=2, default=str))
        z.writestr("LISEZMOI.txt",
                   "analyse.R            script R reproduisant le calcul (FactoMineR, car… selon l'analyse)\n"
                   "donnees.csv          données réellement analysées (population et exclusions appliquées)\n"
                   "fiche_de_calcul.json spécification, effectifs, exclusions, paramètres et avertissements\n\n"
                   "Attention : donnees.csv contient des réponses individuelles. Ne le diffusez pas sans vérifier\n"
                   "qu'il ne permet pas de réidentifier des répondants (petits effectifs, combinaisons rares).\n")
    return tampon.getvalue()


# ----------------------------------------------------------------------------
# Journal méthodologique
# ----------------------------------------------------------------------------

def _decrire_etape(et: dict, meta: dict) -> str:
    p, t = et.get("params", {}), et["type"]
    nom = lambda v: (meta.get(v, {}).get("nom") if meta.get(v, {}).get("nom") not in (None, v) else None) or \
        (meta.get(v, {}).get("sous_libelle") or meta.get(v, {}).get("libelle") or v)
    cible = p.get("cible", {})
    tete = f"**{TYPES_ETAPES.get(t, t)}** → `{cible.get('nom') or cible.get('id', '')}` — {cible.get('libelle', '')}" if cible else \
        f"**{TYPES_ETAPES.get(t, t)}**"
    lignes = [tete]
    if t == "recoder":
        lignes.append(f"  - source : {nom(p['source'])}")
        groupes: dict = {}
        for a, b in p.get("correspondance", {}).items():
            groupes.setdefault(b if b is not None else "(mis en manquant)", []).append(a)
        lignes += [f"  - « {b} » ← {' ; '.join('« ' + a + ' »' for a in aa)}" for b, aa in groupes.items()]
    elif t == "decouper":
        lignes.append(f"  - source : {nom(p['source'])} ; bornes : {p.get('bornes')}")
    elif t == "score":
        lignes.append(f"  - {p.get('mode', 'compter')} sur {len(p.get('sources', []))} variables : "
                      + " ; ".join(nom(v) for v in p.get("sources", [])))
        if p.get("mode", "compter") == "compter":
            lignes.append(f"  - réponses comptées : {p.get('valeurs', ['Oui'])}")
        elif p.get("points"):
            lignes.append(f"  - points : {p['points']}")
    elif t == "regle":
        lignes += [f"  - si {decrire(c.get('si'), meta)} → « {c.get('alors')} »" for c in p.get("cas", [])]
        lignes.append(f"  - sinon → {('« ' + p['sinon'] + ' »') if p.get('sinon') else 'manquant'}")
    elif t == "fusionner":
        for s in p.get("sources", []):
            lignes.append(f"  - source : {nom(s['var'])}" + (f" (recodée : {s['correspondance']})" if s.get("correspondance") else ""))
    elif t == "exclure":
        lignes.append(f"  - individus écartés si : {decrire(p.get('si'), meta)} — motif : {p.get('motif', '')}")
    elif t in ("convertir", "croiser"):
        lignes.append("  - sources : " + " ; ".join(nom(v) for v in sources_etape(et)))
    if et.get("note"):
        lignes.append(f"  - *Justification* : {et['note']}")
    if not et.get("actif", True):
        lignes.append("  - (étape désactivée)")
    return "\n".join(lignes)


def journal_markdown(projet) -> str:
    e = projet.etat
    table = projet.table()
    meta = table.meta
    L = [f"# Journal méthodologique — {e['nom']}", "",
         f"Généré par Établi le {datetime.now():%d/%m/%Y à %H:%M} (version {e.get('version')} du projet).", ""]
    if e.get("fictif"):
        L += [f"> **{MENTION_FICTIF}**", ""]
    L += ["## 1. Sources", ""]
    for s in e["sources"]:
        L.append(f"- `{s['fichier']}` — {s['n_lignes']} réponses, {s['n_colonnes']} colonnes, importé le "
                 f"{s['importe'][:16].replace('T', ' à ')} (empreinte SHA-256 : `{s['sha256'][:16]}…`)")
    L += ["", f"Réponses complètes : {int(table.complet.sum())} sur {table.n}.", "",
          "Statut des cellules sans réponse : " + " ; ".join(f"*{v[1]}*" for k, v in STATUTS.items() if k) + ".", ""]
    L += ["## 2. Annotations du dictionnaire", ""]
    champs = [(v, decrire(v["champ"], meta)) for v in e["variables"].values() if v.get("champ") and not v["champ"].get("tous")]
    par_champ: dict = {}
    for v, d in champs:
        par_champ.setdefault(d, []).append(v)
    if par_champ:
        L.append("Champ des questions (à qui la question a été posée) :")
        for d, vs in par_champ.items():
            L.append(f"- {len(vs)} variable(s) posées si {d}")
    nr = [(v, m) for v in e["variables"].values() for m in v.get("modalites", []) if m.get("nr")]
    if nr:
        L += ["", "Modalités déclarées « de non-réponse » :"]
        L += [f"- {v.get('sous_libelle') or v['libelle'][:70]} : « {m['valeur']} »" for v, m in nr]
    sens = [v for v in e["variables"].values() if v.get("role") == "sensible"]
    if sens:
        L += ["", "Variables sensibles (jamais exportées) : " + " ; ".join(v["libelle"][:50] for v in sens)]
    L += ["", "## 3. Recette de préparation", ""]
    if not e["recette"]:
        L.append("Aucune étape : les analyses portent sur les variables brutes.")
    rapports = {r["id"]: r for r in projet.rapports_recette()}
    for k, et in enumerate(e["recette"], start=1):
        L.append(f"{k}. " + _decrire_etape(et, meta))
        r = rapports.get(et["id"], {})
        if r.get("erreur") and et.get("actif", True):
            L.append(f"  - ⚠ erreur : {r['erreur']}")
        for a in r.get("avertissements", []):
            L.append(f"  - ⚠ {a}")
    L += ["", "## 4. Populations", ""]
    for p in e["populations"]:
        ctx = analyses.Contexte(projet, {"population": p["id"]})
        L.append(f"- **{p['nom']}** (n = {int(ctx.masque.sum())}) : {decrire(p['condition'], meta)}"
                 + (f" — {p['note']}" if p.get("note") else ""))
    if not e["populations"]:
        L.append("Aucune population définie.")
    L += ["", "## 5. Analyses enregistrées", ""]
    for a in e["analyses"]:
        L += [f"### {a.get('titre') or analyses.TYPES_ANALYSES.get(a['spec'].get('type'))}", "",
              f"*{analyses.TYPES_ANALYSES.get(a['spec'].get('type'), a['spec'].get('type'))}* — enregistrée le "
              f"{a.get('modifie', a.get('cree', ''))[:10]}", ""]
        try:
            r = analyses.executer(projet, a["spec"])
            f = r["fiche"]
            d = f["donnees"]
            L.append(f"- Population : {d['population']['nom'] if d['population'] else 'tous les répondants'} "
                     f"(n = {d['n_population']}) ; individus analysés : {d['n_analyses']}")
            for x in d["exclusions"]:
                L.append(f"  - écartés pour « {x['nom']} » : {x['n']} ({', '.join(f'{k.lower()} : {v}' for k, v in x['motifs'].items())})")
            L.append(f"- Méthode : {(f['methode'] or {}).get('nom', '')}")
            L.append(f"- Paramètres : `{json.dumps(f['parametres'], ensure_ascii=False, default=str)}`")
            for av in f["avertissements"]:
                L.append(f"- ⚠ {av}")
        except Exception as ex:      # une analyse cassée ne doit pas empêcher d'exporter le journal
            L.append(f"- ⚠ analyse non recalculable en l'état : {ex}")
        if a.get("notes"):
            L += ["", "**Notes et interprétation**", "", a["notes"]]
        L.append("")
    if e.get("carnet"):
        L += ["## 6. Carnet de recherche", ""]
        for n in e["carnet"]:
            L += [f"**{n.get('date', '')[:10]}** — {n.get('texte', '')}", ""]
    return "\n".join(L) + "\n"
