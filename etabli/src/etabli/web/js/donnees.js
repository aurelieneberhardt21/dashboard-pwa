// Vue « Données » : s'orienter dans le questionnaire, lire une variable, documenter le dictionnaire.
import { html, useState, useEffect, useMemo, api, magasin, useMagasin, publier, agir, aller, toast, ent, pct, nf, court, nomVar, titreComplet, TYPES, CATEGORIELS, Badge, Icone, Modale, EditeurCondition, bulle, libelleModalite } from "./base.js";
import { Histogramme, Legende } from "./graphiques.js";

export const COULEURS_STATUT = { valide: "var(--s1)", nsp: "var(--s5)", nr: "var(--s2)", vide: "var(--s4)", exclu: "var(--s7)", filtre: "var(--neutre)", abandon: "var(--neutre-2)" };
const ORDRE_STATUT = ["valide", "nsp", "nr", "vide", "exclu", "filtre", "abandon"];
const GENRES = { simple: "question simple", multiple: "choix multiples", matrice: "matrice", matrice_num: "matrice numérique", groupe: "groupe", technique: "technique" };

/** Barre empilée des statuts de réponse + légende chiffrée. */
export function Statuts({ statuts, legende = true }) {
  const etat = magasin.etat, total = ORDRE_STATUT.reduce((s, k) => s + (statuts[k] || 0), 0) || 1;
  const presents = ORDRE_STATUT.filter((k) => statuts[k] > 0);
  return html`<div>
    <div class="empile" style="height:12px">${presents.map((k) => html`<span style=${`width:${100 * statuts[k] / total}%;background:${COULEURS_STATUT[k]}`} ...${bulle(`${etat.statuts[k]} : ${ent(statuts[k])} (${pct(100 * statuts[k] / total)})`)}></span>`)}</div>
    ${legende && html`<div class="legende">${presents.map((k) => html`<span><i style=${`background:${COULEURS_STATUT[k]}`}></i>${etat.statuts[k]} : <b>${ent(statuts[k])}</b></span>`)}</div>`}
  </div>`;
}

/** Variable à laquelle une partie seulement des répondants l'ayant atteinte a répondu, sans champ documenté. */
const aDocumenter = (v) => v.role === "analyse" && !v.derive && !v.champ && v.type !== "vide" && v.n_vide > 0 && v.n_valide < 0.9 * (v.n_atteint || 1);

function ouvrirAnalyse(pid, spec) { publier({ brouillon: spec }); aller(`/p/${pid}/analyses/nouvelle`); }

// ---------------------------------------------------------------- liste
function Liste({ pid, selection }) {
  const e = useMagasin().etat;
  const [q, setQ] = useState("");
  const [filtre, setFiltre] = useState("toutes");
  const norm = (t) => (t || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const termes = norm(q).split(/\s+/).filter(Boolean);
  const derivees = Object.values(e.variables).filter((v) => v.derive);
  const questions = useMemo(() => Object.values(e.questions).sort((a, b) => (e.variables[a.variables[0]]?.colonne ?? 0) - (e.variables[b.variables[0]]?.colonne ?? 0)), [e]);
  const correspond = (qu) => {
    const vars = qu.variables.map((id) => e.variables[id]).filter(Boolean);
    if (filtre === "a_documenter" && !(qu.genre !== "technique" && vars.some((v) => aDocumenter(v)))) return false;
    if (filtre === "ouvertes" && !vars.some((v) => v.type === "texte" && v.role === "analyse")) return false;
    if (!termes.length) return true;
    const t = norm(qu.libelle + " " + vars.map((v) => (v.sous_libelle || "") + " " + (v.nom || "") + " " + (v.modalites || []).map((m) => m.valeur).join(" ")).join(" "));
    return termes.every((x) => t.includes(x));
  };
  const visibles = questions.filter(correspond);
  const tech = visibles.filter((qu) => qu.genre === "technique"), autres = visibles.filter((qu) => qu.genre !== "technique");
  const ligneQ = (qu) => {
    const vars = qu.variables.map((id) => e.variables[id]).filter(Boolean), v0 = vars[0];
    if (!v0) return null;
    const n = Math.max(...vars.map((v) => v.n_valide)), actif = selection === qu.id || vars.some((v) => v.id === selection);
    const cible = vars.length === 1 ? v0.id : qu.id;
    return html`<div><div class=${"q" + (actif ? " actif" : "")} onClick=${() => aller(`/p/${pid}/donnees/${cible}`)}>
        <div class="lib clamp2">${qu.precision_de ? html`<span class="muet">↳ </span>` : ""}${v0.nom !== v0.id && vars.length === 1 ? html`<b>${v0.nom}</b> · ` : ""}${qu.libelle}</div>
        <div class="meta">${vars.length > 1 ? html`<span class="badge">${GENRES[qu.genre]} · ${vars.length} items</span>` : html`<${Badge} v=${v0} />`}
          ${v0.role === "sensible" && html`<span class="badge" style="background:var(--critique-fond);color:var(--critique)">sensible</span>`}
          <span class="taux" title="Part des répondants ayant une réponse"><span style=${`width:${100 * n / (e.n_base || 1)}%`}></span></span><span>${ent(n)}</span>
          ${qu.genre !== "technique" && qu.genre !== "multiple" && aDocumenter(v0) && html`<span title="Champ de la question non documenté : on ne sait pas distinguer « non concerné » et « non-réponse »" style="color:var(--alerte-encre)">champ ?</span>`}</div>
      </div>
      ${actif && vars.length > 1 && vars.map((v) => html`<div class=${"q item" + (selection === v.id ? " actif" : "")} onClick=${() => aller(`/p/${pid}/donnees/${v.id}`)}><div class="lib tronque">${v.sous_libelle || v.libelle}</div><span class="mini muet">${ent(v.n_valide)}</span></div>`)}</div>`;
  };
  return html`<div class="colonne liste">
    <div class="recherche">
      <input class="champ" placeholder="Chercher une question, un item, une modalité…" value=${q} onInput=${(ev) => setQ(ev.target.value)} />
      <div class="ligne" style="margin-top:7px;gap:4px;flex-wrap:wrap">${[["toutes", "Toutes"], ["a_documenter", "Champ à documenter"], ["ouvertes", "Questions ouvertes"]].map(([id, lib]) => html`<button class=${"btn petit" + (filtre === id ? " primaire" : "")} onClick=${() => setFiltre(id)}>${lib}</button>`)}</div>
    </div>
    ${derivees.length > 0 && filtre === "toutes" && html`<div class="section-titre">Variables construites (${derivees.length})</div>
      ${derivees.filter((v) => !termes.length || termes.every((x) => norm(v.nom + " " + v.libelle).includes(x))).map((v) => html`<div class=${"q" + (selection === v.id ? " actif" : "")} onClick=${() => aller(`/p/${pid}/donnees/${v.id}`)}>
        <div class="lib"><b>${v.nom}</b>${v.libelle !== v.nom ? " · " + court(v.libelle, 60) : ""}</div><div class="meta"><${Badge} v=${v} /><span>${ent(v.n_valide)}</span></div></div>`)}`}
    <div class="section-titre">Questionnaire (${autres.length} question${autres.length > 1 ? "s" : ""})</div>
    ${autres.map(ligneQ)}
    ${tech.length > 0 && html`<div class="section-titre">Paradonnées (ajoutées par l'outil d'enquête)</div>${tech.map(ligneQ)}`}
  </div>`;
}

// ---------------------------------------------------------------- champ d'une question
function Champ({ variables }) {
  const e = magasin.etat, v0 = e.variables[variables[0]];
  const [edition, setEdition] = useState(null);
  if (!v0 || v0.derive) return null;
  const appliquer = (champ, quoi) => agir("/variables", { methode: "PATCH", corps: { description: `Champ de « ${court(v0.libelle, 50)} » : ${quoi}`, modifications: variables.map((id) => ({ id, champ })) } }, "Champ enregistré").then(() => setEdition(null));
  return html`<div class="carte">
    <div class="ligne espace"><h3>Champ de la question</h3>
      <span class="ligne"><button class="btn petit" onClick=${() => appliquer({ tous: true }, "tous les répondants")}>Posée à tous</button>
      <button class="btn petit" onClick=${() => setEdition(v0.champ && !v0.champ.tous ? v0.champ : { op: "et", regles: [] })}>Définir une condition…</button>
      ${v0.champ && html`<button class="btn discret petit" onClick=${() => appliquer(null, "non documenté")}>Effacer</button>`}</span></div>
    <p style="margin-top:6px">${!v0.champ ? html`<span style="color:var(--alerte-encre)">Non documenté.</span> <span class="secondaire">Les cellules vides sont comptées « vide (champ non documenté) » : on ne sait pas si la question n'a pas été posée ou si la personne n'a pas répondu.</span>`
      : v0.champ.tous ? html`Posée à <b>tous les répondants</b> : une cellule vide est une non-réponse.` : html`Posée si <b>${v0.champ_texte}</b>. <span class="secondaire">Hors de ce champ : « non concerné ». Dans ce champ, sans réponse : « non-réponse ».</span>`}</p>
    <details class="aide"><summary>Pourquoi documenter le champ ?</summary><div class="aide-texte">Un pourcentage n'a de sens que rapporté à ceux à qui la question a été posée. LimeSurvey laisse la même cellule vide pour « question non présentée » et « question passée » (sauf pour les cases à cocher, exportées « N/A »). En décrivant le champ, vous permettez à Établi de séparer les <b>non concernés</b>, qui sortent du dénominateur, des <b>non-réponses</b>, qui sont une information sur la question elle-même. Les personnes ayant abandonné avant la question sont repérées à part (« non atteint »).</div></details>
    ${edition && html`<${Modale} titre="À qui cette question a-t-elle été posée ?" onFermer=${() => setEdition(null)} pied=${html`<button class="btn" onClick=${() => setEdition(null)}>Annuler</button><button class="btn primaire" onClick=${() => appliquer(edition, "condition")}>Enregistrer le champ</button>`}>
      <p class="secondaire petit">${court(v0.libelle, 200)}${variables.length > 1 ? ` — la condition s'applique aux ${variables.length} items de la question.` : ""}</p>
      <${EditeurCondition} valeur=${edition} onChange=${setEdition} /><//>`}
  </div>`;
}

// ---------------------------------------------------------------- fiche d'une variable
function FicheVariable({ pid, vid }) {
  const m = useMagasin(), e = m.etat, v = e.variables[vid];
  const [fiche, setFiche] = useState(null);
  const [pop, setPop] = useState("");
  useEffect(() => { setFiche(null); api(`/p/${pid}/variable/${vid}` + (pop ? `?population=${pop}` : "")).then(setFiche).catch((err) => toast(err.message, true)); }, [vid, pop, e.projet.version]);
  if (!v) return html`<div class="page muet">Variable introuvable.</div>`;
  const qu = e.questions[v.question], brute = !v.derive;
  const modifier = (champs, description) => agir("/variables", { methode: "PATCH", corps: { description: `${description} — « ${nomVar(v, 40)} »`, modifications: [{ id: vid, ...champs }] } });
  const mods = fiche?.modalites || [], valides = mods.filter((x) => !x.nr).reduce((s, x) => s + x.n, 0) || 1, maxN = Math.max(1, ...mods.map((x) => x.n));
  const majMods = (liste, description) => modifier({ modalites: liste.map((x) => { const o = { valeur: x.valeur }; if (x.libelle && x.libelle !== x.valeur) o.libelle = x.libelle; if (x.nr) o.nr = true; return o; }) }, description);
  const deplacer = (i, d) => { const l = [...mods]; const [x] = l.splice(i, 1); l.splice(i + d, 0, x); majMods(l, "Ordre des modalités"); };
  const dep = fiche?.dependants, nDep = dep ? dep.etapes.length + dep.populations.length + dep.analyses.length + dep.champs.length : 0;
  return html`<div class="page">
    <div class="ligne haut espace"><div style="min-width:0">
        <div class="mini muet" style="margin-bottom:3px">${v.derive ? "Variable construite" : `Colonne ${v.colonne + 1} de l'export`} · identifiant <code>${v.id}</code>${qu?.precision_de ? html` · précision de <a href=${`#/p/${pid}/donnees/${qu.precision_de}`}>${court(e.questions[qu.precision_de]?.libelle, 50)}</a>` : ""}</div>
        <h2>${v.libelle}</h2>${v.sous_libelle && html`<h3 class="secondaire" style="margin-top:3px">${v.sous_libelle}</h3>`}</div>
      <div class="ligne" style="flex:none">
        ${v.role === "analyse" && v.type !== "vide" && html`<button class="btn" onClick=${() => ouvrirAnalyse(pid, { type: "tri", variable: vid })}>Tri à plat</button>`}
        ${v.role === "analyse" && [...CATEGORIELS, "quanti"].includes(v.type) && html`<button class="btn" onClick=${() => ouvrirAnalyse(pid, { type: "croise", ligne: vid })}>Croiser…</button>`}
        ${v.role === "analyse" && [...CATEGORIELS, "texte", "quanti"].includes(v.type) && html`<button class="btn" onClick=${() => { publier({ brouillonEtape: { type: v.type === "quanti" ? "decouper" : "recoder", params: { source: vid } } }); aller(`/p/${pid}/preparation`); }}>${v.type === "quanti" ? "Découper en classes" : v.type === "texte" ? "Coder les réponses" : "Recoder"}</button>`}
      </div></div>

    <div class="carte" style="margin-top:14px"><div class="grille" style="grid-template-columns:1.2fr 1fr 1fr;align-items:end">
      <div><label class="etq">Nom court (affiché dans les tableaux et graphiques)</label>
        ${brute ? html`<input class="champ" value=${v.nom === v.id ? "" : v.nom} placeholder=${nomVar(v, 40)} onChange=${(ev) => modifier({ nom: ev.target.value.trim() || v.id }, "Nom court")} />` : html`<div class="champ" style="background:var(--surface-2)">${v.nom}</div>`}</div>
      <div><label class="etq">Type</label>
        ${brute ? html`<select class="champ" value=${v.type} onChange=${(ev) => modifier({ type: ev.target.value }, "Type")}>${["quali", "ordinale", "multi", "quanti", "texte", "date", "identifiant", "vide"].filter((t) => t === v.type || ["quali", "ordinale", "quanti", "texte"].includes(t)).map((t) => html`<option value=${t}>${TYPES[t]}</option>`)}</select>` : html`<div class="champ" style="background:var(--surface-2)">${TYPES[v.type]}</div>`}</div>
      <div><label class="etq">Usage</label>
        ${brute ? html`<select class="champ" value=${v.role} onChange=${(ev) => modifier({ role: ev.target.value }, "Usage")}><option value="analyse">Analysable</option><option value="technique">Technique (hors analyses)</option><option value="sensible">Sensible — jamais affichée ni exportée</option></select>` : html`<div class="champ" style="background:var(--surface-2)">Analysable</div>`}</div>
    </div>
    ${v.derive && fiche?.etape && html`<div class="note" style="margin-top:12px">Construite par l'étape de préparation « ${e.types_etapes[fiche.etape.type]} »${fiche.etape.note ? ` — ${fiche.etape.note}` : ""}. <a href=${`#/p/${pid}/preparation`}>Voir ou modifier l'étape</a></div>`}
    ${v.role === "sensible" && html`<div class="note alerte" style="margin-top:12px">Variable marquée sensible (coordonnées, identifiants…) : son contenu n'est ni affiché ni exporté.</div>`}</div>

    ${brute && v.role === "analyse" && html`<${Champ} variables=${qu ? qu.variables.filter((id) => e.variables[id]?.role === "analyse") : [vid]} />`}

    <div class="carte">
      <div class="ligne espace"><h3>Réponses</h3>
        <select class="champ" style="width:auto" value=${pop} onChange=${(ev) => setPop(ev.target.value)}><option value="">Tous les répondants (${ent(e.n_base)})</option>${e.populations.map((p) => html`<option value=${p.id}>${p.nom} (${ent(p.n)})</option>`)}</select></div>
      ${!fiche ? html`<p class="muet">Calcul…</p>` : html`<div style="margin-top:10px"><${Statuts} statuts=${fiche.statuts} /></div>
        ${fiche.modalites && html`<table class="t" style="margin-top:14px"><thead><tr><th>Modalité${brute ? html` <span class="muet" style="font-weight:400">(libellé modifiable)</span>` : ""}</th><th>Effectif</th><th>% des réponses valides</th><th style="width:26%"></th>${brute && html`<th title="Modalité de non-réponse (refus, ne sait pas) : exclue des pourcentages et des analyses par défaut">Non-rép.</th><th></th>`}</tr></thead><tbody>
          ${mods.map((x, i) => html`<tr style=${x.nr ? "color:var(--encre-3)" : ""}>
            <td>${brute && v.type !== "multi" ? html`<input class="champ" style="padding:2px 6px;border-color:transparent;background:transparent" value=${x.libelle} title=${x.valeur} onChange=${(ev) => { const l = mods.map((y, j) => (j === i ? { ...y, libelle: ev.target.value.trim() || y.valeur } : y)); majMods(l, "Libellé de modalité"); }} />` : x.libelle}${x.nouvelle ? html` <span class="badge" style="background:var(--alerte-fond);color:var(--alerte-encre)">nouvelle</span>` : ""}</td>
            <td>${ent(x.n)}${x.n > 0 && x.n < 5 ? html` <span title="Moins de 5 individus : à regrouper, et à ne pas publier tel quel" style="color:var(--alerte-encre)">▲</span>` : ""}</td>
            <td>${x.nr ? "—" : pct(100 * x.n / valides)}</td>
            <td><div class="barre-h" style=${`width:${100 * x.n / maxN}%;${x.nr ? "background:var(--s5)" : ""}`}></div></td>
            ${brute && html`<td class="centre"><input type="checkbox" checked=${x.nr} onChange=${(ev) => majMods(mods.map((y, j) => (j === i ? { ...y, nr: ev.target.checked } : y)), ev.target.checked ? "Modalité déclarée de non-réponse" : "Modalité rétablie comme réponse")} /></td>
              <td class="nowrap">${v.type !== "multi" && html`<button class="btn discret petit" disabled=${i === 0} onClick=${() => deplacer(i, -1)} aria-label="Monter"><${Icone} nom="haut" taille=${13} /></button><button class="btn discret petit" disabled=${i === mods.length - 1} onClick=${() => deplacer(i, 1)} aria-label="Descendre"><${Icone} nom="bas" taille=${13} /></button>`}</td>`}</tr>`)}
          </tbody></table>
          ${brute && v.type !== "multi" && html`<label class="ligne petit" style="margin-top:8px"><input type="checkbox" checked=${v.ordonnee} onChange=${(ev) => modifier({ ordonnee: ev.target.checked }, ev.target.checked ? "Variable déclarée ordinale" : "Variable déclarée nominale")} /> Les modalités sont ordonnées (variable ordinale) — l'ordre ci-dessus est utilisé dans les tableaux, les graphiques et les mesures d'association ordinales.</label>`}`}
        ${fiche.resume && html`<div class="grille" style="grid-template-columns:auto 1fr;gap:24px;margin-top:14px;align-items:start"><dl class="kv"><dt>Réponses valides</dt><dd>${ent(fiche.resume.n)}</dd><dt>Moyenne</dt><dd>${nf(fiche.resume.moyenne, 2)}</dd><dt>Écart-type</dt><dd>${nf(fiche.resume.ecart_type, 2)}</dd><dt>Médiane</dt><dd>${nf(fiche.resume.mediane, 2)}</dd><dt>Quartiles</dt><dd>${nf(fiche.resume.q1, 2)} – ${nf(fiche.resume.q3, 2)}</dd><dt>Étendue</dt><dd>${nf(fiche.resume.min, 2)} – ${nf(fiche.resume.max, 2)}</dd></dl>
          <${Histogramme} bornes=${fiche.resume.histogramme.bornes} effectifs=${fiche.resume.histogramme.effectifs} moyenne=${fiche.resume.moyenne} mediane=${fiche.resume.mediane} largeur=${460} /></div>`}
        ${fiche.textes && html`<p class="secondaire" style="margin-top:12px">${ent(fiche.textes.n)} réponses, ${ent(fiche.textes.n_distinctes)} distinctes.${fiche.textes.masque ? " Contenu masqué (variable sensible)." : ""}</p>
          ${fiche.textes.reponses.length > 0 && html`<div style="max-height:340px;overflow:auto;border:1px solid var(--bord);border-radius:6px"><table class="t"><tbody>${fiche.textes.reponses.map((r) => html`<tr><td style="white-space:pre-wrap">${r.texte}</td><td style="width:50px">${r.n > 1 ? r.n : ""}</td></tr>`)}</tbody></table></div>`}`}`}
    </div>
    ${nDep > 0 && html`<div class="note">Utilisée par ${[dep.etapes.length && `${dep.etapes.length} étape(s) de préparation`, dep.populations.length && `${dep.populations.length} population(s)`, dep.analyses.length && `${dep.analyses.length} analyse(s) enregistrée(s)`, dep.champs.length && `le champ de ${dep.champs.length} variable(s)`].filter(Boolean).join(", ")}.</div>`}
  </div>`;
}

// ---------------------------------------------------------------- fiche d'une question à plusieurs items
function FicheQuestion({ pid, qid }) {
  const e = useMagasin().etat, qu = e.questions[qid];
  const [fiches, setFiches] = useState(null);
  const vars = qu.variables.map((id) => e.variables[id]).filter(Boolean);
  const items = vars.filter((v) => v.role === "analyse" && CATEGORIELS.includes(v.type));
  useEffect(() => { setFiches(null); Promise.all(items.map((v) => api(`/p/${pid}/variable/${v.id}`))).then(setFiches).catch((err) => toast(err.message, true)); }, [qid, e.projet.version]);
  const multi = qu.genre === "multiple";
  const mods = items[0]?.modalites?.filter((x) => !x.nr).map((x) => x.libelle || x.valeur) || [];
  const rampe = (j, n) => `color-mix(in oklab, var(--s1) ${Math.round(22 + 78 * j / Math.max(1, n - 1))}%, var(--surface))`;
  return html`<div class="page">
    <div class="mini muet">${GENRES[qu.genre]} · ${vars.length} colonnes</div>
    <div class="ligne haut espace"><h2>${qu.libelle}</h2><div class="ligne" style="flex:none">
      ${multi && html`<button class="btn" onClick=${() => ouvrirAnalyse(pid, { type: "multiples", variables: items.map((v) => v.id) })}>Analyser les réponses multiples</button>`}
      ${items.length > 2 && html`<button class="btn" onClick=${() => ouvrirAnalyse(pid, { type: "acm", actives: items.map((v) => v.id) })}>ACM sur ces items</button>`}</div></div>
    <div style="margin-top:14px"><${Champ} variables=${vars.filter((v) => v.role === "analyse").map((v) => v.id)} /></div>
    <div class="carte"><h3>Items</h3>
      ${!fiches ? html`<p class="muet">Calcul…</p>` : html`<table class="t" style="margin-top:8px"><thead><tr><th>Item</th><th>Réponses</th>${multi ? html`<th>Cochés</th><th>% des répondants</th><th style="width:28%"></th>` : html`<th style="width:48%">Répartition</th>`}</tr></thead><tbody>
        ${items.map((v, i) => { const f = fiches[i], rep = f.modalites.filter((x) => !x.nr).reduce((s, x) => s + x.n, 0), oui = f.modalites.find((x) => x.valeur === "Oui")?.n || 0;
          return html`<tr class="cliquable" onClick=${() => aller(`/p/${pid}/donnees/${v.id}`)}><td>${v.sous_libelle || v.libelle}</td><td>${ent(rep)}</td>
            ${multi ? html`<td>${ent(oui)}</td><td>${pct(100 * oui / (rep || 1))}</td><td><div class="barre-h" style=${`width:${100 * oui / (rep || 1)}%`}></div></td>`
              : html`<td><div class="empile" style="height:14px">${f.modalites.filter((x) => !x.nr).map((x, j, l) => html`<span style=${`width:${100 * x.n / (rep || 1)}%;background:${rampe(j, l.length)}`} ...${bulle(`${x.libelle} : ${ent(x.n)} (${pct(100 * x.n / (rep || 1))})`)}></span>`)}</div></td>`}</tr>`; })}
        </tbody></table>
        ${!multi && mods.length > 0 && html`<${Legende} items=${mods.map((x, j) => ({ label: x, couleur: rampe(j, mods.length) }))} />`}
        ${multi && html`<p class="aide-champ">Pourcentages calculés sur les répondants à qui la question a été présentée. Un item « N/A » alors qu'un autre item de la question est renseigné est compté « non coché » (cas des options exclusives du type « Aucun »).</p>`}`}
      ${vars.filter((v) => v.type === "texte").map((v) => html`<p class="petit" style="margin-top:8px"><a href=${`#/p/${pid}/donnees/${v.id}`}>${v.sous_libelle || "Texte libre"} : ${ent(v.n_valide)} réponse(s) en clair</a></p>`)}
    </div></div>`;
}

// ---------------------------------------------------------------- propositions de champs
function Propositions({ pid, onFermer }) {
  const e = magasin.etat;
  const [props, setProps] = useState(null);
  const [choix, setChoix] = useState({});
  useEffect(() => { api(`/p/${pid}/champs/propositions`).then((r) => { setProps(r.propositions); setChoix(Object.fromEntries(r.propositions.map((p) => [p.question, !!p.champ && (p.champ.tous || p.precision >= 0.9)]))); }); }, []);
  const accepter = async () => {
    const modifications = props.filter((p) => choix[p.question] && p.champ).flatMap((p) => p.variables.map((id) => ({ id, champ: p.champ })));
    await agir("/variables", { methode: "PATCH", corps: { description: `Champs documentés pour ${props.filter((p) => choix[p.question] && p.champ).length} question(s) (propositions validées)`, modifications } }, "Champs enregistrés");
    onFermer();
  };
  const n = props ? props.filter((p) => choix[p.question] && p.champ).length : 0;
  return html`<${Modale} large titre="Questions conditionnelles : propositions de champ" onFermer=${onFermer} pied=${html`<span class="petit secondaire" style="margin-right:auto">${n} proposition(s) cochée(s). Rien n'est appliqué sans votre validation ; tout reste modifiable question par question.</span><button class="btn" onClick=${onFermer}>Fermer</button><button class="btn primaire" disabled=${!n} onClick=${accepter}>Accepter la sélection</button>`}>
    <div class="aide-texte" style="margin-bottom:12px">Pour chaque question à laquelle une partie seulement des répondants a répondu, Établi cherche dans les questions précédentes ce qui distingue ceux qui ont répondu (une modalité, la conjonction de deux conditions, ou leur réunion). C'est une <b>inférence à partir des données</b>, pas la lecture de la logique du questionnaire : vérifiez-la avec votre connaissance des filtres. « Précision » = part des personnes du champ proposé qui ont effectivement répondu (le reste serait de la non-réponse).</div>
    ${!props ? html`<p class="muet">Analyse des parcours…</p>` : html`<table class="t"><thead><tr><th style="width:28px"></th><th>Question</th><th>Réponses</th><th class="g">Champ proposé</th><th>Précision</th></tr></thead><tbody>
      ${props.map((p) => html`<tr><td><input type="checkbox" disabled=${!p.champ} checked=${!!choix[p.question]} onChange=${(ev) => setChoix({ ...choix, [p.question]: ev.target.checked })} /></td>
        <td title=${p.explication}>${court(e.questions[p.question]?.libelle, 80)}${p.connu_par_export ? html` <span class="badge" title="Pour les cases à cocher, l'export indique déjà (N/A) à qui la question a été présentée">export</span>` : ""}</td>
        <td class="nowrap">${ent(p.n_repondants)} / ${ent(p.n_atteints)}</td>
        <td class="g">${!p.champ ? html`<span class="muet">aucune règle simple trouvée — à documenter à la main</span>` : p.champ.tous ? "tous les répondants" : p.champ_texte}</td>
        <td>${p.precision == null ? "—" : pct(100 * p.precision, 0)}</td></tr>`)}</tbody></table>`}<//>`;
}

function Synthese({ pid }) {
  const e = useMagasin().etat;
  const [props, setProps] = useState(false);
  const vars = Object.values(e.variables).filter((v) => !v.derive);
  const compte = (f) => vars.filter(f).length;
  const aDoc = Object.values(e.questions).filter((q) => q.genre !== "technique" && q.genre !== "multiple" && !q.precision_de && q.variables.some((id) => e.variables[id] && aDocumenter(e.variables[id]))).length;
  const decisions = e.sources.flatMap((s) => s.rapport?.decisions || []);
  const parGenre = (g) => decisions.filter((d) => d.genre === g);
  const style = { texte: "texte complet des questions (sans codes : Établi a fabriqué des identifiants v001, v002… rattachés au texte et au rang de chaque colonne)", codes: "codes des questions", code_texte: "codes et texte des questions" };
  return html`<div class="page">
    <h1>${e.projet.nom}</h1>
    <p class="secondaire" style="margin-top:4px">${e.sources.map((s) => html`<span><code>${s.fichier}</code> — ${ent(s.n_lignes)} réponses, ${ent(s.n_colonnes)} colonnes, en-têtes : ${style[s.rapport?.style_entetes] || "?"}. </span>`)}</p>
    ${aDoc > 0 && html`<div class="carte" style="border-color:var(--alerte);background:var(--alerte-fond)"><div class="ligne"><div style="flex:1"><h3>${aDoc} question(s) n'ont été posées qu'à une partie des répondants</h3>
      <p class="petit" style="margin:4px 0 0">Tant que leur champ n'est pas documenté, on ne peut pas distinguer « non concerné » et « non-réponse ». Établi peut proposer un champ pour chacune, à partir des parcours observés.</p></div>
      <button class="btn primaire" onClick=${() => setProps(true)}>Examiner les propositions</button></div></div>`}
    <div class="carte"><h3>Ce que l'import a reconnu</h3>
      <div class="grille" style="grid-template-columns:repeat(4,1fr);margin-top:10px">
        ${[["Questions", Object.values(e.questions).filter((q) => q.genre !== "technique").length], ["à choix unique ou ordinales", compte((v) => ["quali", "ordinale"].includes(v.type) && v.role === "analyse")], ["cases à cocher", compte((v) => v.type === "multi")], ["numériques", compte((v) => v.type === "quanti" && v.role === "analyse")], ["textes libres", compte((v) => v.type === "texte" && v.role === "analyse")], ["colonnes vides", compte((v) => v.type === "vide")], ["paradonnées", compte((v) => v.role === "technique")], ["sensibles (masquées)", compte((v) => v.role === "sensible")]].map(([lib, n]) => html`<div><div style="font-size:22px;font-family:var(--serif)">${ent(n)}</div><div class="petit secondaire">${lib}</div></div>`)}</div>
      <hr /><div class="aide-texte"><h4 style="margin-top:0">Décisions prises automatiquement — toutes modifiables dans la fiche de chaque variable</h4><ul>
        <li><b>${parGenre("ordre").length} variable(s) reconnues comme ordinales</b> (échelles de fréquence, d'accord, tranches numériques…) : leurs modalités ont été ordonnées. Les autres sont rangées par fréquence décroissante — l'export « réponses complètes » ne conserve pas l'ordre du questionnaire.</li>
        ${parGenre("refus").length > 0 && html`<li><b>${parGenre("refus").length} modalité(s) de refus</b> (« ${[...new Set(parGenre("refus").map((d) => d.modalite))].join(" », « ")} ») déclarées « de non-réponse » : conservées, mais hors des pourcentages par défaut.</li>`}
        ${parGenre("hors_echelle").length > 0 && html`<li><b>${[...new Set(parGenre("hors_echelle").map((d) => d.modalite))].length} modalité(s) hors échelle</b> (« ${court([...new Set(parGenre("hors_echelle").map((d) => d.modalite))].join(" », « "), 160)} ») placées en fin d'échelle et laissées comme réponses : à vous de décider si ce sont des non-réponses.</li>`}
        ${parGenre("sensible").length > 0 && html`<li><b>${parGenre("sensible").length} colonne(s) contenant des courriels ou des numéros de téléphone</b> marquées « sensibles » : jamais affichées ni exportées.</li>`}
        <li>Dans les questions à choix multiples, « N/A » signifie « question non présentée » ; un « N/A » isolé alors que d'autres items sont renseignés est compté « non coché ».</li>
        <li>Les réponses partielles sont conservées : au-delà de la dernière réponse d'un questionnaire non validé, les cellules vides ont le statut « non atteint (abandon) ».</li></ul></div></div>
    <div class="carte"><h3>Pour commencer</h3><div class="aide-texte"><ul>
      <li>Parcourez les questions à gauche ; la recherche porte aussi sur les items et les modalités.</li>
      <li>Donnez un <b>nom court</b> aux variables que vous utiliserez souvent, et raccourcissez les <b>libellés de modalités</b> : ce sont eux qui apparaissent sur les cartes factorielles.</li>
      <li>Recodages, scores, exclusions et populations se définissent dans <a href=${`#/p/${pid}/preparation`}>Préparation</a> ; les données d'origine ne sont jamais modifiées.</li></ul></div></div>
    ${props && html`<${Propositions} pid=${pid} onFermer=${() => setProps(false)} />`}
  </div>`;
}

export function VueDonnees({ pid, reste }) {
  const e = useMagasin().etat, sel = reste[0];
  return html`<div class="deux-colonnes"><${Liste} pid=${pid} selection=${sel} />
    <div class="colonne">${!sel ? html`<${Synthese} pid=${pid} />` : e.questions[sel] ? html`<${FicheQuestion} pid=${pid} qid=${sel} key=${sel} />` : html`<${FicheVariable} pid=${pid} vid=${sel} key=${sel} />`}</div></div>`;
}
