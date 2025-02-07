import logging
from collections import Counter
from pathlib import Path

import yaml
from pyam import IamDataFrame
from pydantic import BaseModel, field_validator, ValidationInfo
from pydantic.types import FilePath
from pydantic_core import PydanticCustomError

from nomenclature.error import custom_pydantic_errors
from nomenclature.processor import Processor
from nomenclature.processor.utils import get_relative_path

logger = logging.getLogger(__name__)

here = Path(__file__).parent.absolute()


class AggregationItem(BaseModel):
    """Item used for aggregation-mapping"""

    name: str
    components: list[str]


class Aggregator(Processor):
    file: FilePath
    dimension: str
    mapping: list[AggregationItem]

    def apply(self, df: IamDataFrame) -> IamDataFrame:
        """Apply region processing

        Parameters
        ----------
        df : IamDataFrame
            Input data that the region processing is applied to

        Returns
        -------
        IamDataFrame:
            Processed data

        """
        return df.rename(
            {self.dimension: self.rename_mapping},
            check_duplicates=False,
        )

    @property
    def rename_mapping(self):
        rename_dict = {}

        for item in self.mapping:
            for c in item.components:
                rename_dict[c] = item.name

        return rename_dict

    @field_validator("mapping")
    def validate_target_names(cls, v, info: ValidationInfo):
        _validate_items([item.name for item in v], info, "target")
        return v

    @field_validator("mapping")
    def validate_components(cls, v, info: ValidationInfo):
        all_components = list()
        for item in v:
            all_components.extend(item.components)
        _validate_items(all_components, info, "component")
        return v

    @classmethod
    def from_file(cls, file: Path | str):
        """Initialize an AggregatorMapping from a file.

        .. code:: yaml

        dimension: <some_dimension>
        aggegate:
          - Target Value:
            - Source Value A
            - Source Value B

        """
        file = Path(file) if isinstance(file, str) else file
        try:
            with open(file, "r", encoding="utf-8") as f:
                mapping_input = yaml.safe_load(f)

            mapping_list: list[dict[str, list]] = []
            for item in mapping_input["aggregate"]:
                # TODO explicit check that only one key-value pair exists per item
                mapping_list.append(
                    dict(name=list(item)[0], components=list(item.values())[0])
                )
        except Exception as error:
            raise ValueError(f"{error} in {get_relative_path(file)}") from error
        return cls(
            dimension=mapping_input["dimension"],
            mapping=mapping_list,  # type: ignore
            file=get_relative_path(file),
        )


def _validate_items(items, info, _type):
    duplicates = [item for item, count in Counter(items).items() if count > 1]
    if duplicates:
        raise PydanticCustomError(
            *custom_pydantic_errors.AggregationMappingConflict,
            {
                "type": _type,
                "duplicates": duplicates,
                "file": info.data["file"],
            },
        )
