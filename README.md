# xarray-enmap

An xarray backend to read the data archives provided by the EOWEB data portal
of the [EnMAP](https://www.enmap.org/) mission.

## Installation

### With mamba or conda

`mamba install xarray-enmap`

or

`conda install xarray-enmap`

> ⚠️ Starting with release 0.0.3, xarray-enmap includes the command-line tool
> `convert-enmap`. If you wish to use `convert-enmap`, you should also install
> the optional packages `zarr` and `numcodecs`.

### With pip

> ⚠️ xarray-enmap requires the gdal library, which cannot be installed with
> pip. If you're working in a conda environment, you can use conda or mamba
> to install the `libgdal-core` package before starting the pip install.
> See the [GDAL documentation](https://gdal.org/en/stable/download.html) for
> other installation methods.

To install the basic package:

`pip install xarray-enmap`

If you want to export Zarr archives using the included command-line tool
`convert-enmap` (available from release 0.0.3):

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
    engine="enmap",
    backend_kwargs={"scale_reflectance": False}
)
```

The optional `scale_reflectance` keyword argument controls whether the
reflectance values are left as raw values or scaled to the range 0–1. When
they are scaled, the special background value of −32768 in the raw data is
also replaced with `NaN`. `scale_reflectance` is `True` by default, so you can
simply omit it if you want the reflectances scaled.

> ⚠️ Theoretically, the raw reflectance values in an EnMAP file should be
> between 0 and 10000. In practice, some real-world EnMAP products contain
> a few values outside this range, which will also result in values outside
> the 0–1 range after scaling.

The supplied path can reference:

- a `.tar.gz` archive as provided by the EnMAP portal, containing one or
  more EnMAP products in `.ZIP` sub-archives, or
- a `.ZIP` archive containing a single product, as found within an EnMAP
  `.tar.gz` archive, or
- a directory contained the unpacked contents of either of the aforementioned
  archive types.

At present, if the archive or directory contains multiple EnMAP products,
xarray-enmap will open only the first.

In addition to the standard `band` index co-ordinate containing the band number,
xarray-enmap creates an additional `wavelength` co-ordinate which can be used
to index by the corresponding band's centre wavelength. So you can do things
like

`enmap_dataset.reflectance.sel(wavelength=slice(950, 1000))`

to select data for a particular wavelength range.

## Usage of the command-line tool `convert-enmap`

Note that, to use the `--zarr-output` option, you must install the appropriate
optional packages (see installation instructions).

```text
usage: convert-enmap [-h] [--zarr-output ZARR_OUTPUT]
                     [--tiff-output TIFF_OUTPUT] [--raw-reflectance]
                     [--tempdir TEMPDIR] [--compress] [--datatree] [--verbose]
                     input_filename

Extract data from EnMAP archives. The expected input is an Zip archive, or a
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
  --raw-reflectance, -r
                        Use raw reflectance values rather than rescaling to
                        0-1 range.
  --tempdir, -t TEMPDIR
                        Use specified path as temporary directory, and don't
                        delete it afterwards (useful for debugging)
  --compress, -c        Higher Zarr output compression. ~25% smaller than
                        default compression. Compression process (but not
                        decompression) is much slower.
  --datatree, -d        Whether to write the data as datatree. This parameter
                        is only considered when the parameter zarr-output is
                        given.
  --verbose, -v
```

> ⚠️ The `--zarr-output` and `--tiff-output` arguments specify the *parent*
> directory for any output files. So e.g. specifying `--zarr-output myzarrs`
> will not produce a Zarr called "myzarrs", but a directory called "myzarrs"
> which contains one or more Zarr archives as subdirectories.
