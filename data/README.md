# data/

Git ignores all files in this folder except this README. Do not commit the archive or weather files.

## 1. Synthetic archive (default, no download)

`riverpulse generate --out data/synthetic_archive.csv --sites 60` writes a synthetic archive
in the Environment Agency CSV format. The demo and the tests make it in memory. Its true
effects are in `riverpulse.synthetic.TRUTH`. It is not real river data.

## 2. Water quality (real data)

| Item | Value |
|---|---|
| Source | Environment Agency, Water Quality Archive (England) |
| URL | https://environment.data.gov.uk/water-quality |
| Licence | Open Government Licence v3.0 |
| Area of the earlier study | Cambridgeshire and Bedfordshire, 2015 to 2024 |
| Files | One CSV for each year, for example `CB-2019-M.csv` |
| Columns used | `sample.samplingPoint.notation`, `sample.sampleDateTime`, `determinand.notation`, `determinand.definition`, `resultQualifier.notation`, `result`, `determinand.unit.label`, `sample.samplingPoint.easting`, `sample.samplingPoint.northing` |

The archive service changes from time to time. Download the CSV files from the current
service page, put them in `data/`, and give them to `--csv`.

| Determinand | EA code | Project name |
|---|---|---|
| pH | 0061 | `ph` |
| Temperature of water | 0076 | `temp_c` |
| Ammoniacal nitrogen as N | 0111 | `ammonia_n` |
| Nitrate as N | 0117 | `nitrate_n` |
| Orthophosphate, reactive as P | 0180 | `orthophosphate_p` |
| Oxygen, dissolved as O2 | 9924 | `do_mg` |
| Oxygen, dissolved, % saturation | 9901 | `do_sat` |
| BOD | 0085 | `bod` |

## 3. Weather

| Mode | Source | Notes |
|---|---|---|
| `--weather synthetic` | Seeded generator | Default. Use it only with the synthetic archive |
| `--weather open-meteo` | Open-Meteo historical weather API, https://open-meteo.com (CC BY 4.0 data) | One call for each 0.1-degree grid cell, cached in `data/weather_cache/` |
| `--weather stations` | Your daily CSV downloads from Open-Meteo | `--station NAME,LAT,LON,path.csv`, repeat for each station. Sites farther than `RIVERPULSE_MAX_STATION_KM` get no weather |

Columns of a station CSV: metadata lines, then `time`, `temperature_2m_mean (°C)`,
`precipitation_sum (mm)`, `relative_humidity_2m_mean (%)`.
