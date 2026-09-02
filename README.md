# London Marylebone PM2.5 forecast (reproducible)

Single-site study used in `results.md`: London Marylebone Road, daily resolution, 1,364 days (7 April 2022–30 December 2025). Train is 1,000 days through 31 December 2024; test is 364 days in 2025.

The frozen modelling tables in `data/modelling/` are what the report numbers come from. Re-running earlier notebooks can rebuild them, but small differences in meteorological aggregation will not bit-match those CSVs.

## Layout

```
data/
  raw/air_quality/       # DEFRA UK-AIR extracts
  raw/meteorology/       # HadUK temperature + MIDAS hourly
  processed/             # cleaned target, feature tables, daily meteorology
  modelling/             # marylebone_{train,test,all}.csv
notebooks/
  cleaning/              # target cleaning
  features/              # Features, meteorology, combine+split
  models/                # training, comparison, saved weights, metric CSVs
```

## Run order

1. **Target cleaning** — `notebooks/cleaning/targ_data_cleaning_london_only.ipynb`  
   Reads yearly/combined extracts under `data/raw/air_quality/`. Keeps Marylebone only.  
   Writes `data/processed/cleaned_london_marylebone_pm25.csv`.

2. **Historical / calendar features** — `notebooks/features/Features.ipynb`  
   Reads `data/raw/air_quality/PM2.5_AirQualityDataDaily_2021-2025.csv`.  
   The merged table used downstream is `data/processed/pm25_all_features_merged.csv`. Auxiliary pollutant columns in that file are dropped later and are not model inputs.

3. **Meteorology** — `notebooks/features/Meterological_features.ipynb`  
   Reads hourly / daily extracts in `data/raw/meteorology/` and the cleaned PM2.5 calendar.  
   Writes `data/processed/meteorological/`.

4. **Combine and split** — `notebooks/features/combined_dataset.ipynb`  
   Merges PM2.5 features + meteorology, aligns to the cleaned target, drops unused columns,  
   writes `data/modelling/marylebone_{train,test,all}.csv`.

5. **Models** (from `notebooks/models/`, all read `../../data/modelling`)  
   - Trees: `Random_Forest_multistep.ipynb`, `XG Boost-2_multistep.ipynb`  
   - Sequence models: `cnn_lstm.ipynb`, `transformer.ipynb`, `gru_lstm_multi_horizon_.ipynb`  
   - Baseline: `climatology_baseline.ipynb`  
   Persistence is scored in the comparison notebook from the tree prediction files.

6. **Report table and figures**  
   `pooled_path_comparison.ipynb` writes `pooled_path_comparison.csv` (the table in `results.md`).  
   `pooled_path_comparison_plots.ipynb` draws Figure 1 (R²), feature-importance ranks, and the RMSE/MAE ratio plot.

Saved CNN-LSTM / transformer weights are in `saved_cnn_lstm/` and `saved_patchtst/`. Metric CSVs used by the comparison notebook are next to it (`cnn_lstm_results/`, `transformer_results/`, `rf_results_path/`, `xgb_results_path/`, `true_multi_horizon_results/`).
