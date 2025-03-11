import os
from collections.abc import Iterable
from typing import Any

import xarray as xr

class EnmapEntrypoint(xr.backends.BackendEntrypoint):

    def open_dataset(
        self,
        filename_or_obj: str | os.PathLike[Any],
        *,
        drop_variables: str | Iterable[str] | None = None,
    ) -> xr.Dataset:
        return xr.open_dataset(filename_or_obj)
