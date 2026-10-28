# Independent R analysis of the frozen Python test predictions.
# Run from project root: Rscript r/validate_fraud.R outputs
# No fitting, threshold selection or retuning against test labels occurs here.

safe_div <- function(a, b, default = 0) if (b == 0) default else a / b

wilson <- function(k, n, level = 0.95) {
  if (n == 0) return(c(lower = NA_real_, upper = NA_real_))
  z <- qnorm(1 - (1 - level) / 2)
  p <- k / n
  center <- (p + z^2 / (2 * n)) / (1 + z^2 / n)
  half <- z * sqrt(p * (1 - p) / n + z^2 / (4 * n^2)) / (1 + z^2 / n)
  c(lower = max(0, center - half), upper = min(1, center + half))
}

evaluate_policy <- function(d, prediction, cfg) {
  y <- d$isFraud == 1
  p <- as.logical(prediction)
  if (length(p) != nrow(d) || anyNA(p)) stop("Invalid prediction vector")
  tp <- sum(y & p); fp <- sum(!y & p)
  fn <- sum(y & !p); tn <- sum(!y & !p)
  captured <- sum(d$amount[y & p]); missed <- sum(d$amount[y & !p])
  workload <- tapply(as.integer(p), d$step, sum)
  review <- sum(p) * cfg$review_cost_units
  friction <- fp * cfg$false_alert_friction_units
  benefit <- captured * cfg$action_success_fraction
  data.frame(rows = nrow(d), tp = tp, fp = fp, fn = fn, tn = tn,
    alerts = sum(p), precision = safe_div(tp, tp + fp), recall = safe_div(tp, tp + fn),
    f1 = safe_div(2 * tp, 2 * tp + fp + fn), false_positive_rate = safe_div(fp, fp + tn),
    alert_rate = mean(p), fraud_value = captured + missed,
    captured_fraud_value = captured, missed_fraud_value = missed,
    value_recall = safe_div(captured, captured + missed), alerts_per_step = mean(workload),
    peak_alerts_per_step = max(workload), review_cost = review,
    false_alert_friction = friction, assumed_prevented_value = benefit,
    scenario_total_cost = captured + missed - benefit + review + friction,
    scenario_net_benefit = benefit - review - friction,
    capacity_feasible = max(workload) <= cfg$review_capacity_per_step)
}

ranking_metrics <- function(y, score) {
  if (anyNA(score) || any(!is.finite(score)) || !all(y %in% c(0, 1))) stop("Invalid ranking input")
  if (length(unique(y)) != 2) stop("Ranking metrics require both classes")
  ord <- order(-score, seq_along(score))
  label <- y[ord]
  # AP uses distinct thresholds, matching sklearn average_precision_score,
  # including tied-score groups. It is not trapezoidal PR-AUC.
  last <- c(which(diff(score[ord]) != 0), length(score))
  cumulative <- cumsum(label)[last]
  ap <- sum((cumulative - c(0, head(cumulative, -1))) / sum(y) * cumulative / last)
  positive <- sum(y); negative <- length(y) - positive
  auc <- (sum(rank(score, ties.method = "average")[y == 1]) - positive * (positive + 1) / 2) / (positive * negative)
  data.frame(average_precision = ap, roc_auc = auc,
             precision_at_100 = mean(label[seq_len(min(100, length(label)))]))
}

cluster_intervals <- function(d, replicates = 500, seed = 42) {
  # Resample recipient accounts, preserving correlated rows within a recipient.
  # This does not model all sender/network dependence or population changes.
  y <- d$isFraud == 1; p <- d$prediction == 1
  values <- data.frame(tp = as.integer(y & p), fp = as.integer(!y & p),
    fn = as.integer(y & !p), tn = as.integer(!y & !p),
    captured = ifelse(y & p, d$amount, 0), fraud_value = ifelse(y, d$amount, 0))
  clusters <- rowsum(as.matrix(values), group = d$nameDest, reorder = FALSE)
  set.seed(seed)
  estimates <- replicate(replicates, {
    totals <- colSums(clusters[sample.int(nrow(clusters), nrow(clusters), replace = TRUE), , drop = FALSE])
    c(precision = safe_div(totals["tp"], totals["tp"] + totals["fp"], NA_real_),
      recall = safe_div(totals["tp"], totals["tp"] + totals["fn"], NA_real_),
      false_positive_rate = safe_div(totals["fp"], totals["fp"] + totals["tn"], NA_real_),
      value_recall = safe_div(totals["captured"], totals["fraud_value"], NA_real_))
  })
  # Strip names inherited from the summed vectors (precision.tp etc.).
  rownames(estimates) <- c("precision", "recall", "false_positive_rate", "value_recall")
  data.frame(metric = rownames(estimates),
    lower = apply(estimates, 1, function(x) if (all(is.na(x))) NA_real_ else quantile(x, .025, na.rm = TRUE, names = FALSE)),
    upper = apply(estimates, 1, function(x) if (all(is.na(x))) NA_real_ else quantile(x, .975, na.rm = TRUE, names = FALSE)),
    valid_replicates = rowSums(!is.na(estimates)), clusters = nrow(clusters),
    method = "Recipient-cluster percentile bootstrap, 95%", row.names = NULL)
}

run_validation <- function(input_dir = "outputs", replicates = 500) {
  needed <- c("dplyr", "ggplot2", "jsonlite")
  missing <- needed[!vapply(needed, requireNamespace, quietly = TRUE, FUN.VALUE = logical(1))]
  if (length(missing)) stop("Install required R packages: ", paste(missing, collapse = ", "))
  suppressPackageStartupMessages(library(dplyr))
  suppressPackageStartupMessages(library(ggplot2))
  manifest <- jsonlite::fromJSON(file.path(input_dir, "manifest.json"))
  cfg <- manifest$config
  d <- read.csv(file.path(input_dir, "test_scored.csv"), stringsAsFactors = FALSE, check.names = FALSE)
  required <- c("row_id", "step", "type", "amount", "nameOrig", "nameDest", "isFraud", "isFlaggedFraud",
    "score", "prediction", "sender_count_24h", "sender_amount_ratio", "recipient_count_24h", "recipient_amount_ratio")
  if (!all(required %in% names(d))) stop("Missing required scored-data columns")
  if (nrow(d) == 0 || anyNA(d[required]) || anyDuplicated(d$row_id)) stop("Missing values, duplicate IDs or empty scored dataset")
  if (!all(d$isFraud %in% 0:1) || !all(d$prediction %in% 0:1) || any(!is.finite(d$score)) ||
      any(d$score < 0 | d$score > 1) || any(!is.finite(d$amount)) || any(d$amount < 0)) stop("Invalid scored-data values")
  if (!all(as.integer(d$score >= manifest$threshold) == d$prediction)) stop("Predictions disagree with locked threshold")
  if (!all(d$step >= manifest$splits$test$first_step & d$step <= manifest$splits$test$last_step)) stop("Test split boundary mismatch")
  dest <- file.path(input_dir, "r")
  dir.create(dest, recursive = TRUE, showWarnings = FALSE)
  write_table <- function(x, name) write.csv(x, file.path(dest, name), row.names = FALSE, na = "")
  risky <- d$type %in% c("TRANSFER", "CASH_OUT")
  policies <- list(
    R01_existing_flag = d$isFlaggedFraud == 1,
    R02_large_transfer_cashout = risky & d$amount > cfg$amount_rule_threshold,
    R03_recipient_burst = d$recipient_count_24h >= cfg$recipient_velocity_threshold & d$recipient_amount_ratio >= cfg$relative_amount_threshold,
    R04_sender_deviation = risky & d$sender_count_24h >= 3 & d$sender_amount_ratio >= cfg$relative_amount_threshold)
  policies$rules_union <- Reduce(`|`, policies)
  policies$selected_model <- d$prediction == 1
  policies$hybrid_union <- policies$selected_model | policies$rules_union
  r_metrics <- bind_rows(lapply(names(policies), function(name) {
    cbind(policy = name, evaluate_policy(d, policies[[name]], cfg))
  }))
  write_table(r_metrics, "policy_metrics.csv")
  py <- read.csv(file.path(input_dir, "policy_comparison.csv"), stringsAsFactors = FALSE)
  if (!setequal(py$policy, r_metrics$policy)) stop("Policy names do not match")
  py <- py[match(r_metrics$policy, py$policy), ]
  numeric_fields <- names(r_metrics)[vapply(r_metrics, is.numeric, logical(1))]
  parity <- bind_rows(lapply(numeric_fields, function(field) {
    delta <- abs(r_metrics[[field]] - py[[field]])
    tolerance <- 1e-8 + 1e-10 * abs(py[[field]])
    data.frame(policy = r_metrics$policy, metric = field, r_value = r_metrics[[field]],
      python_value = py[[field]], absolute_difference = delta, passed = delta <= tolerance)
  }))
  if (!identical(as.logical(r_metrics$capacity_feasible), as.logical(py$capacity_feasible))) stop("Capacity status mismatch")
  ranking <- ranking_metrics(d$isFraud, d$score)
  write_table(ranking, "ranking_metrics.csv")
  py_rank <- read.csv(file.path(input_dir, "ranking_metrics.csv"))
  py_rank <- py_rank[py_rank$period == "test", ]
  if (nrow(py_rank) != 1) stop("Expected one Python test ranking row")
  for (field in names(ranking)) {
    delta <- abs(ranking[[field]] - py_rank[[field]])
    parity <- bind_rows(parity, data.frame(policy = "selected_model", metric = field,
      r_value = ranking[[field]], python_value = py_rank[[field]], absolute_difference = delta, passed = delta <= 1e-8))
  }
  write_table(parity, "python_r_parity.csv")
  if (!all(parity$passed)) stop("Python/R parity failed; inspect python_r_parity.csv")
  intervals <- cluster_intervals(d, replicates, cfg$seed)
  write_table(intervals, "cluster_confidence_intervals.csv")
  rates <- d %>% group_by(type) %>% summarise(transactions = n(), fraud_cases = sum(isFraud),
      fraud_rate = mean(isFraud), .groups = "drop")
  limits <- t(vapply(seq_len(nrow(rates)), function(i) wilson(rates$fraud_cases[i], rates$transactions[i]), numeric(2)))
  rates$lower <- limits[, 1]; rates$upper <- limits[, 2]
  write_table(rates, "fraud_rate_by_type.csv")
  amounts <- d %>% mutate(outcome = ifelse(isFraud == 1, "Labelled fraud", "Legitimate")) %>%
    group_by(outcome) %>% summarise(transactions = n(), median_amount = median(amount),
      q25 = quantile(amount, .25), q75 = quantile(amount, .75), total_amount = sum(amount), .groups = "drop")
  write_table(amounts, "amount_summary.csv")
  set.seed(cfg$seed)
  contingency <- table(d$type, d$isFraud)
  chisq <- suppressWarnings(chisq.test(contingency, simulate.p.value = TRUE, B = 1999))
  pearson <- suppressWarnings(chisq.test(contingency, correct = FALSE))
  # Exploratory comparisons assume independent transactions; confidence intervals
  # above use recipient clusters. Neither establishes a fraud mechanism.
  association <- data.frame(test = "Transaction type vs fraud: Monte Carlo chi-square",
    statistic = as.numeric(chisq$statistic), p_value = chisq$p.value,
    cramers_v = sqrt(as.numeric(pearson$statistic) / (nrow(d) * min(nrow(contingency)-1, ncol(contingency)-1))),
    interpretation = "Exploratory association; repeated-account dependence and simulator design limit inference")
  write_table(association, "statistical_association.csv")
  theme_set(theme_minimal(base_size = 11))
  rate_plot <- ggplot(rates, aes(type, fraud_rate)) + geom_col(fill = "#176b79") +
    geom_errorbar(aes(ymin = lower, ymax = upper), width = .2) +
    scale_y_continuous(labels = function(x) paste0(round(100*x, 1), "%")) +
    labs(title = "Observed fraud rate by transaction type", subtitle = manifest$mode,
      x = "Transaction type", y = "Fraud rate (Wilson intervals)", caption = "Transaction-level intervals assume independent observations; not a real-world safety guarantee.")
  ggsave(file.path(dest, "fraud_rate_by_type.png"), rate_plot, width = 9, height = 5, dpi = 160, bg = "white")
  plot_data <- bind_rows(lapply(c("tp", "fp", "fn"), function(metric) {
    data.frame(policy = r_metrics$policy, outcome = metric, count = r_metrics[[metric]])
  }))
  policy_plot <- ggplot(plot_data, aes(policy, count, fill = outcome)) + geom_col(position = "dodge") +
    scale_fill_manual(values = c(tp = "#176b79", fp = "#d28c28", fn = "#b74545"),
      labels = c(tp = "Detected fraud", fp = "Legitimate alerts", fn = "Missed fraud")) +
    coord_flip() + labs(title = "Policy comparison: fraud caught, missed and legitimate alerts",
      subtitle = manifest$mode, x = NULL, y = "Transactions", fill = "Outcome")
  ggsave(file.path(dest, "policy_outcomes.png"), policy_plot, width = 10, height = 6, dpi = 160, bg = "white")
  intervals$estimate <- vapply(intervals$metric, function(m) r_metrics[r_metrics$policy == "selected_model", m], numeric(1))
  ci_plot <- ggplot(intervals, aes(metric, estimate)) + geom_point(size = 3, colour = "#176b79") +
    geom_errorbar(aes(ymin = lower, ymax = upper), width = .15) + coord_flip() +
    scale_y_continuous(labels = function(x) paste0(round(100*x), "%")) +
    labs(title = "Uncertainty in the locked model's test metrics", subtitle = manifest$mode,
      x = NULL, y = "Rate", caption = paste(replicates, "recipient-cluster bootstrap replicates; conditional on this synthetic test period."))
  ggsave(file.path(dest, "metric_uncertainty.png"), ci_plot, width = 9, height = 5, dpi = 160, bg = "white")
  report <- c("# Independent R validation", "", paste("**Run basis:", manifest$mode, "**"), "",
    sprintf("Verified %d numeric Python/R comparisons across seven policies and ranking metrics.", nrow(parity)),
    "Threshold and model selection remain frozen; this script does not retune on test labels.", "",
    sprintf("Uncertainty: %d recipient clusters, %d bootstrap replicates, seed %d.", length(unique(d$nameDest)), replicates, cfg$seed),
    "Intervals describe sampling variation in the current period, not generalisation to a bank or future fraud types.",
    "Type-rate Wilson intervals and the chi-square association are exploratory and assume transaction independence.",
    "Recipient clustering does not capture all sender/network dependence. Associations do not prove root causes.", "",
    "Costs and action success remain scenario assumptions in dataset currency units. No measured prevention or USD/INR conversion is claimed.",
    "All fixture tables and plots remain labelled as integration tests, not PaySim results.", "",
    "Packages used: dplyr (aggregation), ggplot2 (plots), jsonlite (manifest), base R stats (tests and intervals).",
    "tidymodels is not used or claimed.")
  writeLines(report, file.path(dest, "validation_report.md"))
  jsonlite::write_json(list(source_input_sha256 = manifest$input_sha256,
    test_csv_md5 = unname(tools::md5sum(file.path(input_dir, "test_scored.csv"))),
    selected_model = manifest$selected_model, threshold = manifest$threshold,
    rows = nrow(d), mode = manifest$mode),
    file.path(dest, "validation_metadata.json"), auto_unbox = TRUE, pretty = TRUE, digits = 17)
  capture.output(sessionInfo(), file = file.path(dest, "sessionInfo.txt"))
  cat(sprintf("R VALIDATION PASSED: %d parity checks; %d clusters; %d bootstrap replicates\n", nrow(parity), length(unique(d$nameDest)), replicates))
  invisible(list(metrics = r_metrics, parity = parity, intervals = intervals))
}

if (sys.nframe() == 0L) {
  args <- commandArgs(trailingOnly = TRUE)
  run_validation(if (length(args)) args[[1]] else "outputs")
}
