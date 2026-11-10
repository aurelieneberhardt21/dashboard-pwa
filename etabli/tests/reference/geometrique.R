# Références de validation du moteur géométrique d'Établi.
#
# Ce script produit, avec des logiciels de référence (FactoMineR, GDAtools, ca),
# les sorties auxquelles `tests/test_geometrique.py` compare nos calculs.
# Les fichiers produits (tests/reference/geometrique/*.json et
# tests/reference/donnees/*.csv) sont versionnés : les tests n'exigent PAS R.
#
# Pour régénérer (depuis le dossier etabli/) :
#   Rscript tests/reference/geometrique.R
# Paquets : FactoMineR, jsonlite (obligatoires) ; GDAtools, ca (ACM spécifique,
# taux de Greenacre). Si ces derniers sont installés dans une bibliothèque
# particulière : ETABLI_R_LIBS=/chemin/vers/lib Rscript tests/reference/geometrique.R
#
# Versions utilisées pour les fichiers versionnés : R 4.3.3, FactoMineR 2.9,
# GDAtools 2.3.1, ca 0.71.1.

extra <- Sys.getenv("ETABLI_R_LIBS")
if (nzchar(extra)) .libPaths(c(extra, .libPaths()))
suppressMessages({
  library(FactoMineR)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = FALSE)
f <- sub("^--file=", "", args[grep("^--file=", args)])
ici <- if (length(f)) dirname(normalizePath(f)) else "tests/reference"
dir_json <- file.path(ici, "geometrique")
dir_csv <- file.path(ici, "donnees")
dir.create(dir_json, showWarnings = FALSE, recursive = TRUE)
dir.create(dir_csv, showWarnings = FALSE, recursive = TRUE)

# ---------------------------------------------------------------- utilitaires
mat <- function(x) {
  if (is.null(x)) return(NULL)
  x <- as.matrix(x)
  list(lignes = as.character(rownames(x)), donnees = unname(x))
}
ecrire <- function(nom, obj) {
  writeLines(toJSON(obj, digits = NA, auto_unbox = TRUE, null = "null", na = "null"),
             file.path(dir_json, paste0(nom, ".json")))
  cat("ok", nom, "\n")
}
poids_test <- function(n) {
  w <- 0.5 + ((seq_len(n) * 7) %% 5) / 4
  w * n / sum(w)          # normalisés : somme = n (convention d'Établi)
}
niveaux <- function(df) lapply(df, function(v) levels(as.factor(v)))

data(decathlon); data(children); data(tea); data(poison); data(wine)
write.csv(decathlon, file.path(dir_csv, "decathlon.csv"))
write.csv(children, file.path(dir_csv, "children.csv"))
write.csv(tea, file.path(dir_csv, "tea.csv"))
write.csv(poison, file.path(dir_csv, "poison.csv"))
write.csv(wine, file.path(dir_csv, "wine.csv"))

# ------------------------------------------------------------------------ ACP
sortie_pca <- function(r) list(
  eig = unname(r$eig[, 1]),
  ind = list(coord = mat(r$ind$coord), contrib = mat(r$ind$contrib), cos2 = mat(r$ind$cos2)),
  var = list(coord = mat(r$var$coord), cor = mat(r$var$cor), contrib = mat(r$var$contrib), cos2 = mat(r$var$cos2)),
  ind_sup = if (!is.null(r$ind.sup)) list(coord = mat(r$ind.sup$coord), cos2 = mat(r$ind.sup$cos2)),
  quanti_sup = if (!is.null(r$quanti.sup)) list(coord = mat(r$quanti.sup$coord), cor = mat(r$quanti.sup$cor), cos2 = mat(r$quanti.sup$cos2)),
  quali_sup = if (!is.null(r$quali.sup)) list(coord = mat(r$quali.sup$coord), cos2 = mat(r$quali.sup$cos2),
                                              vtest = mat(r$quali.sup$v.test), eta2 = mat(r$quali.sup$eta2))
)
ecrire("acp_reduite_sup", sortie_pca(
  PCA(decathlon, quanti.sup = 11:12, quali.sup = 13, ind.sup = 37:41, ncp = 5, graph = FALSE)))
ecrire("acp_non_reduite", sortie_pca(
  PCA(decathlon, quanti.sup = 11:12, quali.sup = 13, scale.unit = FALSE, ncp = 5, graph = FALSE)))
w <- poids_test(nrow(decathlon))
r <- sortie_pca(PCA(decathlon, quanti.sup = 11:12, quali.sup = 13, row.w = w, ncp = 5, graph = FALSE))
r$poids <- w
ecrire("acp_ponderee", r)

# ------------------------------------------------------------------------ AFC
sortie_ca <- function(r) list(
  eig = unname(r$eig[, 1]),
  row = list(coord = mat(r$row$coord), contrib = mat(r$row$contrib), cos2 = mat(r$row$cos2)),
  col = list(coord = mat(r$col$coord), contrib = mat(r$col$contrib), cos2 = mat(r$col$cos2)),
  row_sup = if (!is.null(r$row.sup)) list(coord = mat(r$row.sup$coord), cos2 = mat(r$row.sup$cos2)),
  col_sup = if (!is.null(r$col.sup)) list(coord = mat(r$col.sup$coord), cos2 = mat(r$col.sup$cos2))
)
ecrire("afc_children_sup", sortie_ca(CA(children, row.sup = 15:18, col.sup = 6:8, ncp = 4, graph = FALSE)))
ecrire("afc_children_simple", sortie_ca(CA(children[1:14, 1:5], ncp = 4, graph = FALSE)))

# ------------------------------------------------------------------------ ACM
sortie_mca <- function(r) list(
  eig = unname(r$eig[, 1]),
  ind = list(coord = mat(r$ind$coord), contrib = mat(r$ind$contrib), cos2 = mat(r$ind$cos2)),
  var = list(coord = mat(r$var$coord), contrib = mat(r$var$contrib), cos2 = mat(r$var$cos2),
             vtest = mat(r$var$v.test), eta2 = mat(r$var$eta2)),
  ind_sup = if (!is.null(r$ind.sup)) list(coord = mat(r$ind.sup$coord), cos2 = mat(r$ind.sup$cos2)),
  quali_sup = if (!is.null(r$quali.sup)) list(coord = mat(r$quali.sup$coord), cos2 = mat(r$quali.sup$cos2),
                                              vtest = mat(r$quali.sup$v.test), eta2 = mat(r$quali.sup$eta2)),
  quanti_sup = if (!is.null(r$quanti.sup)) list(coord = mat(r$quanti.sup$coord))
)
# NB : les lignes des tableaux de modalités suivent l'ordre « variables dans l'ordre
# des colonnes × niveaux du facteur » ; on exporte ces niveaux pour que le test
# reconstruise la correspondance sans dépendre des renommages de FactoMineR.
r <- sortie_mca(MCA(tea, quanti.sup = 19, quali.sup = 20:36, ind.sup = 291:300, ncp = 5, graph = FALSE))
r$niveaux_actives <- niveaux(tea[1:290, 1:18]); r$niveaux_sup <- niveaux(tea[1:290, 20:36])
ecrire("acm_tea_sup", r)

w <- poids_test(nrow(tea))
r <- sortie_mca(MCA(tea[, 1:22], quanti.sup = 19, quali.sup = 20:22, row.w = w, ncp = 5, graph = FALSE))
r$poids <- w
r$niveaux_actives <- niveaux(tea[, 1:18]); r$niveaux_sup <- niveaux(tea[, 20:22])
ecrire("acm_tea_ponderee", r)

r <- sortie_mca(MCA(poison, quanti.sup = 1:2, quali.sup = 3:4, ncp = 5, graph = FALSE))
r$niveaux_actives <- niveaux(poison[, 5:15]); r$niveaux_sup <- niveaux(poison[, 3:4])
ecrire("acm_poison", r)

# Taux modifiés (Benzécri : GDAtools::modif.rate ; Greenacre : ca::mjca "adjusted")
if (requireNamespace("GDAtools", quietly = TRUE)) {
  rm <- MCA(tea[, 1:18], ncp = 5, graph = FALSE)
  mr <- GDAtools::modif.rate(rm)
  taux <- list(eig = unname(rm$eig[, 1]), benzecri = mr$modif$mrate, benzecri_cumule = mr$modif$cum.mrate)
  if (requireNamespace("ca", quietly = TRUE)) {
    mj <- ca::mjca(tea[, 1:18], lambda = "adjusted")
    taux$greenacre_valeurs <- mj$sv^2
    taux$greenacre_inertie_totale <- mj$inertia.t
    taux$greenacre_pct <- 100 * mj$sv^2 / mj$inertia.t
  }
  ecrire("acm_tea_taux_modifies", taux)
}

# ACM spécifique : modalités passives (une par variable pour quatre variables)
excl_paires <- list(c("Tea", "green"), c("price", "p_unknown"), c("where", "chain store+tea shop"), c("How", "other"))
act <- tea[, 1:18]
idx_cat <- unlist(lapply(seq_along(act), function(j) paste(names(act)[j], levels(act[, j]), sep = "::")))
excl <- match(sapply(excl_paires, paste, collapse = "::"), idx_cat)
stopifnot(!any(is.na(excl)))
r <- sortie_mca(MCA(tea, quanti.sup = 19, quali.sup = 20:36, ncp = 5, graph = FALSE, excl = excl))
r$passives <- excl_paires
r$niveaux_actives <- niveaux(tea[, 1:18]); r$niveaux_sup <- niveaux(tea[, 20:36])
ecrire("acm_specifique_factominer", r)

if (requireNamespace("GDAtools", quietly = TRUE)) {
  sortie_spe <- function(rs, data_sup, quali_sup_noms, w = NULL) {
    mr <- GDAtools::modif.rate(rs)
    sv <- lapply(quali_sup_noms, function(v) {
      s <- GDAtools::supvar(rs, tea[, v])
      list(variable = v, niveaux = levels(tea[, v]), poids = unname(s$weight),
           coord = mat(s$coord), cos2 = mat(s$cos2), typic = mat(s$typic),
           eta2 = unname(unlist(s$var["eta2", ])))
    })
    list(
      eig = rs$eig$eigen, pct = rs$eig$rate,
      benzecri = mr$modif$mrate, benzecri_cumule = mr$modif$cum.mrate,
      ind = list(coord = mat(rs$ind$coord), contrib = mat(rs$ind$contrib), cos2 = mat(rs$ind$cos2)),
      var = list(coord = mat(rs$var$coord), contrib = mat(rs$var$contrib), cos2 = mat(rs$var$cos2),
                 vtest = mat(rs$var$v.test), eta2 = mat(rs$var$eta2), contrib_variable = mat(rs$var$v.contrib),
                 poids = unname(rs$var$weight)),
      categories = rownames(rs$var$coord),
      quali_sup = sv,
      passives = excl_paires, niveaux_actives = niveaux(act), poids = w
    )
  }
  rs <- GDAtools::speMCA(act, excl = excl, ncp = 5)
  ecrire("acm_specifique_gdatools", sortie_spe(rs, NULL, c("sex", "SPC", "age_Q")))
  w <- poids_test(nrow(tea))
  rsw <- GDAtools::speMCA(act, excl = excl, ncp = 5, row.w = w)
  ecrire("acm_specifique_gdatools_ponderee", sortie_spe(rsw, NULL, c("sex", "SPC"), w))
}

# ----------------------------------------------------------------------- AFDM
sortie_famd <- function(r) list(
  eig = unname(r$eig[, 1]),
  ind = list(coord = mat(r$ind$coord), contrib = mat(r$ind$contrib), cos2 = mat(r$ind$cos2)),
  var = list(coord = mat(r$var$coord), contrib = mat(r$var$contrib), cos2 = mat(r$var$cos2),
             coord_sup = mat(r$var$coord.sup)),
  quanti = list(coord = mat(r$quanti.var$coord), contrib = mat(r$quanti.var$contrib), cos2 = mat(r$quanti.var$cos2)),
  quali = list(coord = mat(r$quali.var$coord), contrib = mat(r$quali.var$contrib), cos2 = mat(r$quali.var$cos2),
               vtest = mat(r$quali.var$v.test)),
  ind_sup = if (!is.null(r$ind.sup)) list(coord = mat(r$ind.sup$coord), cos2 = mat(r$ind.sup$cos2)),
  quanti_sup = if (!is.null(r$quanti.sup)) list(coord = mat(r$quanti.sup$coord), cos2 = mat(r$quanti.sup$cos2)),
  quali_sup = if (!is.null(r$quali.sup)) list(coord = mat(r$quali.sup$coord), cos2 = mat(r$quali.sup$cos2),
                                              vtest = mat(r$quali.sup$v.test), eta2 = mat(r$quali.sup$eta2))
)
# wine : colonnes 1-2 qualitatives (Label, Soil), 3+ quantitatives.
# Actives : Soil + colonnes 3:12 ; supplémentaires : Label (quali), 13:14 (quanti) ; individus sup : 1:2.
wn <- wine[, c(2, 3:12, 1, 13:14)]
r <- sortie_famd(FAMD(wn, sup.var = 12:14, ind.sup = 1:2, ncp = 5, graph = FALSE))
r$colonnes <- names(wn); r$niveaux <- niveaux(wn[3:21, c(1, 12)])
ecrire("afdm_wine_sup", r)
w <- poids_test(nrow(wine))
r <- sortie_famd(FAMD(wine[, c(1, 2, 3:10)], row.w = w, ncp = 5, graph = FALSE))
r$poids <- w; r$niveaux <- niveaux(wine[, 1:2])
ecrire("afdm_wine_ponderee", r)

# ------------------------------------------------------------- Classification
sortie_hcpc <- function(h) {
  part <- h$data.clust$clust; names(part) <- rownames(h$data.clust)
  list(
    individus = names(part), partition = as.integer(as.character(part)),
    nb_classes = h$call$t$nb.clust, gains = h$call$t$inert.gain, intra = h$call$t$within,
    quot = h$call$t$quot,
    bw_avant = h$call$bw.before.consol, bw_apres = h$call$bw.after.consol,
    parangons = lapply(h$desc.ind$para, function(x) list(noms = names(x), distances = unname(x)))
  )
}
pc <- PCA(decathlon[, 1:10], ncp = 5, graph = FALSE)
ecrire("cah_decathlon_auto", sortie_hcpc(HCPC(pc, nb.clust = -1, consol = FALSE, graph = FALSE)))
ecrire("cah_decathlon_auto_consol", sortie_hcpc(HCPC(pc, nb.clust = -1, consol = TRUE, graph = FALSE)))
ecrire("cah_decathlon_k4", sortie_hcpc(HCPC(pc, nb.clust = 4, consol = FALSE, graph = FALSE)))
w <- poids_test(nrow(decathlon))
pcw <- PCA(decathlon[, 1:10], ncp = 5, row.w = w, graph = FALSE)
r <- sortie_hcpc(HCPC(pcw, nb.clust = 3, consol = FALSE, graph = FALSE)); r$poids <- w
r$coord <- mat(pcw$ind$coord)
ecrire("cah_decathlon_ponderee", r)
mc <- MCA(tea[, 1:18], ncp = 5, graph = FALSE)
ecrire("cah_tea_k3", sortie_hcpc(HCPC(mc, nb.clust = 3, consol = FALSE, graph = FALSE)))
ecrire("cah_tea_k3_consol", sortie_hcpc(HCPC(mc, nb.clust = 3, consol = TRUE, graph = FALSE)))

# Description des classes (catdes, proba = 1 pour obtenir toutes les lignes)
h <- HCPC(mc, nb.clust = 3, consol = FALSE, graph = FALSE)
part <- h$data.clust[rownames(tea), "clust"]
d <- cbind(tea[, c("Tea", "How", "sex", "SPC", "age_Q", "age")], classe = part)
sortie_catdes <- function(cd, partition) list(
  partition = as.integer(as.character(partition)),
  chi2 = mat(cd$test.chi2),
  categories = lapply(cd$category, mat),
  quanti_var = mat(cd$quanti.var),
  quanti = lapply(cd$quanti, mat)
)
ecrire("catdes_tea", sortie_catdes(catdes(d, num.var = 7, proba = 1), part))
w <- round(poids_test(nrow(tea)) * 4) / 2     # poids variés (0,5 ; 1 ; … ) de somme quelconque
r <- sortie_catdes(catdes(d, num.var = 7, proba = 1, row.w = w), part); r$poids <- w
ecrire("catdes_tea_ponderee", r)

cat("Références écrites dans", dir_json, "\n")
