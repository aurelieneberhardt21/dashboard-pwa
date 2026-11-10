// Test de l'interface dans un vrai navigateur (clics réels), sur le questionnaire FICTIF.
//
//   1. lancer Établi sur un dossier de travail vide :
//        ETABLI_DOSSIER=/tmp/etabli-test uv run etabli --port 8765 --sans-navigateur
//   2. node tests/interface/parcours.cjs           (Playwright doit être installé : npm i playwright)
//
// Le script crée le projet de démonstration, valide les champs proposés, enregistre une ACM, puis déroule
// le parcours : recodage avec aperçu, croisement construit à la main, fiche de calcul, aide, modalité rendue
// passive depuis la carte, comparaison, historique, annulation, journal. Il s'arrête en erreur au moindre écart.
const { chromium } = require('playwright');
const BASE = process.env.ETABLI_URL || 'http://127.0.0.1:8765';

async function preparer() {
  const api = async (chemin, methode = 'GET', corps) => {
    const r = await fetch(BASE + '/api' + chemin, { method: methode, headers: { 'Content-Type': 'application/json' }, body: corps ? JSON.stringify(corps) : undefined });
    if (!r.ok) throw new Error(chemin + ' : ' + (await r.text()));
    return r.json();
  };
  const { id } = await api('/projets/demo', 'POST');
  const e = await api('/p/' + id);
  const props = (await api('/p/' + id + '/champs/propositions')).propositions;
  await api('/p/' + id + '/variables', 'PATCH', { description: 'Champs acceptés', modifications: props.filter((p) => p.champ).flatMap((p) => p.variables.map((v) => ({ id: v, champ: p.champ }))) });
  const vars = Object.values(e.variables), debut = (t) => vars.find((v) => v.libelle.startsWith(t)).id;
  const genres = vars.filter((v) => v.libelle.startsWith('À quelle fréquence lisez-vous')).map((v) => v.id);
  await api('/p/' + id + '/analyses', 'POST', { titre: 'ACM des lectures', spec: { type: 'acm', actives: genres, sup_quali: [debut('Quel est votre genre'), debut('Quel âge')] } });
  await api('/p/' + id + '/analyses', 'POST', { titre: 'Tri diplôme', spec: { type: 'tri', variable: debut('Quel est le diplôme') } });
  return id;
}

(async () => {
  const U = BASE + '/#/p/' + (await preparer());
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1500, height: 1100 } });
  const erreurs = [];
  p.on('console', (m) => { if (m.type() === 'error') erreurs.push(m.text()); });
  p.on('pageerror', (e) => erreurs.push('PAGEERROR ' + e.message));
  p.on('dialog', (d) => d.accept());
  let echecs = 0;
  const etape = async (nom, f) => { try { await f(); console.log('ok  ', nom); } catch (e) { echecs++; console.log('ECHEC', nom, '—', e.message.split('\n')[0]); } await p.waitForTimeout(500); };
  await p.goto(U + '/donnees'); await p.waitForTimeout(1200);
  // 1. recodage depuis la fiche d'une variable
  await etape('ouvrir la variable âge', () => p.getByText('Quel âge avez-vous', { exact: false }).first().click());
  await etape('ouvrir le recodage', () => p.getByRole('button', { name: 'Recoder' }).click());
  await etape('cocher deux modalités', async () => { await p.locator('.modale tbody tr').nth(3).locator('input[type=checkbox]').check(); await p.locator('.modale tbody tr').nth(4).locator('input[type=checkbox]').check(); });
  await etape('regrouper', async () => { await p.fill("input[placeholder='regrouper sous le nom…']", '45 ans ou plus'); await p.getByRole('button', { name: 'Regrouper', exact: true }).click(); });
  await etape('nommer', () => p.fill("input[placeholder='ex. age3, score_lecture']", 'age4'));
  await p.waitForTimeout(1200);
  await etape("aperçu affiché", async () => { const t = await p.locator('.modale').innerText(); if (!t.includes('45 ans ou plus') || !t.includes('Aperçu du résultat')) throw new Error('aperçu absent'); });
  await etape('ajouter à la recette', () => p.getByRole('button', { name: 'Ajouter à la recette' }).click());
  await etape('étape visible', async () => { await p.waitForSelector('.etape'); const t = await p.locator('.etape').first().innerText(); if (!t.includes('age4')) throw new Error(t); });
  // 2. population
  await etape('onglet populations', () => p.getByRole('tab', { name: /Populations/ }).click());
  // 3. nouvelle analyse : tableau croisé construit à la main
  await p.goto(U + '/analyses'); await p.waitForTimeout(800);
  await etape('choisir croisement', () => p.locator('.type-analyse .carte', { hasText: 'Croisement de deux variables' }).click());
  await etape('ligne = age4', async () => { await p.locator("input[placeholder='Choisir une variable…']").first().fill('age4'); await p.locator('.menu .option').first().click(); });
  await etape('colonne = genre', async () => { await p.locator("input[placeholder='Choisir une variable…']").first().fill('genre'); await p.locator('.menu .option').first().click(); });
  await p.waitForTimeout(1500);
  await etape('résultat calculé', async () => { const t = await p.locator('.colonne').first().innerText(); if (!t.includes('V de Cramér') || !t.includes('45 ans ou plus')) throw new Error('pas de tableau'); });
  await etape('fiche de calcul : lignage', async () => { const t = await p.locator('aside.colonne').innerText(); if (!t.includes('construite') || !t.includes('analysés')) throw new Error(t.slice(0, 200)); });
  await etape('enregistrer', () => p.getByRole('button', { name: 'Enregistrer', exact: true }).first().click());
  await p.waitForTimeout(800);
  await etape('url analyse enregistrée', async () => { if (!/analyses\/a\d+/.test(p.url())) throw new Error(p.url()); });
  await etape('comprendre', async () => { await p.getByRole('tab', { name: 'Comprendre' }).click(); await p.waitForTimeout(300); const t = await p.locator('aside.colonne').innerText(); if (!t.includes('Les choix à faire')) throw new Error('aide absente'); });
  // 4. ACM : clic sur une modalité → rendre passive
  await p.goto(U + '/analyses/a001'); await p.waitForTimeout(1800);
  
  await etape('clic sur une modalité de la carte', async () => { console.log('   points cliquables :', await p.locator('.svg-cadre svg g[style*="pointer"]').count()); const g = p.locator('.svg-cadre svg g[style*="pointer"]').first(); await g.locator('circle').first().click({ force: true, timeout: 5000 }); await p.waitForSelector('text=Rendre passive', { timeout: 3000 }); });
  await etape('rendre passive', () => p.getByRole('button', { name: 'Rendre passive' }).click());
  await p.waitForTimeout(1500);
  await etape('modalité passive listée + non enregistré', async () => { const t = await p.locator('.colonne').first().innerText(); if (!t.includes('Modalités passives') || !t.includes('modifications non enregistrées')) throw new Error('pas recalculé'); });
  await etape('comparer avec une autre analyse', async () => { await p.locator('select[title^="Afficher une autre analyse"]').selectOption({ index: 1 }); await p.waitForTimeout(1500); const t = await p.locator('.colonne').first().innerText(); if (!t.includes('B —')) throw new Error('comparaison absente'); });
    // 5. journal
  await p.goto(U + '/journal'); await p.waitForTimeout(900);
  await etape('historique', async () => { const t = await p.locator('.page').innerText(); if (!t.includes('Préparation : recodage « age4 »')) throw new Error('entrée absente'); });
  await etape('annuler depuis la barre', async () => { await p.getByRole('button', { name: /Annuler/ }).first().click(); await p.waitForTimeout(700); });
  await etape('exports : journal', async () => { await p.getByRole('tab', { name: 'Exports' }).click(); await p.getByRole('button', { name: 'Afficher' }).click(); await p.waitForTimeout(900); const t = await p.locator('pre').innerText(); if (!t.includes('Journal méthodologique') || !t.includes('DONNÉES FICTIVES')) throw new Error('journal absent'); });
  console.log(erreurs.length ? 'ERREURS CONSOLE:\n' + erreurs.slice(0, 10).join('\n') : 'aucune erreur console');
  await b.close();
  process.exit(echecs || erreurs.length ? 1 : 0);
})();
