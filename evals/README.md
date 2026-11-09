# Evals

Everything needed to score this project lives here, so anyone can rerun it:

```
evals/
├── data/          # eval set files (only ones whose license allows sharing)
├── test_*.py      # pytest files marked `eval`: run with `make eval`
└── report.md      # latest results, written from the eval report template
```

Rules:

1. Fix the eval set before you tune anything, and never tune on it.
2. Record where every item came from, how it was labelled, and its license.
   Some benchmarks (for example FinanceBench) are non-commercial: link to
   them and keep their files out of git.
3. Report every metric with its sample size and a 95% bootstrap interval.
4. A metric that falls below its threshold fails the build.
