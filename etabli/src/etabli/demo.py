"""Jeu de données FICTIF pour la démonstration et les tests.

Tout est tiré au hasard (graine fixe) : ces « réponses » n'ont aucun rapport avec une enquête réelle et ne
doivent jamais être interprétées. Le fichier imite un export LimeSurvey « texte complet des questions /
réponses complètes » avec ses difficultés habituelles : parcours conditionnels (deux profils), questions à
choix multiples (Oui / Non / N/A, option exclusive), matrice d'échelles, questions ouvertes, réponses
partielles (abandons), modalités rares, colonne de contact à ne pas diffuser.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

FREQ = ["Jamais", "Rarement", "Parfois", "Souvent", "Très souvent"]
ACCORD = ["Pas du tout d’accord", "Plutôt pas d’accord", "Plutôt d’accord", "Tout à fait d’accord"]
GENRES = ["Romans", "Essais et sciences humaines", "Bandes dessinées et mangas", "Poésie et théâtre", "Presse professionnelle"]
TACHES = ["Accueil du public", "Acquisitions et commandes", "Animations et médiation", "Catalogage", "Gestion et administration",
          "Aucune de ces tâches"]
PROFESSIONS = ["institutrice", "Ouvrier dans l'automobile", "infirmière", "cadre dans une banque", "Agricultrice", "employée de mairie",
               "professeur de lettres", "aide-soignante", "commerçante", "Ingénieure", "secrétaire médicale", "mère au foyer",
               "bibliothécaire", "vendeuse", "comptable", "médecin généraliste", "assistante maternelle", "technicienne de laboratoire"]


def generer(n: int = 420, graine: int = 20240) -> tuple[list[str], list[list[str]]]:
    """Renvoie (en-têtes, lignes) d'un export fictif."""
    g = np.random.default_rng(graine)
    entetes = ["ID de la réponse", "Date de soumission", "Dernière page", "Langue de départ", "Tête de série",
               "Date de lancement", "Date de la dernière action",
               "Quelle est votre situation actuelle ?",                                           # page 1
               "En quelle année de formation êtes-vous ?",                                        # page 2 (formation)
               "Quelle filière suivez-vous ?", "Si autre, merci de préciser :",
               "Dans quel type d’établissement travaillez-vous ?",                                # page 2 (en poste)
               "Depuis combien d’années exercez-vous ce métier ?",
               *[f"Quelles tâches occupent l’essentiel de votre temps ? [{t}]" for t in TACHES],   # page 2 (en poste)
               *[f"À quelle fréquence lisez-vous les genres suivants ? [{x}]" for x in GENRES],    # page 3
               "Combien de livres avez-vous lus au cours des douze derniers mois ?",
               "Diriez-vous que les métiers du livre sont reconnus à leur juste valeur ?",         # page 4
               *[f"Par quels moyens vous informez-vous sur l’actualité éditoriale ? [{x}]"
                 for x in ["Presse spécialisée", "Réseaux sociaux", "Collègues", "Salons et rencontres", "Autre"]],
               "Quel est votre genre ?", "Quel âge avez-vous ?",                                   # page 5
               "Quel est le diplôme le plus élevé de vos parents ?",
               "Quelle est ou était la profession de votre mère ?",
               "Souhaitez-vous ajouter quelque chose ? (facultatif)",
               "Si vous acceptez d’être recontacté·e pour un entretien, indiquez un courriel :"]
    lignes = []
    for i in range(n):
        capital = g.normal()                      # dimension latente 1 (fictive) : rapport « lettré » à la lecture
        anciennete = g.normal()                   # dimension latente 2 (fictive)
        en_poste = g.random() < 0.58
        derniere = 5 if g.random() > 0.14 else int(g.integers(0, 5))
        complet = derniere == 5
        jour = int(g.integers(1, 28))
        debut = f"2024-03-{jour:02d} {int(g.integers(8, 22)):02d}:{int(g.integers(0, 60)):02d}:00"
        L = [str(i + 1), debut if complet else "", str(derniere), "fr", str(int(g.integers(1e8, 2e9))), debut, debut]
        choix = lambda options, p=None: str(g.choice(options, p=p))
        prob = lambda x: 1 / (1 + np.exp(-x))
        # page 1
        L.append(("Je suis en poste (bibliothèque, librairie, édition…)" if en_poste else
                  "Je suis en formation aux métiers du livre") if derniere >= 1 else "")
        vu2, vu3, vu4, vu5 = derniere >= 2, derniere >= 3, derniere >= 4, derniere >= 5
        # page 2 : formation
        if not en_poste and vu2:
            filiere = choix(["Métiers du livre", "Documentation et information", "Autre"], [0.55, 0.37, 0.08])
            L += [choix(["1re année", "2e année", "3e année ou plus"], [0.4, 0.35, 0.25]), filiere,
                  choix(["reconversion, formation continue", "Édition jeunesse", "master patrimoine"]) if filiere == "Autre" else ""]
        else:
            L += ["", "", ""]
        # page 2 : en poste
        if en_poste and vu2:
            p_etab = np.array([0.34, 0.2 + 0.08 * (capital > 0), 0.22, 0.14 - 0.06 * (capital > 0), 0.03])
            L.append(choix(["Bibliothèque municipale", "Bibliothèque universitaire", "Librairie indépendante",
                            "Grande surface culturelle", "Autre"], p_etab / p_etab.sum()))
            L.append(str(max(0, int(round(9 + 7 * anciennete + g.normal(0, 2))))) if g.random() > 0.04 else "")
            aucune = g.random() < 0.05
            if aucune:
                L += ["N/A"] * 5 + ["Oui"]
            else:
                base = [0.65, 0.4 + 0.1 * capital, 0.35, 0.3 - 0.1 * capital, 0.2 + 0.15 * anciennete]
                L += ["Oui" if g.random() < np.clip(b, 0.03, 0.97) else "Non" for b in base] + ["Non"]
        else:
            L += ["", ""] + ["N/A"] * 6
        # page 3 : lectures (tous)
        if vu3:
            pentes = [0.2, 1.1, -0.9, 0.8, 0.5 if en_poste else -0.3]
            for b in pentes:
                if g.random() < 0.03:
                    L.append("")
                else:
                    L.append(FREQ[int(np.clip(round(2 + b * capital + g.normal(0, 0.9)), 0, 4))])
            L.append(str(max(0, int(round(22 + 12 * capital + g.normal(0, 8))))) if g.random() > 0.06 else "")
        else:
            L += [""] * 6
        # page 4 : reconnaissance + information
        if vu4:
            if g.random() < 0.04:
                L.append("Préfère ne pas répondre")
            else:
                L.append(ACCORD[int(np.clip(round(1.3 - 0.5 * anciennete + g.normal(0, 0.8)), 0, 3))])
            L += ["Oui" if g.random() < prob(0.2 + 0.9 * capital) else "Non",
                  "Oui" if g.random() < prob(0.4 - 0.8 * anciennete) else "Non",
                  "Oui" if g.random() < (0.7 if en_poste else 0.3) else "Non",
                  "Oui" if g.random() < prob(-0.6 + 0.5 * capital) else "Non",
                  "Oui" if g.random() < 0.04 else "Non"]
        else:
            L += [""] + ["N/A"] * 5
        # page 5 : caractéristiques sociales
        if vu5:
            L.append(choix(["Femme", "Homme", "Non-binaire ou autre"], [0.71, 0.27, 0.02]) if g.random() > 0.02 else "")
            ages = ["Moins de 25 ans", "25-34 ans", "35-44 ans", "45-54 ans", "55 ans ou plus"]
            centre = (2.2 + 1.0 * anciennete) if en_poste else 0.5
            L.append(ages[int(np.clip(round(centre + g.normal(0, 0.7)), 0, 4))])
            dipl = ["Aucun diplôme ou certificat d’études", "CAP, BEP ou équivalent", "Baccalauréat", "Bac +2 à bac +4",
                    "Bac +5 ou plus", "Je ne sais pas"]
            L.append(dipl[5] if g.random() < 0.03 else dipl[int(np.clip(round(2.2 + 1.0 * capital + g.normal(0, 1)), 0, 4))])
            precisions = ["", "", " (à la retraite)", " dans le privé", " à temps partiel", ", puis sans emploi", " en province"]
            L.append(choix(PROFESSIONS) + choix(precisions) if g.random() > 0.12 else "")
            remarques = ["Questionnaire un peu long mais intéressant.", "Certaines questions ne correspondent pas à ma situation.",
                         "Bon courage pour la suite de l'enquête !", "J'aurais aimé pouvoir nuancer mes réponses sur la reconnaissance.",
                         "Merci, hâte de lire les résultats."]
            L.append(choix(remarques) + (" " + choix(["", "Cordialement.", "Bonne continuation."])).rstrip() if g.random() < 0.05 else "")
            L.append(f"personne{i + 1}@exemple.invalid" if g.random() < 0.08 else "")
        else:
            L += [""] * 6
        lignes.append(L)
    return entetes, lignes


def ecrire_export(chemin: Path, n: int = 420, graine: int = 20240) -> Path:
    entetes, lignes = generer(n, graine)
    with open(chemin, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(entetes)
        w.writerows(lignes)
    return chemin
