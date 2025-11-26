# xarray-enmap

An xarray backend to read the data archives provided by the EOWEB data portal
of the [EnMAP](https://www.enmap.org/) mission.

## Installation

### With mamba or conda

`mamba install xarray-enmap`

or

`conda install xarray-enmap`

> ⚠️ If you want to export Zarr archives using the included command-line tool
> `convert-enmap`, also install the packages `zarr` and `numcodecs`.

### With pip

To install the basic package:

`pip install xarray-enmap`

If you want to export Zarr archives using the included command-line tool `convert-enmap`:

`pip install xarray-enmap[zarr]`

### Development install from the git repository

Clone the repository and set the current working directory:

```bash
git clone https://github.com/bcdev/xarray-enmap.git
cd xarray-enmap
```

Install the dependencies with mamba or conda:

```bash
mamba env create
mamba activate xarray-enmap
```

Install xarray-enmap itself:

```bash
pip install --no-deps --editable .
```

## Usage as an xarray extension

```
import xarray as xr

enmap_dataset = xr.open_dataset(
    "/path/to/enmap/data/filename.tar.gz",
    engine="enmap"
)
```

The supplied path can reference:

- a `.tar.gz` archive as provided by the EnMAP portal, containing one or
  more EnMAP products in `.ZIP` sub-archives, or
- a `.ZIP` archive containing a single product, as found within an EnMAP
  `.tar.gz` archive, or
- a directory contained the unpacked contents of either of the aforementioned
  archive types.

At present, if the archive or directory contains multiple EnMAP products,
xarray-enmap will open only the first.

## Usage of the command-line tool `convert-enmap`

Note that, to use the `--zarr-output` option, you must install the appropriate
optional packages (see installation instructions).

```text
usage: convert-enmap [-h] [--zarr-output ZARR_OUTPUT]
                     [--tiff-output TIFF_OUTPUT] [--tempdir TEMPDIR]
                     [--compress] [--verbose]
                     input_filename

Extract data from EnMAP archives. The expected input is a Zip archive, or a
.tar.gz archive of multiple Zip archives, downloaded from the EnMAP portal.
Output can be written as TIFF, Zarr, or both.

positional arguments:
  input_filename        Either a Zip for a single product, or a .tar.gz
                        containing multiple Zips

options:
  -h, --help            show this help message and exit
  --zarr-output ZARR_OUTPUT
                        Write Zarr output to this directory.
  --tiff-output TIFF_OUTPUT
                        Write TIFF output to this directory.
  --tempdir, -t TEMPDIR
                        Use specified path as temporary directory, and don't
                        delete it afterwards (useful for debugging)
  --compress, -c        Higher Zarr output compression. ~25% smaller than
                        default compression. Compression process (but not
                        decompression) is much slower.
  --verbose, -v
```
