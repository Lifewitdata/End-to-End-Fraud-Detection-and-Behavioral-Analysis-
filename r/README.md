# R statistical validation and visualisation

This layer independently checks the **frozen** Python test outputs. It uses
`dplyr`, `ggplot2`, `jsonlite`, and base R statistics. It does not train another
model or optimise a threshold on the final test labels; `tidymodels` is not used.

Install R 4.1 or newer and the three packages, then run from the project root:

```bash
Rscript -e 'install.packages(c("dplyr", "ggplot2", "jsonlite"), repos="https://cloud.r-project.org")'
python -m fraudrisk.pipeline --demo
Rscript r/test_validation.R
Rscript r/validate_fraud.R outputs
Rscript r/test_integration.R outputs
```

For a corrected PaySim run, generate that source-data evaluation first, then pass
its output directory, for example `Rscript r/validate_fraud.R outputs/paysim`.
The manifest's run basis appears in every report and plot. The Python pipeline
remains independently runnable without R; Python never downloads R packages.

## Implemented analysis

- Independently reconstruct all four rules, their union, locked-model decisions
  and the hybrid, and reconcile confusion counts, rates, value capture, workload
  and costs with Python. A mismatch produces a non-zero exit.
- Recalculate average precision, ROC-AUC and precision@100, including score ties.
- Produce 95% recipient-cluster bootstrap intervals for precision, recall,
  false-positive rate and fraud-value recall (500 replicates, seeded).
- Summarise fraud rates by type with Wilson intervals, compare fraud/legitimate
  amount distributions, and run an exploratory Monte Carlo chi-square association.
- Generate three ggplot2 figures and retain `sessionInfo()` for reproducibility.

All outputs live under `<python-output-directory>/r/`. The dashboard optionally
shows them when present. Repeat the R analysis after each new Python run;
its parity check prevents reusing predictions from a different operating point.
The R metadata records the source-data hash and an MD5 of the scored CSV. The
dashboard displays R results only when these match its current Python outputs.

The intervals are conditional on the available synthetic period. Recipient
clustering does not capture every sender/network dependency; transaction-level
Wilson intervals and the type association assume independence. None proves
causation, a control failure, real savings or real-world fraud-type safety.
