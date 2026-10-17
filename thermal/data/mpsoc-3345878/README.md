# MPSoC thermal-modeling dataset

Source: https://zenodo.org/records/3345878, version 2.0 (2019), CC BY 4.0. The authors are Federico Terraneo, Alberto Leva and William Fornaciari.

We don't commit the raw archive. Download it and check it with:

```bash
mkdir -p data/raw && cd data/raw
curl -L -o release.tar.gz "https://zenodo.org/api/records/3345878/files/release.tar.gz/content"
md5sum release.tar.gz      # on macOS: md5 release.tar.gz
# expected d399debadf28ed5ed494ea3bae887581, 37,381,859 bytes
tar -xzf release.tar.gz
```

`data/raw/` is already in the repo's `.gitignore`.

## What it contains

There are three cooling setups, each with its own directory: `chip` (bare chip), `heatsink` and `heatsink_with_fan`. Each setup has the same 13 heater layouts, so the archive holds 39 experiments in total.

| Layout | Nominal total power |
|---|---|
| one | 6 W |
| four, line_1, line_2 | 14.4 W |
| hotspot_1 to hotspot_4 | 10 W |
| thickline_1, thickline_2, checkboard | 25.6 W |
| nine | 28.4 W |
| sixteen | 48 W |

Heaters form a 4x4 grid. A heater is on at 3.0 W, or 7.0 W in the hotspot layouts. The other heaters run at 0.2 W to simulate leakage. The per-heater maps are in [`release-docs/experiments-overview.txt`](release-docs/experiments-overview.txt).

## CSV format

Files are space-separated with no header, 49 columns per row, one row per sample. The authors' plotting script, [`release-docs/plot.sce`](release-docs/plot.sce), gives the sample rate as 1 kHz and reads the columns as follows.

| Columns | Meaning |
|---|---|
| 1 to 16 | Heater voltage |
| 17 to 32 | Heater current |
| 33 to 48 | Temperature, °C |
| 49 | Flag. The release doesn't document what it means. |

Power per heater is voltage times current. In `heatsink/one.csv`, the summed power is about 2.9 W for most of the run and steps to about 5.8 W near sample 19,000. That means the measured input differs from the nominal layout and changes during a run, so a model should take measured power as its input.

## Run lengths

| Setup | Samples per run | Duration |
|---|---|---|
| chip | 19,099 to 20,000 | about 19 to 20 s |
| heatsink | 20,559 to 39,213 | about 21 to 39 s |
| heatsink_with_fan | 30,771 to 37,896 | about 31 to 38 s |

## Ambient temperature

Each setup's `tests.txt` gives room temperature per run, measured with a Rotronic CP11 sensor. Values range from 23.5°C to 27.2°C. Copies are in [`release-docs/`](release-docs/).

## Known issues fixed in version 2

The release notes say version 2 fixes three problems: rotated sensor channels in two experiments, a calibration offset of up to 1.5°C, and some runs with bad thermal contact between heaters and the heatsink, which were redone. All three affected only `heatsink_with_fan`.

## Files here

| File | What it is |
|---|---|
| `inspection.json` | Archive checksum, size and file list from our download check |
| `brief-series.json` | Downsampled traces used by the visual brief. Each point averages 200 samples per channel |
| `release-docs/` | Unmodified copies of the dataset README, the experiment overview, each setup's `tests.txt` and the chip plotting script |
