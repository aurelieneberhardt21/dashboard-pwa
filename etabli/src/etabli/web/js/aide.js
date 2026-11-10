// Aides méthodologiques : consultables dans l'onglet « Comprendre » de chaque analyse.
// Format : quoi (ce que fait la méthode), choix (décisions et alternatives), lire (comment lire), limites.
import { html } from "./base.js";

export const AIDES = {
  tri: {
    quoi: "Le tri à plat décrit une seule variable : effectifs et pourcentages par modalité (variable qualitative), ou moyenne, médiane et dispersion (variable numérique).",
    choix: [
      ["Le dénominateur", "Les pourcentages sont calculés sur les réponses valides. Les non-concernés et les abandons sortent du calcul ; la non-réponse est comptée à part. Regardez toujours la barre des statuts : un pourcentage sur 40 répondants et un pourcentage sur 400 ne se lisent pas de la même façon."],
      ["Modalités de non-réponse", "« Ne sait pas », « Préfère ne pas répondre » peuvent être exclues (par défaut si elles sont déclarées comme telles) ou gardées comme réponses : cela dépend de ce que le refus signifie pour votre question."],
    ],
    lire: ["L'intervalle de confiance (Wilson, 95 %) indique la marge d'incertitude d'un pourcentage si vos répondants étaient un échantillon aléatoire d'une population plus vaste. Pour une enquête par volontariat, il sous-estime l'incertitude réelle : lisez-le comme un ordre de grandeur de la fragilité liée aux petits effectifs.", "Pour une variable numérique, comparez moyenne et médiane : un écart net signale une distribution dissymétrique, que la moyenne résume mal."],
    limites: ["Un pourcentage ne dit rien de la population d'ensemble si la participation à l'enquête est liée à ce que l'on mesure.", "Moins de 5 individus dans une modalité : regroupez avant de croiser, et ne publiez pas le chiffre tel quel."],
  },
  croise: {
    quoi: "Croiser deux variables, c'est comparer la répartition de l'une selon les modalités de l'autre. Établi choisit la forme adaptée : tableau croisé (deux qualitatives), comparaison de moyennes (une numérique, une qualitative) ou corrélation (deux numériques).",
    choix: [
      ["Pourcentages en ligne ou en colonne", "On calcule les pourcentages dans le sens de la variable que l'on considère comme « explicative » : si le genre est en lignes, les % en ligne comparent les femmes et les hommes. Lire dans le mauvais sens est l'erreur la plus fréquente."],
      ["Chi², Fisher ou simulation", "Le chi² mesure l'écart global à l'indépendance ; son approximation est fragile quand des effectifs théoriques sont inférieurs à 5. Dans ce cas, fiez-vous au test exact de Fisher ou à la p-valeur simulée, indiqués à côté."],
      ["Regrouper des modalités", "Des cellules presque vides rendent le tableau illisible et les tests instables. Un recodage (Préparation) est souvent le vrai remède — c'est un choix d'analyse à justifier."],
    ],
    lire: ["Le V de Cramér résume l'intensité de la liaison entre 0 et 1, indépendamment de l'effectif ; la p-valeur dit seulement si un écart de cette taille serait surprenant sous l'hypothèse d'indépendance. Avec un grand effectif, une liaison infime est « significative » ; avec un petit, une liaison forte peut ne pas l'être.", "Les résidus ajustés localisent la liaison : au-delà de ±2, la cellule s'écarte nettement de l'indépendance (bleu : sur-représentation ; rouge : sous-représentation).", "Le PEM (pourcentage de l'écart maximum, Cibois) exprime l'attraction entre une ligne et une colonne en proportion du maximum possible compte tenu des marges : il se compare d'une cellule à l'autre, ce que ne permet pas le résidu.", "Pour une comparaison de moyennes : eta² est la part de la variance « expliquée » par l'appartenance au groupe."],
    limites: ["Une liaison entre deux variables peut tenir à une troisième (âge, statut…). Pour le vérifier, relancez le croisement sur des sous-populations ou passez à une régression.", "Une liaison n'est pas une causalité, et le sens de lecture choisi ne prouve aucun sens d'influence."],
  },
  multiples: {
    quoi: "Une question à réponses multiples donne une variable oui/non par item. On compare les items entre eux, et éventuellement leur fréquence selon un groupe.",
    choix: [["Deux pourcentages différents", "« % des répondants » : part des personnes ayant coché l'item (la somme dépasse 100 %). « % des réponses » : part de l'item dans l'ensemble des coches (somme = 100 %). Le premier se lit comme une fréquence ; le second comme un poids relatif."]],
    lire: ["Avec un groupe : un test par item. Plus il y a d'items, plus il y a de chances qu'un écart apparaisse par hasard : regardez les p-valeurs ajustées (Holm, Benjamini-Hochberg) plutôt que les brutes."],
    limites: ["Ne pas cocher n'est pas répondre « non » : l'item a pu être survolé. Une consigne du type « trois réponses maximum » contraint aussi mécaniquement les fréquences."],
  },
  correlation: {
    quoi: "Une corrélation mesure à quel point deux variables numériques ou ordinales varient ensemble, de −1 à +1.",
    choix: [["Pearson, Spearman ou Kendall", "Pearson mesure une relation linéaire entre variables numériques et est sensible aux valeurs extrêmes. Spearman et Kendall travaillent sur les rangs : ils conviennent aux échelles ordinales (jamais / parfois / souvent) et aux distributions dissymétriques. Kendall est plus prudent avec beaucoup d'ex æquo."], ["Ajustement des p-valeurs", "Une matrice de k variables contient k(k−1)/2 tests. Holm contrôle le risque d'une seule fausse alerte ; Benjamini-Hochberg, moins sévère, contrôle la proportion de fausses alertes."]],
    lire: ["Lisez d'abord le coefficient et son intervalle de confiance, puis l'effectif de la paire (il varie : chaque paire utilise les individus renseignés sur les deux variables)."],
    limites: ["Une corrélation nulle n'exclut pas une relation non monotone (en U).", "Traiter une échelle en 4 ou 5 modalités comme un nombre est une approximation : restez sur les rangs."],
  },
  regression: {
    quoi: "La régression estime l'association entre une variable à expliquer et chaque variable explicative « toutes choses égales par ailleurs », c'est-à-dire à valeurs fixées des autres variables du modèle. Linéaire pour une variable numérique ; logistique pour une variable à deux modalités ; multinomiale au-delà.",
    choix: [
      ["La modalité de référence", "Chaque modalité d'une variable qualitative est comparée à une référence. Changer de référence ne change pas le modèle, mais change tous les coefficients affichés : choisissez une référence nombreuse et parlante."],
      ["Quelles variables inclure", "Le coefficient d'une variable dépend de celles qui l'accompagnent. Introduisez les variables pour des raisons théoriques, puis comparez des spécifications (dupliquez l'analyse) : un résultat qui ne tient qu'avec un jeu précis de contrôles est fragile."],
      ["Odds ratios ou effets marginaux", "Un odds ratio de 2 ne signifie pas « deux fois plus de chances » : c'est un rapport de cotes, d'autant plus éloigné du rapport de probabilités que l'événement est fréquent. Les effets marginaux moyens, exprimés en points de pourcentage, sont plus faciles à interpréter et à comparer entre modèles."],
      ["Combien de variables ?", "Repère usuel en logistique : au moins 10 « événements » (individus dans la modalité la moins fréquente de la variable à expliquer) par paramètre estimé. En dessous, les estimations sont instables."],
    ],
    lire: ["Regardez l'intervalle de confiance avant la p-valeur : il donne la plage des valeurs compatibles avec les données. Un intervalle très large signifie « on ne sait pas », même s'il exclut zéro.", "Le test par variable (colonne dédiée) dit si la variable prise dans son ensemble contribue au modèle : plus pertinent que les p de chaque modalité, qui dépendent de la référence.", "GVIF élevé : deux variables explicatives sont trop liées pour démêler leurs associations respectives."],
    limites: ["« Toutes choses égales par ailleurs » ne vaut que pour les variables incluses, et suppose que l'on puisse faire varier l'une sans les autres — ce qui est souvent sociologiquement artificiel.", "Les individus ayant une valeur manquante sur une seule variable sont écartés : vérifiez combien dans la fiche de calcul.", "Un modèle ne démontre pas une causalité."],
  },
  acm: {
    quoi: "L'analyse des correspondances multiples résume les liaisons entre plusieurs variables qualitatives en construisant un espace où deux individus sont proches s'ils ont répondu de la même façon, et où deux modalités sont proches si elles sont choisies par les mêmes personnes. Les axes sont les directions le long desquelles les individus se différencient le plus.",
    choix: [
      ["Variables actives et supplémentaires", "Les variables actives construisent l'espace ; choisissez-les homogènes par leur thème (des pratiques, des opinions) et équilibrées en nombre de modalités. Les variables supplémentaires (caractéristiques sociales, par exemple) n'influencent pas les axes : on les projette ensuite pour voir comment elles se distribuent dans l'espace. C'est le geste classique : construire l'espace des pratiques, y projeter les positions sociales."],
      ["Non-réponses et modalités rares : l'ACM spécifique", "Une modalité rare ou une non-réponse traitée comme active peut créer un axe à elle seule. L'ACM spécifique (Le Roux et Rouanet) les rend « passives » : les individus restent dans l'analyse, mais ces modalités ne participent plus aux distances. C'est le réglage par défaut pour les non-réponses."],
      ["La population", "Tous les individus doivent être concernés par toutes les variables actives. Mélanger des questions posées à des sous-groupes différents écarte la plupart des individus : restreignez la population ou harmonisez d'abord les questions (étape « fusion »)."],
      ["Combien d'axes interpréter", "Regardez l'éboulis et les taux modifiés de Benzécri (les taux bruts sous-estiment toujours les premiers axes en ACM). On retient les axes avant le « coude », à condition de savoir les interpréter."],
    ],
    lire: ["Interprétez un axe à partir des modalités qui y contribuent le plus (contribution supérieure à la moyenne), en opposant celles de coordonnée positive et négative.", "Le cos² dit si un point est bien représenté sur l'axe ou le plan : un point au cos² faible peut paraître proche d'un autre sans l'être réellement.", "Pour une modalité supplémentaire, la valeur-test indique si sa position s'écarte de l'origine au-delà de ce que donnerait le hasard (repère : |v| > 2), et un écart entre deux modalités supérieur à 0,5 est « notable », supérieur à 1 « important » (Le Roux et Rouanet).", "L'ellipse de concentration d'un sous-groupe résume où se situent ses membres dans le nuage (environ 86 % d'entre eux si le sous-nuage est régulier)."],
    limites: ["La proximité de deux modalités de variables différentes s'interprète en moyenne, pas pour chaque individu.", "Les axes changent quand on change les variables actives, les recodages ou la population : dupliquez l'analyse et comparez pour savoir ce qui est robuste.", "L'ACM décrit une structure ; elle ne teste pas une hypothèse et ne « prouve » pas un espace social."],
  },
  acp: {
    quoi: "L'analyse en composantes principales résume plusieurs variables numériques corrélées par quelques axes (combinaisons des variables) qui restituent au mieux les différences entre individus.",
    choix: [["Réduire ou non", "En ACP normée (par défaut), chaque variable est ramenée à la même dispersion : indispensable si les unités diffèrent. Sans réduction, les variables les plus dispersées dominent."], ["Variables supplémentaires", "Comme en ACM : projetées sans influencer les axes."]],
    lire: ["Le cercle des corrélations : une variable proche du bord est bien représentée ; deux flèches proches signalent des variables corrélées, opposées des variables anti-corrélées, à angle droit des variables indépendantes.", "Interprétez chaque axe par les variables qui lui sont le plus corrélées."],
    limites: ["Les individus ayant une valeur manquante sont écartés (aucune imputation).", "L'ACP ne voit que les relations linéaires. Pour des échelles ordinales courtes, l'ACM est souvent plus adaptée."],
  },
  afc: {
    quoi: "L'analyse factorielle des correspondances représente un tableau croisé : les lignes et les colonnes qui s'attirent (sur-représentation) sont du même côté des axes.",
    choix: [["Lignes ou colonnes supplémentaires", "Une modalité à très faible effectif ou atypique peut être projetée en supplémentaire pour ne pas déformer l'analyse."]],
    lire: ["L'inertie totale est le chi² du tableau divisé par l'effectif : l'AFC décompose l'écart à l'indépendance.", "La proximité entre deux lignes signifie des profils semblables ; entre une ligne et une colonne, elle s'interprète par rapport à l'origine (même direction = attraction)."],
    limites: ["Sur un tableau à peu de lignes ou de colonnes, le tableau croisé et ses résidus suffisent."],
  },
  afdm: {
    quoi: "L'analyse factorielle de données mixtes traite ensemble des variables numériques et qualitatives, en équilibrant leur influence : elle se comporte comme une ACP pour les premières et comme une ACM pour les secondes.",
    choix: [["Quand l'utiliser", "Quand le thème étudié mêle réellement les deux types. Sinon, découper les variables numériques en classes et faire une ACM est souvent plus lisible."]],
    lire: ["Variables numériques : corrélation avec les axes. Qualitatives : position des modalités et rapport de corrélation eta²."],
    limites: ["Individus avec valeur manquante écartés. Les modalités rares pèsent lourd, comme en ACM."],
  },
  cah: {
    quoi: "La classification ascendante hiérarchique regroupe de proche en proche les individus qui se ressemblent dans l'espace factoriel, en fusionnant à chaque étape les deux groupes dont la réunion fait perdre le moins d'inertie inter-classes (critère de Ward).",
    choix: [
      ["Sur combien d'axes classer", "Ne garder que les premiers axes élimine le « bruit » des derniers ; en garder trop peu efface des différences réelles. Essayez plusieurs valeurs : une typologie qui change du tout au tout n'est pas robuste."],
      ["Combien de classes", "Le dendrogramme et le diagramme des gains d'inertie suggèrent où couper (un grand saut = des classes bien séparées). La suggestion automatique est un point de départ : retenez un nombre de classes que vous savez décrire et qui garde des effectifs suffisants."],
      ["Consolidation", "Réaffecter chaque individu à la classe dont le centre est le plus proche (centres mobiles) améliore l'homogénéité des classes ; la partition ne correspond alors plus exactement à l'arbre."],
    ],
    lire: ["Décrivez chaque classe par les modalités sur-représentées (valeur-test positive élevée) : « % de la classe ayant la modalité » comparé au « % dans l'ensemble ».", "Les parangons sont les individus les plus proches du centre de la classe : des cas « typiques »."],
    limites: ["Une classification produit toujours des classes, même quand le nuage est continu : les classes sont un découpage commode, pas des groupes réels aux frontières nettes.", "Les effectifs par classe fondent vite : attention avant de recroiser."],
  },
  exploration: {
    quoi: "L'exploration confronte une variable « cible » à une série de variables candidates et mesure, pour chacune, l'intensité de la liaison. C'est un outil pour repérer des pistes, pas pour produire des résultats.",
    choix: [["Le choix des candidates", "Plus vous en testez, plus des liaisons apparaîtront par hasard. Limitez-vous aux variables qui ont un sens pour votre question, et notez dans le carnet ce que vous cherchiez avant de regarder."], ["L'ajustement", "Les p-valeurs ajustées tiennent compte du nombre de tests du tableau — pas de ceux que vous avez lancés avant."]],
    lire: ["Le tableau est trié par intensité (V de Cramér, eta, |rho| : tous entre 0 et 1), pas par p-valeur.", "« Fragile » : effectifs trop faibles pour conclure. Une liaison forte mais fragile mérite un recodage, pas une interprétation."],
    limites: ["Une liaison repérée ici doit être examinée (tableau croisé, contrôle par d'autres variables) et, idéalement, était attendue pour une raison théorique. Rapporter seulement les liaisons « significatives » d'une exploration, c'est présenter du bruit comme un résultat."],
  },
};

export function Comprendre({ type }) {
  const a = AIDES[type];
  if (!a) return null;
  return html`<div class="aide-texte">
    <p>${a.quoi}</p>
    <h4>Les choix à faire</h4>${a.choix.map(([t, d]) => html`<p><b>${t}.</b> ${d}</p>`)}
    <h4>Comment lire le résultat</h4><ul>${a.lire.map((x) => html`<li>${x}</li>`)}</ul>
    <h4>Ce que le résultat n'autorise pas</h4><ul>${a.limites.map((x) => html`<li>${x}</li>`)}</ul>
  </div>`;
}
