from collections.abc import Iterable
import logging
import os
import pathlib
import rioxarray
import shutil
import tarfile
import tempfile
from typing import Any
import xml.etree
import zipfile

import shapely
import xarray as xr


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
    # We omit the quicklook files QL_SWIR and QL_VNIR.
)


class EnmapEntrypoint(xr.backends.BackendEntrypoint):

    temp_dir = None

    def open_dataset(
        self,
        filename_or_obj: str | os.PathLike[Any],
        *,
        drop_variables: str | Iterable[str] | None = None,
    ) -> xr.Dataset:
        self.temp_dir = tempfile.mkdtemp(prefix="xrenmap-")
        ds = process(filename_or_obj, self.temp_dir)
        ds.set_close(self.close)
        return ds

    def close(self):
        if self.temp_dir:
            shutil.rmtree(self.temp_dir)


def process(
    input_filename: str,
    temp_dir: str,
):
    return convert(input_filename, temp_dir)


def convert(
    input_filename: str, temp_dir: str) -> xr.Dataset:
    data_dirs = list(extract_archives(input_filename, temp_dir))
    if len(data_dirs) > 1:
        LOGGER.warning("Multiple data archives found; reading the first.")
    return read_dataset_from_directory(data_dirs[0])


def read_dataset_from_directory(data_dir):
    LOGGER.info(f"Processing {data_dir}")
    arrays = {
        name: rioxarray.open_rasterio(
            data_dir / (filename + ".TIF")
        ).squeeze()
        for name, filename in VAR_MAP.items()
    }
    ds = xr.Dataset(arrays)
    add_metadata(ds, data_dir)
    return ds


def add_metadata(ds: xr.Dataset, data_dir: pathlib.Path):
    root = xml.etree.ElementTree.parse(data_dir / "METADATA.XML").getroot()

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


def extract_archives(
    archive_path: os.PathLike | str, dest_dir: os.PathLike | str
) -> Iterable[pathlib.Path]:
    dest_path = pathlib.Path(dest_dir)
    archive_path = pathlib.Path(archive_path)
    if archive_path.name.endswith(".tar.gz"):
        # An EnMAP tgz usually contains one or more zip archives
        # containing the actual data files.
        outer_path = dest_path / "outer-archive"
        LOGGER.info(f"Extracting {archive_path.name}")
        with tarfile.open(archive_path) as tgz_file:
            tgz_file.extractall(path=outer_path, filter="data")
    else:
        # Assume it's a zip and skip the outer archive
        # extraction step.
        LOGGER.info(f"Assuming {archive_path} is an inner zipfile")
        outer_path = archive_path.parent
    inner_path = dest_path / "inner-archive"

    data_paths = []
    final_path = dest_path / "data"
    os.mkdir(final_path)
    for index, path_to_zip_file in enumerate(find_zips(outer_path)):
        LOGGER.info(f"Extracting {path_to_zip_file.name}")
        extract_path = inner_path / str(index)
        with zipfile.ZipFile(path_to_zip_file, "r") as zip_ref:
            zip_ref.extractall(extract_path)
        input_data_path = list(extract_path.iterdir())[0]
        input_data_dir = input_data_path.name
        output_data_path = final_path / input_data_dir
        data_paths.append(output_data_path)
        prefix_length = len(input_data_path.name) + 1
        os.mkdir(output_data_path)
        for filepath in input_data_path.iterdir():
            os.rename(
                filepath, output_data_path / filepath.name[prefix_length:]
            )
    return data_paths


def find_zips(root: os.PathLike):
    root_path = pathlib.Path(root)
    for parent, dirs, files in root_path.walk(on_error=print):
        for filename in files:
            if filename.endswith(".ZIP"):
                yield pathlib.Path(parent, filename)
