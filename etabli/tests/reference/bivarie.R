# Références R pour les statistiques uni/bivariées, corrélations et régressions d'Établi.
#
# Usage (depuis le dossier etabli/) :   Rscript tests/reference/bivarie.R
# Produit tests/reference/bivarie/*.json et tests/reference/donnees/*.csv.
# Ces fichiers sont versionnés : les tests Python (tests/test_bivarie.py) n'ont PAS besoin de R.
#
# Paquets : base R + MASS, nnet (recommandés), car, sandwich, jsonlite.
# descriptio (PEM de Cibois) est utilisé s'il est installé ; sinon la référence PEM est omise.
# Bibliothèque R particulière : R_LIBS=/chemin/vers/lib Rscript tests/reference/bivarie.R

suppressPackageStartupMessages({
  library(jsonlite); library(MASS); library(nnet); library(car); library(sandwich)
})

dir_json <- "tests/reference/bivarie"
dir_data <- "tests/reference/donnees"
dir.create(dir_json, recursive = TRUE, showWarnings = FALSE)
dir.create(dir_data, recursive = TRUE, showWarnings = FALSE)

ecrire <- function(x, nom) {
  writeLines(toJSON(x, digits = NA, auto_unbox = TRUE, null = "null", na = "null",
                    pretty = TRUE, matrix = "rowmajor"),
             file.path(dir_json, paste0(nom, ".json")))
}
mat <- function(m) { m <- unclass(m); attributes(m) <- list(dim = dim(m)); m }
versions <- list(R = R.version.string, car = as.character(packageVersion("car")),
                 sandwich = as.character(packageVersion("sandwich")),
                 MASS = as.character(packageVersion("MASS")),
                 nnet = as.character(packageVersion("nnet")))

# ---------------------------------------------------------------- données ----
data(survey, package = "MASS"); data(birthwt, package = "MASS")
write.csv(survey, file.path(dir_data, "survey.csv"), row.names = FALSE, na = "")
bw <- birthwt
bw$race <- factor(bw$race, levels = 1:3, labels = c("white", "black", "other"))
bw$smoke <- factor(bw$smoke, levels = 0:1, labels = c("non", "oui"))
bw$ht <- factor(bw$ht, levels = 0:1, labels = c("non", "oui"))
bw$ui <- factor(bw$ui, levels = 0:1, labels = c("non", "oui"))
write.csv(bw, file.path(dir_data, "birthwt.csv"), row.names = FALSE)
write.csv(mtcars, file.path(dir_data, "mtcars.csv"), row.names = TRUE)

# ------------------------------------------------------------ tableaux croisés ----
# IC du V de Cramér par inversion du chi² non central (méthode « ncchisq » de
# DescTools::CramerV, Smithson 2003) : on cherche les paramètres de non-centralité
# pour lesquels le chi² observé est au quantile 1-alpha/2 puis alpha/2.
ic_v_ncchisq <- function(chi2, ddl, n, k, niveau = 0.95) {
  a <- (1 - niveau) / 2
  f <- function(ncp, cible) pchisq(chi2, ddl, ncp) - cible
  bas <- if (pchisq(chi2, ddl) < 1 - a) 0 else
    uniroot(f, c(0, chi2 * 10 + 100), cible = 1 - a, tol = 1e-13)$root
  haut <- if (pchisq(chi2, ddl) < a) 0 else
    uniroot(f, c(0, chi2 * 10 + 100), cible = a, tol = 1e-13)$root
  sqrt(c(bas, haut) / (n * (k - 1)))
}
# Paires concordantes / discordantes par force brute (O(n²)) sur données individuelles.
paires_brutes <- function(tab) {
  d <- as.data.frame(as.table(tab)); d <- d[rep(seq_len(nrow(d)), d$Freq), 1:2]
  x <- as.integer(d[[1]]); y <- as.integer(d[[2]])
  C <- 0; D <- 0
  for (i in seq_along(x)) {
    s <- sign(x[i] - x) * sign(y[i] - y)
    C <- C + sum(s > 0); D <- D + sum(s < 0)
  }
  list(C = C / 2, D = D / 2, x = x, y = y)
}

ref_tableau <- function(tab, ordinal = FALSE, graine = 1) {
  tab <- as.matrix(tab)
  n <- sum(tab); k <- min(dim(tab)); r <- nrow(tab); cc <- ncol(tab)
  ct <- suppressWarnings(chisq.test(tab, correct = FALSE))
  chi2 <- unname(ct$statistic); ddl <- unname(ct$parameter)
  phi2 <- chi2 / n
  phi2c <- max(0, phi2 - (r - 1) * (cc - 1) / (n - 1))
  rc <- r - (r - 1)^2 / (n - 1); ccc <- cc - (cc - 1)^2 / (n - 1)
  set.seed(graine)
  sim <- chisq.test(tab, simulate.p.value = TRUE, B = 20000)
  # Fisher exact (réseau FEXACT) ; s'il dépasse la mémoire de travail (grand tableau),
  # on retient la version simulée de R et on le signale (fisher_exact = FALSE).
  fisher_exact <- TRUE
  ft <- tryCatch(fisher.test(tab, workspace = 2e7), error = function(e) NULL)
  if (is.null(ft)) { fisher_exact <- FALSE; set.seed(graine); ft <- fisher.test(tab, simulate.p.value = TRUE, B = 1e5) }
  out <- list(
    table = mat(tab), lignes = rownames(tab), colonnes = colnames(tab), n = n,
    chi2 = chi2, ddl = ddl, p = ct$p.value,
    theoriques = mat(ct$expected), residus = mat(ct$residuals), residus_ajustes = mat(ct$stdres),
    contributions = mat(100 * ct$residuals^2 / chi2),
    v = sqrt(phi2 / (k - 1)), v_corrige = sqrt(phi2c / min(rc - 1, ccc - 1)),
    v_ic = ic_v_ncchisq(chi2, ddl, n, k),
    p_simulee = sim$p.value, fisher_p = ft$p.value, fisher_exact = fisher_exact
  )
  if (r == 2 && cc == 2) {
    y <- suppressWarnings(chisq.test(tab, correct = TRUE))
    out$yates <- list(chi2 = unname(y$statistic), p = y$p.value)
    out$fisher_or <- unname(ft$estimate); out$fisher_ic <- as.numeric(ft$conf.int)
    out$or <- tab[1, 1] * tab[2, 2] / (tab[1, 2] * tab[2, 1])
    se <- sqrt(sum(1 / tab))
    out$or_ic <- exp(log(out$or) + c(-1, 1) * qnorm(0.975) * se)
    out$phi <- (tab[1, 1] * tab[2, 2] - tab[1, 2] * tab[2, 1]) /
      sqrt(prod(rowSums(tab)) * prod(colSums(tab)))
  }
  # PEM de Cibois : descriptio::assoc.twocat (successeur de GDAtools::pem)
  if (requireNamespace("descriptio", quietly = TRUE)) {
    d <- as.data.frame(as.table(tab)); d <- d[rep(seq_len(nrow(d)), d$Freq), 1:2]
    # sort = TRUE : lignes et colonnes réordonnées selon le premier facteur de l'AFC avant de construire le
    # tableau de liaison maximale (définition de Cibois). Avec sort = FALSE (défaut d'assoc.twocat), le PEM
    # global dépend de l'ordre dans lequel les modalités sont présentées.
    pm <- descriptio:::pem.table(droplevels(d[[1]]), droplevels(d[[2]]), sort = TRUE, digits = NULL)
    pl <- pm$peml[levels(droplevels(d[[1]])), levels(droplevels(d[[2]]))]
    out$pem_local <- mat(unclass(pl)); out$pem_global <- pm$pemg
  }
  if (ordinal) {
    pb <- paires_brutes(tab)
    out$gamma <- (pb$C - pb$D) / (pb$C + pb$D)
    out$concordantes <- pb$C; out$discordantes <- pb$D
    kt <- suppressWarnings(cor.test(pb$x, pb$y, method = "kendall", exact = FALSE))
    out$tau_b <- unname(kt$estimate); out$tau_b_p <- kt$p.value
  }
  out
}

cheveux_yeux <- margin.table(HairEyeColor, c(1, 2))            # 4×4, n = 592
titanic <- margin.table(Titanic, c(2, 4))                       # 2×2, n = 2201 (Sex × Survived)
the <- matrix(c(3, 1, 1, 3), 2, dimnames = list(c("Lait", "The"), c("Lait", "The")))
emploi <- matrix(c(1, 2, 1, 0, 3, 3, 6, 1, 10, 10, 14, 9, 6, 7, 12, 11), 4, 4,
                 dimnames = list(revenu = c("<15k", "15-25k", "25-40k", ">40k"),
                                 satisfaction = c("TresInsat", "PeuInsat", "AssezSat", "TresSat")))
sv <- survey
sv$Smoke <- factor(sv$Smoke, levels = c("Never", "Occas", "Regul", "Heavy"))
sv$Exer <- factor(sv$Exer, levels = c("None", "Some", "Freq"))
fume_sport <- table(sv$Smoke, sv$Exer)                           # 4×3 avec NA exclus par paires
ecrire(list(
  versions = versions,
  cheveux_yeux = ref_tableau(cheveux_yeux),
  titanic = ref_tableau(titanic),
  the = ref_tableau(the),
  emploi = ref_tableau(emploi, ordinal = TRUE),
  fume_sport = c(ref_tableau(fume_sport, ordinal = TRUE),
                 list(n_exclus = sum(is.na(sv$Smoke) | is.na(sv$Exer))))
), "croise")

# ------------------------------------------------------------------ univarié ----
wilson <- lapply(list(c(0, 20), c(3, 20), c(7, 50), c(45, 124), c(349, 349), c(120, 349)), function(kn) {
  pt <- prop.test(kn[1], kn[2], correct = FALSE)
  list(k = kn[1], n = kn[2], ic = as.numeric(pt$conf.int))
})
x <- survey$Height
xv <- x[!is.na(x)]; n <- length(xv); m <- mean(xv); s <- sd(xv)
tt <- t.test(xv)
ecrire(list(
  wilson = wilson,
  fume = list(effectifs = as.list(table(sv$Smoke)), n = sum(!is.na(sv$Smoke)), n_manquants = sum(is.na(sv$Smoke))),
  height = list(
    n = n, n_manquants = sum(is.na(x)), moyenne = m, ecart_type = s, variance = var(xv),
    mediane = median(xv), quartiles = as.numeric(quantile(xv, c(.25, .75), type = 7)),
    deciles = as.numeric(quantile(xv, c(.1, .9), type = 7)),
    min = min(xv), max = max(xv), ic_moyenne = as.numeric(tt$conf.int),
    # G1 (type 2, SAS/SPSS) et G2 : coefficients corrigés du biais
    asymetrie = n / ((n - 1) * (n - 2)) * sum(((xv - m) / s)^3),
    aplatissement = n * (n + 1) / ((n - 1) * (n - 2) * (n - 3)) * sum(((xv - m) / s)^4) -
      3 * (n - 1)^2 / ((n - 2) * (n - 3)),
    hist10 = list(bornes = hist(xv, breaks = seq(min(xv), max(xv), length.out = 11), plot = FALSE, include.lowest = TRUE, right = FALSE)$breaks,
                  effectifs = hist(xv, breaks = seq(min(xv), max(xv), length.out = 11), plot = FALSE, include.lowest = TRUE, right = FALSE)$counts)
  )
), "univarie")

# ------------------------------------------------------- comparaison de groupes ----
ref_groupes <- function(y, g) {
  ok <- !is.na(y) & !is.na(g); y <- y[ok]; g <- droplevels(g[ok])
  a <- aov(y ~ g); sa <- summary(a)[[1]]
  ssb <- sa[1, "Sum Sq"]; ssw <- sa[2, "Sum Sq"]; k <- nlevels(g); n <- length(y); msw <- sa[2, "Mean Sq"]
  w <- oneway.test(y ~ g, var.equal = FALSE)
  kw <- kruskal.test(y ~ g)
  lv <- car::leveneTest(y ~ g, center = median)
  out <- list(
    n = n, n_exclus = sum(!ok),
    groupes = lapply(levels(g), function(l) {
      v <- y[g == l]; ic <- if (length(v) > 1) as.numeric(t.test(v)$conf.int) else c(NA, NA)
      list(groupe = l, n = length(v), moyenne = mean(v), ecart_type = sd(v), mediane = median(v),
           q1 = unname(quantile(v, .25)), q3 = unname(quantile(v, .75)), ic = ic)
    }),
    anova = list(f = sa[1, "F value"], ddl1 = sa[1, "Df"], ddl2 = sa[2, "Df"], p = sa[1, "Pr(>F)"],
                 eta2 = ssb / (ssb + ssw), omega2 = (ssb - (k - 1) * msw) / (ssb + ssw + msw)),
    welch = list(f = unname(w$statistic), ddl1 = unname(w$parameter[1]), ddl2 = unname(w$parameter[2]), p = w$p.value),
    kruskal = list(h = unname(kw$statistic), ddl = unname(kw$parameter), p = kw$p.value,
                   epsilon2 = unname(kw$statistic) / (n - 1)),
    levene = list(w = lv[1, "F value"], p = lv[1, "Pr(>F)"])
  )
  if (k == 2) {
    l <- levels(g); a1 <- y[g == l[1]]; a2 <- y[g == l[2]]
    tw <- t.test(a1, a2, var.equal = FALSE)
    n1 <- length(a1); n2 <- length(a2)
    sp <- sqrt(((n1 - 1) * var(a1) + (n2 - 1) * var(a2)) / (n1 + n2 - 2))
    d <- (mean(a1) - mean(a2)) / sp
    J <- 1 - 3 / (4 * (n1 + n2 - 2) - 1)
    mw <- suppressWarnings(wilcox.test(a1, a2, exact = FALSE, correct = TRUE))
    out$deux <- list(
      t = unname(tw$statistic), ddl = unname(tw$parameter), p = tw$p.value,
      difference = mean(a1) - mean(a2), ic = as.numeric(tw$conf.int),
      d = d, g = d * J,
      u = unname(mw$statistic), p_mw = mw$p.value,
      r_biseriale = 2 * unname(mw$statistic) / (n1 * n2) - 1
    )
  }
  out
}
# petit exemple sans ex æquo pour le test exact de Mann-Whitney
ex_a <- c(1.1, 2.3, 3.7, 4.2, 5.9, 6.4); ex_b <- c(2.9, 4.8, 7.1, 8.3, 9.6, 10.2, 11.5)
mwx <- wilcox.test(ex_a, ex_b)
ecrire(list(
  height_sexe = ref_groupes(survey$Height, survey$Sex),
  pulse_exer = ref_groupes(survey$Pulse, sv$Exer),
  age_fume = ref_groupes(survey$Age, sv$Smoke),
  exact = list(a = ex_a, b = ex_b, u = unname(mwx$statistic), p = mwx$p.value)
), "groupes")

# ---------------------------------------------------------------- corrélations ----
ref_cor <- function(d, methode) {
  v <- names(d); paires <- list()
  for (i in 1:(length(v) - 1)) for (j in (i + 1):length(v)) {
    ok <- complete.cases(d[, c(i, j)])
    ct <- suppressWarnings(cor.test(d[ok, i], d[ok, j], method = methode, exact = FALSE))
    r <- unname(ct$estimate); n <- sum(ok)
    ic <- if (methode == "pearson") as.numeric(ct$conf.int) else if (methode == "spearman")
      tanh(atanh(r) + c(-1, 1) * qnorm(0.975) / sqrt(n - 3)) else c(NA, NA)
    paires[[length(paires) + 1]] <- list(x = v[i], y = v[j], r = r, n = n, p = ct$p.value, ic = ic)
  }
  p <- sapply(paires, function(z) z$p)
  list(paires = paires, p_holm = p.adjust(p, "holm"), p_bh = p.adjust(p, "BH"))
}
dm <- mtcars[, c("mpg", "hp", "wt", "qsec", "drat")]
ds <- survey[, c("Height", "Pulse", "Age", "Wr.Hnd", "NW.Hnd")]
ecrire(list(
  mtcars = list(pearson = ref_cor(dm, "pearson"), spearman = ref_cor(dm, "spearman"), kendall = ref_cor(dm, "kendall")),
  survey = list(pearson = ref_cor(ds, "pearson"), spearman = ref_cor(ds, "spearman"), kendall = ref_cor(ds, "kendall")),
  p_adjust = list(p = c(0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216, 0.5, 0.9),
                  holm = p.adjust(c(0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216, 0.5, 0.9), "holm"),
                  bh = p.adjust(c(0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216, 0.5, 0.9), "BH"))
), "correlation")

# ----------------------------------------------------------------- régressions ----
coefs <- function(m, vc = NULL) {
  s <- coef(summary(m)); ic <- confint.default(m)
  out <- lapply(rownames(s), function(t) list(terme = t, coef = s[t, 1], se = s[t, 2], stat = s[t, 3], p = s[t, 4],
                                              ic = as.numeric(ic[t, ])))
  if (!is.null(vc)) for (i in seq_along(out)) out[[i]]$se_robuste <- sqrt(diag(vc))[i]
  out
}
anova2 <- function(a, colstat) {
  a <- as.data.frame(a); a <- a[rownames(a) != "Residuals", , drop = FALSE]
  lapply(rownames(a), function(t) list(terme = t, ddl = a[t, "Df"], stat = a[t, colstat], p = a[t, ncol(a)]))
}
vifs <- function(m) {
  v <- car::vif(m)
  if (is.matrix(v)) lapply(rownames(v), function(t) list(terme = t, gvif = v[t, 1], ddl = v[t, 2], gvif_ajuste = v[t, 3]))
  else lapply(names(v), function(t) list(terme = t, gvif = unname(v[t]), ddl = 1, gvif_ajuste = sqrt(unname(v[t]))))
}

# --- linéaire
ml <- lm(bwt ~ age + lwt + race + smoke + ht, data = bw)
sl <- summary(ml)
ic_t <- confint(ml)
ml_int <- lm(bwt ~ age * smoke + race, data = bw)
ref_lm <- list(
  n = nobs(ml), termes = coefs(ml, sandwich::vcovHC(ml, type = "HC3")),
  ic_t = lapply(rownames(ic_t), function(t) as.numeric(ic_t[t, ])),
  r2 = sl$r.squared, r2_ajuste = sl$adj.r.squared, f = unname(sl$fstatistic[1]),
  ddl1 = unname(sl$fstatistic[2]), ddl2 = unname(sl$fstatistic[3]),
  p_f = unname(pf(sl$fstatistic[1], sl$fstatistic[2], sl$fstatistic[3], lower.tail = FALSE)),
  sigma = sl$sigma, aic = AIC(ml), bic = BIC(ml), logvrais = as.numeric(logLik(ml)),
  anova2 = anova2(car::Anova(ml, type = 2), "F value"), vif = vifs(ml),
  interaction = list(termes = coefs(ml_int), anova2 = anova2(car::Anova(ml_int, type = 2), "F value"),
                     r2 = summary(ml_int)$r.squared)
)

# --- logistique
mg <- glm(low ~ age + lwt + race + smoke + ht + ui, data = bw, family = binomial)
p_hat <- fitted(mg); y <- bw$low; n <- length(y)
ll <- as.numeric(logLik(mg)); ll0 <- as.numeric(logLik(update(mg, . ~ 1)))
# Effets marginaux moyens calculés « à la main »
b <- coef(mg)
ame_continu <- function(v) mean(b[v] * p_hat * (1 - p_hat))
ame_binaire <- function(var, niveau, ref) {
  d1 <- bw; d1[[var]] <- factor(niveau, levels = levels(bw[[var]]))
  d0 <- bw; d0[[var]] <- factor(ref, levels = levels(bw[[var]]))
  mean(predict(mg, d1, type = "response") - predict(mg, d0, type = "response"))
}
mg_int <- glm(low ~ lwt * smoke + race, data = bw, family = binomial)
ref_glm <- list(
  n = n, termes = coefs(mg), deviance = deviance(mg), deviance_nulle = mg$null.deviance,
  aic = AIC(mg), bic = BIC(mg), logvrais = ll, logvrais_nul = ll0,
  mcfadden = 1 - ll / ll0,
  nagelkerke = (1 - exp((2 / n) * (ll0 - ll))) / (1 - exp((2 / n) * ll0)),
  lr = list(chi2 = mg$null.deviance - deviance(mg), ddl = mg$df.null - mg$df.residual,
            p = pchisq(mg$null.deviance - deviance(mg), mg$df.null - mg$df.residual, lower.tail = FALSE)),
  anova2 = anova2(car::Anova(mg, type = 2, test.statistic = "LR"), "LR Chisq"), vif = vifs(mg),
  auc = unname(wilcox.test(p_hat[y == 1], p_hat[y == 0])$statistic) / (sum(y == 1) * sum(y == 0)),
  bons_classements = mean((p_hat >= 0.5) == (y == 1)),
  ame = list(age = unname(ame_continu("age")), lwt = unname(ame_continu("lwt")),
             smoke_oui = ame_binaire("smoke", "oui", "non"), ht_oui = ame_binaire("ht", "oui", "non"),
             race_black = ame_binaire("race", "black", "white"), race_other = ame_binaire("race", "other", "white")),
  interaction = list(termes = coefs(mg_int),
                     anova2 = anova2(car::Anova(mg_int, type = 2, test.statistic = "LR"), "LR Chisq"))
)

# --- multinomiale (nnet::multinom : optimiseur BFGS, tolérance plus large côté tests)
mm <- nnet::multinom(race ~ age + lwt + smoke, data = bw, trace = FALSE, reltol = 1e-12, maxit = 1000, Hess = TRUE)
sm <- summary(mm)
ref_mn <- list(
  n = nrow(bw), modalites = rownames(sm$coefficients), termes_noms = colnames(sm$coefficients),
  coef = mat(sm$coefficients), se = mat(sm$standard.errors),
  logvrais = as.numeric(logLik(mm)), aic = AIC(mm), deviance = deviance(mm)
)
ecrire(list(versions = versions, lineaire = ref_lm, logistique = ref_glm, multinomiale = ref_mn), "regression")

cat("Références écrites dans", dir_json, "\n")
