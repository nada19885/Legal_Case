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


def _invalidate(dataset_name: str) -> None:
    with _CACHE_LOCK:
        _DATASET_CACHE.pop(dataset_name, None)


def replace_case_rows(
    dataset_name: str,
    case_id: str,
    rows: Iterable[dict] = (),
    remove_where=None,
) -> int:
    """Rewrite one case's slice of a dataset, leaving every other case intact.

    remove_where(frame) -> boolean mask selects which of this case's existing
    rows to drop (default: all of them). The new rows are then added. The
    read-modify-write happens under the shared write lock and the read cache
    is cleared afterwards, so the next case_rows() call sees the result.

    If the existing dataset cannot be read, nothing is overwritten: new rows
    are appended instead, because a blind overwrite would erase other cases.
    """
    rows = list(rows)
    new_frame = _clean_frame(pd.DataFrame(rows)) if rows else pd.DataFrame()

    with _WRITE_LOCK:
        dataset = dataiku.Dataset(dataset_name, ignore_flow=True)
        try:
            existing = dataset.get_dataframe()
        except Exception:
            existing = None

        if existing is None:
            if rows:
                dataset.spec_item["appendMode"] = True
                dataset.write_with_schema(new_frame)
            _invalidate(dataset_name)
            return len(new_frame)

        if not existing.empty and "case_id" in existing.columns:
            in_case = existing["case_id"].astype(str) == str(case_id)
            if remove_where is not None:
                case_part = existing[in_case]
                drop = pd.Series(False, index=existing.index)
                if not case_part.empty:
                    drop.loc[case_part.index] = remove_where(case_part).astype(bool).values
            else:
                drop = in_case
            kept = existing[~drop]
        else:
            kept = existing

        if not rows and len(kept) == len(existing):
            return 0

        result = pd.concat([kept, new_frame], ignore_index=True) if rows else kept
        dataset.write_with_schema(result)
        _invalidate(dataset_name)

    return len(new_frame)


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
