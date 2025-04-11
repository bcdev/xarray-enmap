# xarray-enmap

An xarray backend to read the data archives provided by the EOWEB data portal
of the [EnMAP](https://www.enmap.org/) mission.

## Installation

### With mamba or conda

`mamba install xarray-enmap`

or

`conda install xarray-enmap`

### With pip

`pip install xarray-enmap`

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
pip install --no-deps editable .
```

## Usage

```
import xarray as xr

enmap_dataset = xr.open_dataset(
    "/path/to/enmap/data/filename.tar.gz",
    engine="enmap"
)
```

The path can be to either a `.tar.gz` archive as provided by the EnMAP portal,
or to a directory containing the extracted archive contents.

If the archive or directory contains multiple EnMAP products, xarray-enmap
will open only the first. This will be improved in a future version.
