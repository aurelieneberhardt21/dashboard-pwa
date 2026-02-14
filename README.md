# Focus Grid PWA (React + Supabase + Push)

Transformation du `dashboard.html` localStorage en PWA installable (desktop + iPhone), avec sync multi-appareils et notifications Web Push.

## Stack
- Frontend: Vite + React + TypeScript + Tailwind.
- Offline/sync local: IndexedDB (Dexie) + queue offline.
- Backend data/auth: Supabase (Auth Magic Link + Postgres + RLS).
- Push: Push API + VAPID + table `push_subscriptions`.
- Scheduler: Vercel Cron (`*/5 * * * *`) + API serverless Node.

## Ce qui est livré
- Onglets: `Today`, `Week`, `Calendar`, `Settings`.
- Migration automatique des anciennes clés `fg_*`:
  - backup complet des clés legacy,
  - migration des tâches `fg_tasks` vers le nouveau modèle,
  - **sans écraser** les dates des tâches non faites vers aujourd’hui.
- Sync `last-write-wins` basée sur `updated_at`.
- Queue offline (ajout/modif/suppression), rejouée au retour réseau.
- Push:
  - bouton explicite “Activer les notifications”,
  - subscription stockée en DB,
  - désactivation (unsubscribe + suppression DB),
  - cron serveur qui envoie les rappels et marque `last_notified_at`.

---

## Setup en 20 minutes

### 1) Prérequis
- Node 20+.
- Projet Supabase.
- Compte Vercel.

### 2) Installer
```bash
npm install
```

### 3) Générer des clés VAPID
```bash
npm run generate:vapid
```
Copier `publicKey` et `privateKey`.

### 4) Variables d’environnement
Créer `.env` à partir de `.env.example`:
```bash
cp .env.example .env
```
Renseigner:
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `VITE_VAPID_PUBLIC_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `VAPID_PUBLIC_KEY`
- `VAPID_PRIVATE_KEY`
- `VAPID_SUBJECT` (ex: `mailto:toi@example.com`)
- `CRON_SECRET`
- `INTERNAL_API_SECRET`

### 5) Créer le schéma Supabase
Exécuter le SQL `supabase/migrations/202602121700_init_tasks_and_push.sql` dans l’éditeur SQL Supabase.

Ce script crée:
- `public.tasks`
- `public.push_subscriptions`
- triggers `updated_at`
- RLS strict (chaque user voit ses lignes)
- fonctions `get_due_tasks` + `mark_tasks_notified`
- publication realtime pour `tasks`

### 6) Configurer Auth Magic Link
Dans Supabase:
- `Authentication > URL Configuration`:
  - `Site URL`: ton URL (local + prod)
  - `Redirect URLs`: ajoute `http://localhost:5173` et l’URL prod.

### 7) Lancer en local
```bash
npm run dev
```

### 8) Déployer sur Vercel
```bash
npx vercel
```
Ajouter les mêmes variables d’environnement dans Vercel (Project Settings > Environment Variables).

Le cron est défini dans `vercel.json`:
- `path`: `/api/cron/dispatch-due`
- `schedule`: toutes les 5 minutes.

### 9) Vérifier le cron
Option manuelle:
```bash
curl -H "Authorization: Bearer $CRON_SECRET" https://<ton-domaine>/api/cron/dispatch-due
```

---

## Schéma tâches (MVP)
Table `tasks`:
- `id uuid`
- `user_id`
- `title`
- `status (todo/done)`
- `priority`
- `tags text[]`
- `scheduled_date date`
- `due_time time`
- `estimate_minutes int`
- `energy text`
- `created_at`
- `updated_at`
- `completed_at`
- `original_scheduled_date`
- extras MVP: `timezone`, `top3_slot`, `last_notified_at`

Règles métier clés:
- Overdue: `scheduled_date < today && status != done`.
- “Reporter à aujourd’hui”: met à jour `scheduled_date`, conserve `original_scheduled_date` si vide.
- Calendar heatmap basé sur `completed_at`.

---

## Push: fonctionnement
1. L’utilisateur clique “Activer les notifications”.
2. Front:
- demande permission Notification,
- crée la subscription (`PushManager.subscribe`),
- enregistre endpoint/keys dans `push_subscriptions`.
3. Cron `/api/cron/dispatch-due`:
- lit `get_due_tasks(window=5)`,
- envoie push à toutes les subscriptions du user,
- supprime subscriptions invalides (404/410),
- marque les tâches notifiées (`mark_tasks_notified`).

---

## Migration legacy `fg_*`
Au premier lancement après login:
- snapshot complet des clés `fg_*` vers `legacyBackups` (IndexedDB),
- migration `fg_tasks` vers `tasks` (nouveau modèle),
- aucune “migration forcée vers aujourd’hui”.

Fallback manuel:
- Export JSON depuis `Settings`,
- Import JSON depuis `Settings`.

---

## Tests manuels (critères d’acceptation)
1. Créer une tâche sur PC (`scheduled_date=demain`, `due_time=10:00`).
2. Ouvrir iPhone avec le même compte: vérifier que la tâche apparaît (sync).
3. Installer la PWA iPhone (Safari > Partager > Ajouter à l’écran d’accueil).
4. Activer notifications depuis le bouton dédié.
5. Attendre l’horaire: la push doit arriver même app fermée.
6. Vérifier que `Calendar` montre le nombre de tâches complétées par jour.
7. Vérifier backup/import pour confirmer absence de perte legacy.

---

## Troubleshooting iOS
- Push iOS ne marche pas si:
  - pas en HTTPS,
  - app non installée en PWA,
  - permission notifications non accordée,
  - iOS < 16.4.
- Après activation push, si rien ne part:
  - vérifier que `push_subscriptions` contient bien une ligne,
  - tester `/api/cron/dispatch-due` à la main,
  - vérifier les variables VAPID côté Vercel.
- Si sync partielle:
  - vérifier RLS,
  - vérifier `VITE_SUPABASE_URL/ANON_KEY`,
  - vérifier que la publication realtime inclut bien `public.tasks`.

