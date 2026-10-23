from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def remove_existing_shapefile(shp_path: Path) -> None:
    for ext in [".shp", ".shx", ".dbf", ".prj", ".cpg"]:
        candidate = shp_path.with_suffix(ext)
        if candidate.exists():
            candidate.unlink()


def find_upstream_subbasins(
    gdf: pd.DataFrame,
    target_subbasin_id: int,
    basin_id_col: str = "SubId",
    down_basin_id_col: str = "DowSubId",
) -> set[int]:
    upstream_subbasins: set[int] = set()
    stack = [target_subbasin_id]

    while stack:
        current_subbasin_id = stack.pop()
        upstream_subbasins.add(current_subbasin_id)

        upstream = gdf[gdf[down_basin_id_col] == current_subbasin_id][basin_id_col]
        for subbasin_id in upstream:
            if subbasin_id not in upstream_subbasins:
                stack.append(int(subbasin_id))

    return upstream_subbasins


def add_upstream_column(subbasin_df: pd.DataFrame) -> pd.DataFrame:
    upstream_dict: dict[int, list[int]] = {}

    for _, row in subbasin_df.iterrows():
        sub_id = int(row["SubId"])
        dow_sub_id = int(row["DowSubId"])
        upstream_dict.setdefault(dow_sub_id, []).append(sub_id)

    out = subbasin_df.copy()
    out["UpSubId"] = out["SubId"].map(upstream_dict)
    out["UpSubId"] = out["UpSubId"].apply(lambda value: value if isinstance(value, list) else [])
    return out


def standardize_region_column(signals_df: pd.DataFrame) -> pd.DataFrame:
    out = signals_df.copy()
    out.columns = [str(col).replace("\ufeff", "").strip() for col in out.columns]

    if "Region" not in out.columns:
        raise ValueError("Missing required column 'Region' in alteration signals CSV.")

    out["Region"] = (
        out["Region"]
        .astype(str)
        .str.replace("\ufeff", "", regex=False)
        .str.strip()
        .str.upper()
    )
    return out


def read_region_inputs(
    project_root: Path,
    region: str,
    olrrp_version: str,
    signals_csv_name: str,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, pd.DataFrame]:
    data_dir = project_root / "data"
    region_dir = data_dir / "OLRRPv2" / region

    subbasin_shp = region_dir / f"finalcat_info_{olrrp_version}.shp"
    river_shp = region_dir / f"finalcat_info_riv_{olrrp_version}.shp"
    signals_csv = data_dir / signals_csv_name

    if not subbasin_shp.exists():
        raise FileNotFoundError(f"Missing subbasin shapefile: {subbasin_shp}")
    if not river_shp.exists():
        raise FileNotFoundError(f"Missing river shapefile: {river_shp}")
    if not signals_csv.exists():
        raise FileNotFoundError(f"Missing alteration signals CSV: {signals_csv}")

    subbasin_info = gpd.read_file(subbasin_shp, encoding="utf-8", engine="pyogrio")
    river_info = gpd.read_file(river_shp, encoding="utf-8", engine="pyogrio")

    signals_df = pd.read_csv(signals_csv)
    signals_df = standardize_region_column(signals_df)

    required_cols = [
        "Region", "SubId", "Lat", "Lon", "Level_I", "Level_II",
    ]
    missing_cols = [col for col in required_cols if col not in signals_df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns in alteration signals CSV: {missing_cols}")

    signals_df["SubId"] = pd.to_numeric(signals_df["SubId"], errors="coerce")
    signals_df["Level_I"] = pd.to_numeric(signals_df["Level_I"], errors="coerce").fillna(0).astype(int)
    signals_df["Level_II"] = pd.to_numeric(signals_df["Level_II"], errors="coerce").fillna(0).astype(int)

    region_clean = region.strip().upper()
    signals_region_df = signals_df.loc[signals_df["Region"] == region_clean].copy()

    if signals_region_df.empty:
        all_regions = sorted(
            signals_df["Region"]
            .dropna()
            .astype(str)
            .str.strip()
            .str.upper()
            .unique()
            .tolist()
        )
        raise ValueError(
            f"No alteration signals found for region '{region_clean}' in {signals_csv.name}. "
            f"Available Region values are: {all_regions}"
        )

    if "Subregion" not in subbasin_info.columns:
        subbasin_info["Subregion"] = ""

    return subbasin_info, river_info, signals_region_df


def assign_signal_flags(
    subbasin_info: gpd.GeoDataFrame,
    signals_region_df: pd.DataFrame,
) -> gpd.GeoDataFrame:
    out = subbasin_info.copy()

    grouped = (
        signals_region_df.dropna(subset=["SubId"])
        .groupby("SubId", dropna=True)[["Level_I", "Level_II"]]
        .max()
        .reset_index()
    )
    grouped["SubId"] = grouped["SubId"].astype(int)

    signal_i_map = dict(zip(grouped["SubId"], grouped["Level_I"].astype(int)))
    signal_ii_map = dict(zip(grouped["SubId"], grouped["Level_II"].astype(int)))

    out["Signal_I"] = out["SubId"].map(signal_i_map).fillna(0).astype(int)
    out["Signal_II"] = out["SubId"].map(signal_ii_map).fillna(0).astype(int)
    out["SAI_I"] = np.nan
    out["SAI_II"] = np.nan

    return out


def derive_sai(
    subbasin_df: gpd.GeoDataFrame,
    signal_col: str,
    output_col: str,
) -> gpd.GeoDataFrame:
    working = add_upstream_column(subbasin_df.copy())
    result = deepcopy(working)

    pending = working.copy()
    ready = pending[
        pending["UpSubId"].apply(lambda x: isinstance(x, list) and len(x) == 0)
    ].reset_index(drop=True)

    while not pending.empty:
        if ready.empty:
            raise RuntimeError(
                f"No headwater subbasins found during propagation for {output_col}. "
                "The network may contain a cycle or invalid topology."
            )

        for _, row in ready.iterrows():
            subid = int(row["SubId"])
            idx = result.index[result["SubId"] == subid][0]

            upstream_ids = result.at[idx, "UpSubId"]
            local_signal = float(result.at[idx, signal_col])
            bas_area = float(result.at[idx, "BasArea"])
            drain_area = float(result.at[idx, "DrainArea"])

            if len(upstream_ids) == 0:
                sai_value = local_signal * 100.0

            else:
                upstream_info = result[result["SubId"].isin(upstream_ids)].copy()

                upstream_weighted = (
                    upstream_info["DrainArea"].astype(float) *
                    upstream_info[output_col].astype(float)
                ).sum()

                upstream_area = upstream_info["DrainArea"].astype(float).sum()

                if drain_area <= 0:
                    raise ValueError(f"DrainArea must be positive for SubId {subid}.")

                sai_value = (
                    upstream_weighted + bas_area * local_signal * 100.0
                ) / drain_area

                if local_signal > 0:
                    sai_value = max(sai_value, 100.0)

            result.at[idx, output_col] = float(sai_value)

        pending = pending[~pending["SubId"].isin(ready["SubId"])].reset_index(drop=True)
        pending = add_upstream_column(pending)
        ready = pending[
            pending["UpSubId"].apply(lambda x: isinstance(x, list) and len(x) == 0)
        ].reset_index(drop=True)

    return result


def attach_sai_to_rivers(
    river_info: gpd.GeoDataFrame,
    subbasin_info: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    join_cols = ["SubId", "SAI_I", "SAI_II"]
    river_out = river_info.merge(
        subbasin_info[join_cols],
        on="SubId",
        how="left",
    )
    return river_out


def select_subbasin_output_columns(subbasin_info: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    candidate_cols = [
        "geometry",
        "Region",
        "Subregion",
        "SubId",
        "DowSubId",
        "BasArea",
        "DrainArea",
        "SAI_I",
        "SAI_II",
    ]
    keep_cols = [col for col in candidate_cols if col in subbasin_info.columns]
    return subbasin_info[keep_cols].copy()


def select_river_output_columns(river_info: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    candidate_cols = [
        "geometry",
        "Region",
        "Subregion",
        "SubId",
        "DowSubId",
        "SAI_I",
        "SAI_II",
    ]
    keep_cols = [col for col in candidate_cols if col in river_info.columns]
    return river_info[keep_cols].copy()


def write_outputs(
    subbasin_out: gpd.GeoDataFrame,
    river_out: gpd.GeoDataFrame,
    results_dir: Path,
    region: str,
    export_crs: str,
) -> None:
    output_region_dir = results_dir / region
    ensure_dir(output_region_dir)

    if export_crs:
        subbasin_out = subbasin_out.to_crs(export_crs)
        river_out = river_out.to_crs(export_crs)

    subbasin_shp = output_region_dir / f"{region}_subbasin_sai.shp"
    river_shp = output_region_dir / f"{region}_river_sai.shp"

    remove_existing_shapefile(subbasin_shp)
    remove_existing_shapefile(river_shp)

    subbasin_out.to_file(subbasin_shp, driver="ESRI Shapefile", encoding="utf-8", engine="pyogrio")
    river_out.to_file(river_shp, driver="ESRI Shapefile", encoding="utf-8", engine="pyogrio")

    print(f"Saved: {subbasin_shp}")
    print(f"Saved: {river_shp}")


def run_sai_for_region(
    project_root: Path,
    region: str,
    olrrp_version: str = "v2-0",
    export_crs: str = "EPSG:4269",
    signals_csv_name: str = "ontario_alteration_signals.csv",
) -> None:
    results_dir = project_root / "results"
    ensure_dir(results_dir)

    print(f"=== Calculating SAI for region {region} ===")

    subbasin_info, river_info, signals_region_df = read_region_inputs(
        project_root=project_root,
        region=region,
        olrrp_version=olrrp_version,
        signals_csv_name=signals_csv_name,
    )

    subbasin_info = assign_signal_flags(subbasin_info, signals_region_df)
    subbasin_info = derive_sai(subbasin_info, signal_col="Signal_I", output_col="SAI_I")
    subbasin_info = derive_sai(subbasin_info, signal_col="Signal_II", output_col="SAI_II")

    subbasin_out = select_subbasin_output_columns(subbasin_info)
    river_out = attach_sai_to_rivers(river_info, subbasin_info)
    river_out = select_river_output_columns(river_out)

    write_outputs(
        subbasin_out=subbasin_out,
        river_out=river_out,
        results_dir=results_dir,
        region=region,
        export_crs=export_crs,
    )

    print("Done.")
