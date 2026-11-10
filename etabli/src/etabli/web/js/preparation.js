// Vue « Préparation » : la recette (étapes déclaratives, rejouables), les populations, les sources.
import { html, useState, useEffect, useRef, api, magasin, useMagasin, publier, agir, toast, ent, pct, nf, court, nomVar, titreComplet, TYPES, CATEGORIELS, Icone, Modale, Onglets, ChoixVariable, EditeurCondition, Avertissements, libelleModalite } from "./base.js";
import { Statuts } from "./donnees.js";

const DESCRIPTIONS = {
  recoder: "Regrouper ou renommer les modalités d'une variable ; coder une question ouverte en catégories.",
  decouper: "Découper une variable numérique en classes (tranches d'âge, d'ancienneté…).",
  score: "Compter des réponses ou additionner / moyenner plusieurs items pour construire un indicateur.",
  regle: "Construire une variable par règles « si … alors … » combinant plusieurs questions.",
  fusionner: "Réunir en une seule variable des questions comparables posées à des groupes différents.",
  convertir: "Transformer une variable catégorielle ou textuelle en nombre.",
  croiser: "Combiner les modalités de deux variables (par exemple genre × statut).",
  exclure: "Écarter des individus de toutes les analyses (ils restent dans les données d'origine).",
};
const AIDES = {
  recoder: "Un recodage est une décision d'analyse : il fait disparaître des distinctions. Regroupez des modalités proches par leur sens (pas seulement parce qu'elles sont rares), vérifiez l'effectif de chaque nouvelle modalité, et notez la justification : elle figurera dans le journal méthodologique. La variable d'origine reste disponible.",
  decouper: "Les bornes changent ce que l'on voit. Des classes d'effectifs comparables (quantiles) stabilisent les pourcentages ; des bornes « rondes » ou institutionnelles (25, 35, 50 ans) facilitent la comparaison avec d'autres enquêtes. Essayez les deux et comparez.",
  score: "Additionner des items suppose qu'ils mesurent une même dimension et qu'une « unité » vaut autant d'un item à l'autre. Vérifiez-le (corrélations entre items, ACM) avant d'interpréter le score. Les individus qui n'ont pas répondu à assez d'items n'ont pas de score.",
  regle: "Les règles sont examinées dans l'ordre : la première qui est vraie s'applique. Les individus qui ne correspondent à aucune règle sont mis en manquant (ou reçoivent la modalité « sinon »).",
  fusionner: "Fusionner deux questions, c'est affirmer qu'elles mesurent la même chose. Si la formulation, les modalités ou le contexte diffèrent (deux pays, deux statuts), documentez ce qui n'est pas strictement comparable dans la justification, et gardez la possibilité d'analyser les groupes séparément. La première source renseignée l'emporte.",
  exclure: "L'exclusion s'applique à toutes les analyses et apparaît dans chaque fiche de calcul. Pour une analyse sur un sous-groupe, préférez une population : elle ne retire personne du projet.",
};

function Apercu({ etape, id }) {
  const [r, setR] = useState(null);
  const [err, setErr] = useState(null);
  const cle = JSON.stringify(etape.params);
  useEffect(() => {
    setErr(null);
    const t = setTimeout(() => {
      api(`/p/${magasin.pid}/recette/apercu`, { methode: "POST", corps: { id, type: etape.type, params: etape.params } }).then(setR).catch((e) => { setR(null); setErr(e.message); });
    }, 450);
    return () => clearTimeout(t);
  }, [cle]);
  if (err) return html`<div class="note">Aperçu indisponible : ${err}</div>`;
  if (!r) return html`<div class="note muet">Aperçu en cours de calcul…</div>`;
  const total = (r.modalites || []).reduce((s, m) => s + m.n, 0) || 1, mx = Math.max(1, ...(r.modalites || []).map((m) => m.n));
  return html`<div class="carte" style="background:var(--surface-2)"><h4>Aperçu du résultat <span class="muet" style="font-weight:400">— rien n'est encore enregistré</span></h4>
    ${r.rapport.erreur && html`<div class="note erreur" style="margin-top:8px">${r.rapport.erreur}</div>`}
    <${Avertissements} liste=${r.rapport.avertissements} />
    ${r.n_exclus !== undefined && html`<p style="margin-top:8px"><b>${ent(r.n_exclus)}</b> individu(s) seraient écartés ; il en resterait <b>${ent(r.n_restants)}</b>.</p>`}
    ${r.statuts && html`<div style="margin-top:10px"><${Statuts} statuts=${r.statuts} /></div>`}
    ${r.modalites && html`<table class="t" style="margin-top:10px"><thead><tr><th>Nouvelle modalité</th><th>Effectif</th><th>%</th><th style="width:35%"></th></tr></thead><tbody>
      ${r.modalites.map((m) => html`<tr><td>${m.valeur}</td><td>${ent(m.n)}${m.n > 0 && m.n < 5 ? html` <span style="color:var(--alerte-encre)" title="Moins de 5 individus">▲</span>` : ""}</td><td>${pct(100 * m.n / total)}</td><td><div class="barre-h" style=${`width:${100 * m.n / mx}%`}></div></td></tr>`)}</tbody></table>`}
    ${r.resume && html`<p style="margin-top:8px">n = ${ent(r.resume.n)} · moyenne ${nf(r.resume.moyenne, 2)} · écart-type ${nf(r.resume.ecart_type, 2)} · médiane ${nf(r.resume.mediane, 2)} · de ${nf(r.resume.min, 2)} à ${nf(r.resume.max, 2)}</p>`}
    ${r.controle && html`<details class="aide" style="margin-top:8px"><summary>Tableau de contrôle : anciennes modalités (lignes) × nouvelles (colonnes)</summary><div class="defile-x"><table class="t"><thead><tr><th></th>${r.controle.colonnes.map((c) => html`<th>${court(c, 22)}</th>`)}</tr></thead><tbody>${r.controle.lignes.map((l, i) => html`<tr><td>${court(l, 50)}</td>${r.controle.effectifs[i].map((n) => html`<td class=${n ? "" : "muet"}>${n || "·"}</td>`)}</tr>`)}</tbody></table></div></details>`}
  </div>`;
}

// ---------------------------------------------------------------- formulaires par type d'étape
function FormRecoder({ p, maj }) {
  const e = magasin.etat, src = p.source && e.variables[p.source];
  const [fiche, setFiche] = useState(null);
  const [sel, setSel] = useState(new Set());
  const [groupe, setGroupe] = useState("");
  const [filtre, setFiltre] = useState("");
  useEffect(() => { setFiche(null); setSel(new Set()); if (p.source) api(`/p/${magasin.pid}/variable/${p.source}`).then(setFiche); }, [p.source]);
  const corr = p.correspondance || {};
  const lignes = fiche ? (fiche.modalites ? fiche.modalites.map((m) => ({ valeur: m.valeur, libelle: m.libelle, n: m.n })) : (fiche.textes?.reponses || []).map((r) => ({ valeur: r.texte, libelle: r.texte, n: r.n }))) : [];
  const visibles = lignes.filter((l) => !filtre || l.libelle.toLowerCase().includes(filtre.toLowerCase()));
  const cibles = [...new Set(Object.values(corr).filter((x) => x))];
  const affecter = (valeurs, cible) => { const c = { ...corr }; valeurs.forEach((v) => { if (cible === undefined) delete c[v]; else c[v] = cible; }); maj({ correspondance: c }); };
  const ordre = [...new Set([...(p.ordre || []).filter((x) => cibles.includes(x) || lignes.some((l) => !(l.valeur in corr) && l.valeur === x)), ...lignes.map((l) => (l.valeur in corr ? corr[l.valeur] : (p.autres === "manquant" ? null : l.valeur))).filter((x) => x)])];
  const deplacer = (i, d) => { const o = [...ordre]; const [x] = o.splice(i, 1); o.splice(i + d, 0, x); maj({ ordre: o }); };
  return html`<div>
    <label class="etq">Variable à recoder</label>
    <${ChoixVariable} valeur=${p.source} types=${["quali", "ordinale", "multi", "texte"]} onChange=${(id) => maj({ source: id, correspondance: {}, ordre: [] })} />
    ${src && src.type === "texte" && html`<p class="aide-champ">Question ouverte : attribuez une catégorie aux réponses (les 300 plus fréquentes sont listées). Les réponses non codées ${p.autres === "manquant" ? "seront mises en manquant" : "sont conservées telles quelles"}.</p>`}
    ${fiche && html`<div class="ligne" style="margin:12px 0 6px;flex-wrap:wrap">
        <input class="champ" style="width:180px" placeholder="Filtrer les modalités…" value=${filtre} onInput=${(ev) => setFiltre(ev.target.value)} />
        <span class="petit secondaire">${sel.size} sélectionnée(s) →</span>
        <input class="champ" style="width:220px" list="cibles-recodage" placeholder="regrouper sous le nom…" value=${groupe} onInput=${(ev) => setGroupe(ev.target.value)} onKeyDown=${(ev) => { if (ev.key === "Enter" && groupe.trim() && sel.size) { affecter([...sel], groupe.trim()); setSel(new Set()); setGroupe(""); } }} />
        <button class="btn petit primaire" disabled=${!sel.size || !groupe.trim()} onClick=${() => { affecter([...sel], groupe.trim()); setSel(new Set()); setGroupe(""); }}>Regrouper</button>
        <button class="btn petit" disabled=${!sel.size} title="Les individus concernés n'auront pas de valeur pour la nouvelle variable" onClick=${() => { affecter([...sel], null); setSel(new Set()); }}>Mettre en manquant</button>
        <button class="btn discret petit" disabled=${!sel.size} onClick=${() => { affecter([...sel], undefined); setSel(new Set()); }}>Rétablir</button>
        <datalist id="cibles-recodage">${cibles.map((c) => html`<option value=${c} />`)}</datalist></div>
      <div style="max-height:320px;overflow:auto;border:1px solid var(--bord);border-radius:6px"><table class="t"><thead><tr><th style="width:26px"><input type="checkbox" checked=${visibles.length > 0 && visibles.every((l) => sel.has(l.valeur))} onChange=${(ev) => setSel(ev.target.checked ? new Set(visibles.map((l) => l.valeur)) : new Set())} /></th><th class="g">Modalité d'origine</th><th>Effectif</th><th class="g" style="width:36%">Devient</th></tr></thead><tbody>
        ${visibles.map((l) => html`<tr><td><input type="checkbox" checked=${sel.has(l.valeur)} onChange=${(ev) => { const s = new Set(sel); ev.target.checked ? s.add(l.valeur) : s.delete(l.valeur); setSel(s); }} /></td>
          <td class="g" style="white-space:pre-wrap">${court(l.libelle, 160)}</td><td>${ent(l.n)}</td>
          <td class="g"><input class="champ" style="padding:2px 7px" list="cibles-recodage" placeholder=${l.valeur in corr && corr[l.valeur] === null ? "(manquant)" : (p.autres === "manquant" ? "(manquant)" : "inchangée")} value=${corr[l.valeur] || ""} onChange=${(ev) => affecter([l.valeur], ev.target.value.trim() || undefined)} /></td></tr>`)}</tbody></table></div>
      <div class="grille" style="grid-template-columns:1fr 1fr;margin-top:10px;align-items:start">
        <div><label class="etq">Modalités non recodées</label><select class="champ" value=${p.autres || "conserver"} onChange=${(ev) => maj({ autres: ev.target.value })}><option value="conserver">Conservées telles quelles</option><option value="manquant">Mises en manquant</option></select>
          <label class="ligne petit" style="margin-top:10px"><input type="checkbox" checked=${!!p.ordonnee} onChange=${(ev) => maj({ ordonnee: ev.target.checked })} /> Les nouvelles modalités sont ordonnées (variable ordinale)</label></div>
        <div><label class="etq">Ordre des nouvelles modalités</label>${ordre.length > 30 ? html`<span class="muet petit">${ordre.length} modalités</span>` : ordre.map((x, i) => html`<div class="ligne petit" style="padding:1px 0"><button class="btn discret petit" disabled=${i === 0} onClick=${() => deplacer(i, -1)}><${Icone} nom="haut" taille=${12} /></button><button class="btn discret petit" disabled=${i === ordre.length - 1} onClick=${() => deplacer(i, 1)}><${Icone} nom="bas" taille=${12} /></button><span class="tronque">${x}</span></div>`)}</div>
      </div>`}
  </div>`;
}

function FormDecouper({ p, maj }) {
  const [fiche, setFiche] = useState(null);
  const [texte, setTexte] = useState((p.bornes || []).join(" ; "));
  useEffect(() => { setFiche(null); if (p.source) api(`/p/${magasin.pid}/variable/${p.source}`).then(setFiche); }, [p.source]);
  const poser = (t) => { setTexte(t); maj({ bornes: t.split(/[;\s]+/).map((x) => Number(x.replace(",", "."))).filter((x) => x === x && t.trim() !== "") }); };
  const r = fiche?.resume;
  return html`<div><label class="etq">Variable numérique</label><${ChoixVariable} valeur=${p.source} types=${["quanti"]} onChange=${(id) => maj({ source: id })} />
    ${r && html`<p class="aide-champ">n = ${ent(r.n)} · de ${nf(r.min, 1)} à ${nf(r.max, 1)} · quartiles : ${nf(r.q1, 1)} / ${nf(r.mediane, 1)} / ${nf(r.q3, 1)}</p>`}
    <label class="etq">Bornes (séparées par des points-virgules)</label>
    <div class="ligne"><input class="champ" placeholder="ex. 25 ; 35 ; 50" value=${texte} onInput=${(ev) => poser(ev.target.value)} />
      ${r && html`<button class="btn petit" onClick=${() => poser(String(r.mediane))}>Médiane</button><button class="btn petit" onClick=${() => poser([r.q1, r.mediane, r.q3].join(" ; "))}>Quartiles</button>`}</div>
    <label class="ligne petit" style="margin-top:8px"><input type="checkbox" checked=${!!p.droite} onChange=${(ev) => maj({ droite: ev.target.checked })} /> Une valeur égale à une borne va dans la classe inférieure (par défaut : dans la classe supérieure, « 25 à moins de 35 »)</label></div>`;
}

function FormScore({ p, maj }) {
  const e = magasin.etat, v0 = p.sources?.[0] && e.variables[p.sources[0]];
  const mode = p.mode || "compter", mods = (v0?.modalites || []).filter((m) => !m.nr);
  return html`<div><label class="etq">Variables (items)</label><${ChoixVariable} multiple valeur=${p.sources || []} types=${["quali", "ordinale", "multi", "quanti"]} onChange=${(ids) => maj({ sources: ids })} />
    <label class="etq">Calcul</label><select class="champ" value=${mode} onChange=${(ev) => maj({ mode: ev.target.value })}><option value="compter">Compter le nombre d'items où la réponse est…</option><option value="somme">Additionner des points</option><option value="moyenne">Moyenne des points</option></select>
    ${mode === "compter" && mods.length > 0 && html`<div style="margin-top:8px">${mods.map((m) => html`<label class="ligne petit"><input type="checkbox" checked=${(p.valeurs || ["Oui"]).includes(m.valeur)} onChange=${(ev) => { const cur = p.valeurs || ["Oui"]; maj({ valeurs: ev.target.checked ? [...cur, m.valeur] : cur.filter((x) => x !== m.valeur) }); }} /> ${libelleModalite(m)}</label>`)}</div>`}
    ${mode !== "compter" && v0 && v0.type !== "quanti" && html`<div style="margin-top:8px"><div class="ligne espace"><span class="etq" style="margin:0">Points par modalité</span><button class="btn petit" onClick=${() => maj({ points: Object.fromEntries(mods.map((m, i) => [m.valeur, i])) })}>0, 1, 2… dans l'ordre</button></div>
      ${mods.map((m) => html`<div class="ligne petit" style="padding:2px 0"><input class="champ" type="number" style="width:80px;padding:2px 6px" value=${p.points?.[m.valeur] ?? ""} onInput=${(ev) => maj({ points: { ...(p.points || {}), [m.valeur]: ev.target.value === "" ? undefined : Number(ev.target.value) } })} /><span>${libelleModalite(m)}</span></div>`)}
      <p class="aide-champ">Les points s'appliquent à tous les items (mêmes modalités). Une modalité sans points est traitée comme manquante.</p></div>`}
    <label class="etq">Nombre minimal d'items renseignés pour calculer le score</label><input class="champ" type="number" style="width:110px" placeholder=${mode === "moyenne" ? "la moitié" : "tous"} value=${p.min_valides ?? ""} onInput=${(ev) => maj({ min_valides: ev.target.value === "" ? undefined : Number(ev.target.value) })} /></div>`;
}

function FormRegle({ p, maj }) {
  const cas = p.cas || [];
  const majCas = (i, m) => maj({ cas: cas.map((c, j) => (j === i ? { ...c, ...m } : c)) });
  return html`<div>${cas.map((c, i) => html`<div class="carte" style="padding:12px 14px;margin-bottom:8px"><div class="ligne espace"><b class="petit">Règle ${i + 1}</b><button class="btn discret petit" onClick=${() => maj({ cas: cas.filter((_, j) => j !== i) })}>Retirer</button></div>
      <${EditeurCondition} valeur=${c.si} onChange=${(si) => majCas(i, { si })} />
      <div class="ligne" style="margin-top:8px"><span class="petit secondaire">alors la modalité est</span><input class="champ" style="flex:1" value=${c.alors || ""} onInput=${(ev) => majCas(i, { alors: ev.target.value })} /></div></div>`)}
    <button class="btn petit" onClick=${() => maj({ cas: [...cas, { si: { op: "et", regles: [] }, alors: "" }] })}><${Icone} nom="plus" taille=${13} /> Ajouter une règle</button>
    <label class="etq">Sinon (aucune règle vraie)</label><input class="champ" placeholder="laisser vide = manquant" value=${p.sinon || ""} onInput=${(ev) => maj({ sinon: ev.target.value || null })} />
    <label class="ligne petit" style="margin-top:8px"><input type="checkbox" checked=${!!p.ordonnee} onChange=${(ev) => maj({ ordonnee: ev.target.checked })} /> Modalités ordonnées (dans l'ordre des règles)</label></div>`;
}

function FormFusionner({ p, maj }) {
  const e = magasin.etat, srcs = p.sources || [];
  const ids = srcs.map((s) => s.var);
  return html`<div><label class="etq">Variables à réunir (dans l'ordre de priorité)</label>
    <${ChoixVariable} multiple valeur=${ids} types=${["quali", "ordinale", "multi", "quanti"]} onChange=${(nv) => maj({ sources: nv.map((id) => srcs.find((s) => s.var === id) || { var: id, correspondance: null }) })} />
    ${srcs.map((s, i) => { const v = e.variables[s.var]; if (!v || v.type === "quanti") return null; return html`<details class="aide" style="margin-top:8px"><summary>Faire correspondre les modalités de « ${nomVar(v, 50)} » (${(v.modalites || []).length})</summary>
      ${(v.modalites || []).filter((m) => !m.nr).map((m) => html`<div class="ligne petit" style="padding:2px 0"><span style="flex:1" class="tronque" title=${m.valeur}>${libelleModalite(m)}</span><span class="muet">→</span><input class="champ" style="flex:1;padding:2px 7px" placeholder="inchangée" value=${s.correspondance?.[m.valeur] || ""} onChange=${(ev) => maj({ sources: srcs.map((x, j) => (j === i ? { ...x, correspondance: { ...(x.correspondance || {}), [m.valeur]: ev.target.value.trim() || undefined } } : x)) })} /></div>`)}</details>`; })}
    <label class="ligne petit" style="margin-top:8px"><input type="checkbox" checked=${!!p.ordonnee} onChange=${(ev) => maj({ ordonnee: ev.target.checked })} /> Modalités ordonnées</label></div>`;
}

const FORMULAIRES = {
  recoder: FormRecoder, decouper: FormDecouper, score: FormScore, regle: FormRegle, fusionner: FormFusionner,
  convertir: ({ p, maj }) => html`<div><label class="etq">Variable à convertir en nombre</label><${ChoixVariable} valeur=${p.source} types=${["quali", "ordinale", "texte"]} onChange=${(id) => maj({ source: id })} /><p class="aide-champ">Le premier nombre présent dans chaque réponse est retenu (« 8 semestres » → 8). Les réponses sans nombre sont mises en manquant et comptées dans l'aperçu.</p></div>`,
  croiser: ({ p, maj }) => html`<div><label class="etq">Deux variables à combiner</label><${ChoixVariable} multiple valeur=${p.sources || []} types=${CATEGORIELS} onChange=${(ids) => maj({ sources: ids.slice(0, 2) })} /></div>`,
  exclure: ({ p, maj }) => html`<div><label class="etq">Écarter les individus pour lesquels…</label><${EditeurCondition} valeur=${p.si} onChange=${(si) => maj({ si })} /><label class="etq">Motif (figurera dans chaque fiche de calcul)</label><input class="champ" value=${p.motif || ""} onInput=${(ev) => maj({ motif: ev.target.value })} placeholder="ex. consentement non donné ; réponse de test" /></div>`,
};

function pret(et) {
  const p = et.params;
  if (et.type === "recoder" || et.type === "convertir") return !!p.source;
  if (et.type === "decouper") return !!p.source && (p.bornes || []).length > 0;
  if (et.type === "score") return (p.sources || []).length > 0;
  if (et.type === "croiser") return (p.sources || []).length === 2;
  if (et.type === "fusionner") return (p.sources || []).length >= 2;
  if (et.type === "regle") return (p.cas || []).length > 0 && p.cas.every((c) => c.alors && c.si?.regles?.length);
  if (et.type === "exclure") return (p.si?.regles || []).length > 0;
  return true;
}

function EditeurEtape({ initiale, onFermer }) {
  const e = magasin.etat;
  const [et, setEt] = useState(() => JSON.parse(JSON.stringify({ note: "", ...initiale, params: { ...(initiale.params || {}) } })));
  const maj = (m) => setEt((x) => ({ ...x, params: { ...x.params, ...m } }));
  const majCible = (m) => setEt((x) => ({ ...x, params: { ...x.params, cible: { ...(x.params.cible || {}), ...m } } }));
  const Form = FORMULAIRES[et.type];
  const cible = et.params.cible || {}, aCible = et.type !== "exclure";
  const src = et.params.source && e.variables[et.params.source];
  const enregistrer = async () => {
    const params = { ...et.params };
    if (aCible) params.cible = { ...cible, nom: (cible.nom || "").trim() || undefined, libelle: (cible.libelle || "").trim() || (cible.nom || "").trim() || undefined };
    if (et.id) await agir(`/recette/${et.id}`, { methode: "PUT", corps: { params, note: et.note, description: `Préparation : étape « ${cible.nom || e.types_etapes[et.type]} » modifiée` } }, "Étape modifiée");
    else await agir("/recette", { methode: "POST", corps: { type: et.type, params, note: et.note } }, "Étape ajoutée à la recette");
    onFermer();
  };
  return html`<${Modale} large titre=${(et.id ? "Modifier : " : "Nouvelle étape : ") + e.types_etapes[et.type].toLowerCase()} onFermer=${onFermer}
      pied=${html`<span class="petit secondaire" style="margin-right:auto">Les données d'origine ne sont pas modifiées : l'étape ${aCible ? "ajoute une variable" : "marque des individus"} et peut être corrigée ou supprimée à tout moment.</span><button class="btn" onClick=${onFermer}>Annuler</button><button class="btn primaire" disabled=${!pret(et) || (aCible && !(cible.nom || "").trim())} onClick=${enregistrer}>${et.id ? "Enregistrer les modifications" : "Ajouter à la recette"}</button>`}>
    ${AIDES[et.type] && html`<details class="aide" style="margin-bottom:10px"><summary>Ce que cette étape engage</summary><div class="aide-texte">${AIDES[et.type]}</div></details>`}
    <${Form} p=${et.params} maj=${maj} />
    ${aCible && html`<div class="grille" style="grid-template-columns:1fr 2fr;margin-top:6px">
      <div><label class="etq">Nom de la nouvelle variable</label><input class="champ" placeholder="ex. age3, score_lecture" value=${cible.nom || ""} onInput=${(ev) => majCible({ nom: ev.target.value })} /></div>
      <div><label class="etq">Libellé</label><input class="champ" placeholder=${src ? court(src.libelle, 60) + " (recodé)" : "description en clair"} value=${cible.libelle || ""} onInput=${(ev) => majCible({ libelle: ev.target.value })} /></div></div>`}
    <label class="etq">Justification (pourquoi ce choix ? — reprise dans le journal méthodologique)</label>
    <textarea class="champ" style="min-height:48px" value=${et.note || ""} onInput=${(ev) => setEt({ ...et, note: ev.target.value })} placeholder="ex. effectifs trop faibles pour distinguer les deux dernières modalités ; regroupement conforme à la nomenclature…"></textarea>
    <div style="margin-top:14px">${pret(et) ? html`<${Apercu} etape=${et} id=${et.id} />` : html`<div class="note muet">L'aperçu s'affichera dès que l'étape sera suffisamment définie.</div>`}</div>
  <//>`;
}

function resumeEtape(et, e) {
  const p = et.params, n = (id) => (e.variables[id] ? nomVar(e.variables[id], 44) : `${id} (introuvable)`);
  if (et.type === "recoder") { const g = new Set(Object.values(p.correspondance || {}).filter(Boolean)); return `« ${n(p.source)} » : ${Object.keys(p.correspondance || {}).length} modalité(s) recodée(s) en ${g.size} groupe(s)`; }
  if (et.type === "decouper") return `« ${n(p.source)} » découpée aux bornes ${(p.bornes || []).join(" ; ")}`;
  if (et.type === "score") return `${{ compter: "nombre de réponses", somme: "somme de points", moyenne: "moyenne de points" }[p.mode || "compter"]} sur ${(p.sources || []).length} items (${(p.sources || []).slice(0, 3).map(n).join(", ")}${(p.sources || []).length > 3 ? "…" : ""})`;
  if (et.type === "regle") return `${(p.cas || []).length} règle(s) : ${(p.cas || []).map((c) => `« ${c.alors} »`).join(", ")}${p.sinon ? ` ; sinon « ${p.sinon} »` : ""}`;
  if (et.type === "fusionner") return `réunit ${(p.sources || []).map((s) => `« ${n(s.var)} »`).join(" et ")}`;
  if (et.type === "croiser") return (p.sources || []).map((s) => `« ${n(s)} »`).join(" × ");
  if (et.type === "convertir") return `« ${n(p.source)} » lue comme un nombre`;
  if (et.type === "exclure") return `${p.motif || "sans motif indiqué"}`;
  if (et.type === "partition") { const a = e.analyses.find((x) => x.id === p.analyse); return `classes de la classification « ${a ? a.titre : "supprimée"} »`; }
  return "";
}

function Recette({ pid }) {
  const m = useMagasin(), e = m.etat;
  const [edition, setEdition] = useState(null);
  const [choix, setChoix] = useState(false);
  useEffect(() => { if (m.brouillonEtape) { setEdition(m.brouillonEtape); publier({ brouillonEtape: null }); } }, []);
  const deplacer = (i, d) => { const o = e.recette.map((x) => x.id); const [x] = o.splice(i, 1); o.splice(i + d, 0, x); agir("/recette/ordre", { methode: "POST", corps: { ordre: o } }); };
  return html`<div>
    <div class="ligne espace"><p class="secondaire" style="max-width:700px;margin:0">La recette est la liste des transformations appliquées aux données d'origine, dans l'ordre. Chaque étape reste visible, modifiable et désactivable ; la recette entière est rejouée sur tout nouvel export.</p>
      <button class="btn primaire" onClick=${() => setChoix(true)}><${Icone} nom="plus" taille=${14} /> Ajouter une étape</button></div>
    <div style="margin-top:16px">${e.recette.length === 0 && html`<div class="carte muet">Aucune étape : les analyses portent sur les variables telles qu'importées.</div>`}
      ${e.recette.map((et, i) => { const r = et.rapport || {}, cible = et.params.cible; const sortie = cible && e.variables[cible.id];
        return html`<div class=${"carte etape" + (et.actif === false ? " inactif" : "")}><div class="num">${i + 1}</div>
          <div style="min-width:0"><div class="ligne" style="flex-wrap:wrap"><span class="badge">${et.type_libelle}</span>${cible && html`<a href=${`#/p/${pid}/donnees/${cible.id}`} class="gras">${cible.nom}</a>`}${cible && cible.libelle && cible.libelle !== cible.nom && html`<span class="secondaire">${court(cible.libelle, 70)}</span>`}
              ${sortie && html`<span class="mini muet">${ent(sortie.n_valide)} valeurs</span>`}${et.type === "exclure" && r.n_exclus !== undefined && html`<span class="mini muet">${ent(r.n_exclus)} individu(s) écartés</span>`}${et.actif === false && html`<span class="badge">désactivée</span>`}</div>
            <div class="petit" style="margin-top:4px">${resumeEtape(et, e)}</div>
            ${et.note && html`<div class="petit secondaire" style="margin-top:3px;font-style:italic">${et.note}</div>`}
            ${r.erreur && et.actif !== false && html`<div class="note erreur" style="margin-top:6px">${r.erreur}</div>`}
            <${Avertissements} liste=${r.avertissements} /></div>
          <div class="ligne" style="gap:2px"><button class="btn discret petit" disabled=${i === 0} onClick=${() => deplacer(i, -1)} title="Monter"><${Icone} nom="haut" taille=${14} /></button><button class="btn discret petit" disabled=${i === e.recette.length - 1} onClick=${() => deplacer(i, 1)} title="Descendre"><${Icone} nom="bas" taille=${14} /></button>
            ${et.type !== "partition" && html`<button class="btn discret petit" onClick=${() => setEdition(et)} title="Modifier"><${Icone} nom="crayon" taille=${14} /></button>`}
            <button class="btn discret petit" onClick=${() => agir(`/recette/${et.id}`, { methode: "PUT", corps: { actif: et.actif === false, description: `Préparation : étape ${et.actif === false ? "réactivée" : "désactivée"}` } })} title=${et.actif === false ? "Réactiver" : "Désactiver sans supprimer"}><${Icone} nom="oeil" taille=${14} /></button>
            <button class="btn discret petit danger" onClick=${() => confirm("Supprimer cette étape ? (annulable)") && agir(`/recette/${et.id}`, { methode: "DELETE" }, "Étape supprimée — Annuler pour la rétablir")} title="Supprimer"><${Icone} nom="poubelle" taille=${14} /></button></div></div>`; })}</div>
    ${choix && html`<${Modale} titre="Quelle transformation ?" onFermer=${() => setChoix(false)}><div class="type-analyse">${Object.keys(DESCRIPTIONS).map((t) => html`<div class="carte cliquable" onClick=${() => { setChoix(false); setEdition({ type: t, params: {} }); }}><h3>${e.types_etapes[t]}</h3><p class="petit secondaire" style="margin:4px 0 0">${DESCRIPTIONS[t]}</p></div>`)}</div>
      <p class="aide-champ" style="margin-top:12px">Pour transformer en variable les classes d'une classification, enregistrez la classification puis utilisez « Enregistrer les classes comme variable » depuis son résultat.</p><//>`}
    ${edition && html`<${EditeurEtape} initiale=${edition} onFermer=${() => setEdition(null)} />`}
  </div>`;
}

function Populations() {
  const e = useMagasin().etat;
  const [ed, setEd] = useState(null);
  const enregistrer = async () => { const corps = { nom: ed.nom.trim(), condition: ed.condition, note: ed.note || "" }; if (ed.id) await agir(`/populations/${ed.id}`, { methode: "PUT", corps }, "Population modifiée"); else await agir("/populations", { methode: "POST", corps }, "Population créée"); setEd(null); };
  return html`<div><div class="ligne espace"><p class="secondaire" style="max-width:700px;margin:0">Une population est un sous-ensemble nommé de répondants (« internes », « en poste depuis moins de 5 ans »). Elle ne retire personne du projet : chaque analyse indique sur quelle population elle porte, et la même analyse peut être relancée sur une autre pour comparer.</p>
      <button class="btn primaire" onClick=${() => setEd({ nom: "", condition: { op: "et", regles: [] } })}><${Icone} nom="plus" taille=${14} /> Nouvelle population</button></div>
    <div style="margin-top:16px">${e.populations.length === 0 && html`<div class="carte muet">Aucune population : les analyses portent sur l'ensemble des ${ent(e.n_base)} répondants.</div>`}
      ${e.populations.map((p) => html`<div class="carte ligne"><div style="flex:1;min-width:0"><h3>${p.nom} <span class="secondaire" style="font-family:var(--sans);font-weight:400;font-size:13px">· ${p.n === null ? "?" : ent(p.n)} individus (${p.n === null ? "?" : pct(100 * p.n / (e.n_base || 1), 0)})</span></h3>
        <div class="petit secondaire" style="margin-top:3px">${p.erreur ? html`<span style="color:var(--critique)">${p.erreur}</span>` : p.description}</div>${p.note && html`<div class="petit secondaire" style="font-style:italic">${p.note}</div>`}</div>
        <button class="btn discret petit" onClick=${() => setEd(JSON.parse(JSON.stringify(p)))}><${Icone} nom="crayon" taille=${14} /></button>
        <button class="btn discret petit danger" onClick=${() => confirm(`Supprimer la population « ${p.nom} » ? Les analyses qui l'utilisent ne pourront plus être recalculées.`) && agir(`/populations/${p.id}`, { methode: "DELETE" })}><${Icone} nom="poubelle" taille=${14} /></button></div>`)}</div>
    ${ed && html`<${Modale} titre=${ed.id ? "Modifier la population" : "Nouvelle population"} onFermer=${() => setEd(null)} pied=${html`<button class="btn" onClick=${() => setEd(null)}>Annuler</button><button class="btn primaire" disabled=${!ed.nom.trim() || !(ed.condition?.regles || []).length} onClick=${enregistrer}>Enregistrer</button>`}>
      <label class="etq" style="margin-top:0">Nom</label><input class="champ" value=${ed.nom} onInput=${(ev) => setEd({ ...ed, nom: ev.target.value })} placeholder="ex. Internes" />
      <label class="etq">Individus retenus</label><${EditeurCondition} valeur=${ed.condition} onChange=${(condition) => setEd({ ...ed, condition })} />
      <label class="etq">Note (facultative)</label><input class="champ" value=${ed.note || ""} onInput=${(ev) => setEd({ ...ed, note: ev.target.value })} /><//>`}
  </div>`;
}

function Sources() {
  const e = useMagasin().etat;
  const [rapport, setRapport] = useState(null);
  const [occupe, setOccupe] = useState(false);
  const reimporter = async (fichier, alias) => {
    if (!fichier || !confirm(`Remplacer les données par « ${fichier.name} » ?\n\nLe dictionnaire, la recette, les populations et les analyses sont conservés et recalculés. L'ancien fichier reste dans le dossier du projet, et l'opération est annulable.`)) return;
    setOccupe(true);
    try { const corps = new FormData(); corps.append("fichier", fichier); corps.append("alias", alias); const r = await agir("/sources", { methode: "POST", corps }, "Nouvel export importé"); setRapport(r.rapport.reimport); } finally { setOccupe(false); }
  };
  return html`<div>${e.sources.map((s) => html`<div class="carte"><h3>${s.fichier}</h3>
      <dl class="kv" style="margin-top:8px"><dt>Importé le</dt><dd>${s.importe.replace("T", " à ")}</dd><dt>Contenu</dt><dd>${ent(s.n_lignes)} réponses × ${ent(s.n_colonnes)} colonnes</dd><dt>Lecture</dt><dd>${s.rapport?.lecture?.encodage || s.rapport?.lecture?.format} ${s.rapport?.lecture?.separateur ? `· séparateur « ${s.rapport.lecture.separateur} »` : ""}</dd><dt>Empreinte</dt><dd><code>${s.sha256.slice(0, 20)}…</code> (SHA-256 : identifie exactement ce fichier)</dd><dt>Copie conservée</dt><dd><code>${e.projet.dossier}/${s.chemin}</code></dd>
        ${(s.precedents || []).length > 0 && html`<dt>Exports précédents</dt><dd>${s.precedents.map((x) => `${x.fichier} (${ent(x.n_lignes)} réponses, ${x.importe.slice(0, 10)})`).join(" ; ")}</dd>`}</dl>
      <hr /><h4>Charger un nouvel export de la même enquête</h4>
      <p class="petit secondaire" style="margin-top:4px">Les colonnes sont ré-appariées par leur en-tête : annotations, champs, recette et analyses sont conservés. Les colonnes nouvelles ou disparues et les modalités inédites sont signalées.</p>
      <input type="file" accept=".csv,.tsv,.txt,.xlsx" disabled=${occupe} onChange=${(ev) => { reimporter(ev.target.files[0], s.alias); ev.target.value = ""; }} /></div>`)}
    ${rapport && html`<div class="note info" style="margin-top:12px">Ré-import terminé : ${rapport.nouvelles_colonnes.length} colonne(s) nouvelle(s), ${rapport.colonnes_disparues.length} disparue(s), ${rapport.modalites_nouvelles.length} modalité(s) inédite(s)${rapport.modalites_nouvelles.length ? " (marquées « nouvelle » dans la fiche des variables ; vérifiez vos recodages)" : ""}.</div>`}
    <div class="note" style="margin-top:12px">Conseil pour LimeSurvey : exportez de préférence avec « réponses complètes » et toujours les mêmes options, pour que les en-têtes restent stables d'un export à l'autre. Réunir plusieurs enquêtes (par exemple deux pays) dans un même projet n'est pas encore proposé dans l'interface.</div></div>`;
}

export function VuePreparation({ pid, reste }) {
  const [onglet, setOnglet] = useState(reste[0] || "recette");
  const e = useMagasin().etat;
  return html`<div class="page"><h1>Préparation</h1>
    <div style="margin-top:14px"><${Onglets} onglets=${[["recette", `Recette (${e.recette.length})`], ["populations", `Populations (${e.populations.length})`], ["sources", "Sources"]]} actif=${onglet} onChange=${setOnglet} /></div>
    ${onglet === "recette" ? html`<${Recette} pid=${pid} />` : onglet === "populations" ? html`<${Populations} />` : html`<${Sources} />`}</div>`;
}
