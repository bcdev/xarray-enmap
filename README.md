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
pip install --no-deps --editable .
```

## Usage

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
