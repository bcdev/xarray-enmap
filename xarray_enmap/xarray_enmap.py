# Copyright (c) 2025-2026 by Brockmann Consult GmbH
# Permissions are hereby granted under the terms of the MIT License:
# https://opensource.org/licenses/MIT.

import re
from collections.abc import Iterable
import logging
import os
import pathlib

import numpy as np
import rioxarray
import shutil
import tarfile
import tempfile
from typing import Any, Mapping
import xml.etree
import zipfile

import shapely
import xarray
import xarray as xr
from xarray import DataTree, Dataset
from xarray.backends import AbstractDataStore

LOGGER = logging.getLogger(__name__)

VAR_MAP = dict(
    reflectance="SPECTRAL_IMAGE",
    mask="QL_PIXELMASK",
    cirrus="QL_QUALITY_CIRRUS",
    classes="QL_QUALITY_CLASSES",
    cloudshadow="QL_QUALITY_CLOUDSHADOW",
    cloud="QL_QUALITY_CLOUD",
    haze="QL_QUALITY_HAZE",
    snow="QL_QUALITY_SNOW",
    testflags="QL_QUALITY_TESTFLAGS",
    swirquicklook="QL_SWIR",
    vnirquicklook="QL_VNIR",
)

QUICKLOOK_VAR_NAMES = ["swirquicklook", "vnirquicklook"]


class EnmapEntrypoint(xr.backends.BackendEntrypoint):

    supports_groups = True
    temp_dir = None

    def open_dataset(
        self,
        filename_or_obj: str | os.PathLike[Any],
        *,
        drop_variables: str | Iterable[str] | None = None,
        scale_reflectance: bool = True,
    ) -> xr.Dataset:
        self.temp_dir = tempfile.mkdtemp(prefix="xarray-enmap-")
        path = pathlib.Path(filename_or_obj)
        if path.is_file():
            ds = read_dataset_from_archive(
                filename_or_obj, self.temp_dir, scale_reflectance
            )
        elif path.is_dir():
            ds = read_dataset_from_unknown_directory(
                path, self.temp_dir, scale_reflectance
            )
        elif filename_or_obj.startswith("s3://"):
            ds = read_dataset_from_inner_directory(
                filename_or_obj, scale_reflectance
            )
        else:
            raise ValueError(
                f"{filename_or_obj} is neither a path nor a directory."
            )
        ds.set_close(self.close)
        return ds

    def open_datatree(
        self,
        filename_or_obj: str | os.PathLike[Any],
        *,
        drop_variables: str | Iterable[str] | None = None,
    ) -> DataTree:
        groups = self.open_groups_as_dict(
            filename_or_obj, drop_variables=drop_variables
        )
        dt = xarray.DataTree.from_dict(data=groups)
        return dt

    def open_groups_as_dict(
        self,
        filename_or_obj: str | os.PathLike[Any],
        *,
        drop_variables: str | Iterable[str] | None = None,
    ) -> dict[str, Dataset]:
        self.temp_dir = tempfile.mkdtemp(prefix="xarray-enmap-")
        path = pathlib.Path(filename_or_obj)
        if path.is_file():
            groups = read_groups_from_archive(filename_or_obj, self.temp_dir)
        elif path.is_dir():
            groups = read_groups_from_unknown_directory(path, self.temp_dir)
        else:
            raise ValueError(
                f"{filename_or_obj} is neither a path nor a directory."
            )
        return groups

    def close(self):
        if self.temp_dir:
            shutil.rmtree(self.temp_dir)


def read_dataset_from_archive(
    input_filename: str | os.PathLike[Any],
    temp_dir: str,
    scale_reflectance: bool = True,
) -> xr.Dataset:
    data_dirs = list(extract_archives(input_filename, temp_dir))
    if len(data_dirs) > 1:
        LOGGER.warning("Multiple data archives found; reading the first.")
    return read_dataset_from_inner_directory(data_dirs[0], scale_reflectance)


def read_dataset_from_unknown_directory(
    data_dir: str | os.PathLike[Any],
    temp_dir: str,
    scale_reflectance: bool = True,
) -> xr.Dataset:
    data_path = pathlib.Path(data_dir)
    metadata_files = list(data_path.glob("*METADATA.XML"))
    match len(metadata_files):
        case 0:
            # assume outer directory
            return read_dataset_from_archive(
                data_path, temp_dir, scale_reflectance
            )
        case 1:
            # assume inner directory
            return read_dataset_from_inner_directory(
                data_path, scale_reflectance
            )
        case _:
            raise RuntimeError("Too many METADATA.XML files")


def read_dataset_from_inner_directory(
    data_dir: str | os.PathLike[Any], scale_reflectance: bool = True
) -> xr.Dataset:
    data_path = pathlib.Path(data_dir)
    LOGGER.info(f"Opening {data_path}")
    arrays = {
        name: rioxarray.open_rasterio(filename).squeeze()
        for name, filename in find_datafiles(data_path).items()
    }
    for quicklook_name in QUICKLOOK_VAR_NAMES:
        if quicklook_name in arrays.keys():
            ql = arrays.get(quicklook_name)
            arrays[quicklook_name] = ql.rename({"band": "quicklookband"})
    if "reflectance" in arrays.keys() and scale_reflectance:
        reflectance = arrays.get("reflectance")
        fill_value = reflectance.attrs.get("_FillValue", -32768)
        reflectance = reflectance.astype(dtype=np.float32)
        reflectance = xr.where(
            np.abs(reflectance - fill_value) > 1e-8, reflectance, np.nan
        )
        arrays["reflectance"] = reflectance / 10000
    ds = xr.Dataset(arrays)
    add_metadata(ds, data_path)
    ds = set_wavelengths_as_dimensions(ds, data_path)
    return ds


def read_groups_from_archive(
    input_filename: str | os.PathLike[Any], temp_dir: str
) -> dict[str, Dataset]:
    data_dirs = list(extract_archives(input_filename, temp_dir))
    groups = {}
    for data_dir in data_dirs:
        group_name = data_dir if isinstance(data_dir, str) else data_dir.name
        groups[group_name] = read_dataset_from_inner_directory(data_dir)
    return groups


def read_groups_from_unknown_directory(
    data_dir: str | os.PathLike[Any], temp_dir: str
) -> dict[str, Dataset]:
    data_path = pathlib.Path(data_dir)
    metadata_files = list(data_path.glob("*METADATA.XML"))
    match len(metadata_files):
        case 0:
            # assume outer directory
            return read_groups_from_archive(data_path, temp_dir)
        case 1:
            # assume inner directory
            return dict(data_path=read_dataset_from_inner_directory(data_path))
        case _:
            raise RuntimeError("Too many METADATA.XML files")


def find_datafiles(data_path: pathlib.Path) -> Mapping[str, pathlib.Path]:
    assert data_path.is_dir()
    tiffs = list(data_path.glob("*.TIF"))
    result = {}
    for name, basename in VAR_MAP.items():
        pattern = f"(ENMAP.*)?{basename}.TIF"
        matches = [tiff for tiff in tiffs if re.match(pattern, tiff.name)]
        assert len(matches) > 0, f"Can't find TIFF for {name}"
        assert len(matches) < 2, f"Too many TIFFs for {name}"
        result[name] = matches[0]
    return result


def set_wavelengths_as_dimensions(
    ds: xr.Dataset, data_dir: pathlib.Path
) -> xr.Dataset:
    root = _open_metadata_root(data_dir)
    bandids = root.findall("specific/bandCharacterisation/bandID")
    if len(bandids) != len(ds.band):
        LOGGER.info(
            "Cannot retrieve wavelengths for all bands: omitting 'wavelength' co-ordinate."
        )
        return ds
    wavelengths = [
        float(b.find("wavelengthCenterOfBand").text) for b in bandids
    ]
    ds = ds.assign_coords(wavelength=("band", wavelengths)).set_xindex(
        "wavelength"
    )
    return ds


def add_metadata(ds: xr.Dataset, data_dir: pathlib.Path):
    root = _open_metadata_root(data_dir)
    points = root.findall("base/spatialCoverage/boundingPolygon/point")
    bounds = shapely.Polygon(
        [float(p.find("longitude").text), p.find("latitude").text]
        for p in points
        if p.find("frame").text != "center"
    )
    bbox = bounds.bounds

    def text(xpath):
        return root.find(xpath).text

    global_attrs = {
        "id": text("product/image/merge/name").removesuffix(
            "-SPECTRAL_IMAGE.TIF"
        ),
        "title": text("metadata/comment"),
        "summary": text("metadata/citation"),
        "keywords": "EnMAP,hyperspectral,remote sensing",
        "Conventions": "ACDD-1.3,CF-1.8",
        "naming_authority": "de.dlr",
        "processing_level": "2A",
        "geospatial_bounds": shapely.to_wkt(bounds),
        "geospatial_bounds_crs": "EPSG:4326",
        "geospatial_lat_min": bbox[1],
        "geospatial_lat_max": bbox[3],
        "geospatial_lon_min": bbox[0],
        "geospatial_lon_max": bbox[2],
        "time_coverage_start": text("base/temporalCoverage/startTime"),
        "time_coverage_end": text("base/temporalCoverage/stopTime"),
    }
    ds.attrs.update(global_attrs)

    var_attrs: dict[str, tuple] = {
        "reflectance": (
            "reflectance",
            "surface_bidirectional_reflectance",
            1,
            "physicalMeasurement",
        ),
        "cirrus": (
            "cirrus mask",
            "cirrus",
            1,
            "qualityInformation",
        ),
        "classes": (
            "area type",
            "area_type",
            1,
            "qualityInformation",
            {
                "flag_values": [1, 2, 3],
                "flag_meanings": ["Land", "Water", "Background"],
            },
        ),
        "cloud": ("cloud mask", "cloud_binary_mask", 1, "qualityInformation"),
        "cloudshadow": (
            "cloud shadow",
            "cloud_shadow",
            1,
            "qualityInformation",
        ),
        "haze": ("haze mask", "haze", 1, "qualityInformation"),
        "mask": ("pixel mask", "mask", 1, "qualityInformation"),
        "snow": (
            "snow mask",
            "surface_snow_binary_mask",
            1,
            "qualityInformation",
        ),
        "testflags": ("test flags", "test_flags", 1, "qualityInformation"),
    }

    for var, values in var_attrs.items():
        attrs = {
            "long_name": values[0],
            "standard_name": values[1],
            "units": values[2],
            "coverage_content_type": values[3],
        }
        if len(values) > 4:
            attrs.update(values[4])
        ds[var].attrs.update(attrs)


def _open_metadata_root(
    data_dir: pathlib.Path,
) -> xml.etree.ElementTree.Element:
    metadata_paths = list(data_dir.glob("*METADATA.XML"))
    assert len(metadata_paths) == 1
    metadata_path = metadata_paths[0]
    if str(data_dir).startswith("s3://"):
        import fsspec

        fs = fsspec.filesystem("s3")
        with fs.open(metadata_path) as fh:
            root = xml.etree.ElementTree.parse(fh).getroot()
    else:
        root = xml.etree.ElementTree.parse(metadata_path).getroot()
    return root


def extract_archives(
    archive_path: os.PathLike | str, dest_dir: os.PathLike | str
) -> Iterable[pathlib.Path]:
    dest_path = pathlib.Path(dest_dir)
    inner_path = dest_path / "inner-archive"
    final_path = dest_path / "data"
    os.mkdir(final_path)
    archive_path = pathlib.Path(archive_path)
    if archive_path.name.endswith(".tar.gz") or archive_path.is_dir():
        if archive_path.is_dir():
            outer_path = archive_path
        else:
            # An EnMAP tgz usually contains one or more zip archives containing
            # the actual data files.
            outer_path = dest_path / "outer-archive"
            LOGGER.info(f"Extracting {archive_path.name}")
            with tarfile.open(archive_path) as tgz_file:
                tgz_file.extractall(path=outer_path, filter="data")
        data_paths = []
        for index, path_to_zip_file in enumerate(find_zips(outer_path)):
            data_paths.append(
                extract_zip(final_path, index, inner_path, path_to_zip_file)
            )
        return data_paths
    else:
        # Assume it's a zip and skip the outer archive extraction step.
        LOGGER.info(f"Assuming {archive_path} is an inner zipfile")
        return [extract_zip(final_path, 0, inner_path, archive_path)]


def find_zips(root: os.PathLike):
    root_path = pathlib.Path(root)
    for parent, dirs, files in root_path.walk(on_error=print):
        for filename in files:
            if filename.endswith(".ZIP"):
                yield pathlib.Path(parent, filename)


def extract_zip(
    final_path: pathlib.Path,
    index: int,
    inner_path: pathlib.Path,
    path_to_zip_file: pathlib.Path,
) -> pathlib.Path:
    LOGGER.info(f"Extracting {path_to_zip_file.name}")
    extract_path = inner_path / str(index)
    with zipfile.ZipFile(path_to_zip_file, "r") as zip_ref:
        zip_ref.extractall(extract_path)
    input_data_path = list(extract_path.iterdir())[0]
    input_data_dir = input_data_path.name
    output_data_path = final_path / input_data_dir
    prefix_length = len(input_data_path.name) + 1
    os.mkdir(output_data_path)
    # Strip the long, redundant prefix from the filenames. Not visible anyway
    # via the xarray plugin, but convenient if using this function as a
    # standalone archive extractor.
    for filepath in input_data_path.iterdir():
        os.rename(filepath, output_data_path / filepath.name[prefix_length:])
    return output_data_path
