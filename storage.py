import threading
import time
from typing import Iterable

import dataiku
import pandas as pd

_WRITE_LOCK = threading.RLock()
_CACHE_LOCK = threading.RLock()
_DATASET_CACHE = {}
_CACHE_TTL_SECONDS = 10.0  # Keep data in memory for 10 seconds to absorb redundant calls

def _clean_frame(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    result = dataframe.copy()

    for column in result.columns:
        if result[column].dtype == "object":
            result[column] = (
                result[column]
                .fillna("")
                .astype(str)
            )

    return result


def read_dataset(dataset_name: str) -> pd.DataFrame:
    with _CACHE_LOCK:
        # 1. Return from memory if we fetched this exact dataset within the last 10 seconds
        cached = _DATASET_CACHE.get(dataset_name)
        if cached and (time.time() - cached["timestamp"] < _CACHE_TTL_SECONDS):
            return cached["df"].copy()

        # 2. Otherwise, fetch it from Dataiku
        try:
            df = dataiku.Dataset(
                dataset_name,
                ignore_flow=True,
            ).get_dataframe()
            
            # Save it to memory for the next rapid-fire request
            _DATASET_CACHE[dataset_name] = {"df": df, "timestamp": time.time()}
            return df.copy()

        except Exception:
            return pd.DataFrame()


def append_rows(dataset_name: str, rows: Iterable[dict]) -> int:
    rows = list(rows)
    if not rows:
        return 0

    dataframe = _clean_frame(pd.DataFrame(rows))

    with _WRITE_LOCK:
        dataset = dataiku.Dataset(
            dataset_name,
            ignore_flow=True,
        )
        dataset.spec_item["appendMode"] = True
        dataset.write_with_schema(dataframe)
        
        # WIPE THE CACHE for this specific dataset so the next read gets the new rows
        with _CACHE_LOCK:
            _DATASET_CACHE.pop(dataset_name, None)

    return len(dataframe)


def case_rows(
    dataset_name: str,
    case_id: str,
) -> pd.DataFrame:
    dataframe = read_dataset(
        dataset_name
    )

    if (
        dataframe.empty
        or "case_id" not in dataframe.columns
    ):
        return pd.DataFrame()

    return dataframe[
        dataframe["case_id"]
        .astype(str)
        == str(case_id)
    ].copy()


def latest_case(
    case_id: str,
):
    dataframe = case_rows(
        "cases",
        case_id,
    )

    if dataframe.empty:
        return None

    return dataframe.iloc[-1].to_dict()


def list_cases() -> pd.DataFrame:
    dataframe = read_dataset(
        "cases"
    )

    if dataframe.empty:
        return dataframe

    return dataframe.drop_duplicates(
        "case_id",
        keep="last",
    )
