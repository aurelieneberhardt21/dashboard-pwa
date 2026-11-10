// Établi — point d'entrée de l'interface : accueil, coquille du projet, navigation.
import { html, render, useState, useEffect, api, magasin, useMagasin, publier, chargerProjet, agir, aller, useRoute, toast, ent, Icone } from "./base.js";
import { VueDonnees } from "./donnees.js";
import { VuePreparation } from "./preparation.js";
import { VueAnalyses } from "./analyses.js";
import { VueJournal } from "./journal.js";

function Accueil() {
  const [liste, setListe] = useState(null);
  const [nom, setNom] = useState("");
  const [fichier, setFichier] = useState(null);
  const [occupe, setOccupe] = useState(false);
  const charger = () => api("/projets").then(setListe).catch((e) => toast(e.message, true));
  useEffect(() => { charger(); publier({ etat: null, pid: null }); }, []);
  const creer = async () => {
    if (!fichier) return;
    setOccupe(true);
    try {
      const corps = new FormData(); corps.append("nom", nom || fichier.name.replace(/\.[^.]+$/, "")); corps.append("fichier", fichier);
      const r = await api("/projets", { methode: "POST", corps });
      aller(`/p/${r.id}/donnees`);
    } catch (e) { toast(e.message, true); } finally { setOccupe(false); }
  };
  const demo = async () => { setOccupe(true); try { const r = await api("/projets/demo", { methode: "POST" }); aller(`/p/${r.id}/donnees`); } catch (e) { toast(e.message, true); } finally { setOccupe(false); } };
  const supprimer = async (p) => { if (!confirm(`Mettre le projet « ${p.nom} » à la corbeille ?\n(Le dossier est déplacé dans Etabli/.corbeille, rien n'est détruit.)`)) return; await api(`/projets/${p.id}`, { methode: "DELETE" }); charger(); };
  return html`<div class="vue"><div class="page" style="max-width:900px">
    <h1 style="font-size:34px;margin-top:20px">Établi</h1>
    <p class="secondaire" style="font-size:15.5px;max-width:640px;margin-top:6px">Un atelier pour traiter et analyser des enquêtes par questionnaire — en gardant la main sur chaque décision. Tout se passe sur cet ordinateur : aucune donnée n'est envoyée ailleurs.</p>
    <div class="carte" style="margin-top:22px">
      <h2>Nouveau projet</h2>
      <p class="secondaire petit" style="margin-top:4px">Export de réponses LimeSurvey (CSV ou Excel ; en-têtes « texte complet » ou « codes », réponses complètes ou codes), ou tout tableau avec une ligne d'en-têtes. Le fichier d'origine est copié dans le projet et n'est jamais modifié.</p>
      <div class="ligne" style="margin-top:10px;flex-wrap:wrap">
        <input type="file" accept=".csv,.tsv,.txt,.xlsx" onChange=${(e) => { const f = e.target.files[0]; setFichier(f); if (f && !nom) setNom(f.name.replace(/\.[^.]+$/, "")); }} />
        <input class="champ" style="flex:1;min-width:200px" placeholder="Nom du projet" value=${nom} onInput=${(e) => setNom(e.target.value)} />
        <button class="btn primaire" disabled=${!fichier || occupe} onClick=${creer}>${occupe ? "Import en cours…" : "Créer le projet"}</button>
      </div>
      <hr />
      <div class="ligne"><span class="secondaire petit" style="flex:1">Pour découvrir l'outil sans vos données : un questionnaire entièrement <b>fictif</b> (réponses tirées au hasard, signalées comme telles partout).</span>
        <button class="btn" disabled=${occupe} onClick=${demo}>Ouvrir la démonstration</button></div>
    </div>
    <h2 style="margin:26px 0 10px">Projets</h2>
    ${liste === null ? html`<p class="muet">Chargement…</p>` : liste.projets.length === 0 ? html`<p class="muet">Aucun projet pour l'instant.</p>` : liste.projets.map((p) => html`
      <div class="carte cliquable ligne" onClick=${() => aller(`/p/${p.id}/donnees`)}>
        <div style="flex:1;min-width:0"><h3>${p.nom} ${p.fictif && html`<span class="badge" style="background:var(--alerte-fond);color:var(--alerte-encre)">données fictives</span>`}</h3>
          <div class="petit muet">${p.sources.map((s) => `${s.fichier} · ${ent(s.n_lignes)} réponses`).join(" ; ")} · ${p.n_variables} variables · ${p.n_analyses} analyse(s) · modifié le ${(p.modifie || "").slice(0, 16).replace("T", " à ")}</div></div>
        <button class="btn discret danger" title="Mettre à la corbeille" onClick=${(e) => { e.stopPropagation(); supprimer(p); }}><${Icone} nom="poubelle" /></button>
      </div>`)}
    ${liste && html`<p class="mini muet" style="margin-top:18px">Dossier des projets : <code>${liste.dossier}</code> — à inclure dans vos sauvegardes.</p>`}
  </div></div>`;
}

function Projet({ pid, vue, reste }) {
  const m = useMagasin();
  const [erreur, setErreur] = useState(null);
  useEffect(() => { if (m.pid !== pid) chargerProjet(pid).catch((e) => setErreur(e.message)); }, [pid]);
  if (erreur) return html`<div class="page"><div class="note erreur">${erreur}</div><p><a href="#/">Retour à l'accueil</a></p></div>`;
  const e = m.etat;
  if (!e || m.pid !== pid) return html`<div class="page muet">Ouverture du projet…</div>`;
  const nav = [["donnees", "Données", "donnees", Object.keys(e.variables).length], ["preparation", "Préparation", "preparation", e.recette.length || ""], ["analyses", "Analyses", "analyses", e.analyses.length || ""], ["journal", "Journal", "journal", ""]];
  const annuler = async (sens) => { const r = await agir(sens === "annuler" ? "/annuler" : "/retablir", { methode: "POST" }); const quoi = r.annule || r.retabli; if (quoi) toast((sens === "annuler" ? "Annulé : " : "Rétabli : ") + quoi); };
  const Vue = { donnees: VueDonnees, preparation: VuePreparation, analyses: VueAnalyses, journal: VueJournal }[vue] || VueDonnees;
  const n_excl = e.n_total - e.n_base;
  return html`<div class="app">
    <aside class="barre">
      <div class="marque" onClick=${() => aller("/")} title="Tous les projets">Établi</div>
      <div class="projet-nom" title=${e.projet.nom}>${e.projet.nom}</div>
      ${nav.map(([id, lib, icone, n]) => html`<button class=${"nav" + (vue === id ? " actif" : "")} onClick=${() => aller(`/p/${pid}/${id}`)}><${Icone} nom=${icone} /> ${lib}<span class="compte">${n}</span></button>`)}
      <div class="bas">
        <div class="ligne"><button class="btn petit" style="flex:1" disabled=${!e.historique.peut_annuler} onClick=${() => annuler("annuler")} title="Annuler la dernière modification du projet"><${Icone} nom="annuler" taille=${14} /> Annuler</button>
          <button class="btn petit" disabled=${!e.historique.peut_retablir} onClick=${() => annuler("retablir")} title="Rétablir"><${Icone} nom="retablir" taille=${14} /></button></div>
        <div>Enregistré automatiquement · version ${e.projet.version}</div>
        <div class="ligne" style="gap:5px"><${Icone} nom="cadenas" taille=${13} /> Données locales uniquement</div>
      </div>
    </aside>
    <main class="principal">
      ${e.projet.fictif && html`<div class="bandeau-fictif">Données fictives — démonstration. Les « résultats » affichés n'ont aucune signification.</div>`}
      <div class="contexte">
        <span><b>${ent(e.n_total)}</b> réponses</span><span><b>${ent(e.n_complets)}</b> complètes · ${ent(e.n_base - e.n_complets)} partielles</span>
        ${n_excl > 0 && html`<span title=${e.exclusions.map((x) => `${x.n} : ${x.motif || "sans motif"}`).join("\n")}><b>${ent(n_excl)}</b> exclues par la préparation</span>`}
        <span class="pousse muet">${e.sources.map((s) => s.fichier).join(" + ")}</span>
      </div>
      <div class="vue"><${Vue} pid=${pid} reste=${reste} /></div>
    </main>
  </div>`;
}

function App() {
  const route = useRoute();
  const m = useMagasin();
  return html`${route[0] === "p" && route[1] ? html`<${Projet} pid=${route[1]} vue=${route[2] || "donnees"} reste=${route.slice(3)} />` : html`<${Accueil} />`}
    ${m.toast && html`<div class=${"toast" + (m.toast.erreur ? " erreur" : "")} role="status">${m.toast.message}</div>`}`;
}

render(html`<${App} />`, document.getElementById("racine"));
