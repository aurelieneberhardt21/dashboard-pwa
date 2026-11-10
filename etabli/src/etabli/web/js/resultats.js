// Affichage des résultats, type d'analyse par type d'analyse. Tout tableau est copiable / exportable,
// toute figure est exportable (SVG, PNG), et les cartes renvoient aux variables qui les produisent.
import { html, useState, useEffect, useRef, useMemo, api, magasin, aller, publier, agir, toast, ent, pct, nf, pval, court, nomVar, titreComplet, Segments, Onglets, Icone, BoutonsTable, BoutonsFigure, Avertissements, bulle, ChoixVariable, CATEGORIELS } from "./base.js";
import { Barres, Profils, Histogramme, Eboulis, Intervalles, Nuage, Dendrogramme, Carte, Legende, SERIES, ellipseConcentration } from "./graphiques.js";
import { Statuts } from "./donnees.js";

const V = (id) => magasin.etat.variables[id];
const nomMod = (m, n = 24) => `${nomVar(m.variable, n)} : ${m.modalite}`;
const Bloc = ({ titre, outils, children }) => html`<div class="carte"><div class="ligne espace" style="margin-bottom:8px"><h3>${titre}</h3><span class="ligne">${outils}</span></div>${children}</div>`;
const fondResidu = (r) => (r == null || Math.abs(r) < 2) ? "" : `background:color-mix(in oklab, ${r > 0 ? "var(--s1)" : "var(--s8)"} ${Math.min(55, 14 + 9 * (Math.abs(r) - 2))}%, transparent)`;
const fondCorr = (r) => (r == null) ? "" : `background:color-mix(in oklab, ${r > 0 ? "var(--s1)" : "var(--s8)"} ${Math.round(Math.min(1, Math.abs(r)) * 62)}%, transparent)`;
const Stat = ({ nom, valeur, aide }) => html`<div ...${aide ? bulle(aide) : {}}><div class="mini muet">${nom}</div><div style="font-size:16px;font-variant-numeric:tabular-nums">${valeur}</div></div>`;

// ---------------------------------------------------------------- tri à plat
export function ResTri({ r, spec }) {
  const refT = useRef(), refF = useRef(), v = V(spec.variable), titre = nomVar(v, 80);
  if (r.type === "texte") return html`<${Bloc} titre=${`${ent(r.n)} réponses, ${ent(r.n_distinctes)} distinctes`} outils=${html`<${BoutonsTable} refTable=${refT} titre=${titre} />`}>
    <div style="max-height:520px;overflow:auto"><table class="t" ref=${refT}><thead><tr><th>Réponse</th><th>n</th></tr></thead><tbody>${r.reponses.map((x) => html`<tr><td style="white-space:pre-wrap">${x.texte}</td><td>${x.n}</td></tr>`)}</tbody></table></div><//>`;
  if (r.moyenne !== undefined) return html`<div><${Bloc} titre="Résumé" outils=${html`<${BoutonsTable} refTable=${refT} titre=${titre} />`}>
      <${Statuts} statuts=${r.statuts} />
      <table class="t" ref=${refT} style="margin-top:12px"><thead><tr><th>Indicateur</th><th>Valeur</th></tr></thead><tbody>
        ${[["Réponses valides", ent(r.n)], ["Moyenne", nf(r.moyenne, 2)], ["IC 95 % de la moyenne", `${nf(r.ic_bas, 2)} – ${nf(r.ic_haut, 2)}`], ["Écart-type", nf(r.ecart_type, 2)], ["Minimum", nf(r.min, 2)], ["1er décile", nf(r.d1, 2)], ["1er quartile", nf(r.q1, 2)], ["Médiane", nf(r.mediane, 2)], ["3e quartile", nf(r.q3, 2)], ["9e décile", nf(r.d9, 2)], ["Maximum", nf(r.max, 2)], ["Asymétrie", nf(r.asymetrie, 2)]].map(([a, b]) => html`<tr><td>${a}</td><td>${b}</td></tr>`)}</tbody></table><//>
    <${Bloc} titre="Distribution" outils=${html`<${BoutonsFigure} refSvg=${refF} nom=${titre} />`}><div ref=${refF}><${Histogramme} bornes=${r.histogramme.bornes} effectifs=${r.histogramme.effectifs} moyenne=${r.moyenne} mediane=${r.mediane} largeur=${640} hauteur=${230} /></div><//></div>`;
  return html`<div><${Bloc} titre=${`${ent(r.n)} réponses valides sur ${ent(r.n_population)} individus`} outils=${html`<${BoutonsTable} refTable=${refT} titre=${titre} notes=${[`Champ : ${ent(r.n)} réponses valides.`]} />`}>
      <${Statuts} statuts=${r.statuts} />
      <table class="t" ref=${refT} style="margin-top:12px"><thead><tr><th>${titre}</th><th>Effectif</th><th>%</th><th>IC 95 %</th></tr></thead><tbody>
        ${r.modalites.map((m) => html`<tr><td>${m.modalite}</td><td>${ent(m.n)}</td><td>${nf(m.pct, 1)}</td><td class="muet">${m.ic_bas == null ? "" : `${nf(m.ic_bas, 1)} – ${nf(m.ic_haut, 1)}`}</td></tr>`)}
        <tr class="total"><td>Ensemble</td><td>${ent(r.n)}</td><td>100,0</td><td></td></tr></tbody></table><//>
    <${Bloc} titre="Répartition (% des réponses valides, IC 95 %)" outils=${html`<${BoutonsFigure} refSvg=${refF} nom=${titre} />`}><div ref=${refF}><${Barres} donnees=${r.modalites.map((m) => ({ label: m.modalite, valeur: m.pct, n: m.n, ic_bas: m.ic_bas, ic_haut: m.ic_haut, detail: "% des réponses valides" }))} max=${Math.min(100, Math.max(...r.modalites.map((m) => m.ic_haut || m.pct)) * 1.08)} /></div><//></div>`;
}

// ---------------------------------------------------------------- croisement
function TestsTableau({ r }) {
  const c = r.chi2 || {}, v = r.v_cramer || {}, cond = r.conditions_chi2 || {}, d = r.deux_par_deux, o = r.ordinal;
  return html`<div><div class="grille" style="grid-template-columns:repeat(auto-fit,minmax(130px,1fr));margin-top:4px">
      <${Stat} nom="V de Cramér" valeur=${nf(v.v, 3)} aide="Intensité de la liaison, de 0 (indépendance) à 1. Repères usuels : 0,1 faible, 0,3 moyenne, 0,5 forte — à relativiser selon le domaine." />
      <${Stat} nom="IC 95 % du V" valeur=${v.ic_bas == null ? "—" : `${nf(v.ic_bas, 2)} – ${nf(v.ic_haut, 2)}`} aide=${v.methode_ic} />
      <${Stat} nom="V corrigé du biais" valeur=${nf(v.v_corrige, 3)} aide="Le V brut est gonflé dans les petits tableaux ; la correction de Bergsma (2013) le ramène vers 0." />
      <${Stat} nom=${`Chi² (ddl = ${c.ddl ?? "—"})`} valeur=${nf(c.statistique, 2)} />
      <${Stat} nom="p (chi²)" valeur=${pval(c.p)} aide="Probabilité d'observer un écart au moins aussi grand si les deux variables étaient indépendantes. Fragile quand des effectifs théoriques sont < 5." />
      ${r.fisher && html`<${Stat} nom="p (Fisher)" valeur=${pval(r.fisher.p)} aide=${r.fisher.methode} />`}
      ${r.simulation && r.simulation.p_chi2 != null && html`<${Stat} nom="p simulée" valeur=${pval(r.simulation.p_chi2)} aide=${`Monte-Carlo, ${ent(r.simulation.n_simulations)} tableaux tirés à marges fixées : ne repose pas sur l'approximation du chi².`} />`}
      <${Stat} nom="PEM global" valeur=${pct(r.pem_global, 0)} aide="Pourcentage de l'écart maximum (Cibois) : part de la liaison maximale possible compte tenu des marges." />
      ${d && d.odds_ratio && html`<${Stat} nom="Odds ratio" valeur=${`${nf(d.odds_ratio.valeur, 2)} [${nf(d.odds_ratio.ic_bas, 2)} ; ${nf(d.odds_ratio.ic_haut, 2)}]`} aide=${d.odds_ratio.lecture} />`}
      ${o && o.gamma && html`<${Stat} nom="Gamma (ordinal)" valeur=${nf(o.gamma.valeur, 2)} aide="Goodman-Kruskal : de −1 à +1, sens et force de la liaison entre deux variables ordonnées." />`}
      ${o && o.tau_b && html`<${Stat} nom="Tau-b de Kendall" valeur=${`${nf(o.tau_b.valeur, 2)} (p ${pval(o.tau_b.p)})`} />`}</div>
    <p class="petit secondaire" style="margin-top:10px">Effectifs théoriques : minimum ${nf(cond.min_theorique, 1)} ; ${ent(cond.n_theoriques_inf_5)} cellule(s) sur ${ent(cond.n_cellules)} en dessous de 5. ${r.recommandation || ""}</p></div>`;
}

export function ResCroise({ r, spec }) {
  const [mode, setMode] = useState("pct_ligne");
  const [couleur, setCouleur] = useState(true);
  const refT = useRef(), refF = useRef();
  if (r.forme === "groupes") {
    const g = r.groupes, a = r.anova || {}, dg = r.deux_groupes;
    return html`<div><${Bloc} titre=${`${nomVar(r.quanti, 50)} selon ${nomVar(r.groupe, 50)}`} outils=${html`<${BoutonsTable} refTable=${refT} titre="Comparaison de moyennes" />`}>
        <table class="t" ref=${refT}><thead><tr><th>${nomVar(r.groupe, 40)}</th><th>n</th><th>Moyenne</th><th>IC 95 %</th><th>Écart-type</th><th>Médiane</th></tr></thead><tbody>
          ${g.map((x) => html`<tr><td>${x.groupe}</td><td>${ent(x.n)}${x.n < 5 ? html` <span style="color:var(--alerte-encre)">▲</span>` : ""}</td><td>${nf(x.moyenne, 2)}</td><td class="muet">${x.ic_bas == null ? "" : `${nf(x.ic_bas, 2)} – ${nf(x.ic_haut, 2)}`}</td><td>${nf(x.ecart_type, 2)}</td><td>${nf(x.mediane, 2)}</td></tr>`)}</tbody></table><//>
      <${Bloc} titre="Moyennes et intervalles de confiance à 95 %" outils=${html`<${BoutonsFigure} refSvg=${refF} nom="moyennes" />`}><div ref=${refF}><${Intervalles} reference=${null} lignes=${g.filter((x) => x.n).map((x) => ({ label: x.groupe, valeur: x.moyenne, bas: x.ic_bas, haut: x.ic_haut, n: x.n, nomValeur: "moyenne" }))} /></div><//>
      <${Bloc} titre="Mesures et tests"><div class="grille" style="grid-template-columns:repeat(auto-fit,minmax(130px,1fr))">
        <${Stat} nom="eta²" valeur=${nf(a.eta2, 3)} aide="Part de la variance de la variable numérique « expliquée » par l'appartenance au groupe (0 à 1)." />
        <${Stat} nom="ANOVA : F" valeur=${`${nf(a.f, 2)} (p ${pval(a.p)})`} aide="Suppose des variances comparables entre groupes." />
        ${r.welch && html`<${Stat} nom="Welch : F" valeur=${`${nf(r.welch.f, 2)} (p ${pval(r.welch.p)})`} aide="Variante qui ne suppose pas l'égalité des variances : à préférer si les écarts-types diffèrent nettement." />`}
        ${r.kruskal && html`<${Stat} nom="Kruskal-Wallis" valeur=${`p ${pval(r.kruskal.p)}`} aide="Test sur les rangs : robuste aux valeurs extrêmes et aux distributions dissymétriques." />`}
        ${dg && dg.d_cohen && html`<${Stat} nom="d de Cohen" valeur=${nf(dg.d_cohen.d, 2)} aide="Écart entre les deux moyennes en nombre d'écarts-types. Repères : 0,2 petit, 0,5 moyen, 0,8 grand." />`}
        ${dg && dg.mann_whitney && html`<${Stat} nom="Mann-Whitney" valeur=${`p ${pval(dg.mann_whitney.p)}`} />`}</div><//></div>`;
  }
  if (r.forme === "correlation") {
    const p = r.paires[0] || {};
    return html`<div><${Bloc} titre="Corrélation"><div class="grille" style="grid-template-columns:repeat(4,1fr)"><${Stat} nom=${r.coefficient || "coefficient"} valeur=${nf(p.r, 3)} /><${Stat} nom="IC 95 %" valeur=${p.ic_bas == null ? "—" : `${nf(p.ic_bas, 2)} – ${nf(p.ic_haut, 2)}`} /><${Stat} nom="n" valeur=${ent(p.n)} /><${Stat} nom="p" valeur=${pval(p.p)} /></div><//>
      <${Bloc} titre="Nuage de points" outils=${html`<${BoutonsFigure} refSvg=${refF} nom="nuage" />`}><div ref=${refF}><${Nuage} points=${r.points || []} nomX=${nomVar(spec.ligne, 70)} nomY=${nomVar(spec.colonne, 50)} /></div><//></div>`;
  }
  const modes = [["effectifs", "Effectifs"], ["pct_ligne", "% ligne", "Chaque ligne fait 100 % : compare les lignes entre elles"], ["pct_colonne", "% colonne", "Chaque colonne fait 100 %"], ["pct_total", "% total"], ["theoriques", "Théoriques", "Effectifs attendus si les deux variables étaient indépendantes"], ["residus_ajustes", "Résidus ajustés", "Écart à l'indépendance, standardisé : |r| > 2 est notable"], ["pem", "PEM", "Pourcentage de l'écart maximum (Cibois)"]];
  const dec = { effectifs: 0, theoriques: 1, residus_ajustes: 2, pem: 0 }[mode] ?? 1;
  const nomL = nomVar(spec.ligne, 40), nomC = nomVar(spec.colonne, 60);
  const margeL = (i) => mode === "effectifs" ? ent(r.marge_lignes[i]) : mode === "pct_ligne" ? "100,0" : mode === "pct_total" || mode === "pct_colonne" ? nf(r.pct_marge_lignes[i], 1) : "";
  const margeC = (j) => mode === "effectifs" ? ent(r.marge_colonnes[j]) : mode === "pct_colonne" ? "100,0" : mode === "pct_total" || mode === "pct_ligne" ? nf(r.pct_marge_colonnes[j], 1) : "";
  return html`<div><${Bloc} titre=${`${nomL} × ${nomC}`} outils=${html`<${BoutonsTable} refTable=${refT} titre=${`${nomL} x ${nomC} (${modes.find((m) => m[0] === mode)[1]})`} notes=${[`n = ${r.n}. Chi² = ${nf(r.chi2?.statistique, 2)}, ddl = ${r.chi2?.ddl}, p = ${pval(r.chi2?.p)} ; V de Cramér = ${nf(r.v_cramer?.v, 3)}.`]} />`}>
      <div class="ligne" style="flex-wrap:wrap;margin-bottom:10px"><${Segments} options=${modes} valeur=${mode} onChange=${setMode} />
        <label class="ligne petit pousse" title="Fond bleu : sur-représentation (résidu ajusté > 2) ; rouge : sous-représentation (< −2)"><input type="checkbox" checked=${couleur} onChange=${(e) => setCouleur(e.target.checked)} /> colorer les écarts à l'indépendance</label></div>
      <div class="defile-x"><table class="t" ref=${refT}><thead><tr><th>${nomL} <span class="muet" style="font-weight:400">\\ ${court(nomC, 30)}</span></th>${r.colonnes.map((c) => html`<th title=${c}>${court(c, 26)}</th>`)}<th>Ensemble</th>${mode.startsWith("pct") && html`<th class="muet">n</th>`}</tr></thead><tbody>
        ${r.lignes.map((l, i) => html`<tr><td title=${l}>${court(l, 46)}</td>${r.colonnes.map((_, j) => html`<td style=${couleur ? fondResidu(r.residus_ajustes[i][j]) : ""} ...${bulle(() => html`<div><b>${court(l, 40)} × ${court(r.colonnes[j], 40)}</b><div class="l"><span>effectif</span><span>${ent(r.effectifs[i][j])}</span></div><div class="l"><span>% ligne / % colonne</span><span>${nf(r.pct_ligne[i][j], 1)} / ${nf(r.pct_colonne[i][j], 1)}</span></div><div class="l"><span>théorique</span><span>${nf(r.theoriques[i][j], 1)}</span></div><div class="l"><span>résidu ajusté</span><span>${nf(r.residus_ajustes[i][j], 2)}</span></div><div class="l"><span>PEM</span><span>${pct(r.pem[i][j], 0)}</span></div></div>`)}>${mode === "effectifs" ? ent(r.effectifs[i][j]) : nf(r[mode][i][j], dec)}</td>`)}<td class="gras">${margeL(i)}</td>${mode.startsWith("pct") && html`<td class="muet">${ent(r.marge_lignes[i])}</td>`}</tr>`)}
        <tr class="total"><td>Ensemble</td>${r.colonnes.map((_, j) => html`<td>${margeC(j)}</td>`)}<td>${mode === "effectifs" ? ent(r.n) : mode.startsWith("pct") ? "100,0" : ""}</td>${mode.startsWith("pct") && html`<td class="muet">${ent(r.n)}</td>`}</tr></tbody></table></div>
      ${couleur && html`<${Legende} items=${[{ label: "sur-représentation (résidu ajusté > 2)", couleur: "color-mix(in oklab, var(--s1) 35%, transparent)" }, { label: "sous-représentation (< −2)", couleur: "color-mix(in oklab, var(--s8) 35%, transparent)" }]} />`}<//>
    <${Bloc} titre="Liaison entre les deux variables"><${TestsTableau} r=${r} /><//>
    <${Bloc} titre=${`Profils : répartition de « ${court(nomC, 40)} » selon « ${court(nomL, 40)} »`} outils=${html`<${BoutonsFigure} refSvg=${refF} nom="profils" />`}><div ref=${refF}><${Profils} categories=${r.colonnes} lignes=${[...r.lignes.map((l, i) => ({ label: `${l} (n=${r.marge_lignes[i]})`, parts: r.pct_ligne[i], effectifs: r.effectifs[i] })), { label: "Ensemble", parts: r.pct_marge_colonnes, effectifs: r.marge_colonnes, total: true }]} /></div><//></div>`;
}

// ---------------------------------------------------------------- réponses multiples
export function ResMultiples({ r }) {
  const refT = useRef(), refG = useRef(), refF = useRef(), pg = r.par_groupe;
  const items = [...r.items].sort((a, b) => b.n - a.n);
  return html`<div><${Bloc} titre=${`${ent(r.n_repondants)} répondants · ${nf(r.nb_moyen_reponses, 1)} réponses cochées en moyenne`} outils=${html`<${BoutonsTable} refTable=${refT} titre="Réponses multiples" />`}>
      <table class="t" ref=${refT}><thead><tr><th>Item</th><th>Cochés</th><th>% des répondants</th><th>IC 95 %</th><th>% des réponses</th></tr></thead><tbody>
        ${items.map((it) => html`<tr><td>${it.libelle || it.item}</td><td>${ent(it.n)}</td><td>${nf(it.pct_repondants, 1)}</td><td class="muet">${nf(it.ic_bas, 1)} – ${nf(it.ic_haut, 1)}</td><td>${nf(it.pct_reponses, 1)}</td></tr>`)}
        <tr class="total"><td>Aucun item coché</td><td>${ent(r.n_aucun_coche)}</td><td>${nf(100 * r.n_aucun_coche / (r.n_repondants || 1), 1)}</td><td></td><td></td></tr></tbody></table><//>
    <${Bloc} titre="% des répondants ayant coché chaque item" outils=${html`<${BoutonsFigure} refSvg=${refF} nom="reponses_multiples" />`}><div ref=${refF}><${Barres} donnees=${items.map((it) => ({ label: it.libelle || it.item, valeur: it.pct_repondants, n: it.n, ic_bas: it.ic_bas, ic_haut: it.ic_haut }))} /></div><//>
    ${pg && html`<${Bloc} titre="Selon le groupe (% de chaque groupe ayant coché l'item)" outils=${html`<${BoutonsTable} refTable=${refG} titre="Réponses multiples par groupe" />`}>
      <div class="defile-x"><table class="t" ref=${refG}><thead><tr><th>Item</th>${pg.groupes.map((g, j) => html`<th>${court(g, 22)}<br /><span class="muet" style="font-weight:400">n=${pg.n_groupes[j]}</span></th>`)}<th>V</th><th>p</th><th title="Benjamini-Hochberg">p ajustée</th></tr></thead><tbody>
        ${r.items.map((it, i) => { const t = pg.tests[i] || {}; return html`<tr><td>${it.libelle || it.item}</td>${pg.pct[i].map((x) => html`<td>${nf(x, 1)}</td>`)}<td>${nf(t.v_cramer, 2)}</td><td>${pval(t.p)}</td><td>${pval(t.p_bh)}${t.fragile ? html` <span title="Effectifs trop faibles : test fragile" style="color:var(--alerte-encre)">▲</span>` : ""}</td></tr>`; })}</tbody></table></div>
      <p class="aide-champ">${ent(r.items.length)} tests : comparez les p ajustées (Benjamini-Hochberg), pas les p brutes.</p><//>`}</div>`;
}

// ---------------------------------------------------------------- corrélations
export function ResCorrelation({ r }) {
  const refT = useRef(), refP = useRef(), noms = r.variables.map((v) => nomVar(v, 26));
  return html`<div><${Bloc} titre=${`Matrice des corrélations (${r.coefficient || r.methode_correlation})`} outils=${html`<${BoutonsTable} refTable=${refT} titre="Corrélations" />`}>
      <div class="defile-x"><table class="t" ref=${refT}><thead><tr><th></th>${noms.map((n, j) => html`<th title=${titreComplet(r.variables[j])}>${court(n, 16)}</th>`)}</tr></thead><tbody>
        ${r.matrice.map((l, i) => html`<tr><td title=${titreComplet(r.variables[i])}>${noms[i]}</td>${l.map((x, j) => html`<td style=${i === j ? "color:var(--encre-3)" : fondCorr(x)} ...${i === j ? {} : bulle(`n = ${r.matrice_n[i][j]} · p = ${pval(r.matrice_p[i][j])} · p ajustée = ${pval(r.matrice_p_ajustee[i][j])}`)}>${i === j ? "1" : nf(x, 2)}</td>`)}</tr>`)}</tbody></table></div>
      <${Legende} items=${[{ label: "corrélation positive", couleur: "color-mix(in oklab, var(--s1) 45%, transparent)" }, { label: "corrélation négative", couleur: "color-mix(in oklab, var(--s8) 45%, transparent)" }]} /><//>
    <${Bloc} titre=${`Détail des ${r.n_tests} paires`} outils=${html`<${BoutonsTable} refTable=${refP} titre="Corrélations par paire" />`}>
      <table class="t" ref=${refP}><thead><tr><th>Paire</th><th>r</th><th>IC 95 %</th><th>n</th><th>p</th><th>p ajustée (${r.ajustement})</th></tr></thead><tbody>
        ${[...r.paires].sort((a, b) => Math.abs(b.r || 0) - Math.abs(a.r || 0)).map((p) => html`<tr><td>${nomVar(p.x, 30)} — ${nomVar(p.y, 30)}</td><td>${nf(p.r, 3)}</td><td class="muet">${p.ic_bas == null ? "" : `${nf(p.ic_bas, 2)} – ${nf(p.ic_haut, 2)}`}</td><td>${ent(p.n)}</td><td>${pval(p.p)}</td><td>${pval(p.p_ajustee)}</td></tr>`)}</tbody></table><//></div>`;
}

// ---------------------------------------------------------------- régression
export function ResRegression({ r }) {
  const refT = useRef(), refF = useRef(), refA = useRef();
  const log = r.modele === "logistique", multi = r.modele === "multinomiale", a = r.ajustement || {};
  const termes = (r.termes || []).filter((t) => !/onstante/.test(t.terme));
  const nomTerme = (t) => t.modalite != null ? `${nomVar(t.variable, 28)} : ${t.modalite}${t.reference ? " (réf.)" : ""}` : (V(t.variable) ? nomVar(t.variable, 44) : t.terme);
  const yv = r.y || {};
  return html`<div><${Bloc} titre=${log ? `Régression logistique — probabilité de « ${yv.modalite_cible} » (vs « ${yv.modalite_reference} »)` : multi ? `Régression multinomiale — référence : « ${yv.modalite_reference} »` : "Régression linéaire"}>
      <div class="grille" style="grid-template-columns:repeat(auto-fit,minmax(125px,1fr))"><${Stat} nom="Individus" valeur=${ent(r.n)} aide=${`${ent(r.n_exclus)} écarté(s) pour valeur manquante sur au moins une variable du modèle`} />
        ${log && html`<${Stat} nom=${`« ${court(String(yv.modalite_cible), 16)} »`} valeur=${`${ent(yv.n_cible)} (${pct(100 * yv.part_cible, 0)})`} />`}
        ${!log && !multi && html`<${Stat} nom="R²" valeur=${nf(a.r2, 3)} aide="Part de la variance de la variable à expliquer restituée par le modèle." /><${Stat} nom="R² ajusté" valeur=${nf(a.r2_ajuste, 3)} aide="Pénalise le nombre de variables." /><${Stat} nom="F global" valeur=${`p ${pval(a.p_f)}`} />`}
        ${(log || multi) && html`<${Stat} nom="Pseudo-R² (McFadden)" valeur=${nf(a.pseudo_r2_mcfadden, 3)} aide="Gain de vraisemblance par rapport au modèle sans variable. Ne se lit pas comme une part de variance ; 0,2 est déjà élevé." />
          ${a.pseudo_r2_nagelkerke != null && html`<${Stat} nom="Nagelkerke" valeur=${nf(a.pseudo_r2_nagelkerke, 3)} />`}<${Stat} nom="Test global (RV)" valeur=${`p ${pval(a.lr_p)}`} aide="Le modèle fait-il mieux que le modèle sans aucune variable ?" />`}
        <${Stat} nom="AIC" valeur=${nf(a.aic, 1)} aide="Pour comparer des modèles estimés sur les MÊMES individus : le plus petit est préférable." />
        ${log && r.classement && html`<${Stat} nom="AUC" valeur=${nf(r.classement.auc, 2)} aide=${r.classement.note} />`}
        ${r.diagnostics?.evenements_par_parametre != null && html`<${Stat} nom="Événements / paramètre" valeur=${nf(r.diagnostics.evenements_par_parametre, 1)} aide="Repère : au moins 10 pour des estimations stables." />`}</div><//>
    <${Bloc} titre="Coefficients" outils=${html`<${BoutonsTable} refTable=${refT} titre="Coefficients de régression" notes=${[`n = ${r.n}`]} />`}>
      <div class="defile-x"><table class="t" ref=${refT}><thead><tr><th>Terme</th>${multi && html`<th class="g">Modalité de Y</th>`}<th>Coefficient</th><th>Erreur type</th>${(log || multi) && html`<th>${multi ? "RRR" : "Odds ratio"}</th>`}<th>IC 95 %${(log || multi) ? " (OR)" : ""}</th><th>p</th><th>n</th></tr></thead><tbody>
        ${(r.termes || []).map((t) => html`<tr style=${t.reference ? "color:var(--encre-3);font-style:italic" : ""}><td>${/onstante/.test(t.terme) ? "Constante" : nomTerme(t)}</td>${multi && html`<td class="g">${t.modalite_y}</td>`}<td>${t.reference ? "0" : nf(t.coef, 3)}</td><td>${nf(t.se, 3)}</td>${(log || multi) && html`<td>${/onstante/.test(t.terme) ? "" : nf(t.odds_ratio ?? t.rrr ?? Math.exp(t.coef), 2)}</td>`}
          <td class="muet">${t.reference || t.ic_bas == null ? "" : (log || multi) ? `${nf(t.or_ic_bas ?? Math.exp(t.ic_bas), 2)} – ${nf(t.or_ic_haut ?? Math.exp(t.ic_haut), 2)}` : `${nf(t.ic_bas, 3)} – ${nf(t.ic_haut, 3)}`}</td><td>${t.reference ? "" : pval(t.p)}</td><td class="muet">${t.n ?? ""}</td></tr>`)}</tbody></table></div>
      ${r.robuste && html`<p class="aide-champ">Erreurs types robustes à l'hétéroscédasticité (${r.robuste}).</p>`}<//>
    ${!multi && html`<${Bloc} titre=${log ? "Odds ratios et intervalles de confiance (échelle logarithmique)" : "Coefficients et intervalles de confiance à 95 %"} outils=${html`<${BoutonsFigure} refSvg=${refF} nom="coefficients" />`}>
      <div ref=${refF}><${Intervalles} log=${log} reference=${log ? 1 : 0} titreAxe=${log ? "odds ratio (1 = pas de différence avec la référence)" : "coefficient (0 = pas d'association)"}
        lignes=${termes.map((t) => ({ label: nomTerme(t), valeur: t.reference ? (log ? 1 : 0) : (log ? t.odds_ratio : t.coef), bas: t.reference ? null : (log ? t.or_ic_bas : t.ic_bas), haut: t.reference ? null : (log ? t.or_ic_haut : t.ic_haut), ref: t.reference, n: t.n, nomValeur: log ? "odds ratio" : "coefficient" }))} /></div><//>`}
    ${log && (r.effets_marginaux || []).length > 0 && html`<${Bloc} titre="Effets marginaux moyens (en points de pourcentage)" outils=${html`<${BoutonsTable} refTable=${refA} titre="Effets marginaux moyens" />`}>
      <table class="t" ref=${refA}><thead><tr><th>Terme</th><th>Effet (points de %)</th><th>IC 95 %</th><th>p</th></tr></thead><tbody>${r.effets_marginaux.map((x) => html`<tr><td>${nomTerme(x)}</td><td>${nf(100 * x.ame, 1)}</td><td class="muet">${nf(100 * x.ic_bas, 1)} – ${nf(100 * x.ic_haut, 1)}</td><td>${pval(x.p)}</td></tr>`)}</tbody></table>
      <p class="aide-champ">Écart moyen de probabilité prédite : pour une modalité, par rapport à la référence ; pour une variable numérique, pour une unité de plus. Plus directement interprétable qu'un odds ratio.</p><//>`}
    ${(r.tests_variables || []).length > 0 && html`<${Bloc} titre="Contribution de chaque variable au modèle">
      <table class="t"><thead><tr><th>Variable</th><th>ddl</th><th>Statistique</th><th>p</th>${r.diagnostics?.vif?.length ? html`<th title="Facteur d'inflation de la variance généralisé, ramené à l'échelle d'un coefficient. Au-delà de 2,2 environ (soit un VIF de 5), la variable est fortement liée aux autres.">GVIF ajusté</th>` : ""}</tr></thead><tbody>
        ${r.tests_variables.map((t) => { const vif = (r.diagnostics?.vif || []).find((x) => x.terme === t.terme); return html`<tr><td>${V(t.terme) ? nomVar(t.terme, 50) : t.terme}</td><td>${t.ddl}</td><td>${nf(t.stat, 2)}</td><td>${pval(t.p)}</td>${r.diagnostics?.vif?.length ? html`<td>${vif ? nf(vif.gvif_ajuste, 2) : ""}</td>` : ""}</tr>`; })}</tbody></table>
      <p class="aide-champ">${r.methode?.tests_variables || ""}</p><//>`}</div>`;
}

// ---------------------------------------------------------------- exploration
export function ResExploration({ r, spec, pid }) {
  const refT = useRef();
  const ouvrir = (a) => { publier({ brouillon: { type: "croise", ligne: a.variable, colonne: spec.cible, population: spec.population } }); aller(`/p/${pid}/analyses/nouvelle`); };
  return html`<${Bloc} titre=${`${r.n_tests} variables confrontées à « ${nomVar(spec.cible, 50)} »`} outils=${html`<${BoutonsTable} refTable=${refT} titre="Exploration d'associations" notes=${[r.avertissement]} />`}>
    <div class="note alerte" style="margin-bottom:10px">${r.avertissement}</div>
    <div class="defile-x"><table class="t" ref=${refT}><thead><tr><th>Variable</th><th class="g">Mesure</th><th>Valeur</th><th style="width:110px">Intensité</th><th>IC 95 %</th><th>n</th><th>p brute</th><th title="Benjamini-Hochberg">p (BH)</th><th>p (Holm)</th><th></th></tr></thead><tbody>
      ${r.associations.map((a) => html`<tr class="cliquable" onClick=${() => ouvrir(a)} title="Ouvrir le croisement détaillé"><td title=${titreComplet(a.variable)}>${nomVar(a.variable, 46)}</td><td class="g muet">${a.mesure}</td><td>${nf(a.effet, 3)}</td>
        <td data-v=${a.intensite ?? ""}><div class="piste"><div class="barre-h" style=${`width:${100 * Math.min(1, a.intensite || 0)}%;opacity:${a.fragile ? 0.4 : 1}`}></div></div></td>
        <td class="muet">${a.ic_bas == null ? "" : `${nf(a.ic_bas, 2)} – ${nf(a.ic_haut, 2)}`}</td><td>${ent(a.n)}</td><td>${pval(a.p)}</td><td>${pval(a.p_bh)}</td><td>${pval(a.p_holm)}</td>
        <td class="g">${a.fragile ? html`<span class="badge" style="background:var(--alerte-fond);color:var(--alerte-encre)" title=${a.raisons_fragilite.join(" ; ")}>fragile</span>` : ""}</td></tr>`)}</tbody></table></div>
    ${(r.non_calculees || []).length > 0 && html`<p class="aide-champ">${r.non_calculees.length} variable(s) non analysables (trop peu de réponses communes) : ${r.non_calculees.slice(0, 6).map((x) => nomVar(x.variable, 30)).join(" ; ")}${r.non_calculees.length > 6 ? "…" : ""}</p>`}<//>`;
}

// ---------------------------------------------------------------- analyses factorielles
function useValeurs(pid, variable) {
  const [v, setV] = useState(null);
  useEffect(() => { setV(null); if (variable) api(`/p/${pid}/valeurs?variable=${variable}`).then((r) => setV({ ...r, parId: Object.fromEntries(r.ids.map((id, i) => [id, r.valeurs[i]])) })).catch((e) => toast(e.message, true)); }, [variable]);
  return v;
}
const titreAxe = (axes, k) => { const a = axes[k]; return a ? `Axe ${a.axe} — ${nf(a.pct, 1)} % de l'inertie${a.pct_modifie != null ? ` (taux modifié : ${nf(a.pct_modifie, 1)} %)` : ""}` : `Axe ${k + 1}`; };
const infoPoint = (titre, sous, lignes) => () => html`<div><b>${titre}</b>${sous && html`<div style="opacity:.8">${sous}</div>`}${lignes.filter((l) => l[1] != null && l[1] !== "—").map(([a, b]) => html`<div class="l"><span>${a}</span><span>${b}</span></div>`)}</div>`;

export function ResFactorielle({ r, spec, pid, majSpec }) {
  const nAxes = (r.individus?.coord?.[0] || r.lignes?.[0]?.coord || [0, 0]).length;
  const [ax, setAx] = useState([0, 1]);
  const [onglet, setOnglet] = useState("carte");
  const [voir, setVoir] = useState({ actives: true, sup: true, individus: r.methode === "acp", trajectoires: false, taille: true });
  const [etq, setEtq] = useState("principales");
  const [colorer, setColorer] = useState(null);
  const [sel, setSel] = useState(null);
  const [triAxe, setTriAxe] = useState(0);
  const refCarte = useRef(), refCercle = useRef(), refEb = useRef(), refT = useRef(), refS = useRef();
  const valeurs = useValeurs(pid, colorer);
  const [x, y] = ax, afc = r.methode === "afc", acm = r.methode.startsWith("acm");
  const mods = (r.modalites || []), actives = mods.filter((m) => !m.passive), passives = mods.filter((m) => m.passive);
  const varsActives = [...new Set(actives.map((m) => m.variable))];
  const couleurVar = (v) => varsActives.length <= 8 ? SERIES[varsActives.indexOf(v)] : SERIES[0];
  const moyenne = actives.length ? 100 / actives.length : 0;
  const quanti = (r.variables || []).filter((v) => v.type === "quanti");

  const { points, ellipses, liens, legende } = useMemo(() => {
    const pts = [], ell = [], li = [], leg = [];
    const maxC = Math.max(1e-9, ...actives.map((m) => (m.contrib?.[x] || 0) + (m.contrib?.[y] || 0)));
    if (afc) {
      for (const [cle, forme, coul, nom] of [["lignes", "rond", SERIES[0], nomVar(spec.ligne, 40)], ["colonnes", "carre", SERIES[1], nomVar(spec.colonne, 40)]]) {
        leg.push({ label: nom, couleur: coul, forme: forme === "rond" ? "rond" : "" });
        for (const p of r[cle]) pts.push({ id: cle + p.id, x: p.coord[x], y: p.coord[y], label: p.id, couleur: coul, forme, r: voir.taille ? 4 + 6 * Math.sqrt(((p.contrib[x] || 0) + (p.contrib[y] || 0)) / 200) : 5, priorite: 1 + (p.contrib[x] || 0) + (p.contrib[y] || 0),
          bulle: infoPoint(p.id, nom, [["contribution", `${nf(p.contrib[x], 1)} % / ${nf(p.contrib[y], 1)} %`], ["cos²", `${nf(p.cos2[x], 2)} / ${nf(p.cos2[y], 2)}`]]) });
        for (const p of (r.sup?.[cle] || [])) pts.push({ id: "sup" + cle + p.id, x: p.coord[x], y: p.coord[y], label: p.id, couleur: coul, forme, creux: true, priorite: 1, bulle: infoPoint(p.id, nom + " (supplémentaire)", [["cos²", `${nf(p.cos2?.[x], 2)} / ${nf(p.cos2?.[y], 2)}`]]) });
      }
      return { points: pts, ellipses: ell, liens: li, legende: leg };
    }
    if (voir.individus && r.individus) {
      const cats = valeurs?.modalites || [], parCat = {};
      r.individus.ids.forEach((id, i) => {
        const c = r.individus.coord[i], val = valeurs ? valeurs.parId[id] : null, k = cats.indexOf(val);
        if (valeurs && val != null && k >= 0) (parCat[val] = parCat[val] || []).push([c[x], c[y]]);
        pts.push({ id: "i" + id, x: c[x], y: c[y], fond: true, r: 2.6, opacite: valeurs ? 0.75 : 0.45, couleur: valeurs ? (k >= 0 && cats.length <= 8 ? SERIES[k] : "var(--neutre)") : "var(--neutre-2)",
          bulle: infoPoint(`Individu ${id}`, valeurs && val != null ? `${nomVar(colorer, 30)} : ${val}` : null, [["coordonnées", `${nf(c[x], 2)} ; ${nf(c[y], 2)}`], ["cos² (plan)", nf((r.individus.cos2[i][x] || 0) + (r.individus.cos2[i][y] || 0), 2)]]) });
      });
      if (valeurs && cats.length <= 8) cats.forEach((c, k) => { const e = ellipseConcentration(parCat[c] || []); if (e) { ell.push({ ...e, couleur: SERIES[k] }); pts.push({ id: "moy" + c, x: e.cx, y: e.cy, label: c, couleur: SERIES[k], forme: "losange", r: 6, priorite: 500, bulle: infoPoint(c, `Point moyen de ${e.n} individus — ${nomVar(colorer, 30)}`, [["coordonnées", `${nf(e.cx, 2)} ; ${nf(e.cy, 2)}`]]) }); leg.push({ label: `${c} (n=${e.n})`, couleur: SERIES[k] }); } });
      for (const [i, id] of (r.sup?.individus?.ids || []).entries()) { const c = r.sup.individus.coord[i]; pts.push({ id: "is" + id, x: c[x], y: c[y], fond: true, r: 2.6, couleur: SERIES[1], opacite: 0.7, bulle: infoPoint(`Individu supplémentaire ${id}`, null, [["coordonnées", `${nf(c[x], 2)} ; ${nf(c[y], 2)}`]]) }); }
      if (r.sup?.individus?.ids?.length) leg.push({ label: `individus supplémentaires (${r.sup.individus.ids.length})`, couleur: SERIES[1], forme: "rond" });
    }
    if (voir.actives) {
      for (const m of actives) {
        const c = (m.contrib[x] || 0) + (m.contrib[y] || 0), fort = m.contrib[x] > moyenne || m.contrib[y] > moyenne;
        pts.push({ id: m.id, x: m.coord[x], y: m.coord[y], label: varsActives.length > 1 ? nomMod(m, 18) : m.modalite, couleur: couleurVar(m.variable), r: voir.taille ? 3.5 + 7 * Math.sqrt(c / maxC) : 5, priorite: fort ? 10 + c : 0, estompe: etq === "principales" && !fort, meta: m,
          bulle: infoPoint(m.modalite, nomVar(m.variable, 60), [["effectif", ent(m.n)], ["coordonnées", `${nf(m.coord[x], 2)} ; ${nf(m.coord[y], 2)}`], [`contribution axe ${x + 1} / ${y + 1}`, `${nf(m.contrib[x], 1)} % / ${nf(m.contrib[y], 1)} %`], ["cos²", `${nf(m.cos2[x], 2)} / ${nf(m.cos2[y], 2)}`]]) });
      }
      if (varsActives.length > 1 && varsActives.length <= 8) varsActives.forEach((v) => leg.push({ label: nomVar(v, 30), couleur: couleurVar(v), forme: "rond" }));
      if (voir.trajectoires) for (const v of varsActives) { const ms = actives.filter((m) => m.variable === v); if (V(v)?.ordonnee && ms.length > 2) li.push({ points: ms.map((m) => [m.coord[x], m.coord[y]]), couleur: couleurVar(v) }); }
    }
    if (voir.sup) for (const m of (r.sup?.modalites || [])) {
      const vt = Math.max(Math.abs(m.vtest?.[x] || 0), Math.abs(m.vtest?.[y] || 0));
      pts.push({ id: "s" + m.id, x: m.coord[x], y: m.coord[y], label: nomMod(m, 16), couleur: "var(--encre-2)", forme: "losange", creux: true, r: 5, priorite: vt > 2 ? 5 + vt : 0, estompe: etq === "principales" && vt <= 2, meta: m, sup: true,
        bulle: infoPoint(m.modalite, nomVar(m.variable, 60) + " — supplémentaire", [["effectif", ent(m.n)], ["coordonnées", `${nf(m.coord[x], 2)} ; ${nf(m.coord[y], 2)}`], [`valeur-test axe ${x + 1} / ${y + 1}`, `${nf(m.vtest?.[x], 1)} / ${nf(m.vtest?.[y], 1)}`], ["cos²", `${nf(m.cos2?.[x], 2)} / ${nf(m.cos2?.[y], 2)}`]]) });
    }
    if (voir.sup && (r.sup?.modalites || []).length) leg.push({ label: "modalités supplémentaires", couleur: "var(--encre-2)", forme: "contour" });
    return { points: pts, ellipses: ell, liens: li, legende: leg };
  }, [r, x, y, voir, etq, valeurs]);

  // cercle des corrélations (ACP, AFDM, variables numériques supplémentaires)
  const fleches = [...quanti.map((v) => ({ ...v, sup: false })), ...(r.sup?.variables || []).filter((v) => v.type === "quanti" || v.cor || (v.coord && !v.eta2)).map((v) => ({ ...v, sup: true }))];
  const cercle = fleches.length ? { points: fleches.map((v) => { const c = v.cor || v.coord; return { id: v.id, x: c[x], y: c[y], label: nomVar(v.id, 26), couleur: v.sup ? "var(--encre-2)" : SERIES[0], creux: v.sup, r: 4.5, priorite: 1 + Math.abs(c[x]) + Math.abs(c[y]), bulle: infoPoint(nomVar(v.id, 60), v.sup ? "supplémentaire" : "active", [[`corrélation axe ${x + 1} / ${y + 1}`, `${nf(c[x], 2)} / ${nf(c[y], 2)}`], ["contribution", v.contrib ? `${nf(v.contrib[x], 1)} % / ${nf(v.contrib[y], 1)} %` : null]]) }; }),
    liens: fleches.map((v) => { const c = v.cor || v.coord; return { points: [[0, 0], [c[x], c[y]]], couleur: v.sup ? "var(--encre-3)" : SERIES[0] }; }), ellipses: [{ cx: 0, cy: 0, rx: 1, ry: 1, angle: 0, couleur: "var(--axe)" }] } : null;

  const selM = sel?.meta;
  const agirSpec = (modif, message) => { majSpec(modif); setSel(null); toast(message); };
  const choixAxes = html`<span class="ligne petit">Axes <select class="champ" style="width:auto;padding:3px 6px" value=${x} onChange=${(e) => setAx([+e.target.value, y])}>${Array.from({ length: nAxes }, (_, k) => html`<option value=${k}>${k + 1}</option>`)}</select> × <select class="champ" style="width:auto;padding:3px 6px" value=${y} onChange=${(e) => setAx([x, +e.target.value])}>${Array.from({ length: nAxes }, (_, k) => html`<option value=${k}>${k + 1}</option>`)}</select></span>`;
  const coche = (cle, lib, titre) => html`<label class="ligne petit" title=${titre || ""} style="gap:4px"><input type="checkbox" checked=${voir[cle]} onChange=${(e) => setVoir({ ...voir, [cle]: e.target.checked })} /> ${lib}</label>`;
  const lignesTable = afc ? [...r.lignes.map((p) => ({ ...p, groupe: nomVar(spec.ligne, 30) })), ...r.colonnes.map((p) => ({ ...p, groupe: nomVar(spec.colonne, 30) }))] : actives;
  const tries = [...lignesTable].sort((a, b) => (b.contrib?.[triAxe] || 0) - (a.contrib?.[triAxe] || 0));
  const onglets = [["carte", "Carte"], ["axes", "Axes et inertie"], ["elements", afc ? "Lignes et colonnes" : acm || mods.length ? "Modalités" : "Variables"], ...(r.variables?.length && (acm || mods.length) ? [["variables", "Variables"]] : []), ...((r.sup?.modalites?.length || r.sup?.variables?.length) ? [["sup", "Supplémentaires"]] : [])];
  return html`<div>
    <${Onglets} onglets=${onglets} actif=${onglet} onChange=${setOnglet} />
    ${onglet === "carte" && html`<div><${Bloc} titre=${afc ? "Carte des lignes et des colonnes" : r.methode === "acp" ? "Nuage des individus" : "Carte des modalités"} outils=${html`${choixAxes}<${BoutonsFigure} refSvg=${refCarte} nom=${`carte_axes_${x + 1}_${y + 1}`} />`}>
        <div class="ligne" style="flex-wrap:wrap;gap:6px 14px;margin-bottom:8px">
          ${!afc && mods.length > 0 && coche("actives", "modalités actives")}${!afc && coche("sup", "supplémentaires")}${!afc && coche("individus", "individus")}
          ${coche("taille", "taille selon la contribution", "La surface du point croît avec sa contribution au plan affiché")}
          ${!afc && mods.length > 0 && coche("trajectoires", "relier les modalités ordonnées", "Relie dans l'ordre les modalités des variables ordinales : une trajectoire régulière le long d'un axe aide à l'interpréter")}
          <span class="ligne petit">Étiquettes <${Segments} options=${[["principales", "principales", "Modalités de contribution supérieure à la moyenne ; supplémentaires de valeur-test > 2"], ["toutes", "toutes"], ["aucune", "aucune"]]} valeur=${etq} onChange=${setEtq} /></span></div>
        ${!afc && voir.individus && html`<div class="ligne" style="margin-bottom:8px"><span class="petit secondaire nowrap">Colorer les individus selon</span><div style="flex:1;max-width:420px"><${ChoixVariable} valeur=${colorer} types=${CATEGORIELS} onChange=${setColorer} placeholder="une variable (points moyens et ellipses de concentration)…" /></div></div>`}
        <div ref=${refCarte}><${Carte} points=${points} ellipses=${ellipses} liens=${liens} legende=${legende} etiquettes=${etq} titreX=${titreAxe(r.axes, x)} titreY=${titreAxe(r.axes, y)} selection=${sel?.id} onClic=${(p) => setSel(p.meta ? p : null)} /></div>
        <p class="aide-champ">Molette : zoom · glisser : déplacer · double-clic : recadrer · clic sur une modalité : détails et actions. Les deux axes ont la même échelle : les distances se comparent.</p>
        ${selM && html`<div class="note info" style="margin-top:8px"><div class="ligne" style="flex-wrap:wrap"><b>${selM.modalite}</b><span>— ${nomVar(selM.variable, 70)} · n = ${ent(selM.n)}</span>
          <span class="pousse ligne" style="flex-wrap:wrap"><button class="btn petit" onClick=${() => aller(`/p/${pid}/donnees/${selM.variable}`)}>Fiche de la variable</button>
          ${!sel.sup && acm && html`<button class="btn petit" title="La modalité ne participe plus à la construction des axes ; les individus restent dans l'analyse (ACM spécifique)" onClick=${() => agirSpec({ passives: [...(spec.passives || []), [selM.variable, selM.modalite]] }, "Modalité rendue passive — analyse recalculée")}>Rendre passive</button>
            <button class="btn petit" onClick=${() => agirSpec({ actives: spec.actives.filter((v) => v !== selM.variable), sup_quali: [...(spec.sup_quali || []), selM.variable] }, "Variable passée en supplémentaire — analyse recalculée")}>Passer la variable en supplémentaire</button>`}
          ${sel.sup && html`<button class="btn petit" onClick=${() => agirSpec({ sup_quali: (spec.sup_quali || []).filter((v) => v !== selM.variable) }, "Variable retirée")}>Retirer la variable</button>`}</span></div></div>`}<//>
      ${cercle && html`<${Bloc} titre="Cercle des corrélations (variables numériques)" outils=${html`<${BoutonsFigure} refSvg=${refCercle} nom="cercle_correlations" />`}><div ref=${refCercle}><${Carte} points=${cercle.points} liens=${cercle.liens} ellipses=${cercle.ellipses} etiquettes="toutes" titreX=${titreAxe(r.axes, x)} titreY=${titreAxe(r.axes, y)} largeur=${520} hauteur=${500} legende=${fleches.some((f) => f.sup) ? [{ label: "active", couleur: SERIES[0], forme: "rond" }, { label: "supplémentaire", couleur: "var(--encre-2)", forme: "contour" }] : null} /></div><//>`}
      ${passives.length > 0 && html`<div class="note">Modalités passives (hors construction des axes) : ${passives.map((m) => html`<span class="puce" style="margin:2px">${nomMod(m, 20)} (${ent(m.n)})${(spec.passives || []).some((p) => p[0] === m.variable && p[1] === m.modalite) ? html`<button title="Rendre de nouveau active" onClick=${() => agirSpec({ passives: spec.passives.filter((p) => !(p[0] === m.variable && p[1] === m.modalite)) }, "Modalité de nouveau active")}>×</button>` : ""}</span>`)}</div>`}</div>`}
    ${onglet === "axes" && html`<div><${Bloc} titre="Éboulis des valeurs propres" outils=${html`<${BoutonsFigure} refSvg=${refEb} nom="eboulis" />`}><div ref=${refEb}><${Eboulis} axes=${r.axes} choisis=${[x + 1, y + 1]} /></div>
        <p class="aide-champ">Inertie totale : ${nf(r.inertie_totale, 4)}. ${acm ? "En ACM, les taux bruts sous-estiment toujours l'importance des premiers axes : les taux modifiés de Benzécri en donnent une idée plus juste." : ""}</p><//>
      <${Bloc} titre="Valeurs propres" outils=${html`<${BoutonsTable} refTable=${refT} titre="Valeurs propres" />`}><table class="t" ref=${refT}><thead><tr><th>Axe</th><th>Valeur propre</th><th>% d'inertie</th><th>% cumulé</th>${acm && html`<th>Taux modifié (Benzécri)</th><th>Cumulé</th>`}</tr></thead><tbody>
        ${r.axes.slice(0, 15).map((a) => html`<tr><td>${a.axe}</td><td>${nf(a.valeur_propre, 4)}</td><td>${nf(a.pct, 1)}</td><td>${nf(a.pct_cumule, 1)}</td>${acm && html`<td>${a.pct_modifie == null ? "" : nf(a.pct_modifie, 1)}</td><td>${a.pct_modifie_cumule == null ? "" : nf(a.pct_modifie_cumule, 1)}</td>`}</tr>`)}</tbody></table><//></div>`}
    ${onglet === "elements" && html`<${Bloc} titre=${`Coordonnées, contributions et qualité de représentation — triées par contribution à l'axe ${triAxe + 1}`} outils=${html`<span class="ligne petit">Trier sur l'axe <${Segments} options=${[[x, String(x + 1)], [y, String(y + 1)]]} valeur=${triAxe} onChange=${setTriAxe} /></span><${BoutonsTable} refTable=${refT} titre="Modalités" />`}>
      <div class="defile-x"><table class="t" ref=${refT}><thead><tr><th>${afc ? "Élément" : mods.length ? "Modalité" : "Variable"}</th>${mods.length || afc ? html`<th>n</th>` : ""}${[x, y].map((k) => html`<th>Coord. ${k + 1}</th><th>Contrib. ${k + 1} (%)</th><th>cos² ${k + 1}</th>`)}</tr></thead><tbody>
        ${(mods.length || afc ? tries : [...quanti].sort((a, b) => (b.contrib?.[triAxe] || 0) - (a.contrib?.[triAxe] || 0))).map((m) => html`<tr class=${m.variable ? "cliquable" : ""} onClick=${m.variable ? () => aller(`/p/${pid}/donnees/${m.variable}`) : null}><td>${afc ? html`${m.id} <span class="muet">· ${m.groupe}</span>` : m.variable ? nomMod(m, 30) : nomVar(m.id, 50)}</td>${mods.length || afc ? html`<td>${ent(m.n ?? m.poids)}</td>` : ""}
          ${[x, y].map((k) => html`<td>${nf(m.coord[k], 2)}</td><td style=${(m.contrib?.[k] || 0) > (afc ? 100 / (r.lignes.length) : mods.length ? moyenne : 100 / (quanti.length || 1)) ? "font-weight:600" : "color:var(--encre-3)"}>${nf(m.contrib?.[k], 1)}</td><td>${nf(m.cos2?.[k], 2)}</td>`)}</tr>`)}</tbody></table></div>
      <p class="aide-champ">En gras : contribution supérieure à la moyenne${mods.length ? ` (${nf(moyenne, 1)} %)` : ""} — ce sont les éléments sur lesquels fonder l'interprétation de l'axe, en opposant coordonnées positives et négatives.</p><//>`}
    ${onglet === "variables" && html`<${Bloc} titre="Variables : contribution cumulée et rapport de corrélation (eta²)" outils=${html`<${BoutonsTable} refTable=${refT} titre="Variables" />`}>
      <table class="t" ref=${refT}><thead><tr><th>Variable</th>${[x, y].map((k) => html`<th>Contrib. ${k + 1} (%)</th><th>eta² ${k + 1}</th>`)}</tr></thead><tbody>
        ${[...r.variables].sort((a, b) => (b.contrib?.[x] || 0) - (a.contrib?.[x] || 0)).map((v) => html`<tr class="cliquable" onClick=${() => aller(`/p/${pid}/donnees/${v.id}`)}><td title=${titreComplet(v.id)}>${nomVar(v.id, 60)}</td>${[x, y].map((k) => html`<td>${nf(v.contrib?.[k], 1)}</td><td>${nf((v.eta2 || v.cos2)?.[k], 2)}</td>`)}</tr>`)}</tbody></table>
      <p class="aide-champ">eta² : part de la variance des coordonnées des individus sur l'axe qui tient à la variable (0 à 1). Une variable dont plusieurs modalités contribuent structure l'axe.</p><//>`}
    ${onglet === "sup" && html`<${Bloc} titre="Éléments supplémentaires (projetés, sans influence sur les axes)" outils=${html`<${BoutonsTable} refTable=${refS} titre="Supplémentaires" />`}>
      <div class="defile-x"><table class="t" ref=${refS}><thead><tr><th>Élément</th><th>n</th>${[x, y].map((k) => html`<th>Coord. ${k + 1}</th><th>Valeur-test ${k + 1}</th><th>cos² ${k + 1}</th>`)}</tr></thead><tbody>
        ${(r.sup?.modalites || []).map((m) => html`<tr><td>${nomMod(m, 30)}</td><td>${ent(m.n)}</td>${[x, y].map((k) => html`<td>${nf(m.coord[k], 2)}</td><td style=${Math.abs(m.vtest?.[k] || 0) > 2 ? "font-weight:600" : "color:var(--encre-3)"}>${nf(m.vtest?.[k], 1)}</td><td>${nf(m.cos2?.[k], 2)}</td>`)}</tr>`)}
        ${(r.sup?.variables || []).filter((v) => v.cor || v.type === "quanti").map((v) => { const c = v.cor || v.coord; return html`<tr><td>${nomVar(v.id, 40)} <span class="muet">(corrélation)</span></td><td>${ent(v.n)}</td>${[x, y].map((k) => html`<td>${nf(c?.[k], 2)}</td><td></td><td>${nf(v.cos2?.[k], 2)}</td>`)}</tr>`; })}</tbody></table></div>
      ${(r.sup?.variables || []).some((v) => v.eta2) && html`<table class="t" style="margin-top:14px"><thead><tr><th>Variable supplémentaire</th>${[x, y].map((k) => html`<th>eta² axe ${k + 1}</th>`)}</tr></thead><tbody>${r.sup.variables.filter((v) => v.eta2).map((v) => html`<tr><td>${nomVar(v.id, 60)}</td>${[x, y].map((k) => html`<td>${nf(v.eta2[k], 3)}</td>`)}</tr>`)}</tbody></table>`}
      <p class="aide-champ">En gras : valeur-test > 2 en valeur absolue (position qui s'écarte de l'origine au-delà de ce que donnerait le hasard). Écart entre deux modalités : notable au-delà de 0,5, important au-delà de 1.</p><//>`}
  </div>`;
}

// ---------------------------------------------------------------- classification
export function ResCah({ r, spec, pid, majSpec, analyseId, enregistrer }) {
  const refD = useRef(), refC = useRef(), refT = useRef();
  const [classe, setClasse] = useState(1);
  const f = r.factorielle, d = r.description;
  const parId = Object.fromEntries(r.ids.map((id, i) => [id, r.partition[i]]));
  const points = [], ell = [];
  const parClasse = {};
  f.individus.ids.forEach((id, i) => { const c = f.individus.coord[i], k = parId[id]; (parClasse[k] = parClasse[k] || []).push([c[0], c[1]]); points.push({ id: "i" + id, x: c[0], y: c[1], fond: true, r: 3, opacite: 0.75, couleur: SERIES[(k - 1) % 8], bulle: () => html`<div><b>Individu ${id}</b><div>Classe ${k}</div></div>` }); });
  Object.entries(parClasse).forEach(([k, pts]) => { const e = ellipseConcentration(pts); if (e) { ell.push({ ...e, couleur: SERIES[(k - 1) % 8] }); points.push({ id: "c" + k, x: e.cx, y: e.cy, label: `Classe ${k}`, couleur: SERIES[(k - 1) % 8], forme: "losange", r: 6.5, priorite: 100 }); } });
  const dc = d.par_classe.find((x) => x.classe === classe) || d.par_classe[0];
  const creerVariable = async () => {
    let id = analyseId;
    if (!id) { id = await enregistrer(); if (!id) return; }
    await agir("/recette", { methode: "POST", corps: { type: "partition", params: { analyse: id, cible: { nom: `classe_${id}`, libelle: `Classes (${r.k}) — classification ${id}` } }, note: "" } }, "Les classes sont maintenant une variable (voir Préparation)");
  };
  return html`<div>
    <${Bloc} titre=${`${r.k} classes — ${nf(r.pct_inter, 1)} % de l'inertie entre les classes`} outils=${html`<button class="btn petit" onClick=${creerVariable} title="Ajoute une étape à la recette : la variable suivra la classification si vous la modifiez">Enregistrer les classes comme variable</button>`}>
      <div class="ligne" style="flex-wrap:wrap;margin-bottom:10px"><span class="petit secondaire">Nombre de classes</span><${Segments} options=${r.gains.slice(0, 9).map((g) => [g.k, String(g.k), `${nf(g.pct_inter, 1)} % d'inertie inter-classes`])} valeur=${r.k} onChange=${(k) => majSpec({ k })} />
        <span class="petit muet">suggestion : ${r.k_suggere}${spec.k ? html` · <a href="#" onClick=${(e) => { e.preventDefault(); majSpec({ k: null }); }}>revenir à la suggestion</a>` : ""}</span></div>
      <table class="t" ref=${refT}><thead><tr><th>Classe</th><th>Effectif</th><th>%</th><th>Inertie intra</th><th class="g">Individus les plus typiques (parangons)</th></tr></thead><tbody>
        ${r.classes.map((c) => html`<tr class="cliquable" onClick=${() => setClasse(c.classe)}><td><i style=${`display:inline-block;width:10px;height:10px;border-radius:50%;background:${SERIES[(c.classe - 1) % 8]};margin-right:6px`}></i>Classe ${c.classe}</td><td>${ent(c.n)}${c.n < 10 ? html` <span style="color:var(--alerte-encre)" title="Classe de moins de 10 individus">▲</span>` : ""}</td><td>${nf(c.pct, 1)}</td><td>${nf(c.inertie_intra, 3)}</td><td class="g muet">${c.parangons.slice(0, 4).map((p) => p.id).join(", ")}</td></tr>`)}</tbody></table>
      <p class="aide-champ">Classification sur les ${f.n_axes_utilises} premiers axes (${nf(f.pct_inertie_utilisee, 1)} % de l'inertie)${r.consolidation?.effectuee ? ` ; consolidation : ${r.consolidation.deplaces} individu(s) réaffecté(s)` : ""}.</p><//>
    <${Bloc} titre="Arbre hiérarchique (dendrogramme)" outils=${html`<${BoutonsFigure} refSvg=${refD} nom="dendrogramme" />`}><div ref=${refD}><${Dendrogramme} d=${r.dendrogramme} k=${r.k} /></div>
      <p class="aide-champ">Hauteur d'un nœud : inertie perdue en fusionnant deux groupes. Un grand saut entre deux niveaux indique une coupure naturelle.${r.dendrogramme.tronque ? " L'arbre est tronqué à ses derniers nœuds." : ""}</p><//>
    <${Bloc} titre="Les classes dans le premier plan factoriel" outils=${html`<${BoutonsFigure} refSvg=${refC} nom="classes" />`}><div ref=${refC}><${Carte} points=${points} ellipses=${ell} etiquettes="toutes" titreX=${titreAxe(f.axes, 0)} titreY=${titreAxe(f.axes, 1)} hauteur=${460} /></div><//>
    <${Bloc} titre="Ce qui caractérise chaque classe" outils=${html`<${Segments} options=${d.par_classe.map((c) => [c.classe, `Classe ${c.classe}`])} valeur=${dc.classe} onChange=${setClasse} />`}>
      <table class="t"><thead><tr><th>Modalité</th><th title="Part des membres de la classe ayant cette modalité">% dans la classe</th><th>% dans l'ensemble</th><th title="Part des porteurs de la modalité qui sont dans la classe">% de la modalité dans la classe</th><th>Valeur-test</th></tr></thead><tbody>
        ${dc.modalites.filter((m) => Math.abs(m.vtest) >= 2).sort((a, b) => b.vtest - a.vtest).map((m) => html`<tr><td>${nomVar(m.variable, 30)} : ${m.modalite}</td><td>${nf(m.mod_cla, 1)}</td><td>${nf(m.global, 1)}</td><td>${nf(m.cla_mod, 1)}</td><td style=${fondResidu(m.vtest)}>${nf(m.vtest, 1)}</td></tr>`)}
        ${dc.modalites.filter((m) => Math.abs(m.vtest) >= 2).length === 0 && html`<tr><td colspan="5" class="muet">Aucune modalité ne distingue nettement cette classe (|valeur-test| < 2).</td></tr>`}</tbody></table>
      ${(dc.quanti || []).length > 0 && html`<table class="t" style="margin-top:14px"><thead><tr><th>Variable numérique</th><th>Moyenne dans la classe</th><th>Moyenne d'ensemble</th><th>Valeur-test</th></tr></thead><tbody>${dc.quanti.map((q) => html`<tr><td>${nomVar(q.variable, 50)}</td><td>${nf(q.moyenne_classe, 2)}</td><td>${nf(q.moyenne_globale, 2)}</td><td style=${fondResidu(q.vtest)}>${nf(q.vtest, 1)}</td></tr>`)}</tbody></table>`}
      <p class="aide-champ">Seules les modalités de valeur-test supérieure à 2 en valeur absolue sont listées (bleu : sur-représentée dans la classe ; rouge : sous-représentée). Les variables actives décrivent mécaniquement les classes ; ce sont les variables supplémentaires qui disent à qui elles correspondent.</p><//>
  </div>`;
}
