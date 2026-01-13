# Copyright (c) 2025-2026 by Brockmann Consult GmbH
# Permissions are hereby granted under the terms of the MIT License:
# https://opensource.org/licenses/MIT.

import argparse
import importlib
import logging
import os
import pathlib
import shutil
import sys
import tempfile
from collections.abc import Iterable

import xarray

from . import xarray_enmap

LOGGER = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="""Extract data from EnMAP archives.
        The expected input is an Zip archive, or a .tar.gz archive
        of multiple Zip archives, downloaded from the EnMAP portal.
        Output can be written as TIFF, Zarr, or both.
        """
    )
    parser.add_argument(
        "input_filename",
        type=str,
        help="Either a Zip for a single product, "
        "or a .tar.gz containing multiple Zips",
    )
    parser.add_argument(
        "--zarr-output", type=str, help="Write Zarr output to this directory."
    )
    parser.add_argument(
        "--tiff-output", type=str, help="Write TIFF output to this directory."
    )
    parser.add_argument(
        "--raw-reflectance",
        "-r",
        action="store_true",
        help="Use raw reflectance values rather than rescaling to 0-1 range.",
    )
    parser.add_argument(
        "--tempdir",
        "-t",
        type=str,
        help="Use specified path as temporary directory, and don't "
        "delete it afterwards (useful for debugging)",
    )
    parser.add_argument(
        "--compress",
        "-c",
        action="store_true",
        help="Higher Zarr output compression. ~25%% smaller than default compression. "
        "Compression process (but not decompression) is much slower.",
    )
    parser.add_argument(
        "--datatree",
        "-d",
        action="store_true",
        help="Whether to write the data as datatree. This parameter is only considered when "
        "the parameter zarr-output is given.",
    )
    parser.add_argument("--verbose", "-v", action="count", default=0)
    args = parser.parse_args()
    scale_reflectance = not args.raw_reflectance

    def loglevel(verbosity):
        match verbosity:
            case 0:
                return logging.WARN
            case 1:
                return logging.INFO
            case _:
                return logging.DEBUG

    logging.basicConfig(level=loglevel(args.verbose))
    LOGGER.debug("debug level!")

    if args.tempdir is None:
        with tempfile.TemporaryDirectory() as temp_dir:
            process(
                args.input_filename,
                args.zarr_output,
                args.tiff_output,
                temp_dir,
                args.compress,
                args.datatree,
                scale_reflectance,
            )
    else:
        temp_dir = os.path.expanduser(args.tempdir)
        shutil.rmtree(temp_dir, ignore_errors=True)
        os.mkdir(temp_dir)
        process(
            args.input_filename,
            args.zarr_output,
            args.tiff_output,
            temp_dir,
            args.compress,
            args.datatree,
            scale_reflectance,
        )


def process(
    input_filename: str,
    output_dir_zarr: str,
    output_dir_tiff: str,
    temp_dir: str,
    compress: bool = False,
    open_as_datatree: bool = False,
    scale_reflectance: bool = True,
):
    if output_dir_zarr is output_dir_tiff is None:
        LOGGER.warning("No output destinations specified.")
        LOGGER.warning(
            "Archive will be extracted and opened but no data will be written."
        )
    input_path = pathlib.Path(input_filename)
    if input_path.is_file():
        data_dirs = list(
            xarray_enmap.extract_archives(input_filename, temp_dir)
        )
    elif input_path.is_dir():
        metadata_files = list(input_path.glob("*METADATA.XML"))
        match len(metadata_files):
            case 0:
                # assume outer directory
                data_dirs = list(
                    xarray_enmap.extract_archives(input_filename, temp_dir)
                )
            case 1:
                # assume inner directory
                data_dirs = [input_path]
            case _:
                raise RuntimeError("Too many METADATA.XML files")
    else:
        raise ValueError(
            f"{input_filename} is neither a file nor a directory."
        )
    if output_dir_zarr is not None and open_as_datatree:
        write_datatree_as_zarr(
            input_path, data_dirs, output_dir_zarr, compress, scale_reflectance
        )
    else:
        for data_dir in data_dirs:
            if output_dir_tiff is not None:
                shutil.copytree(
                    data_dir, pathlib.Path(output_dir_tiff) / data_dir.name
                )
            if output_dir_zarr is not None:
                write_zarr(
                    data_dir, output_dir_zarr, compress, scale_reflectance
                )


def write_zarr(
    data_dir,
    output_dir: str,
    compress: bool = False,
    scale_reflectance: bool = True,
):
    LOGGER.info(f"Writing {data_dir} to a Zarr archive...")
    ensure_module_importable("zarr")
    LOGGER.info(
        f"Using {'scaled' if scale_reflectance else 'unscaled'} "
        f"reflectance."
    )
    ds = xarray_enmap.read_dataset_from_inner_directory(
        data_dir, scale_reflectance
    )
    store_path = pathlib.Path(output_dir) / (data_dir.name + ".zarr")
    zarr_args = _get_zarr_args(compress, store_path)
    ds.to_zarr(**zarr_args)


def write_datatree_as_zarr(
    input_path: pathlib.Path,
    data_dirs: Iterable[pathlib.Path | str],
    output_dir: str,
    compress: bool = False,
    scale_reflectance: bool = True,
):
    name = input_path.name
    LOGGER.info(f"Writing {name} to a Zarr archive...")
    suffixes = input_path.suffixes
    suffixes.reverse()
    for suffix in suffixes:
        name = name.removesuffix(suffix)
    ensure_module_importable("zarr")
    LOGGER.info(
        f"Using {'scaled' if scale_reflectance else 'unscaled'} "
        f"reflectance."
    )
    groups = {}
    for data_dir in data_dirs:
        group_name = data_dir if isinstance(data_dir, str) else data_dir.name
        groups[group_name] = xarray_enmap.read_dataset_from_inner_directory(
            data_dir, scale_reflectance
        )
    dt = xarray.DataTree.from_dict(groups)
    store_path = pathlib.Path(output_dir) / (name + ".zarr")
    zarr_args = _get_zarr_args(compress, store_path)
    dt.to_zarr(**zarr_args)


def _get_zarr_args(compress: bool, store_path: str):
    zarr_args = {"zarr_format": 2, "store": store_path}
    if compress:
        ensure_module_importable("numcodecs")
        import numcodecs

        zarr_args["encoding"] = {
            "reflectance": {
                "compressor": numcodecs.Blosc(
                    cname="zstd", clevel=9, shuffle=numcodecs.Blosc.SHUFFLE
                )
            }
        }
    return zarr_args


def ensure_module_importable(module_name: str):
    if importlib.util.find_spec(module_name) is None:
        LOGGER.error(f"This functionality requires the {module_name} module.")
        LOGGER.error(f"Please install {module_name} and try again.")
        sys.exit(1)
