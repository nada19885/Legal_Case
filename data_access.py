import dataiku
import pandas as pd

from .config import (
    LEGAL_NODES_DATASET,
    LEGAL_RELATIONSHIPS_DATASET,
)


def load_legal_nodes() -> pd.DataFrame:
    return dataiku.Dataset(
        LEGAL_NODES_DATASET
    ).get_dataframe()


def load_legal_relationships() -> pd.DataFrame:
    return dataiku.Dataset(
        LEGAL_RELATIONSHIPS_DATASET
    ).get_dataframe()


def dataframe_to_records(
    df: pd.DataFrame,
) -> list[dict]:
    clean_df = df.where(
        pd.notnull(df),
        None,
    )

    return clean_df.to_dict(
        orient="records"
    )
