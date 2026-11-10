// Vue « Journal » : historique et versions du projet, carnet de recherche, exports d'ensemble.
import { html, useState, useEffect, api, magasin, useMagasin, agir, toast, ent, Icone, Onglets, telecharger, telechargerDepuis } from "./base.js";

const CATEGORIES = { source: "Données", dictionnaire: "Dictionnaire", recette: "Préparation", population: "Population", analyse: "Analyse", carnet: "Carnet", version: "Version", autre: "Projet" };

function Historique({ pid }) {
  const e = useMagasin().etat;
  const [h, setH] = useState(null);
  const [nom, setNom] = useState("");
  const charger = () => api(`/p/${pid}/historique`).then(setH);
  useEffect(() => { charger(); }, [e.projet.version]);
  if (!h) return html`<p class="muet">Chargement…</p>`;
  const jalons = Object.fromEntries(h.jalons.map((j) => [j.n, j]));
  const poser = async () => { await api(`/p/${pid}/jalons`, { methode: "POST", corps: { nom: nom.trim() } }); setNom(""); toast("Version nommée"); charger(); };
  const restaurer = async (x) => { if (!confirm(`Revenir à l'état du projet après « ${x.description} » ?\n\nL'état actuel reste dans l'historique : vous pourrez y revenir.`)) return; await agir(`/restaurer/${x.n}`, { methode: "POST" }, "Version restaurée"); };
  return html`<div>
    <div class="carte"><h3>Nommer la version actuelle</h3><p class="petit secondaire" style="margin:4px 0 8px">Avant un changement important (nouveau recodage, autre population…), donnez un nom à l'état actuel pour le retrouver facilement. Chaque modification est de toute façon enregistrée ci-dessous.</p>
      <div class="ligne"><input class="champ" placeholder="ex. Avant regroupement des statuts ; version envoyée à ma directrice" value=${nom} onInput=${(ev) => setNom(ev.target.value)} onKeyDown=${(ev) => ev.key === "Enter" && nom.trim() && poser()} /><button class="btn primaire" disabled=${!nom.trim()} onClick=${poser}>Nommer cette version</button></div></div>
    <div class="carte"><h3>Historique des modifications</h3>
      <table class="t" style="margin-top:8px"><thead><tr><th>Date</th><th class="g">Modification</th><th class="g">Domaine</th><th></th></tr></thead><tbody>
        ${[...h.entrees].reverse().map((x) => html`<tr style=${x.n === h.version ? "background:var(--accent-clair)" : ""}><td class="nowrap muet">${x.date.replace("T", " ").slice(0, 16)}</td>
          <td class="g">${x.description}${jalons[x.n] ? html` <span class="badge" style="background:var(--accent);color:var(--surface)">${jalons[x.n].nom}</span>` : ""}${x.n === h.version ? html` <span class="badge">état actuel</span>` : ""}</td>
          <td class="g muet">${CATEGORIES[x.categorie] || ""}</td><td>${x.n !== h.version ? html`<button class="btn discret petit" onClick=${() => restaurer(x)}>Revenir à cet état</button>` : ""}</td></tr>`)}</tbody></table>
      <p class="aide-champ">Rien n'est jamais effacé : « Annuler » et « Revenir à cet état » déplacent le projet dans son historique. Les fichiers de données d'origine ne sont pas concernés (ils ne changent jamais).</p></div></div>`;
}

function Carnet() {
  const e = useMagasin().etat;
  const [texte, setTexte] = useState("");
  const ajouter = async () => { await agir("/carnet", { methode: "PUT", corps: { carnet: [...e.carnet, { date: new Date().toISOString(), texte: texte.trim() }] } }, "Note ajoutée"); setTexte(""); };
  return html`<div><div class="carte"><h3>Nouvelle note</h3><p class="petit secondaire" style="margin:4px 0 8px">Questions de recherche, hypothèses, décisions à prendre, pistes abandonnées et pourquoi. Le carnet est repris à la fin du journal méthodologique.</p>
      <textarea class="champ" style="min-height:90px" value=${texte} onInput=${(ev) => setTexte(ev.target.value)}></textarea>
      <button class="btn primaire" style="margin-top:8px" disabled=${!texte.trim()} onClick=${ajouter}>Ajouter au carnet</button></div>
    ${[...e.carnet].reverse().map((n, i) => html`<div class="carte ligne haut"><div style="flex:1"><div class="mini muet">${(n.date || "").slice(0, 16).replace("T", " ")}</div><div style="white-space:pre-wrap;margin-top:3px">${n.texte}</div></div>
      <button class="btn discret petit danger" onClick=${() => confirm("Supprimer cette note ? (annulable)") && agir("/carnet", { methode: "PUT", corps: { carnet: e.carnet.filter((_, j) => j !== e.carnet.length - 1 - i) } })}><${Icone} nom="poubelle" taille=${14} /></button></div>`)}</div>`;
}

function Exports({ pid }) {
  const e = useMagasin().etat;
  const [apercu, setApercu] = useState(null);
  const journal = () => api(`/p/${pid}/export/journal`).then(setApercu).catch((err) => toast(err.message, true));
  return html`<div>
    <div class="carte"><h3>Journal méthodologique</h3><p class="petit secondaire" style="margin:4px 0 8px">Un document lisible qui retrace tout : sources, décisions du dictionnaire, chaque étape de préparation avec sa justification, populations, analyses enregistrées (effectifs, exclusions, méthode, avertissements, notes) et carnet. À relire, à annexer, à transmettre.</p>
      <div class="ligne"><button class="btn" onClick=${journal}>Afficher</button><button class="btn primaire" onClick=${() => api(`/p/${pid}/export/journal`).then((t) => telecharger(`journal_${e.projet.id}.md`, t, "text/markdown;charset=utf-8"))}><${Icone} nom="export" taille=${14} /> Télécharger (.md)</button></div>
      ${apercu && html`<pre style="white-space:pre-wrap;font-family:var(--sans);font-size:13px;background:var(--surface-2);padding:14px;border-radius:6px;margin-top:12px;max-height:520px;overflow:auto">${apercu}</pre>`}</div>
    <div class="carte"><h3>Données préparées</h3><p class="petit secondaire" style="margin:4px 0 8px">Toutes les variables analysables (d'origine et construites), libellés en clair, « NA » pour les valeurs manquantes — pour R, Stata, un tableur. Les variables sensibles et les réponses textuelles ne sont pas exportées.</p>
      <div class="ligne" style="flex-wrap:wrap"><button class="btn" onClick=${() => telechargerDepuis("/export/donnees", `donnees_${e.projet.id}.csv`)}><${Icone} nom="export" taille=${14} /> Tous les répondants (.csv)</button>
        ${e.populations.map((p) => html`<button class="btn" onClick=${() => telechargerDepuis(`/export/donnees?population=${p.id}`, `donnees_${p.nom}.csv`)}>${p.nom}</button>`)}</div>
      <div class="note alerte" style="margin-top:10px">Ce fichier contient des réponses individuelles. Avec de petits effectifs, la combinaison de quelques caractéristiques (âge, statut, lieu) peut suffire à reconnaître une personne : ne le partagez qu'avec les personnes autorisées par votre protocole.</div></div>
    <div class="carte"><h3>Le projet lui-même</h3><p class="petit secondaire" style="margin:4px 0 0">Tout le projet (fichiers d'origine, dictionnaire, recette, analyses, historique) tient dans un dossier : <code>${e.projet.dossier}</code>. Pour le sauvegarder, le déplacer sur un autre ordinateur ou l'archiver avec la thèse, copiez ce dossier.</p></div></div>`;
}

export function VueJournal({ pid, reste }) {
  const [onglet, setOnglet] = useState(reste[0] || "historique");
  const e = useMagasin().etat;
  return html`<div class="page"><h1>Journal</h1>
    <div style="margin-top:14px"><${Onglets} onglets=${[["historique", "Historique et versions"], ["carnet", `Carnet de recherche (${e.carnet.length})`], ["exports", "Exports"]]} actif=${onglet} onChange=${setOnglet} /></div>
    ${onglet === "historique" ? html`<${Historique} pid=${pid} />` : onglet === "carnet" ? html`<${Carnet} />` : html`<${Exports} pid=${pid} />`}</div>`;
}
