Across the provided papers, a wide variety of features were used to predict PM2.5 concentrations, ranging from strictly historical PM2.5 readings to complex combinations of meteorological, chemical, and spatial data. These features can be grouped into the following main categories:

**1. Historical PM2.5 Data and Trend Attributes** - Hiruni

*   **Raw Historical Data:** Many models directly utilize sequences of past hourly PM2.5 concentrations over specific time windows (e.g., the previous 12 to 72 hours) as their primary inputs.

*   **Extracted Trend Attributes:** One study relies exclusively on a univariate approach, extracting 15 distinct trend attributes from the prior 12 hours of PM2.5 recordings without using any external data. These attributes include **rolling averages** (e.g., past 3, 6, and 12 hours), **differences between specific past hours**, **rates of change**, and **seasonal components**.

*   **Spatiotemporal Peer Data:** To capture regional pollution dynamics, some models incorporate historical PM2.5 sequences from neighboring or "peer" monitoring stations. These peer stations are dynamically selected based on temporal pattern similarity using techniques like Dynamic Time Warping (DTW) rather than just geographical proximity. 

**2. Meteorological Factors** - Matt

Meteorological variables are widely integrated to provide context for how weather influences pollutant dispersion, accumulation, and atmospheric stability. Commonly used features include:

*   **Temperature:** Air temperature or dew point temperature.

*   **Wind Metrics:** Wind speed, wind direction, combined wind direction, cumulated wind speed, and vertical wind speed.
*   **Pressure:** Barometric air pressure.

*   **Moisture and Precipitation:** Relative humidity, total rainfall, precipitation, and cumulated hours of rain or snow.

*   **Solar Radiation:** Included in initial datasets to account for weather impacts.

**3. Auxiliary Air Pollutants and Chemical Compounds** - Veena

Models frequently incorporate co-pollutants that share emission sources with PM2.5 or participate in secondary aerosol formation. Features used across various studies include:

*   **Common Gases and Particulates:** Carbon Monoxide (CO), Nitrogen Dioxide (NO2), Nitrous Oxide (NO), Nitrogen Oxides (NOx), Sulfur Dioxide (SO2), Ozone (O3), Ammonia (NH3), and PM10. 

*   **Volatile Organic Compounds (VOCs):** Features such as Benzene, Toluene, Ethylbenzene, Xylene, and m,p-Xylene.

**4. Temporal and Geographic Metadata** - Veena
To account for seasonal cycles, human activity rhythms, and spatial contexts, some datasets incorporate fundamental metadata:

*   **Time Variables:** Date, day of the week, month, year, and hour of the day.

*   **Location Variables:** City name, spatial clusters, and distances between measurement sites.

**5. External and Remote Sensing Data**
A comprehensive review of deep learning architectures highlights that, to improve predictive accuracy and spatial resolution, some advanced models also assimilate:

*   **Satellite Imagery:** Satellite-derived aerosol optical depth (AOD) and other multisource remote sensing data.

*   **Anthropogenic Data:** Features representing traffic volume, industrial emissions, and large-scale human mobility datasets.

References:

Wood, D. A. (2024). Trend-attribute forecasting of hourly PM2.5 trends in fifteen cities of Central England applying optimized machine learning feature selection. Journal of Environmental Management, 356, 120561.

Patel, P., Patel, S., Shah, K., Desai, K., Patel, S., Shah, M., & Patel, S. (2025). A systematic study on PM2.5 and PM10 concentration prediction in air pollution using machine learning and deep learning model. Environmental Chemistry and Ecotoxicology, 7, 1401–1415.

Naeini, A. A., Naeini, A. A., Mohammadi, F. K., & Ghaffarpasand, O. Long-Term PM2.5 Forecasting Using a DTW-Enhanced CNN-GRU Model. (Preprint / ArXiv).

Zeng, L., Dong, R., Yuan, M., Jing, L., & Jiao, S. (2026). Evaluating deep learning time series models for PM2.5 forecasting across diverse horizons. iScience, 29, 114770.

Zhou, S., Wang, W., Zhu, L., Qiao, Q., & Kang, Y. (2024). Deep-learning architecture for PM2.5 concentration prediction: A review. Environmental Science and Ecotechnology, 21, 100400.

Zhang, Z., & Zhang, S. (2023). Modeling air quality PM2.5 forecasting using deep sparse attention-based transformer networks. International Journal of Environmental Science and Technology, 20, 13535–13550