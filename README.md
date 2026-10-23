# streamflow-alteration-index

Python tools for calculating the Streamflow Alteration Index (SAI) from
Ontario Lake and River Routing Product (OLRRP) networks and alteration signal
tables. The workflow calculates `SAI_I` and `SAI_II` for subbasins and attaches
the results to river reaches through `SubId`.

SAI is a screening measure of upstream spatial exposure to mapped alteration
sources. It does not quantify the observed magnitude of streamflow change.

## Setup

Use Python 3.11. The included SE example was tested with Python 3.11.14,
GeoPandas 1.1.1, NumPy 2.3.3, pandas 2.3.3, and pyogrio 0.11.0. The tested
package versions are listed in `requirements.txt`.

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.

## Included SE example

The repository includes inputs and reference outputs for southeastern Ontario
(`SE`): 7,741 subbasins, 4,565 river features, and 334 alteration signal records.
The supplied signal CSV contains only SE records, despite its
`ontario_alteration_signals.csv` filename.

```text
streamflow-alteration-index/
|-- CITATION.cff
|-- LICENSE
|-- README.md
|-- requirements.txt
|-- data/
|   |-- OLRRPv2/SE/
|   |   |-- finalcat_info_v2-0.shp
|   |   `-- finalcat_info_riv_v2-0.shp
|   `-- ontario_alteration_signals.csv
|-- results/SE/
`-- scripts/
    |-- run_sai.py
    `-- sai_utils.py
```

Each shapefile also requires its companion files, including `.shx`, `.dbf`,
and `.prj`. The included shapefiles also have `.cpg` files.

Run the example from the repository root:

```bash
python scripts/run_sai.py --region SE
```

The scripts resolve data and output paths relative to the repository, so they
can also be launched from another working directory.

## Inputs for another region

Both subbasin and river shapefiles are required. Place them under
`data/OLRRPv2/<REGION>/` using these names:

```text
finalcat_info_<VERSION>.shp
finalcat_info_riv_<VERSION>.shp
```

The default version string is `v2-0`, matching the included files. For files
named with `v2-0-1`, pass `--olrrp-version v2-0-1`. This option selects the
filename suffix; it does not convert or update the routing data.

Supply a signal CSV in `data/` containing records for the selected region.
Use `--signals-csv-name` to select a filename other than
`ontario_alteration_signals.csv`. For example, after supplying the SW routing
inputs and a corresponding signal table:

```bash
python scripts/run_sai.py --region SW --olrrp-version v2-0-1 --signals-csv-name sw_alteration_signals.csv
```

Required attributes are:

| Input | Required attributes |
| --- | --- |
| Subbasin shapefile | `SubId`, `DowSubId`, `BasArea`, `DrainArea`, geometry, and a defined CRS |
| River shapefile | `SubId`, geometry, and a defined CRS |
| Signal CSV | `Region`, `SubId`, `Lat`, `Lon`, `Level_I`, and `Level_II` |

Subbasin IDs must be unique and the routing network must be acyclic. Areas
must use consistent units, and drainage areas must be positive. Signal IDs
must match the routing network. `Lat` and `Lon` are required CSV columns but
do not enter the SAI calculation. `Region` values are matched after trimming
whitespace and converting to uppercase. `Level_I` and `Level_II` must contain
binary flags: 0 for absent and 1 for present.

## Processing rules

- Multiple signal records in a subbasin are combined using the maximum flag
  for each level.
- `SAI_I` and `SAI_II` are calculated separately from `Level_I` and `Level_II`.
  The `Level_III` flag is not used in these calculations.
- The calculation follows the network from headwaters downstream. A flagged
  subbasin receives 100% exposure. Downstream values combine upstream SAI
  using drainage-area weights, with dilution from unflagged local area.
- River features receive the SAI values of their matching subbasins through
  `SubId`.

## Outputs

The workflow writes:

```text
results/<REGION>/<REGION>_subbasin_sai.shp
results/<REGION>/<REGION>_river_sai.shp
```

`SAI_I` and `SAI_II` are percentages from 0 to 100, allowing for small
floating-point rounding differences. The default output CRS is NAD83
geographic coordinates (`EPSG:4269`), so coordinates are in degrees.

To select another output CRS, pass `--export-crs EPSG:3161`. To preserve the
input CRS, pass `--export-crs ""`.

Rerunning a region replaces its existing output shapefiles and companion
files. Copy any outputs you need to retain before rerunning.

## Citation and data sources

### Software

Software author: Hongren Shen. Citation metadata for software version 1.0.0
is provided in `CITATION.cff`. Cite the DOI of the exact software version
used in your work:

Shen, H. (2026). *Streamflow Alteration Index (SAI) calculation tools*
(Version v1.0.0) [Computer software]. Zenodo.
[https://doi.org/10.5281/zenodo.23602080](https://doi.org/10.5281/zenodo.23602080)

### SAI paper

For the scientific method and Ontario application, please also cite:

Shen, H., Tolson, B. A., Craig, J. R., Metcalfe, R. A., Romero-Cuellar, J.,
and Luce, J. (2026). *Network-Based Subbasin-Scale Mapping of Streamflow
Alteration in Ontario, Canada*. Earth System Science Data Discussions
[preprint]. [https://doi.org/10.5194/essd-2026-286](https://doi.org/10.5194/essd-2026-286)

The revised manuscript has been accepted. The citation above identifies the
available preprint and will be updated when the final article DOI is available.

### SAI dataset

The included SE signal records and reference outputs are associated with the
SAI v1.0 dataset. If you use that dataset, please cite:

Shen, H., Tolson, B., Craig, J., Metcalfe, R. A., Romero-Cuellar, J., & Luce, J.
(2026). *Streamflow Alteration Index (SAI) v1.0 Database for Ontario, Canada*
(v1.0) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.19547932

### OLRRP routing inputs

The included SE routing layers are from OLRRP v2. If you use these inputs or
other OLRRP v2 routing layers, please also cite:

Shen, H., Han, M., Tolson, B., & Metcalfe, R. A. (2024).
*The Ontario Lake and River Routing Product Version 2 (OLRRP V2)* [Data set].
Zenodo. https://doi.org/10.5281/zenodo.14225103

The dataset DOIs identify the data products. Software version 1.0.0 is
archived separately at [https://doi.org/10.5281/zenodo.23602080](https://doi.org/10.5281/zenodo.23602080).

## License

Code is provided under the [MIT License](LICENSE). See the source dataset
records above for data documentation and reuse terms.
