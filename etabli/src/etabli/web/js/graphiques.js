// Graphiques SVG d'Établi. Sobres par principe : marques fines, grille discrète, texte en encre (jamais en
// couleur de série), une légende dès qu'il y a deux séries, une infobulle sur chaque marque.
import { html, useState, useRef, useMemo, nf, ent, pct, court, montrerBulle, cacherBulle } from "./base.js";

export const SERIES = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)", "var(--s6)", "var(--s7)", "var(--s8)"];
const ENCRE = "var(--encre)", ENCRE2 = "var(--encre-2)", ENCRE3 = "var(--encre-3)", GRILLE = "var(--grille)", AXE = "var(--axe)";
const largeurTexte = (t, taille = 11.5) => String(t).length * taille * 0.54;

function graduations(min, max, n = 5) {
  if (!(max > min)) return [min];
  const brut = (max - min) / n, p = Math.pow(10, Math.floor(Math.log10(brut)));
  const pas = [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= brut) || 10 * p;
  const t = [];
  for (let v = Math.ceil(min / pas - 1e-9) * pas; v <= max + pas * 1e-9; v += pas) t.push(Math.abs(v) < pas * 1e-9 ? 0 : v);
  return t;
}
const fmtGrad = (v) => { const a = Math.abs(v); return nf(v, a >= 100 || Number.isInteger(v) ? 0 : (a >= 10 ? 1 : 2)).replace(/,?0+$/, (m) => (m.startsWith(",") ? "" : m)); };

export const Legende = ({ items }) => html`<div class="legende">${items.map((it) => html`<span><i style=${`background:${it.couleur};${it.forme === "contour" ? `background:none;border:2px solid ${it.couleur};` : ""}${it.forme === "rond" ? "border-radius:50%;" : ""}`}></i>${it.label}</span>`)}</div>`;

/** Barres horizontales : une valeur par modalité, intervalle de confiance facultatif. */
export function Barres({ donnees, unite = "%", max, largeur = 640, couleur = SERIES[0], decimales = 1 }) {
  const hL = 26, gauche = Math.min(300, Math.max(90, ...donnees.map((d) => largeurTexte(court(d.label, 46), 12) + 14)));
  const haut = donnees.length * hL + 8, zone = largeur - gauche - 64;
  const m = max ?? Math.max(1e-9, ...donnees.map((d) => Math.max(d.valeur || 0, d.ic_haut || 0)));
  const x = (v) => gauche + zone * Math.max(0, v) / m;
  return html`<svg viewBox=${`0 0 ${largeur} ${haut}`} width=${largeur} role="img">
    ${donnees.map((d, i) => { const y = i * hL + 6, l = Math.max(1, x(d.valeur) - gauche); return html`<g onMouseMove=${(e) => montrerBulle(e, html`<div><b>${d.label}</b><div class="l"><span>${d.detail || "valeur"}</span><span>${nf(d.valeur, decimales)} ${unite}</span></div>${d.n !== undefined && html`<div class="l"><span>effectif</span><span>${ent(d.n)}</span></div>`}${d.ic_bas != null && html`<div class="l"><span>IC 95 %</span><span>${nf(d.ic_bas, 1)} – ${nf(d.ic_haut, 1)}</span></div>`}</div>`)} onMouseLeave=${cacherBulle}>
      <rect x="0" y=${y - 4} width=${largeur} height=${hL} fill="transparent" />
      <text x=${gauche - 8} y=${y + 11} text-anchor="end" font-size="12" fill=${ENCRE}>${court(d.label, 46)}</text>
      <path d=${`M${gauche},${y} h${Math.max(0, l - 4)} a4,4 0 0 1 4,4 v6 a4,4 0 0 1 -4,4 h${-Math.max(0, l - 4)} z`} fill=${d.couleur || couleur} opacity=${d.estompe ? 0.45 : 1} />
      ${d.ic_bas != null && html`<path d=${`M${x(d.ic_bas)},${y + 7} H${x(d.ic_haut)} M${x(d.ic_bas)},${y + 3} v8 M${x(d.ic_haut)},${y + 3} v8`} stroke=${ENCRE} stroke-width="1" opacity=".55" fill="none" />`}
      <text x=${Math.max(x(d.valeur), d.ic_haut != null ? x(d.ic_haut) : 0) + 6} y=${y + 11} font-size="11.5" fill=${ENCRE2}>${nf(d.valeur, decimales)}${unite === "%" ? " %" : ""}</text></g>`; })}
    <line x1=${gauche} x2=${gauche} y1="2" y2=${haut - 2} stroke=${AXE} />
  </svg>`;
}

/** Barres empilées à 100 % : profils-lignes d'un tableau croisé. */
export function Profils({ lignes, categories, largeur = 680, ordonne = false }) {
  const hL = 26, gauche = Math.min(260, Math.max(80, ...lignes.map((l) => largeurTexte(court(l.label, 38), 12) + 14)));
  const zone = largeur - gauche - 24, haut = lignes.length * hL + 22;
  // modalités ordonnées : une seule teinte, du clair au foncé ; sinon une teinte par modalité (8 au plus)
  const couleurs = !ordonne && categories.length <= 8 ? SERIES : null;
  const rampe = (j) => couleurs ? couleurs[j] : `color-mix(in oklab, var(--s1) ${Math.round(25 + 75 * j / Math.max(1, categories.length - 1))}%, var(--surface))`;
  return html`<div><svg viewBox=${`0 0 ${largeur} ${haut}`} width=${largeur} role="img">
    ${[0, 25, 50, 75, 100].map((t) => html`<g><line x1=${gauche + zone * t / 100} x2=${gauche + zone * t / 100} y1="2" y2=${haut - 18} stroke=${GRILLE} /><text x=${gauche + zone * t / 100} y=${haut - 5} font-size="10.5" fill=${ENCRE3} text-anchor="middle">${t} %</text></g>`)}
    ${lignes.map((l, i) => { let cumul = 0; const y = i * hL + 5; return html`<g>
      <text x=${gauche - 8} y=${y + 12} text-anchor="end" font-size="12" fill=${ENCRE} font-weight=${l.total ? 600 : 400}>${court(l.label, 38)}</text>
      ${l.parts.map((p, j) => { const x0 = gauche + zone * cumul / 100, w = zone * (p || 0) / 100; cumul += p || 0; return w > 0.5 ? html`<g onMouseMove=${(e) => montrerBulle(e, html`<div><b>${l.label}</b><div class="l"><span>${categories[j]}</span><span>${pct(p)}</span></div>${l.effectifs && html`<div class="l"><span>effectif</span><span>${ent(l.effectifs[j])}</span></div>`}</div>`)} onMouseLeave=${cacherBulle}>
        <rect x=${x0 + 1} y=${y} width=${Math.max(0.5, w - 2)} height="16" rx="2" fill=${rampe(j)} />
        ${w > 34 && html`<text x=${x0 + w / 2} y=${y + 12} font-size="10.5" text-anchor="middle" fill=${couleurs && j === 3 ? "#0b0b0b" : (couleurs || j > categories.length / 2 ? "#fff" : "#0b0b0b")}>${nf(p, 0)}</text>`}</g>` : null; })}</g>`; })}
  </svg><${Legende} items=${categories.map((c, j) => ({ label: c, couleur: rampe(j) }))} /></div>`;
}

export function Histogramme({ bornes, effectifs, largeur = 560, hauteur = 190, moyenne, mediane }) {
  const mg = { g: 38, d: 10, h: 10, b: 28 }, zx = largeur - mg.g - mg.d, zy = hauteur - mg.h - mg.b;
  const m = Math.max(1, ...effectifs), x0 = bornes[0], x1 = bornes[bornes.length - 1];
  const x = (v) => mg.g + zx * (v - x0) / (x1 - x0 || 1), y = (v) => mg.h + zy * (1 - v / m);
  return html`<svg viewBox=${`0 0 ${largeur} ${hauteur}`} width=${largeur} role="img">
    ${graduations(0, m, 4).map((t) => html`<g><line x1=${mg.g} x2=${largeur - mg.d} y1=${y(t)} y2=${y(t)} stroke=${GRILLE} /><text x=${mg.g - 6} y=${y(t) + 4} font-size="10.5" fill=${ENCRE3} text-anchor="end">${ent(t)}</text></g>`)}
    ${effectifs.map((e, i) => html`<rect x=${x(bornes[i]) + 1} y=${y(e)} width=${Math.max(1, x(bornes[i + 1]) - x(bornes[i]) - 2)} height=${Math.max(0, y(0) - y(e))} fill=${SERIES[0]} rx="2"
      onMouseMove=${(ev) => montrerBulle(ev, html`<div><b>de ${nf(bornes[i], 1)} à ${nf(bornes[i + 1], 1)}</b><div class="l"><span>effectif</span><span>${ent(e)}</span></div></div>`)} onMouseLeave=${cacherBulle} />`)}
    <line x1=${mg.g} x2=${largeur - mg.d} y1=${y(0)} y2=${y(0)} stroke=${AXE} />
    ${graduations(x0, x1, 6).map((t) => html`<text x=${x(t)} y=${hauteur - 9} font-size="10.5" fill=${ENCRE3} text-anchor="middle">${fmtGrad(t)}</text>`)}
    ${moyenne != null && html`<g><line x1=${x(moyenne)} x2=${x(moyenne)} y1=${mg.h} y2=${y(0)} stroke=${ENCRE} stroke-width="1.5" /><text x=${x(moyenne) + 4} y=${mg.h + 9} font-size="10.5" fill=${ENCRE2}>moyenne</text></g>`}
    ${mediane != null && html`<g><line x1=${x(mediane)} x2=${x(mediane)} y1=${mg.h} y2=${y(0)} stroke=${ENCRE} stroke-width="1.5" stroke-dasharray="3 3" /><text x=${x(mediane) + 4} y=${mg.h + 21} font-size="10.5" fill=${ENCRE2}>médiane</text></g>`}
  </svg>`;
}

/** Éboulis des valeurs propres : barres = taux bruts ; points = taux modifiés (ACM). */
export function Eboulis({ axes, largeur = 520, hauteur = 200, choisis = [] }) {
  const a = axes.slice(0, 15), modif = a.some((x) => x.pct_modifie != null);
  const mg = { g: 36, d: 8, h: 10, b: 26 }, zx = largeur - mg.g - mg.d, zy = hauteur - mg.h - mg.b;
  const m = Math.max(...a.map((x) => Math.max(x.pct, x.pct_modifie || 0))), pas = zx / a.length;
  const y = (v) => mg.h + zy * (1 - v / m), lb = Math.min(24, pas - 6);
  return html`<div><svg viewBox=${`0 0 ${largeur} ${hauteur}`} width=${largeur} role="img">
    ${graduations(0, m, 4).map((t) => html`<g><line x1=${mg.g} x2=${largeur - mg.d} y1=${y(t)} y2=${y(t)} stroke=${GRILLE} /><text x=${mg.g - 6} y=${y(t) + 4} font-size="10.5" fill=${ENCRE3} text-anchor="end">${fmtGrad(t)} %</text></g>`)}
    ${a.map((x, i) => { const cx = mg.g + pas * (i + 0.5); return html`<g onMouseMove=${(e) => montrerBulle(e, html`<div><b>Axe ${x.axe}</b><div class="l"><span>valeur propre</span><span>${nf(x.valeur_propre, 4)}</span></div><div class="l"><span>taux brut</span><span>${pct(x.pct)}</span></div><div class="l"><span>cumulé</span><span>${pct(x.pct_cumule)}</span></div>${x.pct_modifie != null && html`<div class="l"><span>taux modifié (Benzécri)</span><span>${pct(x.pct_modifie)}</span></div>`}</div>`)} onMouseLeave=${cacherBulle}>
      <rect x=${cx - pas / 2} y=${mg.h} width=${pas} height=${zy} fill="transparent" />
      <path d=${`M${cx - lb / 2},${y(0)} V${y(x.pct) + 4} a4,4 0 0 1 4,-4 h${lb - 8} a4,4 0 0 1 4,4 V${y(0)} z`} fill=${SERIES[0]} opacity=${choisis.length && !choisis.includes(x.axe) ? 0.4 : 1} />
      ${x.pct_modifie != null && html`<circle cx=${cx} cy=${y(x.pct_modifie)} r="4.5" fill=${SERIES[1]} stroke="var(--surface)" stroke-width="2" />`}
      <text x=${cx} y=${hauteur - 9} font-size="10.5" fill=${ENCRE3} text-anchor="middle">${x.axe}</text></g>`; })}
    <line x1=${mg.g} x2=${largeur - mg.d} y1=${y(0)} y2=${y(0)} stroke=${AXE} />
  </svg>${modif && html`<${Legende} items=${[{ label: "taux d'inertie brut", couleur: SERIES[0] }, { label: "taux modifié (Benzécri)", couleur: SERIES[1], forme: "rond" }]} />`}</div>`;
}

/** Coefficients avec intervalles de confiance (régression) ou moyennes par groupe. */
export function Intervalles({ lignes, reference = 0, largeur = 640, log = false, unite = "", titreAxe }) {
  const hL = 24, gauche = Math.min(280, Math.max(100, ...lignes.map((l) => largeurTexte(court(l.label, 42), 12) + 16)));
  const zone = largeur - gauche - 20, haut = lignes.length * hL + 34;
  const f = (v) => (log ? Math.log(Math.max(v, 1e-9)) : v);
  const vals = lignes.flatMap((l) => [l.valeur, l.bas, l.haut]).filter((v) => v != null && Number.isFinite(v)).map(f).concat(reference != null ? [f(reference)] : []);
  let mn = Math.min(...vals), mx = Math.max(...vals); const marge = (mx - mn || 1) * 0.06; mn -= marge; mx += marge;
  const x = (v) => gauche + zone * (f(v) - mn) / (mx - mn);
  const grad = log ? [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50].filter((t) => f(t) >= mn && f(t) <= mx) : graduations(mn, mx, 5);
  return html`<svg viewBox=${`0 0 ${largeur} ${haut}`} width=${largeur} role="img">
    ${grad.map((t) => html`<g><line x1=${x(t)} x2=${x(t)} y1="4" y2=${haut - 28} stroke=${GRILLE} /><text x=${x(t)} y=${haut - 15} font-size="10.5" fill=${ENCRE3} text-anchor="middle">${fmtGrad(t)}${unite}</text></g>`)}
    ${reference != null && html`<line x1=${x(reference)} x2=${x(reference)} y1="4" y2=${haut - 28} stroke=${AXE} stroke-width="1.5" />`}
    ${titreAxe && html`<text x=${gauche + zone / 2} y=${haut - 2} font-size="10.5" fill=${ENCRE3} text-anchor="middle">${titreAxe}</text>`}
    ${lignes.map((l, i) => { const y = i * hL + 16; return html`<g onMouseMove=${(e) => l.valeur != null && montrerBulle(e, html`<div><b>${l.label}</b><div class="l"><span>${l.nomValeur || "estimation"}</span><span>${nf(l.valeur, 3)}</span></div>${l.bas != null && html`<div class="l"><span>IC 95 %</span><span>${nf(l.bas, 3)} – ${nf(l.haut, 3)}</span></div>`}${l.n != null && html`<div class="l"><span>effectif</span><span>${ent(l.n)}</span></div>`}</div>`)} onMouseLeave=${cacherBulle}>
      <rect x="0" y=${y - 11} width=${largeur} height=${hL} fill="transparent" />
      <text x=${gauche - 10} y=${y + 4} text-anchor="end" font-size="12" fill=${l.ref ? ENCRE3 : ENCRE} font-style=${l.ref ? "italic" : "normal"} font-weight=${l.titre ? 600 : 400}>${court(l.label, 42)}</text>
      ${l.valeur != null && l.bas != null && html`<line x1=${x(l.bas)} x2=${x(l.haut)} y1=${y} y2=${y} stroke=${SERIES[0]} stroke-width="2" stroke-linecap="round" />`}
      ${l.valeur != null && html`<circle cx=${x(l.valeur)} cy=${y} r="4.5" fill=${l.ref ? "var(--surface)" : SERIES[0]} stroke=${l.ref ? ENCRE3 : "var(--surface)"} stroke-width=${l.ref ? 1.5 : 2} />`}</g>`; })}
  </svg>`;
}

export function Nuage({ points, largeur = 520, hauteur = 360, nomX, nomY }) {
  const mg = { g: 48, d: 12, h: 10, b: 38 };
  const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const x = (v) => mg.g + (largeur - mg.g - mg.d) * (v - x0) / (x1 - x0 || 1), y = (v) => mg.h + (hauteur - mg.h - mg.b) * (1 - (v - y0) / (y1 - y0 || 1));
  return html`<svg viewBox=${`0 0 ${largeur} ${hauteur}`} width=${largeur} role="img">
    ${graduations(y0, y1, 5).map((t) => html`<g><line x1=${mg.g} x2=${largeur - mg.d} y1=${y(t)} y2=${y(t)} stroke=${GRILLE} /><text x=${mg.g - 6} y=${y(t) + 4} font-size="10.5" fill=${ENCRE3} text-anchor="end">${fmtGrad(t)}</text></g>`)}
    ${graduations(x0, x1, 6).map((t) => html`<text x=${x(t)} y=${hauteur - 20} font-size="10.5" fill=${ENCRE3} text-anchor="middle">${fmtGrad(t)}</text>`)}
    ${points.map((p) => html`<circle cx=${x(p[0])} cy=${y(p[1])} r="3.5" fill=${SERIES[0]} fill-opacity=".55" />`)}
    <text x=${(largeur + mg.g) / 2} y=${hauteur - 4} font-size="11" fill=${ENCRE2} text-anchor="middle">${court(nomX, 70)}</text>
    <text transform=${`translate(12 ${hauteur / 2 - 10}) rotate(-90)`} font-size="11" fill=${ENCRE2} text-anchor="middle">${court(nomY, 50)}</text>
  </svg>`;
}

export function Dendrogramme({ d, k, largeur = 640, hauteur = 240 }) {
  const mg = { g: 40, d: 8, h: 8, b: 14 };
  const xmax = Math.max(...d.x.flat()), ymax = Math.max(...d.y.flat());
  const x = (v) => mg.g + (largeur - mg.g - mg.d) * v / (xmax + 5), y = (v) => mg.h + (hauteur - mg.h - mg.b) * (1 - v / ymax);
  return html`<svg viewBox=${`0 0 ${largeur} ${hauteur}`} width=${largeur} role="img">
    ${graduations(0, ymax, 4).map((t) => html`<g><line x1=${mg.g} x2=${largeur - mg.d} y1=${y(t)} y2=${y(t)} stroke=${GRILLE} /><text x=${mg.g - 6} y=${y(t) + 4} font-size="10.5" fill=${ENCRE3} text-anchor="end">${fmtGrad(t)}</text></g>`)}
    ${d.x.map((xs, i) => html`<path d=${`M${x(xs[0])},${y(d.y[i][0])} V${y(d.y[i][1])} H${x(xs[2])} V${y(d.y[i][3])}`} fill="none" stroke=${ENCRE2} stroke-width="1.3" />`)}
    ${d.feuilles.map((f, i) => html`<rect x=${x(5 + 10 * i) - 3} y=${y(0) + 2} width="6" height="6" rx="1" fill=${SERIES[(f.classe_cah - 1) % 8]} onMouseMove=${(e) => montrerBulle(e, `${f.id || f.n + " individus"} — classe ${f.classe_cah}`)} onMouseLeave=${cacherBulle} />`)}
    <line x1=${mg.g} x2=${largeur - mg.d} y1=${y(d.hauteur_coupe)} y2=${y(d.hauteur_coupe)} stroke=${SERIES[7]} stroke-width="1.5" stroke-dasharray="5 4" />
    <text x=${largeur - mg.d - 4} y=${y(d.hauteur_coupe) - 5} font-size="10.5" fill=${ENCRE2} text-anchor="end">coupure en ${k} classes</text>
  </svg>`;
}

/** Ellipse de concentration (Le Roux & Rouanet) d'un sous-nuage : centre, demi-axes = 2 écarts-types principaux. */
export function ellipseConcentration(pts) {
  const n = pts.length; if (n < 3) return null;
  const mx = pts.reduce((s, p) => s + p[0], 0) / n, my = pts.reduce((s, p) => s + p[1], 0) / n;
  let sxx = 0, syy = 0, sxy = 0;
  for (const p of pts) { sxx += (p[0] - mx) ** 2; syy += (p[1] - my) ** 2; sxy += (p[0] - mx) * (p[1] - my); }
  sxx /= n; syy /= n; sxy /= n;
  const tr = sxx + syy, det = sxx * syy - sxy * sxy, disc = Math.sqrt(Math.max(0, tr * tr / 4 - det));
  const l1 = tr / 2 + disc, l2 = Math.max(0, tr / 2 - disc);
  return { cx: mx, cy: my, rx: 2 * Math.sqrt(l1), ry: 2 * Math.sqrt(l2), angle: 0.5 * Math.atan2(2 * sxy, sxx - syy), n };
}

const FORMES = {
  rond: (r) => `M${-r},0 a${r},${r} 0 1,0 ${2 * r},0 a${r},${r} 0 1,0 ${-2 * r},0`,
  losange: (r) => { const s = r * 1.25; return `M0,${-s} L${s},0 L0,${s} L${-s},0 Z`; },
  triangle: (r) => { const s = r * 1.3; return `M0,${-s} L${s},${s * 0.85} L${-s},${s * 0.85} Z`; },
  carre: (r) => `M${-r},${-r} h${2 * r} v${2 * r} h${-2 * r} Z`,
};

/**
 * Carte factorielle. Échelle identique sur les deux axes (les distances se lisent), origine marquée.
 * points : [{id, x, y, label, couleur, forme, r, creux, priorite, fond, bulle: () => vnode}]
 * Molette = zoom, glisser = déplacer, double-clic = recadrer.
 */
export function Carte({ points, titreX, titreY, liens = [], ellipses = [], etiquettes = "principales", onClic, selection, largeur = 760, hauteur = 560, legende }) {
  const mg = { g: 46, d: 14, h: 14, b: 40 };
  const [vue, setVue] = useState(null);       // {cx, cy, demi} en unités de données
  const glisse = useRef(null);
  const ref = useRef();
  const etendue = useMemo(() => {
    const tous = points.filter((p) => !p.horsCadrage);
    const xs = tous.map((p) => p.x).concat(ellipses.flatMap((e) => [e.cx - e.rx, e.cx + e.rx]), [0]);
    const ys = tous.map((p) => p.y).concat(ellipses.flatMap((e) => [e.cy - e.rx, e.cy + e.rx]), [0]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const zx = largeur - mg.g - mg.d, zy = hauteur - mg.h - mg.b;
    const demi = Math.max((x1 - x0) / 2, (y1 - y0) / 2 * zx / zy, 1e-6) * 1.12;
    return { cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, demi };
  }, [points, ellipses, largeur, hauteur]);
  const v = vue || etendue;
  const zx = largeur - mg.g - mg.d, zy = hauteur - mg.h - mg.b, ech = zx / (2 * v.demi);
  const X = (x) => mg.g + zx / 2 + (x - v.cx) * ech, Y = (y) => mg.h + zy / 2 - (y - v.cy) * ech;
  const dedans = (p) => X(p.x) >= mg.g - 2 && X(p.x) <= largeur - mg.d + 2 && Y(p.y) >= mg.h - 2 && Y(p.y) <= hauteur - mg.b + 2;

  // placement glouton des étiquettes : les points prioritaires d'abord, quatre positions essayées
  const places = useMemo(() => {
    if (etiquettes === "aucune") return new Map();
    const cand = points.filter((p) => p.label && !p.fond && dedans(p) && (etiquettes === "toutes" || p.priorite > 0)).sort((a, b) => (b.priorite || 0) - (a.priorite || 0));
    const boites = points.filter((p) => !p.fond && dedans(p)).map((p) => { const r = p.r || 4; return [X(p.x) - r, Y(p.y) - r, X(p.x) + r, Y(p.y) + r, p.id]; });
    const res = new Map();
    const libre = (b, id) => b[0] >= mg.g && b[2] <= largeur - mg.d && b[1] >= mg.h && b[3] <= hauteur - mg.b && !boites.some((o) => o[4] !== id && b[0] < o[2] && b[2] > o[0] && b[1] < o[3] && b[3] > o[1]);
    for (const p of cand.slice(0, 400)) {
      const t = court(p.label, 34), w = largeurTexte(t, 11.5), r = (p.r || 4) + 3, x = X(p.x), y = Y(p.y);
      const essais = [[x + r, y - 7, "start", x + r, y + 4], [x - r - w, y - 7, "end", x - r, y + 4], [x - w / 2, y - r - 13, "middle", x, y - r - 3], [x - w / 2, y + r, "middle", x, y + r + 11]];
      for (const [bx, by, ancre, tx, ty] of essais) {
        const b = [bx, by, bx + w, by + 13, p.id];
        if (libre(b, p.id)) { boites.push(b); res.set(p.id, { t, ancre, tx, ty }); break; }
      }
    }
    return res;
  }, [points, v, etiquettes, largeur, hauteur]);

  const molette = (e) => {
    e.preventDefault();
    const rect = ref.current.getBoundingClientRect(), k = largeur / rect.width;
    const px = (e.clientX - rect.left) * k, py = (e.clientY - rect.top) * k;
    const dx = v.cx + (px - mg.g - zx / 2) / ech, dy = v.cy - (py - mg.h - zy / 2) / ech;
    const f = e.deltaY > 0 ? 1.18 : 1 / 1.18, demi = Math.min(etendue.demi * 3, Math.max(etendue.demi / 40, v.demi * f));
    const r = demi / v.demi;
    setVue({ cx: dx + (v.cx - dx) * r, cy: dy + (v.cy - dy) * r, demi });
  };
  const bouge = (e) => {
    if (!glisse.current) return;
    const rect = ref.current.getBoundingClientRect(), k = largeur / rect.width;
    setVue({ ...glisse.current.v, cx: glisse.current.v.cx - (e.clientX - glisse.current.x) * k / ech, cy: glisse.current.v.cy + (e.clientY - glisse.current.y) * k / ech });
  };
  const gx = graduations(v.cx - v.demi, v.cx + v.demi, 6), gy = graduations(v.cy - v.demi * zy / zx, v.cy + v.demi * zy / zx, 5);
  const idClip = useMemo(() => "clip" + Math.random().toString(36).slice(2, 8), []);
  const fond = points.filter((p) => p.fond), avant = points.filter((p) => !p.fond);
  return html`<div class="svg-cadre"><svg ref=${ref} viewBox=${`0 0 ${largeur} ${hauteur}`} width=${largeur} role="img" style="touch-action:none;cursor:${glisse.current ? "grabbing" : "default"}"
      onWheel=${molette} onMouseDown=${(e) => { glisse.current = { x: e.clientX, y: e.clientY, v }; }} onMouseMove=${bouge} onMouseUp=${() => { glisse.current = null; }} onMouseLeave=${() => { glisse.current = null; }} onDblClick=${() => setVue(null)}>
    <defs><clipPath id=${idClip}><rect x=${mg.g} y=${mg.h} width=${zx} height=${zy} /></clipPath></defs>
    <rect x=${mg.g} y=${mg.h} width=${zx} height=${zy} fill="var(--surface)" stroke=${GRILLE} />
    ${gx.map((t) => html`<g><line x1=${X(t)} x2=${X(t)} y1=${mg.h} y2=${hauteur - mg.b} stroke=${t === 0 ? AXE : GRILLE} stroke-width=${t === 0 ? 1.5 : 1} /><text x=${X(t)} y=${hauteur - mg.b + 14} font-size="10.5" fill=${ENCRE3} text-anchor="middle">${fmtGrad(t)}</text></g>`)}
    ${gy.map((t) => html`<g><line x1=${mg.g} x2=${largeur - mg.d} y1=${Y(t)} y2=${Y(t)} stroke=${t === 0 ? AXE : GRILLE} stroke-width=${t === 0 ? 1.5 : 1} /><text x=${mg.g - 6} y=${Y(t) + 4} font-size="10.5" fill=${ENCRE3} text-anchor="end">${fmtGrad(t)}</text></g>`)}
    <text x=${mg.g + zx / 2} y=${hauteur - 6} font-size="11.5" fill=${ENCRE2} text-anchor="middle">${titreX}</text>
    <text transform=${`translate(13 ${mg.h + zy / 2}) rotate(-90)`} font-size="11.5" fill=${ENCRE2} text-anchor="middle">${titreY}</text>
    <g clip-path=${`url(#${idClip})`}>
      ${fond.map((p) => html`<circle cx=${X(p.x)} cy=${Y(p.y)} r=${p.r || 2.5} fill=${p.couleur || "var(--neutre-2)"} fill-opacity=${p.opacite ?? 0.5} onMouseMove=${p.bulle ? (e) => montrerBulle(e, p.bulle()) : null} onMouseLeave=${cacherBulle} onClick=${onClic ? () => onClic(p) : null} />`)}
      ${ellipses.map((e) => html`<g transform=${`translate(${X(e.cx)} ${Y(e.cy)}) rotate(${-e.angle * 180 / Math.PI})`}><ellipse rx=${e.rx * ech} ry=${e.ry * ech} fill=${e.couleur} fill-opacity=".07" stroke=${e.couleur} stroke-width="1.5" /></g>`)}
      ${liens.map((l) => html`<polyline points=${l.points.map((p) => `${X(p[0])},${Y(p[1])}`).join(" ")} fill="none" stroke=${l.couleur || ENCRE3} stroke-width="1.5" stroke-opacity=".6" stroke-linejoin="round" />`)}
      ${avant.map((p) => { const r = p.r || 4.5, sel = selection === p.id; return html`<g transform=${`translate(${X(p.x)} ${Y(p.y)})`} style=${onClic ? "cursor:pointer" : ""} onMouseMove=${p.bulle ? (e) => montrerBulle(e, p.bulle()) : null} onMouseLeave=${cacherBulle} onClick=${onClic ? (e) => { e.stopPropagation(); onClic(p); } : null}>
        <circle r=${Math.max(r + 5, 9)} fill="transparent" />
        ${sel && html`<circle r=${r + 5} fill="none" stroke=${ENCRE} stroke-width="1.5" />`}
        <path d=${(FORMES[p.forme] || FORMES.rond)(r)} fill=${p.creux ? "var(--surface)" : (p.couleur || SERIES[0])} stroke=${p.creux ? (p.couleur || SERIES[0]) : "var(--surface)"} stroke-width=${p.creux ? 1.8 : 1.5} opacity=${p.estompe ? 0.35 : 1} /></g>`; })}
    </g>
    ${avant.map((p) => { const pl = places.get(p.id); return pl ? html`<text x=${pl.tx} y=${pl.ty} text-anchor=${pl.ancre} font-size="11.5" fill=${ENCRE} opacity=${p.estompe ? 0.45 : 1} font-style=${p.creux ? "italic" : "normal"} style="pointer-events:none;paint-order:stroke" stroke="var(--surface)" stroke-width="3" stroke-linejoin="round">${pl.t}</text>` : null; })}
  </svg>${legende && html`<${Legende} items=${legende} />`}</div>`;
}
