// Socle de l'interface : accès au serveur local, état du projet, formats, petits composants partagés.
import { html, render, useState, useEffect, useRef, useMemo, useCallback } from "../vendor/preact-htm.js";
export { html, render, useState, useEffect, useRef, useMemo, useCallback };

// ---------------------------------------------------------------- serveur
export async function api(chemin, { methode = "GET", corps, brut = false } = {}) {
  const options = { method: methode, headers: {} };
  if (corps instanceof FormData) options.body = corps;
  else if (corps !== undefined) { options.body = JSON.stringify(corps); options.headers["Content-Type"] = "application/json"; }
  const r = await fetch("/api" + chemin, options);
  if (!r.ok) {
    let detail = r.statusText;
    try { const j = await r.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (e) { /* pas de JSON */ }
    throw new Error(detail);
  }
  if (brut) return r;
  const type = r.headers.get("content-type") || "";
  return type.includes("json") ? r.json() : r.text();
}

// ---------------------------------------------------------------- état global
const abonnes = new Set();
export const magasin = { etat: null, pid: null, toast: null, version: 0 };
export function publier(modifs) { Object.assign(magasin, modifs); magasin.version++; abonnes.forEach((f) => f(magasin.version)); }
export function useMagasin() {
  const [, set] = useState(0);
  useEffect(() => { abonnes.add(set); return () => abonnes.delete(set); }, []);
  return magasin;
}
export function toast(message, erreur = false) {
  publier({ toast: { message, erreur } });
  clearTimeout(toast.t);
  toast.t = setTimeout(() => publier({ toast: null }), erreur ? 7000 : 3200);
}
export async function chargerProjet(pid) {
  const etat = await api(`/p/${pid}`);
  publier({ etat, pid });
  return etat;
}
/** Appelle le serveur pour une modification du projet et met à jour l'état local. */
export async function agir(chemin, options, message) {
  try {
    const r = await api(`/p/${magasin.pid}${chemin}`, options);
    if (r.etat) publier({ etat: r.etat });
    if (message) toast(message);
    return r;
  } catch (e) { toast(e.message, true); throw e; }
}
export const E = () => magasin.etat;

// ---------------------------------------------------------------- navigation (hash)
export function aller(chemin) { location.hash = chemin; }
export function useRoute() {
  const [h, setH] = useState(location.hash);
  useEffect(() => { const f = () => setH(location.hash); addEventListener("hashchange", f); return () => removeEventListener("hashchange", f); }, []);
  return h.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
}

// ---------------------------------------------------------------- formats
export const nf = (x, d = 1) => (x === null || x === undefined || Number.isNaN(x)) ? "—" : Number(x).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
export const ent = (x) => (x === null || x === undefined) ? "—" : Math.round(x).toLocaleString("fr-FR");
export const pct = (x, d = 1) => (x === null || x === undefined) ? "—" : nf(x, d) + " %";
export function pval(p) {
  if (p === null || p === undefined) return "—";
  if (p < 0.001) return "< 0,001";
  return nf(p, p < 0.1 ? 3 : 2);
}
export const court = (t, n = 60) => { t = (t || "").replace(/\s+/g, " ").trim(); return t.length <= n ? t : t.slice(0, n - 1).trimEnd() + "…"; };
export const TYPES = { quali: "qualitative", ordinale: "ordinale", multi: "case à cocher", quanti: "numérique", texte: "texte libre", date: "date", identifiant: "identifiant", vide: "vide" };
export const CATEGORIELS = ["quali", "ordinale", "multi"];

/** Nom d'affichage d'une variable : nom court choisi, sinon intitulé de l'item, sinon question. */
export function nomVar(v, n = 60) {
  if (typeof v === "string") v = E()?.variables[v] || { id: v };
  if (!v) return "?";
  if (v.nom && v.nom !== v.id) return v.nom;
  return court(v.sous_libelle || v.libelle || v.id, n);
}
export function titreComplet(v) {
  if (typeof v === "string") v = E()?.variables[v] || { id: v };
  return (v.libelle || v.id) + (v.sous_libelle ? ` [${v.sous_libelle}]` : "");
}
export const libelleModalite = (m) => m.libelle || m.valeur;

// ---------------------------------------------------------------- petits composants
export const Icone = ({ nom, taille = 16 }) => {
  const d = {
    donnees: "M3 5h18M3 12h18M3 19h18M8 5v14", preparation: "M4 6h10M4 12h16M4 18h7M17 4v4M14 16v4", analyses: "M4 19V5M4 19h16M8 15l3-4 3 2 5-7",
    journal: "M6 3h11a2 2 0 0 1 2 2v16l-4-2-3 2-3-2-3 2V3zM9 8h7M9 12h7", annuler: "M9 7L4 12l5 5M4 12h11a5 5 0 0 1 0 10h-2", retablir: "M15 7l5 5-5 5M20 12H9a5 5 0 0 0 0 10h2",
    plus: "M12 5v14M5 12h14", fermer: "M6 6l12 12M18 6L6 18", fleche: "M9 6l6 6-6 6", haut: "M6 15l6-6 6 6", bas: "M6 9l6 6 6-6", export: "M12 3v12M7 10l5 5 5-5M5 21h14",
    info: "M12 8h.01M11 12h1v5h1M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", copie: "M9 9h11v11H9zM5 15H4V4h11v1", poubelle: "M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13",
    crayon: "M4 20h4L19 9l-4-4L4 16v4zM13 7l4 4", oeil: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z", cadenas: "M6 11h12v9H6zM9 11V8a3 3 0 0 1 6 0v3",
  }[nom];
  return html`<svg width=${taille} height=${taille} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d=${d} /></svg>`;
};

export function Modale({ titre, onFermer, children, pied, large }) {
  useEffect(() => { const f = (e) => e.key === "Escape" && onFermer(); addEventListener("keydown", f); return () => removeEventListener("keydown", f); }, []);
  return html`<div class="voile" onMouseDown=${(e) => e.target === e.currentTarget && onFermer()}>
    <div class=${"modale" + (large ? " large" : "")} role="dialog" aria-label=${titre}>
      <header><h2>${titre}</h2><button class="btn discret pousse" onClick=${onFermer} aria-label="Fermer"><${Icone} nom="fermer" /></button></header>
      <div class="corps">${children}</div>
      ${pied && html`<footer>${pied}</footer>`}
    </div></div>`;
}

export function Onglets({ onglets, actif, onChange }) {
  return html`<div class="onglets" role="tablist">${onglets.map(([id, lib]) => html`<button role="tab" class=${"onglet" + (actif === id ? " actif" : "")} onClick=${() => onChange(id)}>${lib}</button>`)}</div>`;
}
export function Segments({ options, valeur, onChange }) {
  return html`<div class="segments">${options.map(([id, lib, titre]) => html`<button class=${valeur === id ? "actif" : ""} title=${titre || ""} onClick=${() => onChange(id)}>${lib}</button>`)}</div>`;
}
export const Badge = ({ v }) => html`<span class=${"badge " + (v.derive ? "derive" : v.type)} title=${v.derive ? "Variable construite par une étape de préparation" : ""}>${v.derive ? "construite · " : ""}${TYPES[v.type] || v.type}</span>`;
export const Avertissements = ({ liste }) => (liste || []).length ? html`<div>${liste.map((a) => html`<div class="note alerte">${a}</div>`)}</div>` : null;

/** Infobulle globale : <span ...infobulle("texte")> ou infobulle(() => html`…`). */
let noeudBulle = null;
export function montrerBulle(evt, contenu) {
  if (!noeudBulle) { noeudBulle = document.createElement("div"); noeudBulle.className = "infobulle"; document.body.appendChild(noeudBulle); }
  noeudBulle.style.display = "block";
  render(typeof contenu === "string" ? html`<span>${contenu}</span>` : contenu, noeudBulle);
  const r = noeudBulle.getBoundingClientRect();
  let x = evt.clientX + 14, y = evt.clientY + 14;
  if (x + r.width > innerWidth - 8) x = evt.clientX - r.width - 12;
  if (y + r.height > innerHeight - 8) y = evt.clientY - r.height - 12;
  noeudBulle.style.left = Math.max(4, x) + "px"; noeudBulle.style.top = Math.max(4, y) + "px";
}
export function cacherBulle() { if (noeudBulle) noeudBulle.style.display = "none"; }
export const bulle = (contenu) => ({ onMouseMove: (e) => montrerBulle(e, typeof contenu === "function" ? contenu() : contenu), onMouseLeave: cacherBulle });

// ---------------------------------------------------------------- sélecteur de variables
function texteRecherche(v, q) { return ((v.nom || "") + " " + (v.libelle || "") + " " + (v.sous_libelle || "") + " " + (q?.libelle || "")).toLowerCase(); }
const normaliser = (t) => t.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

/** Liste déroulante avec recherche. types : types acceptés ; multiple : sélection de plusieurs variables. */
export function ChoixVariable({ valeur, onChange, types, multiple, placeholder = "Choisir une variable…", exclure = [], filtre }) {
  const etat = E();
  const [ouvert, setOuvert] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef();
  useEffect(() => {
    if (!ouvert) return;
    const f = (e) => ref.current && !ref.current.contains(e.target) && setOuvert(false);
    addEventListener("mousedown", f); return () => removeEventListener("mousedown", f);
  }, [ouvert]);
  const selection = multiple ? (valeur || []) : (valeur ? [valeur] : []);
  const candidates = useMemo(() => Object.values(etat.variables).filter((v) => v.role === "analyse" && !v.absente
    && (!types || types.includes(v.type)) && !exclure.includes(v.id) && (!filtre || filtre(v))), [etat, types, exclure.join(","), filtre]);
  const termes = normaliser(q).split(/\s+/).filter(Boolean);
  const trouvees = candidates.filter((v) => { const t = normaliser(texteRecherche(v, etat.questions[v.question])); return termes.every((x) => t.includes(x)); }).slice(0, 120);
  const choisir = (v) => {
    if (multiple) onChange(selection.includes(v.id) ? selection.filter((x) => x !== v.id) : [...selection, v.id]);
    else { onChange(v.id); setOuvert(false); setQ(""); }
  };
  const famille = (v) => { const qu = etat.questions[v.question]; return qu && qu.variables.length > 1 ? qu.variables.filter((x) => candidates.some((c) => c.id === x)) : null; };
  return html`<div ref=${ref} style="position:relative">
    ${multiple && selection.length > 0 && html`<div class="puces" style="margin-bottom:5px">${selection.map((id) => html`<span class="puce" title=${titreComplet(id)}><span class="tronque">${nomVar(id, 34)}</span><button onClick=${() => onChange(selection.filter((x) => x !== id))} aria-label="Retirer">×</button></span>`)}</div>`}
    ${!multiple && valeur && !ouvert
      ? html`<div class="champ ligne" style="cursor:pointer" onClick=${() => setOuvert(true)} title=${titreComplet(valeur)}><span class="tronque" style="flex:1">${nomVar(valeur, 70)}</span>${etat.variables[valeur] && html`<${Badge} v=${etat.variables[valeur]} />`}<button class="btn discret petit" onClick=${(e) => { e.stopPropagation(); onChange(null); }} aria-label="Retirer">×</button></div>`
      : html`<input class="champ" placeholder=${multiple && selection.length ? "Ajouter une variable…" : placeholder} value=${q} onFocus=${() => setOuvert(true)} onInput=${(e) => { setQ(e.target.value); setOuvert(true); }} />`}
    ${ouvert && html`<div class="menu" style="left:0;right:0;top:100%;margin-top:3px">
      ${trouvees.length === 0 && html`<div class="option muet">Aucune variable ne correspond${types ? ` (types acceptés : ${types.map((t) => TYPES[t]).join(", ")})` : ""}.</div>`}
      ${trouvees.map((v) => { const fam = multiple && famille(v); return html`<div class=${"option" + (selection.includes(v.id) ? " survol" : "")} onClick=${() => choisir(v)} title=${titreComplet(v)}>
        <span style="flex:1;min-width:0"><span class="clamp2">${v.sous_libelle ? html`<b>${court(v.sous_libelle, 60)}</b> <span class="muet">· ${court(v.libelle, 50)}</span>` : (v.nom !== v.id ? html`<b>${v.nom}</b> <span class="muet">· ${court(v.libelle, 50)}</span>` : court(v.libelle, 90))}</span></span>
        ${fam && fam.length > 1 && html`<button class="btn discret petit" title="Ajouter tous les items de cette question" onClick=${(e) => { e.stopPropagation(); onChange([...new Set([...selection, ...fam])]); }}>+ ${fam.length} items</button>`}
        <${Badge} v=${v} /><span class="mini muet nowrap">n=${v.n_valide}</span></div>`; })}
    </div>`}
  </div>`;
}

// ---------------------------------------------------------------- éditeur de conditions
const TESTS_QUALI = [["dans", "est"], ["hors", "n'est pas"], ["renseigne", "est renseigné"], ["manquant", "est manquant"]];
const TESTS_QUANTI = [[">=", "≥"], [">", ">"], ["<=", "≤"], ["<", "<"], ["=", "="], ["renseigne", "est renseigné"], ["manquant", "est manquant"]];

export function EditeurCondition({ valeur, onChange, compter = true }) {
  const etat = E();
  const cond = valeur && valeur.regles ? valeur : { op: "et", regles: valeur && valeur.var ? [valeur] : [] };
  const [apercu, setApercu] = useState(null);
  const maj = (regles, op = cond.op) => onChange({ op, regles });
  useEffect(() => {
    if (!compter) return;
    const complet = cond.regles.every((r) => r.var && (["renseigne", "manquant"].includes(r.test) || (r.valeurs && r.valeurs.length) || r.valeur !== undefined && r.valeur !== ""));
    if (!complet || !cond.regles.length) { setApercu(null); return; }
    let annule = false;
    api(`/p/${magasin.pid}/populations/apercu`, { methode: "POST", corps: { condition: cond } }).then((r) => !annule && setApercu(r)).catch(() => !annule && setApercu(null));
    return () => { annule = true; };
  }, [JSON.stringify(cond)]);
  return html`<div>
    ${cond.regles.map((r, i) => {
      const v = r.var && etat.variables[r.var];
      const quanti = v && v.type === "quanti";
      const tests = quanti ? TESTS_QUANTI : TESTS_QUALI;
      const majR = (m) => maj(cond.regles.map((x, j) => (j === i ? { ...x, ...m } : x)));
      return html`<div class="ligne haut" style="margin-bottom:8px">
        <span class="muet petit" style="width:26px;padding-top:7px">${i === 0 ? "Si" : (cond.op === "ou" ? "ou" : "et")}</span>
        <div style="flex:2;min-width:0"><${ChoixVariable} valeur=${r.var} types=${["quali", "ordinale", "multi", "quanti"]} onChange=${(id) => majR({ var: id, test: id && etat.variables[id].type === "quanti" ? ">=" : "dans", valeurs: [], valeur: undefined })} /></div>
        ${v && html`<select class="champ" style="width:130px" value=${r.test || "dans"} onChange=${(e) => majR({ test: e.target.value })}>${tests.map(([id, lib]) => html`<option value=${id}>${lib}</option>`)}</select>`}
        ${v && ["dans", "hors"].includes(r.test || "dans") && html`<div style="flex:2;min-width:0;max-height:150px;overflow:auto;border:1px solid var(--bord);border-radius:6px;padding:4px 8px">
          ${(v.modalites || []).map((m) => html`<label class="ligne petit" style="padding:1px 0"><input type="checkbox" checked=${(r.valeurs || []).includes(m.valeur)} onChange=${(e) => majR({ valeurs: e.target.checked ? [...(r.valeurs || []), m.valeur] : (r.valeurs || []).filter((x) => x !== m.valeur) })} /> <span>${court(libelleModalite(m), 70)}</span></label>`)}</div>`}
        ${v && quanti && !["renseigne", "manquant"].includes(r.test) && html`<input class="champ" type="number" style="width:110px" value=${r.valeur ?? ""} onInput=${(e) => majR({ valeur: e.target.value === "" ? "" : Number(e.target.value) })} />`}
        <button class="btn discret petit" onClick=${() => maj(cond.regles.filter((_, j) => j !== i))} aria-label="Retirer la condition">×</button>
      </div>`;
    })}
    <div class="ligne">
      <button class="btn petit" onClick=${() => maj([...cond.regles, { var: null, test: "dans", valeurs: [] }])}><${Icone} nom="plus" taille=${13} /> Ajouter une condition</button>
      ${cond.regles.length > 1 && html`<${Segments} options=${[["et", "toutes (ET)"], ["ou", "au moins une (OU)"]]} valeur=${cond.op || "et"} onChange=${(op) => maj(cond.regles, op)} />`}
      ${apercu && html`<span class="petit secondaire pousse"><b>${ent(apercu.n)}</b> individus sur ${ent(apercu.n_base)}</span>`}
    </div>
  </div>`;
}

// ---------------------------------------------------------------- exports côté navigateur
export function telecharger(nom, contenu, type = "text/plain;charset=utf-8") {
  const blob = contenu instanceof Blob ? contenu : new Blob([contenu], { type });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = nom; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
export async function telechargerDepuis(chemin, nom, corps) {
  try {
    const r = await api(`/p/${magasin.pid}${chemin}`, { methode: corps ? "POST" : "GET", corps, brut: true });
    telecharger(nom, await r.blob());
  } catch (e) { toast(e.message, true); }
}
/** Lit un <table> du DOM et le transforme en {entetes, lignes} pour l'export Excel / le presse-papiers. */
export function lireTable(table) {
  const lignes = [...table.querySelectorAll("tr")].map((tr) => [...tr.children].map((td) => {
    const t = (td.dataset.v !== undefined ? td.dataset.v : td.innerText).trim();
    const n = Number(t.replace(/\s/g, "").replace(",", ".").replace("%", "").replace("−", "-"));
    return t !== "" && !Number.isNaN(n) && /^[−\-+]?[\d\s]+([.,]\d+)?\s*%?$/.test(t) ? n : t;
  }));
  return { entetes: lignes[0] || [], lignes: lignes.slice(1) };
}
export function BoutonsTable({ refTable, titre, notes = [] }) {
  const etat = E();
  const lire = () => ({ titre, ...lireTable(refTable.current), notes: [...notes, ...(etat.projet.fictif ? ["DONNÉES FICTIVES"] : [])] });
  return html`<span class="ligne" style="gap:2px">
    <button class="btn discret petit" title="Copier le tableau (à coller dans un tableur ou un traitement de texte)" onClick=${() => { const t = lire(); navigator.clipboard.writeText([t.entetes, ...t.lignes].map((l) => l.map((c) => typeof c === "number" ? String(c).replace(".", ",") : c).join("\t")).join("\n")); toast("Tableau copié"); }}><${Icone} nom="copie" taille=${14} /> Copier</button>
    <button class="btn discret petit" title="Télécharger en Excel" onClick=${() => telechargerDepuis("/export/xlsx", (titre || "tableau").slice(0, 60) + ".xlsx", { tableaux: [lire()] })}><${Icone} nom="export" taille=${14} /> Excel</button>
  </span>`;
}
/** Exporte un <svg> affiché (SVG vectoriel ou PNG 2×), avec les couleurs calculées et un fond. */
export function exporterSvg(svg, nom, format = "svg") {
  const clone = svg.cloneNode(true);
  const css = getComputedStyle(document.documentElement);
  const resoudre = (v) => v.replace(/var\((--[\w-]+)\)/g, (_, n) => css.getPropertyValue(n).trim());
  clone.querySelectorAll("*").forEach((el) => { for (const a of ["fill", "stroke", "stop-color"]) { const v = el.getAttribute(a); if (v && v.includes("var(")) el.setAttribute(a, resoudre(v)); } });
  const l = svg.viewBox.baseVal.width || svg.clientWidth, h = svg.viewBox.baseVal.height || svg.clientHeight;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg"); clone.setAttribute("width", l); clone.setAttribute("height", h);
  clone.setAttribute("font-family", "Helvetica, Arial, sans-serif");
  const fond = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  fond.setAttribute("width", "100%"); fond.setAttribute("height", "100%"); fond.setAttribute("fill", css.getPropertyValue("--surface").trim());
  clone.insertBefore(fond, clone.firstChild);
  const texte = new XMLSerializer().serializeToString(clone);
  if (format === "svg") return telecharger(nom + ".svg", texte, "image/svg+xml");
  const img = new Image();
  img.onload = () => { const c = document.createElement("canvas"); c.width = l * 2; c.height = h * 2; const ctx = c.getContext("2d"); ctx.scale(2, 2); ctx.drawImage(img, 0, 0); c.toBlob((b) => telecharger(nom + ".png", b)); };
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(texte);
}
export const BoutonsFigure = ({ refSvg, nom }) => html`<span class="ligne" style="gap:2px">
  <button class="btn discret petit" title="Image vectorielle (qualité publication, modifiable dans Inkscape ou Illustrator)" onClick=${() => exporterSvg(refSvg.current.querySelector("svg") || refSvg.current, nom, "svg")}><${Icone} nom="export" taille=${14} /> SVG</button>
  <button class="btn discret petit" title="Image PNG haute définition" onClick=${() => exporterSvg(refSvg.current.querySelector("svg") || refSvg.current, nom, "png")}>PNG</button></span>`;
