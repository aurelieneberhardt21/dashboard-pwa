// Vue « Analyses » : choisir une méthode, la spécifier, lire le résultat avec sa fiche de calcul,
// l'enregistrer, la dupliquer pour essayer une variante, comparer deux analyses.
import { html, useState, useEffect, useRef, api, magasin, useMagasin, publier, agir, aller, toast, ent, pct, nf, court, nomVar, titreComplet, CATEGORIELS, TYPES, Icone, Modale, Onglets, Segments, ChoixVariable, Avertissements, telechargerDepuis, libelleModalite } from "./base.js";
import { ResTri, ResCroise, ResMultiples, ResCorrelation, ResRegression, ResExploration, ResFactorielle, ResCah } from "./resultats.js";
import { Comprendre } from "./aide.js";

const FAMILLES = [
  ["Décrire", [["tri", "Distribution d'une variable : effectifs, pourcentages, non-réponses."], ["multiples", "Question à choix multiples : fréquence de chaque item, éventuellement par groupe."]]],
  ["Relier deux variables", [["croise", "Tableau croisé, comparaison de moyennes ou corrélation selon les variables choisies."], ["correlation", "Matrice de corrélations entre variables numériques ou ordinales."], ["exploration", "Une variable face à beaucoup d'autres : repérer des pistes, effectifs et tailles d'effet à l'appui."]]],
  ["Modéliser", [["regression", "Linéaire, logistique ou multinomiale : associations « toutes choses égales par ailleurs »."]]],
  ["Analyse géométrique des données", [["acm", "Espace des modalités et des individus à partir de variables qualitatives ; modalités passives, éléments supplémentaires."], ["acp", "Résumer des variables numériques corrélées."], ["afc", "Représenter un tableau croisé."], ["afdm", "Variables numériques et qualitatives ensemble."], ["cah", "Typologie : classification sur les axes d'une analyse factorielle enregistrée."]]],
];
const FACTORIELLES = ["acm", "acp", "afdm", "afc"];
const RENDUS = { tri: ResTri, croise: ResCroise, multiples: ResMultiples, correlation: ResCorrelation, regression: ResRegression, exploration: ResExploration, acm: ResFactorielle, acp: ResFactorielle, afdm: ResFactorielle, afc: ResFactorielle, cah: ResCah };

// ---------------------------------------------------------------- constructeur
const Rang = ({ etq, aide, children }) => html`<div style="margin-bottom:10px"><label class="etq" style="margin-top:0">${etq}</label>${children}${aide && html`<div class="aide-champ">${aide}</div>`}</div>`;
const Liste = ({ valeur, onChange, options }) => html`<select class="champ" value=${valeur ?? ""} onChange=${(e) => onChange(e.target.value === "" ? null : e.target.value)}>${options.map(([v, l]) => html`<option value=${v ?? ""}>${l}</option>`)}</select>`;

function Constructeur({ spec, maj }) {
  const e = magasin.etat, t = spec.type, V = (id) => e.variables[id];
  const pops = [[null, `Tous les répondants (${ent(e.n_base)})`], ...e.populations.map((p) => [p.id, `${p.nom} (${p.n === null ? "?" : ent(p.n)})`])];
  const sup = html`<div class="grille" style="grid-template-columns:1fr 1fr">
    <${Rang} etq="Variables supplémentaires qualitatives" aide="Projetées dans l'espace sans influencer les axes : caractéristiques sociales, typologies…"><${ChoixVariable} multiple valeur=${spec.sup_quali || []} types=${CATEGORIELS} exclure=${spec.actives || []} onChange=${(v) => maj({ sup_quali: v })} /><//>
    <${Rang} etq="Variables supplémentaires numériques"><${ChoixVariable} multiple valeur=${spec.sup_quanti || []} types=${["quanti"]} exclure=${spec.actives || []} onChange=${(v) => maj({ sup_quanti: v })} /><//></div>`;
  const indSup = html`<${Rang} etq="Individus supplémentaires" aide="Une population dont les membres sont placés dans l'espace sans participer à sa construction (par exemple un autre groupe de répondants)."><${Liste} valeur=${spec.ind_sup} onChange=${(v) => maj({ ind_sup: v })} options=${[[null, "Aucun"], ...e.populations.map((p) => [p.id, p.nom])]} /><//>`;
  const nsp = html`<${Rang} etq="Modalités déclarées « de non-réponse » (refus, ne sait pas)"><${Segments} options=${[["exclure", "exclues", "Traitées comme des valeurs manquantes"], ["garder", "gardées comme réponses"]]} valeur=${spec.nsp || "exclure"} onChange=${(v) => maj({ nsp: v })} /><//>`;
  let corps = null;
  if (t === "tri") corps = html`<${Rang} etq="Variable"><${ChoixVariable} valeur=${spec.variable} onChange=${(v) => maj({ variable: v })} /><//>${nsp}`;
  else if (t === "croise") corps = html`<div class="grille" style="grid-template-columns:1fr 1fr">
      <${Rang} etq="En lignes" aide="Souvent la variable « explicative » : les % en ligne comparent ses modalités."><${ChoixVariable} valeur=${spec.ligne} types=${[...CATEGORIELS, "quanti"]} exclure=${[spec.colonne].filter(Boolean)} onChange=${(v) => maj({ ligne: v })} /><//>
      <${Rang} etq="En colonnes"><${ChoixVariable} valeur=${spec.colonne} types=${[...CATEGORIELS, "quanti"]} exclure=${[spec.ligne].filter(Boolean)} onChange=${(v) => maj({ colonne: v })} /><//></div>${nsp}`;
  else if (t === "multiples") corps = html`<${Rang} etq="Items de la question (cases à cocher)" aide="Choisissez un item puis « + n items » pour prendre toute la question."><${ChoixVariable} multiple valeur=${spec.variables || []} types=${["multi"]} onChange=${(v) => maj({ variables: v })} /><//>
      <${Rang} etq="Comparer selon (facultatif)"><${ChoixVariable} valeur=${spec.groupe} types=${CATEGORIELS} onChange=${(v) => maj({ groupe: v })} /><//>`;
  else if (t === "correlation") corps = html`<${Rang} etq="Variables numériques ou ordinales"><${ChoixVariable} multiple valeur=${spec.variables || []} types=${["quanti", "ordinale"]} onChange=${(v) => maj({ variables: v })} /><//>
      <div class="grille" style="grid-template-columns:1fr 1fr"><${Rang} etq="Coefficient"><${Liste} valeur=${spec.methode || "spearman"} onChange=${(v) => maj({ methode: v })} options=${[["spearman", "Spearman (rangs) — recommandé pour des échelles"], ["kendall", "Kendall (rangs, prudent avec les ex æquo)"], ["pearson", "Pearson (linéaire, variables numériques)"]]} /><//>
      <${Rang} etq="Ajustement des p-valeurs"><${Liste} valeur=${spec.ajustement || "holm"} onChange=${(v) => maj({ ajustement: v })} options=${[["holm", "Holm (strict)"], ["bh", "Benjamini-Hochberg (proportion de fausses alertes)"], ["aucun", "Aucun"]]} /><//></div>`;
  else if (t === "regression") {
    const y = spec.y && V(spec.y), yQuali = y && y.type !== "quanti", modsY = y ? (y.modalites || []).filter((m) => !m.nr) : [];
    corps = html`<${Rang} etq="Variable à expliquer"><${ChoixVariable} valeur=${spec.y} types=${[...CATEGORIELS, "quanti"]} onChange=${(v) => maj({ y: v, modalite_cible: null, modele: null })} /><//>
      ${yQuali && html`<div class="grille" style="grid-template-columns:1fr 1fr"><${Rang} etq="Modèle"><${Liste} valeur=${spec.modele || "logistique"} onChange=${(v) => maj({ modele: v })} options=${[["logistique", "Logistique : une modalité contre les autres"], ["multinomiale", "Multinomial : chaque modalité contre une référence"]]} /><//>
        ${(spec.modele || "logistique") === "logistique" ? html`<${Rang} etq="Modalité dont on modélise la probabilité"><${Liste} valeur=${spec.modalite_cible} onChange=${(v) => maj({ modalite_cible: v })} options=${[[null, modsY.length === 2 ? "(choix automatique)" : "— choisir —"], ...modsY.map((m) => [libelleModalite(m), court(libelleModalite(m), 50)])]} /><//>`
          : html`<${Rang} etq="Modalité de référence de Y"><${Liste} valeur=${spec.reference_y} onChange=${(v) => maj({ reference_y: v })} options=${[[null, "(la première)"], ...modsY.map((m) => [libelleModalite(m), court(libelleModalite(m), 50)])]} /><//>`}</div>`}
      <${Rang} etq="Variables explicatives"><${ChoixVariable} multiple valeur=${spec.x || []} types=${[...CATEGORIELS, "quanti"]} exclure=${[spec.y].filter(Boolean)} onChange=${(v) => maj({ x: v })} /><//>
      ${(spec.x || []).filter((id) => V(id) && V(id).type !== "quanti").length > 0 && html`<${Rang} etq="Modalités de référence" aide="Chaque modalité est comparée à la référence de sa variable : préférez une modalité nombreuse et parlante.">
        <div class="grille" style="grid-template-columns:1fr 1fr;gap:6px">${(spec.x || []).filter((id) => V(id) && V(id).type !== "quanti").map((id) => html`<div class="ligne petit"><span class="tronque" style="flex:1" title=${titreComplet(id)}>${nomVar(id, 30)}</span><select class="champ" style="flex:1;padding:3px 6px" value=${spec.references?.[id] ?? ""} onChange=${(ev) => maj({ references: { ...(spec.references || {}), [id]: ev.target.value || undefined } })}><option value="">(la première)</option>${(V(id).modalites || []).filter((m) => !m.nr).map((m) => html`<option value=${libelleModalite(m)}>${court(libelleModalite(m), 40)}</option>`)}</select></div>`)}</div><//>`}
      ${y && !yQuali && html`<label class="ligne petit"><input type="checkbox" checked=${spec.robuste === "HC3"} onChange=${(ev) => maj({ robuste: ev.target.checked ? "HC3" : null })} /> Erreurs types robustes à l'hétéroscédasticité (HC3)</label>`}`;
  } else if (t === "acm") corps = html`<${Rang} etq="Variables actives (qualitatives)" aide="Elles construisent l'espace. Visez un ensemble homogène par son thème et tous posés à la même population."><${ChoixVariable} multiple valeur=${spec.actives || []} types=${CATEGORIELS} onChange=${(v) => maj({ actives: v })} /><//>
      ${sup}
      <div class="grille" style="grid-template-columns:1fr 1fr 1fr"><${Rang} etq="Non-réponses des variables actives"><${Liste} valeur=${spec.manquants || "passive"} onChange=${(v) => maj({ manquants: v })} options=${[["passive", "Modalité passive (ACM spécifique) — recommandé"], ["active", "Modalité active « Non-réponse »"], ["exclure", "Écarter les individus concernés"]]} /><//>
        <${Rang} etq="Refus / ne sait pas déclarés"><${Liste} valeur=${spec.nsp_acm || "passive"} onChange=${(v) => maj({ nsp_acm: v })} options=${[["passive", "Modalités passives"], ["active", "Modalités actives"], ["manquant", "Comme des non-réponses"]]} /><//>${indSup}</div>`;
  else if (t === "acp") corps = html`<${Rang} etq="Variables actives (numériques)"><${ChoixVariable} multiple valeur=${spec.actives || []} types=${["quanti"]} onChange=${(v) => maj({ actives: v })} /><//>${sup}
      <div class="grille" style="grid-template-columns:1fr 1fr"><${Rang} etq="Mise à l'échelle"><${Segments} options=${[[true, "ACP normée (réduite)", "Chaque variable ramenée au même écart-type"], [false, "non réduite"]]} valeur=${spec.reduire !== false} onChange=${(v) => maj({ reduire: v })} /><//>${indSup}</div>`;
  else if (t === "afdm") corps = html`<${Rang} etq="Variables actives (numériques ET qualitatives)"><${ChoixVariable} multiple valeur=${spec.actives || []} types=${[...CATEGORIELS, "quanti"]} onChange=${(v) => maj({ actives: v })} /><//>${sup}`;
  else if (t === "afc") corps = html`<div class="grille" style="grid-template-columns:1fr 1fr"><${Rang} etq="En lignes"><${ChoixVariable} valeur=${spec.ligne} types=${CATEGORIELS} onChange=${(v) => maj({ ligne: v })} /><//><${Rang} etq="En colonnes"><${ChoixVariable} valeur=${spec.colonne} types=${CATEGORIELS} onChange=${(v) => maj({ colonne: v })} /><//></div>`;
  else if (t === "cah") {
    const bases = e.analyses.filter((a) => ["acm", "acp", "afdm"].includes(a.spec.type));
    corps = html`<${Rang} etq="Analyse factorielle de départ" aide=${bases.length ? "La classification porte sur les coordonnées des individus dans cette analyse (et sur sa population)." : "Enregistrez d'abord une ACM, une ACP ou une AFDM : la classification s'appuie sur ses axes."}><${Liste} valeur=${typeof spec.base === "string" ? spec.base : null} onChange=${(v) => maj({ base: v, k: null })} options=${[[null, "— choisir —"], ...bases.map((a) => [a.id, `${a.titre} (${e.types_analyses[a.spec.type]})`])]} /><//>
      <div class="grille" style="grid-template-columns:1fr 1fr"><${Rang} etq="Nombre d'axes retenus pour classer" aide="Les derniers axes sont surtout du bruit ; essayez plusieurs valeurs pour juger de la stabilité."><input class="champ" type="number" min="1" max="20" value=${spec.n_axes_cah ?? 5} onChange=${(ev) => maj({ n_axes_cah: Math.max(1, +ev.target.value || 5), k: null })} /><//>
        <${Rang} etq="Consolidation"><${Segments} options=${[[true, "oui (centres mobiles)", "Réaffecte chaque individu à la classe dont le centre est le plus proche"], [false, "non (coupure de l'arbre)"]]} valeur=${spec.consolidation !== false} onChange=${(v) => maj({ consolidation: v })} /><//></div>`;
  } else if (t === "exploration") {
    const tous = Object.values(e.variables).filter((v) => v.role === "analyse" && !v.absente && [...CATEGORIELS, "quanti"].includes(v.type) && v.id !== spec.cible && v.n_valide >= 30).map((v) => v.id);
    corps = html`<${Rang} etq="Variable cible"><${ChoixVariable} valeur=${spec.cible} types=${[...CATEGORIELS, "quanti"]} onChange=${(v) => maj({ cible: v })} /><//>
      <${Rang} etq=${`Variables à confronter (${(spec.candidates || []).length})`} aide="Moins vous en testez, plus les p-valeurs ajustées restent informatives. Choisissez-les pour une raison.">
        <${ChoixVariable} multiple valeur=${(spec.candidates || []).length > 40 ? [] : spec.candidates || []} types=${[...CATEGORIELS, "quanti"]} exclure=${[spec.cible].filter(Boolean)} onChange=${(v) => maj({ candidates: v })} />
        <div class="ligne" style="margin-top:6px">${(spec.candidates || []).length > 40 && html`<span class="petit secondaire">${spec.candidates.length} variables sélectionnées</span>`}<button class="btn petit" onClick=${() => maj({ candidates: tous })}>Toutes les variables analysables (${tous.length})</button>${(spec.candidates || []).length > 0 && html`<button class="btn discret petit" onClick=${() => maj({ candidates: [] })}>Vider</button>`}</div><//>`;
  }
  return html`<div><${Rang} etq="Population"><${Liste} valeur=${spec.population} onChange=${(v) => maj({ population: v })} options=${pops} /><//>${corps}</div>`;
}

function complet(s) {
  const n = (x) => (x || []).length;
  return { tri: !!s.variable, croise: !!(s.ligne && s.colonne), multiples: n(s.variables) >= 2, correlation: n(s.variables) >= 2, regression: !!s.y && n(s.x) >= 1, acm: n(s.actives) >= 2, acp: n(s.actives) >= 2, afdm: n(s.actives) >= 2, afc: !!(s.ligne && s.colonne), cah: !!s.base, exploration: !!s.cible && n(s.candidates) >= 1 }[s.type];
}
function titreAuto(s) {
  const e = magasin.etat, nv = (id) => nomVar(id, 34), pop = s.population ? ` — ${e.populations.find((p) => p.id === s.population)?.nom || "?"}` : "";
  const base = { tri: () => `Tri à plat : ${nv(s.variable)}`, croise: () => `${nv(s.ligne)} × ${nv(s.colonne)}`, multiples: () => `Réponses multiples : ${court(e.variables[s.variables[0]]?.libelle, 40)}`, correlation: () => `Corrélations (${s.variables.length} variables)`, regression: () => `Régression : ${nv(s.y)}`, acm: () => `ACM (${s.actives.length} variables actives)`, acp: () => `ACP (${s.actives.length} variables)`, afdm: () => `AFDM (${s.actives.length} variables)`, afc: () => `AFC : ${nv(s.ligne)} × ${nv(s.colonne)}`, cah: () => `Classification — ${e.analyses.find((a) => a.id === s.base)?.titre || ""}`, exploration: () => `Exploration : ${nv(s.cible)}` }[s.type];
  try { return base() + pop; } catch (err) { return e.types_analyses[s.type]; }
}

// ---------------------------------------------------------------- fiche de calcul
function Fiche({ fiche, spec, titre, pid }) {
  const [script, setScript] = useState(null);
  if (!fiche) return html`<p class="muet petit">La fiche de calcul apparaîtra avec le résultat : données utilisées, exclusions, paramètres, méthode.</p>`;
  const d = fiche.donnees, m = fiche.methode || {};
  const voirScript = () => api(`/p/${pid}/export/script`, { methode: "POST", corps: { spec, titre } }).then((r) => setScript(r.script)).catch((e) => toast(e.message, true));
  return html`<div class="petit">
    <h4>Données</h4>
    <div class="flux"><div><b>${ent(d.n_total)}</b>réponses</div>${d.n_base !== d.n_total ? html`<span>→</span><div><b>${ent(d.n_base)}</b>après exclusions</div>` : ""}${d.population ? html`<span>→</span><div><b>${ent(d.n_population)}</b>${court(d.population.nom, 18)}</div>` : ""}<span>→</span><div style="background:var(--accent-clair);color:var(--accent)"><b>${ent(d.n_analyses)}</b>analysés</div></div>
    ${d.population && html`<p class="secondaire" style="margin-top:4px">Population « ${d.population.nom} » : ${d.population.description}</p>`}
    ${d.exclusions_globales.map((x) => html`<p class="secondaire">Exclusion générale : ${ent(x.n)} individu(s) — ${x.motif || "sans motif indiqué"}</p>`)}
    ${d.exclusions.length > 0 && html`<div style="margin-top:6px"><b>Individus de la population non analysés</b> (valeur manquante) :<ul style="margin:4px 0;padding-left:18px">${d.exclusions.map((x) => html`<li>${x.nom} : ${ent(x.n)} <span class="muet">(${Object.entries(x.motifs).map(([k, v]) => `${k.toLowerCase()} : ${v}`).join(" ; ")})</span></li>`)}</ul><span class="muet">Un même individu peut manquer sur plusieurs variables.</span></div>`}
    <p class="muet" style="margin-top:6px">${d.sources.map((s) => `${s.fichier} (empreinte ${s.sha256})`).join(" ; ")} · version ${fiche.version_projet} du projet</p>
    <hr /><h4>Variables</h4>
    ${fiche.variables.map((v) => html`<div style="margin-top:6px"><a href=${`#/p/${pid}/donnees/${v.id}`} title=${(v.libelle || "") + (v.sous_libelle ? ` [${v.sous_libelle}]` : "")}>${v.nom}</a> <span class="badge">${TYPES[v.type] || v.type}</span>
      ${v.derive && html`<div class="secondaire">↳ construite : ${v.derive.type}${v.derive.sources.length ? ` à partir de ${v.derive.sources.map((s) => `« ${s} »`).join(", ")}` : ""}${v.derive.note ? ` — ${v.derive.note}` : ""}</div>`}
      ${v.champ && html`<div class="secondaire">↳ posée si ${v.champ}</div>`}
      <div class="muet">${Object.entries(v.statuts).filter(([, n]) => n).map(([k, n]) => `${magasin.etat.statuts[k].toLowerCase()} : ${n}`).join(" · ")}</div></div>`)}
    <hr /><h4>Méthode</h4>
    <dl class="kv" style="grid-template-columns:1fr;gap:2px">${Object.entries(m).filter(([, v]) => typeof v === "string" || typeof v === "number").map(([k, v]) => html`<dd><span class="muet">${k.replace(/_/g, " ")} : </span>${v}</dd>`)}</dl>
    <details class="aide" style="margin-top:8px"><summary>Paramètres enregistrés</summary><pre class="mono" style="white-space:pre-wrap;word-break:break-word;background:var(--surface-2);padding:8px;border-radius:6px;margin:0">${JSON.stringify(fiche.parametres, null, 1)}</pre></details>
    <hr /><h4>Reproduire ce calcul</h4>
    <p class="secondaire" style="margin-top:4px">Un script R (FactoMineR, car…) et les données exactement analysées, pour refaire le calcul avec un logiciel de référence ou le joindre à une annexe.</p>
    <div class="ligne" style="flex-wrap:wrap"><button class="btn petit" onClick=${voirScript}>Voir le script R</button><button class="btn petit" onClick=${() => telechargerDepuis("/export/reproduction", "reproduction.zip", { spec, titre })}><${Icone} nom="export" taille=${13} /> Script + données (.zip)</button></div>
    <p class="mini muet" style="margin-top:6px">Le fichier de données contient des réponses individuelles : ne le diffusez pas sans précaution.</p>
    ${script && html`<${Modale} large titre="Script R de reproduction" onFermer=${() => setScript(null)} pied=${html`<button class="btn" onClick=${() => { navigator.clipboard.writeText(script); toast("Script copié"); }}>Copier</button><button class="btn primaire" onClick=${() => setScript(null)}>Fermer</button>`}><pre class="mono" style="white-space:pre-wrap;margin:0">${script}</pre><//>`}
  </div>`;
}

// ---------------------------------------------------------------- atelier (une analyse)
function useCalcul(pid, spec, version) {
  const [etat, setEtat] = useState({ r: null, erreur: null, calcul: false });
  const cle = JSON.stringify(spec);
  useEffect(() => {
    if (!spec || !complet(spec)) { setEtat({ r: null, erreur: null, calcul: false }); return; }
    let annule = false;
    setEtat((x) => ({ ...x, calcul: true }));
    const t = setTimeout(() => api(`/p/${pid}/calcul`, { methode: "POST", corps: spec }).then((r) => !annule && setEtat({ r, erreur: null, calcul: false })).catch((e) => !annule && setEtat({ r: null, erreur: e.message, calcul: false })), 350);
    return () => { annule = true; clearTimeout(t); };
  }, [cle, version]);
  return etat;
}

function Resultat({ etat, spec, pid, majSpec, analyseId, enregistrer }) {
  if (etat.erreur) return html`<div class="note erreur">${etat.erreur}</div>`;
  if (!etat.r) return html`<div class="carte muet">${etat.calcul ? "Calcul en cours…" : "Complétez la spécification ci-dessus : le résultat se calcule automatiquement."}</div>`;
  const R = RENDUS[etat.r.type], f = etat.r.fiche;
  return html`<div style=${etat.calcul ? "opacity:.55" : ""}>
    ${f.lecture && html`<div class="lecture">${f.lecture}</div>`}
    <${Avertissements} liste=${f.avertissements} />
    <div style="margin-top:12px"><${R} r=${etat.r.resultat} spec=${spec} pid=${pid} majSpec=${majSpec} analyseId=${analyseId} enregistrer=${enregistrer} /></div></div>`;
}

function Atelier({ pid, aid }) {
  const m = useMagasin(), e = m.etat;
  const sauvee = aid !== "nouvelle" ? e.analyses.find((a) => a.id === aid) : null;
  const [spec, setSpec] = useState(() => JSON.parse(JSON.stringify(sauvee ? sauvee.spec : m.brouillon || {})));
  const [titre, setTitre] = useState(sauvee ? sauvee.titre : "");
  const [notes, setNotes] = useState(sauvee ? sauvee.notes || "" : "");
  const [panneau, setPanneau] = useState("fiche");
  const [replie, setReplie] = useState(!!sauvee);
  const [comparer, setComparer] = useState(null);
  const etat = useCalcul(pid, spec, e.projet.version);
  const autre = e.analyses.find((a) => a.id === comparer);
  const etatAutre = useCalcul(pid, autre ? autre.spec : null, e.projet.version);
  const maj = (modif) => setSpec((s) => ({ ...s, ...modif }));
  const modifiee = !sauvee || JSON.stringify(spec) !== JSON.stringify(sauvee.spec) || titre !== sauvee.titre || notes !== (sauvee.notes || "");
  const enregistrer = async () => {
    const t = titre.trim() || titreAuto(spec);
    if (sauvee) { await agir(`/analyses/${sauvee.id}`, { methode: "PUT", corps: { titre: t, spec, notes } }, "Analyse enregistrée"); setTitre(t); return sauvee.id; }
    const r = await agir("/analyses", { methode: "POST", corps: { titre: t, spec, notes } }, "Analyse enregistrée");
    publier({ brouillon: null }); aller(`/p/${pid}/analyses/${r.analyse.id}`); return r.analyse.id;
  };
  const dupliquer = () => { publier({ brouillon: JSON.parse(JSON.stringify(spec)) }); aller(`/p/${pid}/analyses/nouvelle`); toast("Copie ouverte : modifiez-la librement, l'original n'est pas touché"); };
  const supprimer = async () => { if (!confirm(`Supprimer l'analyse « ${sauvee.titre} » ? (annulable)`)) return; await agir(`/analyses/${sauvee.id}`, { methode: "DELETE" }, "Analyse supprimée — Annuler pour la rétablir"); aller(`/p/${pid}/analyses`); };
  if (!spec.type) return html`<div class="page muet">Analyse introuvable. <a href=${`#/p/${pid}/analyses`}>Retour</a></div>`;
  return html`<div style="display:grid;grid-template-columns:minmax(0,1fr) 330px;height:100%;min-height:0">
    <div class="colonne"><div style="padding:20px 24px 60px;max-width:1000px;margin:0 auto">
      <div class="ligne" style="margin-bottom:4px"><span class="badge">${e.types_analyses[spec.type]}</span>${!sauvee ? html`<span class="badge" style="background:var(--alerte-fond);color:var(--alerte-encre)">non enregistrée</span>` : modifiee ? html`<span class="badge" style="background:var(--alerte-fond);color:var(--alerte-encre)">modifications non enregistrées</span>` : html`<span class="mini muet">enregistrée</span>`}
        <span class="pousse ligne" style="gap:4px">
          <button class="btn petit primaire" disabled=${!complet(spec) || !modifiee} onClick=${enregistrer}>Enregistrer</button>
          <button class="btn petit" disabled=${!complet(spec)} onClick=${dupliquer} title="Ouvrir une copie pour essayer une autre spécification">Dupliquer</button>
          <select class="champ" style="width:auto;padding:3px 6px;font-size:12.5px" value=${comparer || ""} onChange=${(ev) => setComparer(ev.target.value || null)} title="Afficher une autre analyse enregistrée à la suite, pour comparer"><option value="">Comparer avec…</option>${e.analyses.filter((a) => a.id !== aid).map((a) => html`<option value=${a.id}>${court(a.titre, 44)}</option>`)}</select>
          ${sauvee && html`<button class="btn discret petit danger" onClick=${supprimer} title="Supprimer"><${Icone} nom="poubelle" taille=${14} /></button>`}</span></div>
      <input class="champ" style="font-family:var(--serif);font-size:20px;font-weight:600;border-color:transparent;background:transparent;padding:4px 0" placeholder=${complet(spec) ? titreAuto(spec) : "Titre de l'analyse"} value=${titre} onInput=${(ev) => setTitre(ev.target.value)} />
      <div class="carte" style="margin-top:8px"><div class="ligne espace" style="cursor:pointer" onClick=${() => setReplie(!replie)}><h3>Spécification</h3><span class="btn discret petit"><${Icone} nom=${replie ? "bas" : "haut"} taille=${14} /> ${replie ? "afficher" : "replier"}</span></div>
        ${!replie && html`<div style="margin-top:12px"><${Constructeur} spec=${spec} maj=${maj} /></div>`}</div>
      <div style="margin-top:14px">${comparer && html`<h3 style="margin-bottom:8px">A — ${titre || titreAuto(spec)}</h3>`}<${Resultat} etat=${etat} spec=${spec} pid=${pid} majSpec=${maj} analyseId=${sauvee?.id} enregistrer=${enregistrer} /></div>
      ${autre && html`<div style="margin-top:26px;padding-top:18px;border-top:2px solid var(--bord-fort)"><div class="ligne espace"><h3>B — ${autre.titre}</h3><span class="ligne"><a class="petit" href=${`#/p/${pid}/analyses/${autre.id}`}>ouvrir</a><button class="btn discret petit" onClick=${() => setComparer(null)}>fermer la comparaison</button></span></div>
        ${etat.r && etatAutre.r && html`<div class="note" style="margin:8px 0">A : ${ent(etat.r.fiche.donnees.n_analyses)} individus analysés (${etat.r.fiche.donnees.population?.nom || "tous les répondants"}) · B : ${ent(etatAutre.r.fiche.donnees.n_analyses)} (${etatAutre.r.fiche.donnees.population?.nom || "tous les répondants"}). ${etat.r.fiche.donnees.n_analyses !== etatAutre.r.fiche.donnees.n_analyses ? "Les deux analyses ne portent pas sur les mêmes individus : une différence de résultat peut venir de là." : ""}</div>`}
        <${Resultat} etat=${etatAutre} spec=${autre.spec} pid=${pid} majSpec=${() => toast("Ouvrez l'analyse B pour la modifier")} analyseId=${autre.id} enregistrer=${async () => autre.id} /></div>`}
    </div></div>
    <aside class="colonne" style="border-left:1px solid var(--bord);background:var(--surface);padding:12px 16px 40px">
      <${Onglets} onglets=${[["fiche", "Fiche de calcul"], ["comprendre", "Comprendre"], ["notes", "Notes"]]} actif=${panneau} onChange=${setPanneau} />
      ${panneau === "fiche" && html`<${Fiche} fiche=${etat.r?.fiche} spec=${spec} titre=${titre || (complet(spec) ? titreAuto(spec) : "")} pid=${pid} />`}
      ${panneau === "comprendre" && html`<${Comprendre} type=${spec.type} />`}
      ${panneau === "notes" && html`<div><p class="petit secondaire">Hypothèses de départ, lecture du résultat, pistes : ces notes sont enregistrées avec l'analyse et reprises dans le journal méthodologique. Écrire ce que l'on attend <i>avant</i> de regarder aide à distinguer ce que l'on a trouvé de ce que l'on cherchait.</p>
        <textarea class="champ" style="min-height:260px" value=${notes} onInput=${(ev) => setNotes(ev.target.value)} placeholder="Hypothèse : …&#10;&#10;Lecture : …"></textarea>
        <button class="btn petit primaire" style="margin-top:8px" disabled=${!complet(spec) || !modifiee} onClick=${enregistrer}>Enregistrer</button></div>`}
    </aside></div>`;
}

function Choix({ pid }) {
  const e = useMagasin().etat;
  const nouvelle = (type) => { publier({ brouillon: { type } }); aller(`/p/${pid}/analyses/nouvelle`); };
  return html`<div class="page"><h1>Analyses</h1>
    <p class="secondaire" style="margin-top:4px;max-width:720px">Chaque analyse se calcule dès qu'elle est spécifiée, s'accompagne d'une fiche de calcul (données, exclusions, méthode) et d'une aide de lecture. Enregistrez celles que vous voulez garder ; dupliquez-les pour essayer d'autres choix.</p>
    ${e.analyses.length > 0 && html`<h2 style="margin:22px 0 10px">Analyses enregistrées</h2>
      ${[...e.analyses].reverse().map((a) => html`<div class="carte cliquable ligne" style="padding:10px 14px;margin-top:8px" onClick=${() => aller(`/p/${pid}/analyses/${a.id}`)}><div style="flex:1;min-width:0"><b>${a.titre}</b>${a.notes ? html`<div class="petit secondaire tronque">${a.notes}</div>` : ""}</div><span class="badge">${e.types_analyses[a.spec.type]}</span><span class="mini muet">${(a.modifie || "").slice(0, 10)}</span></div>`)}`}
    ${FAMILLES.map(([nom, types]) => html`<h2 style="margin:24px 0 10px">${nom}</h2><div class="type-analyse">${types.map(([t, d]) => html`<div class="carte cliquable" onClick=${() => nouvelle(t)}><h3>${e.types_analyses[t]}</h3><p class="petit secondaire" style="margin:4px 0 0">${d}</p></div>`)}</div>`)}
  </div>`;
}

export function VueAnalyses({ pid, reste }) {
  const m = useMagasin();
  const aid = reste[0];
  if (!aid || (aid === "nouvelle" && !m.brouillon)) return html`<${Choix} pid=${pid} />`;
  return html`<${Atelier} pid=${pid} aid=${aid} key=${aid + (aid === "nouvelle" ? JSON.stringify(m.brouillon) : "")} />`;
}
