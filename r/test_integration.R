# Run after validate_fraud.R. Confirm evidence and ensure drifted references fail.
source("r/validate_fraud.R")
args <- commandArgs(trailingOnly = TRUE)
input <- if (length(args)) args[[1]] else "outputs"
parity <- read.csv(file.path(input, "r/python_r_parity.csv"))
stopifnot(nrow(parity) > 100, all(parity$passed))
ci <- read.csv(file.path(input, "r/cluster_confidence_intervals.csv"))
stopifnot(nrow(ci) == 4, all(ci$lower <= ci$upper), all(ci$valid_replicates > 0))
for (name in c("fraud_rate_by_type.png", "policy_outcomes.png", "metric_uncertainty.png")) {
  stopifnot(file.info(file.path(input, "r", name))$size > 1000)
}
temp <- tempfile("r-parity-negative-")
dir.create(temp)
tryCatch({
  for (name in c("manifest.json", "test_scored.csv", "policy_comparison.csv", "ranking_metrics.csv")) {
    stopifnot(file.copy(file.path(input, name), file.path(temp, name)))
  }
  wrong <- read.csv(file.path(temp, "policy_comparison.csv"))
  wrong$precision[1] <- wrong$precision[1] + .1
  write.csv(wrong, file.path(temp, "policy_comparison.csv"), row.names = FALSE)
  failure <- try(run_validation(temp, replicates = 10), silent = TRUE)
  stopifnot(inherits(failure, "try-error"), grepl("Python/R parity failed", as.character(failure), fixed = TRUE))
}, finally = unlink(temp, recursive = TRUE))
cat("R INTEGRATION CHECKS PASSED: evidence generated and a deliberately corrupted Python metric rejected\n")
