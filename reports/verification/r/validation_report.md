# Independent R validation

**Run basis: INTEGRATION FIXTURE — NOT PAYSIM RESULTS **

Verified 157 numeric Python/R comparisons across seven policies and ranking metrics.
Threshold and model selection remain frozen; this script does not retune on test labels.

Uncertainty: 400 recipient clusters, 500 bootstrap replicates, seed 42.
Intervals describe sampling variation in the current period, not generalisation to a bank or future fraud types.
Type-rate Wilson intervals and the chi-square association are exploratory and assume transaction independence.
Recipient clustering does not capture all sender/network dependence. Associations do not prove root causes.

Costs and action success remain scenario assumptions in dataset currency units. No measured prevention or USD/INR conversion is claimed.
All fixture tables and plots remain labelled as integration tests, not PaySim results.

Packages used: dplyr (aggregation), ggplot2 (plots), jsonlite (manifest), base R stats (tests and intervals).
tidymodels is not used or claimed.
