# London Marylebone PM2.5 forecast (reproducible)

Single-site study used in `results.md`: London Marylebone Road, daily resolution, 1,364 days (7 April 2022–30 December 2025). Train is 1,000 days through 31 December 2024; test is 364 days in 2025.

The frozen modelling tables in `london_final_dataset/` are what the report numbers come from. Re-running earlier notebooks can rebuild them, but small differences in meteorological aggregation will not bit-match those CSVs.

## Run order

1. **Target cleaning** — `targ_data_cleaning_london_only.ipynb`  
   Reads `data/AirQualityDataDaily2016_2020.csv` and `data/AirQualityDataDaily2021_2025.csv` (DEFRA, all stations in the extract). Keeps Marylebone only. Writes `features/feature_data/cleaned_london_marylebone_pm25.csv`.

2. **Historical / calendar features** — `features/Features.ipynb`  
   Reads `features/data/PM2.5_AirQualityDataDaily_2021-2025.csv`.  
   The merged table used downstream is already saved as `features/pm25_all_features_merged.csv`. Auxiliary pollutant columns in that file are dropped later and are not model inputs.

3. **Meteorology** — `features/Meterological_features.ipynb`  
   Reads hourly / daily extracts in `features/feature_data/`. Writes `features/meteorological/`.  
   The committed daily tables in that folder are the ones merged into the modelling dataset.

4. **Combine and split** — `features/combined_dataset.ipynb`  
   Merges PM2.5 features + meteorology, aligns to the cleaned target, drops unused columns, writes `london_final_dataset/marylebone_{train,test,all}.csv`.

5. **Models** (from `model_training/`, all read `../london_final_dataset`)  
   - Trees: `Random_Forest_multistep.ipynb`, `XG Boost-2_multistep.ipynb`  

   - Sequence models: `cnn_lstm.ipynb`, `transformer.ipynb`, `gru_lstm_multi_horizon_.ipynb`  
   - Baseline: `climatology_baseline.ipynb`  
   Persistence is scored in the comparison notebook from the tree prediction files.

6. **Report table and figures**  
   `pooled_path_comparison.ipynb` writes `pooled_path_comparison.csv` (the table in `results.md`).  
   `pooled_path_comparison_plots.ipynb` draws Figure 1 (R²), feature-importance ranks, and the RMSE/MAE ratio plot.

Saved CNN-LSTM / transformer weights are in `saved_cnn_lstm/` and `saved_patchtst/`. Metric CSVs used by the comparison notebook are next to it (`cnn_lstm_results/`, `transformer_results/`, `rf_results_path/`, `xgb_results_path/`, `true_multi_horizon_results/`).
