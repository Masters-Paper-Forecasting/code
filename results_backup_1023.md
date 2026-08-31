# Experimental Results:

5.1 Setup and Evaluation Protocol

The dataset was assembled from various publicly available sources (DEFRA, no date, Department for Environment, Food and Rural Affairs, 2026, Met Office, 2025a, 2025b, 2026a, 2026b, Met Office et al. 2026b). London Marylebone Road with meteorological data drawn from nearby stations was used as the primary study region for our analysis due to its reliable and comprehensive air quality data. Pooled-path evaluation was conducted on differing long horizons to assess model performance across the full range of the horizons, alongside a single lead day evaluation. Creating a dataset with 1,364 days of observations, we used a daily temporal resolution for our analysis to avoid noise from short-term fluctuations. A series of metrics were utilized to evaluate model performance (MAE, MSE, RMSE,  R², MAPE, MBE) to ensure a comprehensive comparison of model accuracy and reliability. Furthermore, persistence and climatology baselines were used to benchmark the performance of the six models in comparison to a continuation of the origin observation and seasonal averages (EPA, 2003). Mean Bias Error (MBE) was included on public health grounds to quantify systematic over  or under prediction by the models, the more dangerous bias being under-prediction of PM2.5 concentrations.

5.2 Model Comparison

**Table**

The above table shows a distinct performance difference among the models across various evaluation horizons and metrics. Peristance has the lowest 1 day MAE (3.124) and MAPE (37.6%). Across the 7, 14 and 30 day horizions the CNN-LSTM consistently outperforms the persistence baseline and other models on the MAE metric (3.827, 3.912 and 4.160 µg/m³). The MAPE is lowest for the CNN-LSTM at 7 days, at 14 days the GRU was best (42.2%), and the LSTM at 30 days (47.4%). Random Forest achieves the highest R² values across all horizons including 1 day (0.494, 0.243, 0.179, 0.093). Furthermore, it performed best on the RMSE metric at 7 and 14 days, while CNN-LSTM performed best at 1 day and the transformer model performed best at 30 days. The differences in these metrics can be explained by the typical-day versus extreme-day trade-off (Lee et al., 2024; Wood, 2024), the CNN-LSTM under predicts at 7 and 14 days (MBE −1.063 and −1.068 µg/m³), which decreases the MAE as most of our samples sit in a moderate concentration range, however, this comes at the cost of underestimating higher concentration events, creating a higher RMSE in comparison to the Random Forest model which better captures the tail of the distribution. From 7 days onward every model beats persistence on MAE by 6.6–26.7%.

5.3 Skill against the baseline

**Figure 1** + **Feature importance plots**

Figure 1 shows R² at 7, 14 and 30 days. Persistence R² is negative throughout, worsening from −0.23 at 7 days to −0.45 at 30 days, which means it performs worse than a simple mean prediction. MAE improvement over that baseline is therefore a weak claim of skill. The day-of-year climatology is a second reference, the training mean PM₂.₅ for each calendar day, and it is slightly negative at every pooled horizon, so even a seasonal mean does not beat the test-year average. The machine-learning models beat that climatology at 7 days and then close on it. By 30 days CNN-LSTM, GRU and LSTM have negative R² and sit on the climatology line, while Random Forest, XGBoost and the transformer remain above it. The best R² is still only 0.093 (Random Forest), a 9% reduction in mean squared error relative to predicting the mean of the observations. A further observation is the shift in feature importance (Zeng et al., 2026) over time across models, with recent PM₂.₅ and wind at 1 day, temperature and calendar by 7 days, calendar and humidity together at 14 days, and calendar by 30 days, with humidity remaining in the ranking. Within Random Forest the leading permutation score collapses from 0.824 to 0.067.

5.4 Accuracy is not the same as reliability

**RMSE/MAE Ratio plot**

The RMSE/MAE ratio sits well above the Gaussian reference of 1.25 at every pooled horizon, so large errors weigh more on RMSE than they would under Gaussian noise. Random Forest is the flattest series across 7, 14 and 30 days, and the lowest among models that remain competitive on MAE. Transformer is lower at 7 and 30 days, but its 7-day MAE is the worst of the six ML models (4.563), so the low ratio reflects uniformly poor accuracy rather than reliability. At 14 days the typical-day versus extreme-day split is clear, models with |MBE| above 1 (CNN-LSTM, LSTM, GRU) have higher ratios than those with |MBE| below 0.6 (Random Forest, XGBoost, Transformer). That split is present throughout for LSTM while CNN-LSTM demonstrates the link. When the magnitude of its MBE shrinks to 0.168 at 30 days, the ratio falls with it.

Bias = under or over prediction of PM2.5 (MBE)
tail = large errors, the RMSE/MAE ratio measures the scale of this (how much of the total error comes from those large errors)


# Discussion:

6.1 No single best model — interprets 5.2 + 5.4

No single model performs best across all horizons and metrics. Rankings change depending on the metric (Section 5.2) because of the typical-day versus extreme-day trade-off. Shrinking predictions low (MBE) wins the MAE on most days but damages performance on extreme events by concentrating errors in the tail of the distribution (RMSE/MAE ratio). Selecting soley on MAE therefore risks the under-prediction of PM2.5, which section 5.1 used MBE to flag. Random forest never leads on MAE but its among the least biased at every horizon, has the flattest RMSE/MAE ratio, and the highest R² values, making it the most balanced model overall.

6.2 Where skill exists and where it doesn't — interprets 5.3

Skill is concentrated at short range and largely gone by a month (Sun et al., 2021; Zeng et al., 2026) (Section 5.3). At 1-day lead, Random Forest reaches R² 0.494 and even persistence has R² 0.374. On the pooled path that skill then falls: the best R² is 0.243 at 7 days, 0.179 at 14 days, and 0.093 at 30 days, where three of the six models sit below a constant mean. Permutation importance matches that decay independently, at 1 day the leading inputs are recent PM2.5 (pm25_rollmean3) and wind, whereas by 30 days calendar leads, recent PM2.5 has left the ranking, and humidity is what remains. The limited long-horizon R² in Section 5.2 is therefore not only a scoring result, the models have shifted from tracking the last few days to a calendar driven estimate.

6.3 What the forecast actually delivers — interprets 5.3 + the proposal
The forecasts support a graded set of uses, not one claim of skill. At 1 day there is real skill (Section 6.2), enough for daily alerts. Through 7 days and into 14 days the better models still beat a constant mean, enough for week-ahead advisory planning, not a precise daily peak (Section 6.1). By 30 days typical-day error has moved toward the day-of-year climatology alongside a seasonal feature importance shift, with recurrent models collapsing onto the climatology reference and non-recurrent models keeping a small but measurable advantage. That is the proposal’s long-range product, broader trend rather than short-term fluctuation, and the recurrent models do converge to it. What it did not anticipate is how little that trend is worth here, even the day-of-year climatology has negative R², so a seasonal product cannot carry the daily public-health decisions the proposal invoked. Even Random Forest, among the least biased models on MBE, still under-predicts PM₂.₅ on the 7 to 30-day paths, which on public-health grounds (Section 5.1) limits how far those applications can be pushed.

6.4 Limitations

This analysis was limited to one urban site, London Marylebone Road with Meteorology data from nearby Met Office stations. Marylebone was used because it was the most complete station in the extract, after a nationwide sample was dropped due to incompleteness that was too severe for safe imputation. Training is only about 2.7 years for the same reason, Marylebone before 6 April 2022 failing the completeness cut. Test set is one year, so one cycle of weather.

7.1 Conclusion

No single model consistently won across all horizons and metrics. CNN-LSTM has the lowest MAE at 7, 14 and 30 days, so it is the better typical-day forecast, but we infer that this comes with under-prediction of higher concentrations. Although Random Forest never leads on MAE, it has the highest R² values, across all horizons, and the lowest RMSE at 7 and 14 days. For an application where accurate prediction of extreme events is critical, that trade-off makes Random Forest the preferable choice despite not having the lowest MAE. There is skill at short horizons, at a 1-day lead Random Forest reaches R² 0.494, and even persistence has 0.374. On the pooled path the best R² falls to 0.243 at 7 days, 0.179 at 14 days, and 0.093 at 30 days, where CNN-LSTM, GRU and LSTM sit below a constant mean, highlighting the rapid decay of forecast skill with increasing horizon length. Feature importance analysis further supports this, showing that the models rely on recent PM2.5 and meteorological variables at short horizons, but shift to calendar-based features at longer horizons, reflecting the diminishing predictive power of recent observations. Beating our two baselines, persistence and day-of-year climatology, is only a moderate achievement, as both score below the constant mean. This forecast is usable for advisory planning over one to two weeks, not for precise day-by-day forecasts at those horizons, and not at all at a month.

7.2 Future work:

Further research could explore, utilizing longer historical data, this would allow us to build a climatology baseline that esmimated from more than 2 or 3 samples per calendar day, a full decade would allow us to see if the 30 day forecast is limited by the dataset or by the inherent predictability of PM2.5 concentrations. Our single-site analysis used only the London Marylebone Road site, which is an urban, traffic dominated, high-pollution location, so its unclear whether the findings generalize to other urban areas or to rural locations (Wood, 2024). Data availability, not the methodology, was the block for that comparison.



DEFRA (no date) Data archive. Available from: https://uk-air.defra.gov.uk/data/ [Accessed 27 August 2026].

Department for Environment, Food and Rural Affairs (2026) London Marylebone Road air quality measurements (PM2.5, PM10, nitric oxide, nitrogen dioxide, nitrogen oxides as nitrogen dioxide, ozone and carbon monoxide), UK-AIR Data Archive [online]. Available from: https://uk-air.defra.gov.uk/data/ [Accessed 13 July 2026].

Met Office (2025a) MIDAS Open: UK hourly weather observation data, NERC EDS Centre for Environmental Data Analysis (v202507) [online]. Available from: https://dx.doi.org/10.5285/99173f6a802147aeba430d96d2bb3099 [Accessed 27 August 2026].

Met Office (2025b) MIDAS Open: UK hourly rainfall data, NERC EDS Centre for Environmental Data Analysis (v202507) [online]. Available from: https://dx.doi.org/10.5285/c75ca7291a5048739010380dce6ebc99 [Accessed 27 August 2026].

Met Office (2026a) MIDAS Open: UK mean wind data, NERC EDS Centre for Environmental Data Analysis (v202607) [online]. Available from: https://dx.doi.org/10.5285/c7393fdc2c974071a2efd7f8601b1bab [Accessed 27 August 2026].

Met Office, Hollis, D., Carlisle, E., Kendon, M., Packman, S. and Doherty, A. (2026b) HadUK-Grid Climate Observations by Administrative Regions over the UK, NERC EDS Centre for Environmental Data Analysis (v1.3.2.ceda) [online]. Available from: https://dx.doi.org/10.5285/386b3c1ee2054ef5ae0d73060963a9f1 [Accessed 27 August 2026].

Zeng, L., Dong, R., Yuan, M., Jing, L. and Jiao, S. (2026) Evaluating deep learning time series models for PM2.5 forecasting across diverse horizons. iScience [online]. 29 (2), article no. 114770. Available from: https://doi.org/10.1016/j.isci.2026.114770 [Accessed 31 August 2026].

Lee, Y., Chien, F., Chien, H., Lin, Y. and Sun, M. (2024) Enhancing real-time PM2.5 forecasts: A hybrid approach of WRF-CMAQ model and CNN algorithm. Atmospheric Environment [online]. 338, article no. 120835. Available from: https://doi.org/10.1016/j.atmosenv.2024.120835 [Accessed 31 August 2026].

Wood, D.A. (2024) Trend-attribute forecasting of hourly PM2.5 trends in fifteen cities of Central England applying optimized machine learning feature selection. Journal of Environmental Management [online]. 356, article no. 120561. Available from: https://doi.org/10.1016/j.jenvman.2024.120561 [Accessed 31 August 2026].

Sun, H., Fung, J.C.H., Chen, Y., Chen, W., Li, Z., Huang, Y., Lin, C., Hu, M. and Lu, X. (2021) Improvement of PM2.5 and O3 forecasting by integration of 3D numerical simulation with deep learning techniques. Sustainable Cities and Society [online]. 75, article no. 103372. Available from: https://doi.org/10.1016/j.scs.2021.103372 [Accessed 31 August 2026].

EPA (2003) Guidelines for developing an air quality (ozone and PM2.5) forecasting program. EPA-456/R-03-002. Environmental Protection Agency, Office of Air Quality Planning and Standards. Available from: https://www.airnow.gov/sites/default/files/2020-06/aq-forecasting-guidance-1016.pdf