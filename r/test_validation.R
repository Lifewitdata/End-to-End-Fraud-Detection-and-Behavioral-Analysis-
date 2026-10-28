# Base R assertions: no testthat dependency required.
source("r/validate_fraud.R")
cfg <- list(review_cost_units = 5, false_alert_friction_units = 2,
            action_success_fraction = .5, review_capacity_per_step = 2)
d <- data.frame(step = c(1, 1, 2, 2), isFraud = c(1, 1, 0, 0),
                amount = c(100, 200, 20, 30), nameDest = c("A", "B", "A", "B"),
                prediction = c(1, 0, 1, 0))
m <- evaluate_policy(d, d$prediction, cfg)
stopifnot(m$tp == 1, m$fp == 1, m$fn == 1, m$tn == 1,
          m$precision == .5, m$recall == .5, m$false_positive_rate == .5,
          m$scenario_total_cost == 262, m$captured_fraud_value == 100,
          m$missed_fraud_value == 200, m$capacity_feasible)
zero <- evaluate_policy(d, rep(0, 4), cfg)
stopifnot(zero$precision == 0, zero$recall == 0, zero$alerts == 0)
w <- wilson(5, 10)
stopifnot(w[1] < .5, w[2] > .5, all(is.na(wilson(0, 0))))
tied <- ranking_metrics(c(1, 0, 1, 0), c(.5, .5, .2, .2))
stopifnot(abs(tied$average_precision - .5) < 1e-12, abs(tied$roc_auc - .5) < 1e-12)
perfect <- ranking_metrics(c(1, 1, 0, 0), c(.9, .8, .2, .1))
stopifnot(perfect$average_precision == 1, perfect$roc_auc == 1)
intervals <- cluster_intervals(d, replicates = 100)
stopifnot(nrow(intervals) == 4, all(intervals$lower >= 0), all(intervals$upper <= 1),
          all(intervals$lower <= intervals$upper), all(intervals$clusters == 2))
stopifnot(inherits(try(evaluate_policy(d, c(1, NA, 0, 0), cfg), silent = TRUE), "try-error"))
cat("R UNIT CHECKS PASSED: counts, costs, zero denominators, tied scores, intervals and invalid predictions\n")
