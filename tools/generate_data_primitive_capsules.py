#!/usr/bin/env python3
"""Materialize a curated cohort of complete data utility primitives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from textwrap import dedent

from taedri_codegraph.primitives.authoring import (
    PrimitiveAuthoringSpec,
    PrimitiveAuthoringError,
    build_primitive_files,
    render_primitive_directory,
)
from taedri_codegraph.primitives.bundle import (
    InspectedPrimitiveDirectory,
    inspect_primitive_directory,
)


ROOT = Path(__file__).resolve().parents[1]
PYTHON_STATISTICS = "https://docs.python.org/3.12/library/statistics.html"
PANDAS_GUIDE = "https://pandas.pydata.org/docs/user_guide/"
SKLEARN_MINMAX = (
    "https://scikit-learn.org/stable/modules/generated/"
    "sklearn.preprocessing.MinMaxScaler.html"
)
SKLEARN_STANDARD = (
    "https://scikit-learn.org/stable/modules/generated/"
    "sklearn.preprocessing.StandardScaler.html"
)


def _source(value: str) -> str:
    return dedent(value).lstrip()


def _case(kind: str, value: object, *, expected: object = None, error: str = ""):
    result: dict[str, object] = {"kind": kind, "args": [value]}
    if error:
        result["expected_error"] = error
    else:
        result["expected"] = expected
    return result


def _spec(
    *,
    category: str,
    name: str,
    function_name: str,
    source_code: str,
    summary: str,
    keywords: tuple[str, ...],
    use_cases: tuple[str, ...],
    limitations: tuple[str, ...],
    input_name: str,
    input_schema: dict[str, object],
    output_schema: dict[str, object],
    errors: tuple[dict[str, str], ...],
    examples: tuple[dict[str, object], ...],
    tests: tuple[dict[str, object], ...],
    group_id: str,
    group_labels: tuple[str, ...],
    documentation: str,
    references: tuple[str, ...],
    allowed_imports: tuple[str, ...] = (),
) -> PrimitiveAuthoringSpec:
    namespace = "taedri." + category.replace("-", ".")
    relative = f"examples/primitives/{category}/{name}"
    return PrimitiveAuthoringSpec(
        namespace=namespace,
        name=name,
        category=category,
        function_name=function_name,
        source_code=source_code,
        summary=summary,
        keywords=keywords,
        use_cases=use_cases,
        limitations=limitations,
        input_name=input_name,
        input_schema=input_schema,
        output_schema=output_schema,
        errors=errors,
        examples=examples,
        tests=tests,
        group_id=group_id,
        group_labels=group_labels,
        documentation=documentation,
        references=references,
        source_uri=(
            "https://github.com/Amarel-Taylor-Scott/TaedriCodeGraph/tree/main/"
            + relative
        ),
        implementation_producer_id=f"taedri.data.author.{name}.v1",
        oracle_producer_id=f"taedri.data.oracle.{name}.v1",
        policy_decision_id="taedri.policy.data-primitives-v1",
        allowed_imports=allowed_imports,
    )


STRING_SCHEMA = {"type": "string"}
NUMBER_SCHEMA = {"type": "number"}
NUMBER_ARRAY_SCHEMA = {"type": "array", "items": NUMBER_SCHEMA}
JSON_ARRAY_SCHEMA = {"type": "array"}
OBJECT_SCHEMA = {"type": "object"}
FLATTEN_REQUEST_SCHEMA = {
    "type": "object",
    "required": ["record"],
    "properties": {
        "record": {"type": "object"},
        "separator": {"type": "string"},
    },
    "additionalProperties": False,
}


COHORT = (
    _spec(
        category="data-cleaning",
        name="collapse-whitespace",
        function_name="collapse_whitespace",
        source_code=_source(
            '''
            """Collapse every run of Unicode whitespace to one ASCII space."""


            def collapse_whitespace(value: str) -> str:
                """Return a stripped string with internal whitespace runs collapsed."""

                if not isinstance(value, str):
                    raise TypeError("value must be a string")
                return " ".join(value.split())
            '''
        ),
        summary="Collapse Unicode whitespace runs to one space for stable text fields.",
        keywords=("collapse whitespace", "data cleaning", "text", "unicode"),
        use_cases=(
            "clean free-text columns before comparison",
            "normalize tabs, newlines, and non-breaking spaces",
            "prepare text for deterministic keys",
        ),
        limitations=(
            "All whitespace distinctions are replaced by one ASCII space.",
            "Does not normalize Unicode composition or case.",
            "Accepts one string and processes it in memory.",
        ),
        input_name="value",
        input_schema=STRING_SCHEMA,
        output_schema=STRING_SCHEMA,
        errors=({"type": "TypeError", "when": "value is not a string"},),
        examples=(
            _case("positive", "  North\t  America\n", expected="North America"),
            _case("boundary", "", expected=""),
            _case("negative", 42, error="TypeError"),
        ),
        tests=(
            _case("positive", "A\u00a0B", expected="A B"),
            _case("boundary", "already clean", expected="already clean"),
            _case("negative", None, error="TypeError"),
        ),
        group_id="taedri.group.data_cleaning_whitespace",
        group_labels=(
            "collapse internal whitespace",
            "normalize text spacing",
            "unicode whitespace cleanup",
        ),
        documentation=(
            "collapses leading, trailing, and internal Unicode whitespace runs to a "
            "single ASCII space without changing non-whitespace characters."
        ),
        references=(
            "https://docs.python.org/3.12/library/stdtypes.html#str.split",
            "https://pandas.pydata.org/docs/user_guide/text.html",
        ),
    ),
    _spec(
        category="data-cleaning",
        name="normalize-column-name",
        function_name="normalize_column_name",
        source_code=_source(
            '''
            """Normalize one human-provided data column name."""

            import unicodedata


            def normalize_column_name(value: str) -> str:
                """Return a case-folded underscore-delimited Unicode column name."""

                if not isinstance(value, str):
                    raise TypeError("value must be a string")
                normalized = unicodedata.normalize("NFKC", value).strip().casefold()
                result: list[str] = []
                separator_pending = False
                for character in normalized:
                    if character.isalnum():
                        if separator_pending and result:
                            result.append("_")
                        result.append(character)
                        separator_pending = False
                    else:
                        separator_pending = True
                name = "".join(result).strip("_")
                if not name:
                    raise ValueError("value does not contain a letter or number")
                return name
            '''
        ),
        summary="Create a stable NFKC, case-folded, underscore-delimited column name.",
        keywords=("column names", "data cleaning", "schema", "unicode normalization"),
        use_cases=(
            "normalize CSV and spreadsheet headers",
            "create stable field identifiers before schema matching",
            "reduce punctuation and spacing differences across sources",
        ),
        limitations=(
            "NFKC compatibility normalization can change presentation characters.",
            "Case folding can change string length.",
            "The result can contain Unicode letters and numbers, not ASCII only.",
        ),
        input_name="value",
        input_schema=STRING_SCHEMA,
        output_schema=STRING_SCHEMA,
        errors=(
            {"type": "TypeError", "when": "value is not a string"},
            {"type": "ValueError", "when": "value contains no letter or number"},
        ),
        examples=(
            _case("positive", " Customer ID ", expected="customer_id"),
            _case("boundary", "Ｆｕｌｌ　Ｎａｍｅ", expected="full_name"),
            _case("negative", "---", error="ValueError"),
        ),
        tests=(
            _case("positive", "HTTP.Status-Code", expected="http_status_code"),
            _case("boundary", "Straße", expected="strasse"),
            _case("negative", 12, error="TypeError"),
        ),
        group_id="taedri.group.data_cleaning_column_names",
        group_labels=(
            "normalize dataframe column header",
            "schema field name cleanup",
            "stable column identifiers",
        ),
        documentation=(
            "applies Unicode NFKC normalization and case folding, converts runs of "
            "non-alphanumeric characters to underscores, and rejects empty results."
        ),
        references=(
            "https://docs.python.org/3.12/library/unicodedata.html#unicodedata.normalize",
            "https://pandas.pydata.org/docs/reference/api/pandas.Series.str.normalize.html",
        ),
        allowed_imports=("unicodedata",),
    ),
    _spec(
        category="data-cleaning",
        name="stable-deduplicate",
        function_name="stable_deduplicate",
        source_code=_source(
            '''
            """Remove duplicate finite JSON values while preserving first occurrence."""

            import json


            def stable_deduplicate(values: list[object]) -> list[object]:
                """Return first occurrences using canonical JSON equality."""

                if not isinstance(values, list):
                    raise TypeError("values must be a list")
                seen: set[str] = set()
                result: list[object] = []
                for value in values:
                    try:
                        marker = json.dumps(
                            value,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                    except (TypeError, ValueError) as exc:
                        raise TypeError("items must be finite JSON values") from exc
                    if marker not in seen:
                        seen.add(marker)
                        result.append(value)
                return result
            '''
        ),
        summary="Remove duplicate finite JSON values while retaining their first order.",
        keywords=("deduplicate", "distinct", "data cleaning", "stable order"),
        use_cases=(
            "remove repeated categorical values",
            "deduplicate JSON records with key-order-independent equality",
            "retain first-seen order in ingestion pipelines",
        ),
        limitations=(
            "Equality is defined by finite canonical JSON representation.",
            "The full input and a marker per distinct value are retained in memory.",
            "Does not select duplicates by a subset of record fields.",
        ),
        input_name="values",
        input_schema=JSON_ARRAY_SCHEMA,
        output_schema=JSON_ARRAY_SCHEMA,
        errors=(
            {"type": "TypeError", "when": "values is not a list"},
            {"type": "TypeError", "when": "an item is not finite JSON"},
        ),
        examples=(
            _case("positive", [1, 2, 1, 3, 2], expected=[1, 2, 3]),
            _case("boundary", [], expected=[]),
            _case("negative", "not-a-list", error="TypeError"),
        ),
        tests=(
            _case(
                "positive",
                [{"a": 1, "b": 2}, {"b": 2, "a": 1}],
                expected=[{"a": 1, "b": 2}],
            ),
            _case("boundary", [1, 1.0, True, 1], expected=[1, 1.0, True]),
            _case("positive", [None, None, ""], expected=[None, ""]),
        ),
        group_id="taedri.group.data_cleaning_deduplication",
        group_labels=(
            "stable duplicate removal",
            "distinct json values",
            "preserve first occurrence",
        ),
        documentation=(
            "removes repeated finite JSON values by canonical representation while "
            "retaining each first occurrence and its original value."
        ),
        references=(
            "https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.drop_duplicates.html",
            "https://docs.python.org/3.12/library/json.html#json.dumps",
        ),
        allowed_imports=("json",),
    ),
    _spec(
        category="data-engineering",
        name="flatten-record",
        function_name="flatten_record",
        source_code=_source(
            '''
            """Flatten nested JSON objects with explicit collision rejection."""


            def flatten_record(request: dict[str, object]) -> dict[str, object]:
                """Flatten request['record'] using request.get('separator', '.')."""

                if not isinstance(request, dict):
                    raise TypeError("request must be an object")
                if set(request) - {"record", "separator"}:
                    raise ValueError("request contains unknown fields")
                record = request.get("record")
                separator = request.get("separator", ".")
                if not isinstance(record, dict):
                    raise TypeError("record must be an object")
                if not isinstance(separator, str) or not separator:
                    raise ValueError("separator must be a non-empty string")
                result: dict[str, object] = {}

                def visit(prefix: str, value: object) -> None:
                    if isinstance(value, dict) and value:
                        for key, nested in value.items():
                            if not isinstance(key, str):
                                raise TypeError("record keys must be strings")
                            path = key if not prefix else prefix + separator + key
                            visit(path, nested)
                        return
                    if prefix in result:
                        raise ValueError("flattened record has a key collision")
                    result[prefix] = value

                for key, value in record.items():
                    if not isinstance(key, str):
                        raise TypeError("record keys must be strings")
                    visit(key, value)
                return result
            '''
        ),
        summary="Flatten one nested JSON record with explicit separator and collision rules.",
        keywords=("flatten record", "json normalize", "nested data", "data engineering"),
        use_cases=(
            "prepare nested API records for tabular storage",
            "flatten event payloads before column selection",
            "create deterministic dotted field paths",
        ),
        limitations=(
            "Lists remain leaf values and are not exploded.",
            "Existing keys containing the separator can create a rejected collision.",
            "The complete flattened record is materialized in memory.",
        ),
        input_name="request",
        input_schema=FLATTEN_REQUEST_SCHEMA,
        output_schema=OBJECT_SCHEMA,
        errors=(
            {"type": "TypeError", "when": "request or record is not an object"},
            {"type": "ValueError", "when": "separator or flattened keys are ambiguous"},
        ),
        examples=(
            _case(
                "positive",
                {"record": {"user": {"id": 7}, "active": True}},
                expected={"user.id": 7, "active": True},
            ),
            _case("boundary", {"record": {}}, expected={}),
            _case("negative", {"record": []}, error="TypeError"),
        ),
        tests=(
            _case(
                "positive",
                {"record": {"user": {"id": 7}}, "separator": "_"},
                expected={"user_id": 7},
            ),
            _case(
                "negative",
                {"record": {"a": {"b": 1}, "a.b": 2}},
                error="ValueError",
            ),
            _case("negative", None, error="TypeError"),
        ),
        group_id="taedri.group.data_engineering_record_reshape",
        group_labels=(
            "flatten nested record",
            "json object to flat columns",
            "record reshaping",
        ),
        documentation=(
            "turns nested JSON objects into flat path-keyed records, keeps lists as "
            "leaf values, and fails rather than overwriting colliding keys."
        ),
        references=(
            "https://pandas.pydata.org/docs/reference/api/pandas.json_normalize.html",
        ),
    ),
    _spec(
        category="data-engineering",
        name="chunk-sequence",
        function_name="chunk_sequence",
        source_code=_source(
            '''
            """Split a list into bounded contiguous chunks."""


            def chunk_sequence(request: dict[str, object]) -> list[list[object]]:
                """Return contiguous request['size'] chunks of request['items']."""

                if not isinstance(request, dict):
                    raise TypeError("request must be an object")
                if set(request) != {"items", "size"}:
                    raise ValueError("request requires exactly items and size")
                items = request["items"]
                size = request["size"]
                if not isinstance(items, list):
                    raise TypeError("items must be a list")
                if isinstance(size, bool) or not isinstance(size, int):
                    raise TypeError("size must be an integer")
                if size <= 0:
                    raise ValueError("size must be positive")
                return [items[index:index + size] for index in range(0, len(items), size)]
            '''
        ),
        summary="Split an in-memory sequence into deterministic contiguous batches.",
        keywords=("batch", "chunk", "data engineering", "sequence"),
        use_cases=(
            "batch records for bounded API or database operations",
            "partition a sequence for worker jobs",
            "create deterministic fixed-size ingestion units",
        ),
        limitations=(
            "Consumes and returns in-memory lists rather than streaming iterators.",
            "Does not balance work by item cost.",
            "The final chunk can be smaller than the requested size.",
        ),
        input_name="request",
        input_schema={
            "type": "object",
            "required": ["items", "size"],
            "properties": {
                "items": {"type": "array"},
                "size": {"type": "integer", "minimum": 1},
            },
            "additionalProperties": False,
        },
        output_schema={"type": "array", "items": {"type": "array"}},
        errors=(
            {"type": "TypeError", "when": "request, items, or size has the wrong type"},
            {"type": "ValueError", "when": "size is non-positive or fields are invalid"},
        ),
        examples=(
            _case(
                "positive",
                {"items": [1, 2, 3, 4, 5], "size": 2},
                expected=[[1, 2], [3, 4], [5]],
            ),
            _case("boundary", {"items": [], "size": 3}, expected=[]),
            _case("negative", {"items": [1], "size": 0}, error="ValueError"),
        ),
        tests=(
            _case(
                "boundary",
                {"items": [1, 2], "size": 5},
                expected=[[1, 2]],
            ),
            _case("negative", {"items": [1], "size": True}, error="TypeError"),
            _case(
                "negative",
                {"items": [1], "size": 1, "extra": False},
                error="ValueError",
            ),
        ),
        group_id="taedri.group.data_engineering_batching",
        group_labels=(
            "batch sequence chunks",
            "bounded ingestion batches",
            "contiguous list partitioning",
        ),
        documentation=(
            "splits a list into fixed-size contiguous lists with a smaller final batch "
            "when necessary and rejects ambiguous request fields."
        ),
        references=(
            "https://docs.python.org/3.12/library/itertools.html#itertools.batched",
        ),
    ),
    _spec(
        category="data-cleaning",
        name="normalize-null-marker",
        function_name="normalize_null_marker",
        source_code=_source(
            '''
            """Normalize common textual missing-value markers to JSON null."""


            _NULL_MARKERS = frozenset(("", "na", "n/a", "null", "none"))


            def normalize_null_marker(value: str) -> str | None:
                """Return None for a fixed missing-value marker, otherwise value."""

                if not isinstance(value, str):
                    raise TypeError("value must be a string")
                if value.strip().casefold() in _NULL_MARKERS:
                    return None
                return value
            '''
        ),
        summary="Normalize common textual missing-value markers to a JSON null value.",
        keywords=(
            "missing values",
            "null marker",
            "data cleaning",
            "sentinel normalization",
        ),
        use_cases=(
            "normalize CSV missing-value sentinels before type conversion",
            "map blank strings and common null labels to one value",
            "prepare nullable text fields for deterministic comparison",
        ),
        limitations=(
            "The marker set is fixed to blank, NA, N/A, null, and none.",
            "Whitespace and case are ignored only when testing for a marker.",
            "Non-marker strings are returned byte-for-byte unchanged.",
        ),
        input_name="value",
        input_schema=STRING_SCHEMA,
        output_schema={"type": ["string", "null"]},
        errors=({"type": "TypeError", "when": "value is not a string"},),
        examples=(
            _case("positive", " N/A ", expected=None),
            _case("boundary", "", expected=None),
            _case("negative", 0, error="TypeError"),
        ),
        tests=(
            _case("positive", "  NULL\t", expected=None),
            _case("boundary", "none such", expected="none such"),
            _case("negative", None, error="TypeError"),
        ),
        group_id="taedri.group.data_cleaning_missing_values",
        group_labels=(
            "normalize null markers",
            "clean missing value sentinels",
            "map blank text to null",
        ),
        documentation=(
            "matches a small documented set of common missing-value strings after "
            "stripping and case folding, returning `None` for matches and preserving "
            "every non-marker string exactly."
        ),
        references=(
            "https://pandas.pydata.org/docs/reference/api/pandas.read_csv.html",
            "https://docs.python.org/3.12/library/stdtypes.html#str.casefold",
        ),
    ),
    _spec(
        category="data-engineering",
        name="normalize-iso-datetime",
        function_name="normalize_iso_datetime",
        source_code=_source(
            '''
            """Normalize one timezone-aware ISO 8601 timestamp to canonical UTC."""

            from datetime import datetime, timezone


            def normalize_iso_datetime(value: str) -> str:
                """Return a timezone-aware timestamp in UTC with a trailing Z."""

                if not isinstance(value, str):
                    raise TypeError("value must be a string")
                candidate = value.strip()
                if candidate.endswith("Z"):
                    candidate = candidate[:-1] + "+00:00"
                try:
                    parsed = datetime.fromisoformat(candidate)
                except ValueError as exc:
                    raise ValueError("value must be an ISO 8601 timestamp") from exc
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    raise ValueError("value must include a UTC offset")
                normalized = parsed.astimezone(timezone.utc)
                timespec = "microseconds" if normalized.microsecond else "seconds"
                return normalized.isoformat(timespec=timespec).removesuffix("+00:00") + "Z"
            '''
        ),
        summary="Convert one timezone-aware ISO 8601 timestamp to canonical UTC text.",
        keywords=(
            "datetime parsing",
            "ISO 8601",
            "timestamp normalization",
            "UTC",
        ),
        use_cases=(
            "normalize timestamps from APIs with different UTC offsets",
            "create stable UTC text before sorting or deduplication",
            "reject timezone-ambiguous event timestamps during ingestion",
        ),
        limitations=(
            "Timezone-naive inputs are rejected rather than assigned an implicit zone.",
            "Accepted syntax follows Python 3.12 `datetime.fromisoformat`.",
            "Named timezone identifiers and leap seconds are not accepted.",
        ),
        input_name="value",
        input_schema=STRING_SCHEMA,
        output_schema=STRING_SCHEMA,
        errors=(
            {"type": "TypeError", "when": "value is not a string"},
            {"type": "ValueError", "when": "value is invalid or lacks a UTC offset"},
        ),
        examples=(
            _case(
                "positive",
                "2026-07-17T08:30:00-04:00",
                expected="2026-07-17T12:30:00Z",
            ),
            _case(
                "boundary",
                "2000-01-01T00:00:00.123456+00:00",
                expected="2000-01-01T00:00:00.123456Z",
            ),
            _case("negative", "2026-07-17T12:30:00", error="ValueError"),
        ),
        tests=(
            _case(
                "positive",
                "2026-07-17T12:30:00Z",
                expected="2026-07-17T12:30:00Z",
            ),
            _case(
                "boundary",
                "1970-01-01T05:30:00+05:30",
                expected="1970-01-01T00:00:00Z",
            ),
            _case("negative", 1_234, error="TypeError"),
        ),
        group_id="taedri.group.data_engineering_datetime_normalization",
        group_labels=(
            "normalize ISO datetime to UTC",
            "parse timezone aware timestamp",
            "canonical event time",
        ),
        documentation=(
            "parses a timezone-aware ISO 8601 timestamp with the Python 3.12 standard "
            "library, converts it to UTC, and emits seconds or six-digit microseconds "
            "with a trailing `Z`."
        ),
        references=(
            "https://docs.python.org/3.12/library/datetime.html#datetime.datetime.fromisoformat",
            "https://www.rfc-editor.org/rfc/rfc3339",
        ),
        allowed_imports=("datetime",),
    ),
    _spec(
        category="data-science",
        name="numeric-mean",
        function_name="numeric_mean",
        source_code=_source(
            '''
            """Compute a finite floating-point arithmetic mean."""

            import math


            def numeric_mean(values: list[float]) -> float:
                """Return the arithmetic mean using math.fsum."""

                if not isinstance(values, list):
                    raise TypeError("values must be a list")
                if not values:
                    raise ValueError("values cannot be empty")
                numbers: list[float] = []
                for value in values:
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        raise TypeError("values must contain numbers")
                    number = float(value)
                    if not math.isfinite(number):
                        raise ValueError("values must be finite")
                    numbers.append(number)
                return math.fsum(numbers) / len(numbers)
            '''
        ),
        summary="Compute the arithmetic mean of a non-empty finite numeric vector.",
        keywords=("arithmetic mean", "average", "data science", "descriptive statistics"),
        use_cases=(
            "summarize one numeric feature vector",
            "calculate a deterministic aggregate in a small pipeline",
            "verify an upstream numeric transformation",
        ),
        limitations=(
            "Returns binary floating-point output.",
            "Rejects booleans, missing values, NaN, and infinity.",
            "The mean is sensitive to outliers.",
        ),
        input_name="values",
        input_schema=NUMBER_ARRAY_SCHEMA,
        output_schema=NUMBER_SCHEMA,
        errors=(
            {"type": "TypeError", "when": "values is not a numeric list"},
            {"type": "ValueError", "when": "values is empty or non-finite"},
        ),
        examples=(
            _case("positive", [1, 2, 3, 4], expected=2.5),
            _case("boundary", [2.5], expected=2.5),
            _case("negative", [], error="ValueError"),
        ),
        tests=(
            _case("positive", [-1, 1], expected=0.0),
            _case(
                "boundary",
                [1e16, 1, -1e16],
                expected=0.3333333333333333,
            ),
            _case("negative", [1, True], error="TypeError"),
        ),
        group_id="taedri.group.data_science_descriptive_statistics",
        group_labels=(
            "arithmetic mean numeric vector",
            "descriptive statistics",
            "numeric aggregation",
        ),
        documentation=(
            "validates a non-empty finite numeric vector and computes its floating-point "
            "arithmetic mean with `math.fsum` for improved summation accuracy."
        ),
        references=(PYTHON_STATISTICS,),
        allowed_imports=("math",),
    ),
    _spec(
        category="data-science",
        name="numeric-median",
        function_name="numeric_median",
        source_code=_source(
            '''
            """Compute the conventional median of finite numeric values."""

            import math


            def numeric_median(values: list[float]) -> float:
                """Return the middle value or mean of the two middle values."""

                if not isinstance(values, list):
                    raise TypeError("values must be a list")
                if not values:
                    raise ValueError("values cannot be empty")
                numbers: list[float] = []
                for value in values:
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        raise TypeError("values must contain numbers")
                    number = float(value)
                    if not math.isfinite(number):
                        raise ValueError("values must be finite")
                    numbers.append(number)
                ordered = sorted(numbers)
                middle = len(ordered) // 2
                if len(ordered) % 2:
                    return ordered[middle]
                return math.fsum((ordered[middle - 1], ordered[middle])) / 2.0
            '''
        ),
        summary="Compute the conventional median of a non-empty finite numeric vector.",
        keywords=("data science", "descriptive statistics", "median", "robust center"),
        use_cases=(
            "summarize a numeric feature with a robust center",
            "compare mean and median for skew or outlier signals",
            "verify numeric cleaning output",
        ),
        limitations=(
            "Returns binary floating-point output.",
            "Rejects booleans, missing values, NaN, and infinity.",
            "Sorts and copies the complete vector in memory.",
        ),
        input_name="values",
        input_schema=NUMBER_ARRAY_SCHEMA,
        output_schema=NUMBER_SCHEMA,
        errors=(
            {"type": "TypeError", "when": "values is not a numeric list"},
            {"type": "ValueError", "when": "values is empty or non-finite"},
        ),
        examples=(
            _case("positive", [7, 1, 3], expected=3.0),
            _case("boundary", [1, 3, 5, 7], expected=4.0),
            _case("negative", [], error="ValueError"),
        ),
        tests=(
            _case("positive", [2, 2, 8], expected=2.0),
            _case("boundary", [-5, -1], expected=-3.0),
            _case("negative", [1, True], error="TypeError"),
        ),
        group_id="taedri.group.data_science_descriptive_statistics",
        group_labels=(
            "robust median numeric vector",
            "descriptive statistics",
            "numeric center",
        ),
        documentation=(
            "validates and sorts a finite numeric vector, returning the middle value for "
            "odd lengths or the arithmetic mean of the two middle values for even lengths."
        ),
        references=(PYTHON_STATISTICS,),
        allowed_imports=("math",),
    ),
    _spec(
        category="data-science",
        name="minmax-scale",
        function_name="minmax_scale",
        source_code=_source(
            '''
            """Scale one finite numeric vector to the closed interval [0, 1]."""

            import math


            def minmax_scale(values: list[float]) -> list[float]:
                """Fit and transform one vector using its minimum and maximum."""

                if not isinstance(values, list):
                    raise TypeError("values must be a list")
                if not values:
                    raise ValueError("values cannot be empty")
                numbers: list[float] = []
                for value in values:
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        raise TypeError("values must contain numbers")
                    number = float(value)
                    if not math.isfinite(number):
                        raise ValueError("values must be finite")
                    numbers.append(number)
                lower = min(numbers)
                upper = max(numbers)
                width = upper - lower
                if width == 0.0:
                    return [0.0 for _ in numbers]
                return [(value - lower) / width for value in numbers]
            '''
        ),
        summary="Fit and transform one finite numeric vector to the interval from zero to one.",
        keywords=("data science", "feature scaling", "min max", "preprocessing"),
        use_cases=(
            "scale a numeric vector before a bounded downstream calculation",
            "normalize heterogeneous numeric ranges",
            "create deterministic zero-to-one features in a sealed training partition",
        ),
        limitations=(
            "Fits and transforms the same vector; do not include held-out data.",
            "Does not reduce the influence of outliers.",
            "Constant vectors map to all zeros and fitted parameters are not retained.",
        ),
        input_name="values",
        input_schema=NUMBER_ARRAY_SCHEMA,
        output_schema=NUMBER_ARRAY_SCHEMA,
        errors=(
            {"type": "TypeError", "when": "values is not a numeric list"},
            {"type": "ValueError", "when": "values is empty or non-finite"},
        ),
        examples=(
            _case("positive", [1, 2, 3], expected=[0.0, 0.5, 1.0]),
            _case("boundary", [5], expected=[0.0]),
            _case("negative", [], error="ValueError"),
        ),
        tests=(
            _case("positive", [-1, 0, 1], expected=[0.0, 0.5, 1.0]),
            _case("boundary", [2, 2, 2], expected=[0.0, 0.0, 0.0]),
            _case("negative", [1, True], error="TypeError"),
        ),
        group_id="taedri.group.data_science_feature_scaling",
        group_labels=(
            "scale numeric vector zero one",
            "feature range normalization",
            "min max preprocessing",
        ),
        documentation=(
            "validates a finite vector, fits its observed minimum and maximum, and maps "
            "the values linearly into `[0.0, 1.0]`, with constants mapped to zero."
        ),
        references=(SKLEARN_MINMAX,),
        allowed_imports=("math",),
    ),
    _spec(
        category="data-science",
        name="zscore-standardize",
        function_name="zscore_standardize",
        source_code=_source(
            '''
            """Standardize one finite vector with population variance."""

            import math


            def zscore_standardize(values: list[float]) -> list[float]:
                """Return zero-mean, unit-population-variance z scores."""

                if not isinstance(values, list):
                    raise TypeError("values must be a list")
                if not values:
                    raise ValueError("values cannot be empty")
                numbers: list[float] = []
                for value in values:
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        raise TypeError("values must contain numbers")
                    number = float(value)
                    if not math.isfinite(number):
                        raise ValueError("values must be finite")
                    numbers.append(number)
                mean = math.fsum(numbers) / len(numbers)
                variance = math.fsum((value - mean) ** 2 for value in numbers) / len(numbers)
                if variance == 0.0:
                    return [0.0 for _ in numbers]
                deviation = math.sqrt(variance)
                return [(value - mean) / deviation for value in numbers]
            '''
        ),
        summary="Standardize one finite numeric vector using population mean and variance.",
        keywords=("data science", "feature scaling", "standardization", "z score"),
        use_cases=(
            "center and scale one numeric training vector",
            "compare observations in standard deviation units",
            "prepare a sealed numeric feature for scale-sensitive algorithms",
        ),
        limitations=(
            "Fits and transforms the same vector; do not include held-out data.",
            "Uses population variance with zero degrees-of-freedom correction.",
            "Constant vectors map to all zeros and fitted parameters are not retained.",
        ),
        input_name="values",
        input_schema=NUMBER_ARRAY_SCHEMA,
        output_schema=NUMBER_ARRAY_SCHEMA,
        errors=(
            {"type": "TypeError", "when": "values is not a numeric list"},
            {"type": "ValueError", "when": "values is empty or non-finite"},
        ),
        examples=(
            _case(
                "positive",
                [1, 2, 3],
                expected=[-1.224744871391589, 0.0, 1.224744871391589],
            ),
            _case("boundary", [5], expected=[0.0]),
            _case("negative", [], error="ValueError"),
        ),
        tests=(
            _case("positive", [-1, 1], expected=[-1.0, 1.0]),
            _case("boundary", [10, 10, 10], expected=[0.0, 0.0, 0.0]),
            _case("negative", [1, True], error="TypeError"),
        ),
        group_id="taedri.group.data_science_feature_scaling",
        group_labels=(
            "z score standardize vector",
            "zero mean unit variance",
            "feature standardization",
        ),
        documentation=(
            "validates a finite vector, computes its population mean and variance, and "
            "returns z scores; zero-variance vectors produce deterministic zeros."
        ),
        references=(SKLEARN_STANDARD,),
        allowed_imports=("math",),
    ),
    _spec(
        category="data-cleaning",
        name="normalize-unicode-nfkc",
        function_name="normalize_unicode_nfkc",
        source_code=_source(
            '''
            """Apply Unicode NFKC compatibility normalization to one string."""

            import unicodedata


            def normalize_unicode_nfkc(value: str) -> str:
                """Return the Unicode NFKC normalization of value."""

                if not isinstance(value, str):
                    raise TypeError("value must be a string")
                return unicodedata.normalize("NFKC", value)
            '''
        ),
        summary="Apply Unicode NFKC compatibility normalization without changing case.",
        keywords=("NFKC", "unicode", "compatibility normalization", "text cleanup"),
        use_cases=(
            "normalize full-width forms before field comparison",
            "replace compatibility characters with canonical equivalents",
            "prepare Unicode text for a later case or identifier operation",
        ),
        limitations=(
            "Compatibility normalization can change presentation distinctions.",
            "Does not trim, case-fold, transliterate, or remove control characters.",
            "Uses the Unicode database bundled with the pinned Python runtime.",
        ),
        input_name="value",
        input_schema=STRING_SCHEMA,
        output_schema=STRING_SCHEMA,
        errors=({"type": "TypeError", "when": "value is not a string"},),
        examples=(
            _case("positive", "Ｆｕｌｌ　Ｎａｍｅ", expected="Full Name"),
            _case("boundary", "", expected=""),
            _case("negative", 1, error="TypeError"),
        ),
        tests=(
            _case("positive", "ﬁle", expected="file"),
            _case("boundary", "Straße", expected="Straße"),
            _case("negative", None, error="TypeError"),
        ),
        group_id="taedri.group.data_cleaning_unicode_normalization",
        group_labels=(
            "unicode NFKC compatibility normalization",
            "normalize full width unicode text",
            "compatibility character normalization",
        ),
        documentation=(
            "applies the Unicode Normalization Form KC algorithm from the pinned "
            "Python Unicode database and otherwise preserves the string."
        ),
        references=(
            "https://docs.python.org/3.12/library/unicodedata.html#unicodedata.normalize",
            "https://www.unicode.org/reports/tr15/",
        ),
        allowed_imports=("unicodedata",),
    ),
    _spec(
        category="data-cleaning",
        name="remove-control-characters",
        function_name="remove_control_characters",
        source_code=_source(
            '''
            """Remove Unicode control-category characters from one string."""

            import unicodedata


            def remove_control_characters(value: str) -> str:
                """Return value without Unicode general category Cc characters."""

                if not isinstance(value, str):
                    raise TypeError("value must be a string")
                return "".join(
                    character
                    for character in value
                    if unicodedata.category(character) != "Cc"
                )
            '''
        ),
        summary="Remove Unicode Cc control characters while preserving visible text.",
        keywords=("control characters", "unicode", "C0", "C1", "data cleaning"),
        use_cases=(
            "remove embedded NUL and terminal control bytes from decoded text",
            "prepare imported text for single-line storage",
            "sanitize control-category characters before deterministic comparison",
        ),
        limitations=(
            "Removes tabs, newlines, and carriage returns as well as hidden controls.",
            "Does not remove Unicode format characters in category Cf.",
            "Input must already be decoded as a Python string.",
        ),
        input_name="value",
        input_schema=STRING_SCHEMA,
        output_schema=STRING_SCHEMA,
        errors=({"type": "TypeError", "when": "value is not a string"},),
        examples=(
            _case("positive", "A\u0000B\u001fC", expected="ABC"),
            _case("boundary", "", expected=""),
            _case("negative", 1, error="TypeError"),
        ),
        tests=(
            _case("positive", "line\nbreak\t", expected="linebreak"),
            _case("boundary", "already visible", expected="already visible"),
            _case("negative", None, error="TypeError"),
        ),
        group_id="taedri.group.data_cleaning_control_characters",
        group_labels=(
            "remove C0 C1 control characters",
            "strip unicode control category text",
            "delete embedded null and control characters",
        ),
        documentation=(
            "filters characters whose Unicode general category is Cc; format, mark, "
            "separator, symbol, punctuation, number, and letter categories remain."
        ),
        references=(
            "https://docs.python.org/3.12/library/unicodedata.html#unicodedata.category",
            "https://www.unicode.org/reports/tr44/",
        ),
        allowed_imports=("unicodedata",),
    ),
    _spec(
        category="data-engineering",
        name="parse-json-object",
        function_name="parse_json_object",
        source_code=_source(
            '''
            """Parse one strict JSON object without duplicate keys or non-finite values."""

            import json


            def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
                result: dict[str, object] = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("JSON object contains a duplicate key")
                    result[key] = value
                return result


            def _constant(value: str) -> object:
                raise ValueError("JSON contains a non-finite number: " + value)


            def parse_json_object(value: str) -> dict[str, object]:
                """Return a strict top-level JSON object."""

                if not isinstance(value, str):
                    raise TypeError("value must be a string")
                try:
                    result = json.loads(
                        value,
                        object_pairs_hook=_object,
                        parse_constant=_constant,
                    )
                except json.JSONDecodeError as exc:
                    raise ValueError("value is not valid JSON") from exc
                if not isinstance(result, dict):
                    raise ValueError("JSON value must be an object")
                return result
            '''
        ),
        summary="Parse a strict top-level JSON object with duplicate-key rejection.",
        keywords=("JSON parser", "object", "duplicate keys", "deserialization"),
        use_cases=(
            "turn a JSON object string into a record primitive can consume",
            "reject duplicate object keys before data transformation",
            "exclude non-finite JavaScript constants from portable JSON",
        ),
        limitations=(
            "Only accepts a top-level object, not an array or scalar.",
            "Loads the complete string into memory.",
            "Does not validate the object against a domain schema.",
        ),
        input_name="value",
        input_schema=STRING_SCHEMA,
        output_schema=OBJECT_SCHEMA,
        errors=(
            {"type": "TypeError", "when": "value is not a string"},
            {"type": "ValueError", "when": "JSON is invalid, duplicated, or not an object"},
        ),
        examples=(
            _case("positive", '{"b":2,"a":1}', expected={"b": 2, "a": 1}),
            _case("boundary", "{}", expected={}),
            _case("negative", "[1,2]", error="ValueError"),
        ),
        tests=(
            _case("positive", '{"outer":{"x":true}}', expected={"outer": {"x": True}}),
            _case("negative", '{"a":1,"a":2}', error="ValueError"),
            _case("negative", None, error="TypeError"),
        ),
        group_id="taedri.group.data_engineering_json_parsing",
        group_labels=(
            "strict JSON object parser",
            "deserialize JSON text to record",
            "parse object and reject duplicate keys",
        ),
        documentation=(
            "uses the standard-library JSON decoder with hooks that reject duplicate "
            "keys and non-finite constants, then requires a top-level object."
        ),
        references=("https://docs.python.org/3.12/library/json.html#json.loads",),
        allowed_imports=("json",),
    ),
    _spec(
        category="data-engineering",
        name="canonical-json-object",
        function_name="canonical_json_object",
        source_code=_source(
            '''
            """Serialize one JSON-compatible object with stable key order and spacing."""

            import json
            import math


            def _validate_json(value: object) -> None:
                if value is None or isinstance(value, (str, bool, int)):
                    return
                if isinstance(value, float):
                    if not math.isfinite(value):
                        raise ValueError("value contains a non-finite number")
                    return
                if isinstance(value, list):
                    for item in value:
                        _validate_json(item)
                    return
                if isinstance(value, dict):
                    if any(not isinstance(key, str) for key in value):
                        raise ValueError("object keys must be strings")
                    for item in value.values():
                        _validate_json(item)
                    return
                raise ValueError("value contains a non-JSON type")


            def canonical_json_object(value: dict[str, object]) -> str:
                """Return compact UTF-8-preserving JSON with recursively sorted keys."""

                if not isinstance(value, dict):
                    raise TypeError("value must be an object")
                _validate_json(value)
                return json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            '''
        ),
        summary="Serialize a JSON-compatible object with stable keys and compact spacing.",
        keywords=("canonical JSON", "serializer", "stable keys", "object"),
        use_cases=(
            "produce deterministic text after record transformations",
            "create stable cache and comparison payloads",
            "serialize Unicode object data without ASCII escaping",
        ),
        limitations=(
            "This is stable JSON output, not the full RFC 8785 number format.",
            "Only accepts a top-level dictionary.",
            "Rejects non-JSON Python values and non-finite numbers.",
        ),
        input_name="value",
        input_schema=OBJECT_SCHEMA,
        output_schema=STRING_SCHEMA,
        errors=(
            {"type": "TypeError", "when": "value is not a dictionary"},
            {"type": "ValueError", "when": "value is not portable finite JSON"},
        ),
        examples=(
            _case("positive", {"b": 2, "a": 1}, expected='{"a":1,"b":2}'),
            _case("boundary", {}, expected="{}"),
            _case("negative", [], error="TypeError"),
        ),
        tests=(
            _case("positive", {"z": {"b": 2, "a": 1}}, expected='{"z":{"a":1,"b":2}}'),
            _case("boundary", {"text": "Straße"}, expected='{"text":"Straße"}'),
            _case("negative", None, error="TypeError"),
        ),
        group_id="taedri.group.data_engineering_json_serialization",
        group_labels=(
            "canonical compact JSON object serializer",
            "serialize record with stable sorted keys",
            "deterministic JSON object text",
        ),
        documentation=(
            "uses sorted recursive object keys, compact separators, UTF-8 characters, "
            "and strict finite-number handling for stable JSON output."
        ),
        references=("https://docs.python.org/3.12/library/json.html#json.dumps",),
        allowed_imports=("json", "math"),
    ),
    _spec(
        category="data-cleaning",
        name="drop-null-fields",
        function_name="drop_null_fields",
        source_code=_source(
            '''
            """Drop top-level record fields whose value is null."""


            def drop_null_fields(value: dict[str, object]) -> dict[str, object]:
                """Return a new object without top-level None values."""

                if not isinstance(value, dict):
                    raise TypeError("value must be an object")
                if any(not isinstance(key, str) for key in value):
                    raise TypeError("object keys must be strings")
                return {key: item for key, item in value.items() if item is not None}
            '''
        ),
        summary="Drop top-level object fields whose value is null while preserving others.",
        keywords=("drop null fields", "record cleaning", "missing values", "object"),
        use_cases=(
            "remove absent optional fields before serialization",
            "prepare sparse API objects that omit null values",
            "clean one decoded JSON record without mutating the input",
        ),
        limitations=(
            "Only removes top-level null values.",
            "Does not remove empty strings, zero, false, empty objects, or empty arrays.",
            "Requires string keys and returns a shallow copy.",
        ),
        input_name="value",
        input_schema=OBJECT_SCHEMA,
        output_schema=OBJECT_SCHEMA,
        errors=(
            {"type": "TypeError", "when": "value is not an object or keys are not strings"},
        ),
        examples=(
            _case("positive", {"a": 1, "b": None}, expected={"a": 1}),
            _case("boundary", {}, expected={}),
            _case("negative", [], error="TypeError"),
        ),
        tests=(
            _case("positive", {"zero": 0, "false": False, "none": None}, expected={"zero": 0, "false": False}),
            _case("boundary", {"nested": {"x": None}}, expected={"nested": {"x": None}}),
            _case("negative", None, error="TypeError"),
        ),
        group_id="taedri.group.data_cleaning_null_fields",
        group_labels=(
            "drop top level null object fields",
            "omit missing fields from record",
            "remove none values from JSON object",
        ),
        documentation=(
            "constructs a new insertion-order-preserving dictionary containing every "
            "top-level field except those whose value is exactly None."
        ),
        references=("https://docs.python.org/3.12/library/stdtypes.html#dict",),
    ),
    _spec(
        category="data-engineering",
        name="coerce-finite-number",
        function_name="coerce_finite_number",
        source_code=_source(
            '''
            """Parse one finite decimal or scientific-notation string as a number."""

            import math
            import re


            _INTEGER = re.compile(r"^[+-]?[0-9]+$")
            _NUMBER = re.compile(
                r"^[+-]?(?:[0-9]+(?:\\.[0-9]+)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?$"
            )


            def coerce_finite_number(value: str) -> int | float:
                """Return an integer when exact integer syntax is used, otherwise float."""

                if not isinstance(value, str):
                    raise TypeError("value must be a string")
                text = value.strip()
                if not text:
                    raise ValueError("value is empty")
                if not _NUMBER.fullmatch(text):
                    raise ValueError("value is not numeric")
                if _INTEGER.fullmatch(text):
                    return int(text)
                try:
                    number = float(text)
                except ValueError as exc:
                    raise ValueError("value is not numeric") from exc
                if not math.isfinite(number):
                    raise ValueError("value must be finite")
                return number
            '''
        ),
        summary="Parse a finite numeric string, preserving exact integer syntax as int.",
        keywords=("numeric coercion", "parse number", "finite", "string adapter"),
        use_cases=(
            "convert a cleaned CSV scalar into a numeric primitive input",
            "reject NaN and infinity during schema adaptation",
            "preserve integer values while accepting decimal and exponent syntax",
        ),
        limitations=(
            "Decimal and exponent syntax is represented as a binary float.",
            "Does not accept thousands separators, currency symbols, or locale formats.",
            "Very large finite-looking values can overflow and are rejected.",
        ),
        input_name="value",
        input_schema=STRING_SCHEMA,
        output_schema=NUMBER_SCHEMA,
        errors=(
            {"type": "TypeError", "when": "value is not a string"},
            {"type": "ValueError", "when": "value is empty, non-numeric, or non-finite"},
        ),
        examples=(
            _case("positive", " 1.25 ", expected=1.25),
            _case("boundary", "-0", expected=0),
            _case("negative", "nan", error="ValueError"),
        ),
        tests=(
            _case("positive", "+12", expected=12),
            _case("boundary", "1e3", expected=1000.0),
            _case("negative", None, error="TypeError"),
        ),
        group_id="taedri.group.data_engineering_numeric_coercion",
        group_labels=(
            "finite numeric string coercion",
            "parse decimal text to number",
            "convert CSV scalar to finite numeric value",
        ),
        documentation=(
            "strips surrounding whitespace, preserves integer syntax with int, parses "
            "other accepted syntax with float, and rejects every non-finite result."
        ),
        references=(
            "https://docs.python.org/3.12/library/functions.html#float",
            "https://docs.python.org/3.12/library/math.html#math.isfinite",
        ),
        allowed_imports=("math", "re"),
    ),
    _spec(
        category="data-engineering",
        name="wrap-flatten-request",
        function_name="wrap_flatten_request",
        source_code=_source(
            '''
            """Adapt one JSON object to the explicit flatten-record request schema."""


            def wrap_flatten_request(value: dict[str, object]) -> dict[str, object]:
                """Return a request that flattens value with the default separator."""

                if not isinstance(value, dict):
                    raise TypeError("value must be an object")
                if any(not isinstance(key, str) for key in value):
                    raise TypeError("object keys must be strings")
                return {"record": value}
            '''
        ),
        summary="Adapt a JSON object to the explicit flatten-record request contract.",
        keywords=("adapter", "flatten request", "record wrapper", "schema conversion"),
        use_cases=(
            "connect a generic parsed JSON object to flatten-record",
            "make the default dotted separator choice explicit in a recipe",
            "avoid generated glue for one common record-schema transition",
        ),
        limitations=(
            "Always selects flatten-record's default dot separator.",
            "Does not copy nested values and does not itself flatten the object.",
            "Requires top-level string keys.",
        ),
        input_name="value",
        input_schema=OBJECT_SCHEMA,
        output_schema=FLATTEN_REQUEST_SCHEMA,
        errors=(
            {"type": "TypeError", "when": "value is not an object or keys are not strings"},
        ),
        examples=(
            _case("positive", {"user": {"id": 7}}, expected={"record": {"user": {"id": 7}}}),
            _case("boundary", {}, expected={"record": {}}),
            _case("negative", [], error="TypeError"),
        ),
        tests=(
            _case("positive", {"a": 1}, expected={"record": {"a": 1}}),
            _case("boundary", {"record": 1}, expected={"record": {"record": 1}}),
            _case("negative", None, error="TypeError"),
        ),
        group_id="taedri.group.data_engineering_flatten_adapter",
        group_labels=(
            "wrap object for flatten record",
            "adapt parsed JSON to flatten request",
            "record schema adapter for flattening",
        ),
        documentation=(
            "wraps a generic object in flatten-record's required request envelope so "
            "the schema transition is a versioned tested primitive rather than glue."
        ),
        references=(
            "https://pandas.pydata.org/docs/reference/api/pandas.json_normalize.html",
        ),
    ),
    _spec(
        category="data-engineering",
        name="format-compact-number",
        function_name="format_compact_number",
        source_code=_source(
            '''
            """Serialize one finite Python number to compact JSON number text."""

            import json
            import math


            def format_compact_number(value: int | float) -> str:
                """Return compact JSON number syntax for one finite number."""

                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise TypeError("value must be a number")
                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError("value must be finite")
                return json.dumps(value, allow_nan=False, separators=(",", ":"))
            '''
        ),
        summary="Format one finite int or float as compact JSON number text.",
        keywords=("format number", "JSON number", "serialization", "numeric adapter"),
        use_cases=(
            "convert a computed number into a portable text field",
            "serialize numeric pipeline output without surrounding whitespace",
            "reject non-finite values before text output",
        ),
        limitations=(
            "Uses Python's pinned JSON float representation, not locale formatting.",
            "Does not add units, precision padding, or thousands separators.",
            "Boolean values are rejected even though bool subclasses int in Python.",
        ),
        input_name="value",
        input_schema=NUMBER_SCHEMA,
        output_schema=STRING_SCHEMA,
        errors=(
            {"type": "TypeError", "when": "value is not an int or float"},
            {"type": "ValueError", "when": "value is not finite"},
        ),
        examples=(
            _case("positive", 1.25, expected="1.25"),
            _case("boundary", 0, expected="0"),
            _case("negative", True, error="TypeError"),
        ),
        tests=(
            _case("positive", -3, expected="-3"),
            _case("boundary", 1.0, expected="1.0"),
            _case("negative", "1", error="TypeError"),
        ),
        group_id="taedri.group.data_engineering_numeric_formatting",
        group_labels=(
            "compact finite number formatting",
            "serialize numeric value to JSON text",
            "format computed number without locale",
        ),
        documentation=(
            "validates the Python numeric type and finiteness, then uses the pinned "
            "standard-library JSON encoder to produce one compact number token."
        ),
        references=("https://docs.python.org/3.12/library/json.html#json.dumps",),
        allowed_imports=("json", "math"),
    ),
    _spec(
        category="data-science",
        name="numeric-sum",
        function_name="numeric_sum",
        source_code=_source(
            '''
            """Accurately sum one non-empty finite numeric vector."""

            import math


            def numeric_sum(values: list[int | float]) -> float:
                """Return math.fsum over a validated finite numeric list."""

                if not isinstance(values, list):
                    raise TypeError("values must be a list")
                if not values:
                    raise ValueError("values cannot be empty")
                numbers: list[float] = []
                for value in values:
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        raise TypeError("values must contain numbers")
                    try:
                        number = float(value)
                    except OverflowError as exc:
                        raise ValueError("values must be finite") from exc
                    if not math.isfinite(number):
                        raise ValueError("values must be finite")
                    numbers.append(number)
                return math.fsum(numbers)
            '''
        ),
        summary="Accurately sum a non-empty finite numeric vector with math.fsum.",
        keywords=("numeric sum", "aggregation", "fsum", "data science"),
        use_cases=(
            "aggregate a validated numeric vector",
            "reduce floating-point error relative to repeated addition",
            "compute a deterministic total before formatting or comparison",
        ),
        limitations=(
            "Returns a float even when every input is an integer.",
            "Rejects empty, Boolean, and non-finite values.",
            "Processes one in-memory list and does not stream.",
        ),
        input_name="values",
        input_schema=NUMBER_ARRAY_SCHEMA,
        output_schema=NUMBER_SCHEMA,
        errors=(
            {"type": "TypeError", "when": "values is not a numeric list"},
            {"type": "ValueError", "when": "values is empty or non-finite"},
        ),
        examples=(
            _case("positive", [1, 2, 3], expected=6.0),
            _case("boundary", [0], expected=0.0),
            _case("negative", [], error="ValueError"),
        ),
        tests=(
            _case("positive", [-1, 1], expected=0.0),
            _case("boundary", [0.1, 0.2, 0.3], expected=0.6),
            _case("negative", [1, True], error="TypeError"),
        ),
        group_id="taedri.group.data_science_numeric_aggregation",
        group_labels=(
            "accurate finite numeric sum",
            "aggregate numeric vector total",
            "floating point fsum reduction",
        ),
        documentation=(
            "validates a non-empty finite numeric list and applies math.fsum for a "
            "more accurate deterministic total than repeated binary addition."
        ),
        references=("https://docs.python.org/3.12/library/math.html#math.fsum",),
        allowed_imports=("math",),
    ),
    _spec(
        category="data-science",
        name="l2-normalize",
        function_name="l2_normalize",
        source_code=_source(
            '''
            """Normalize one finite numeric vector to unit Euclidean length."""

            import math


            def l2_normalize(values: list[int | float]) -> list[float]:
                """Return a unit-L2 vector, or deterministic zeros for a zero vector."""

                if not isinstance(values, list):
                    raise TypeError("values must be a list")
                if not values:
                    raise ValueError("values cannot be empty")
                numbers: list[float] = []
                for value in values:
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        raise TypeError("values must contain numbers")
                    try:
                        number = float(value)
                    except OverflowError as exc:
                        raise ValueError("values must be finite") from exc
                    if not math.isfinite(number):
                        raise ValueError("values must be finite")
                    numbers.append(number)
                norm = math.sqrt(math.fsum(value * value for value in numbers))
                if norm == 0.0:
                    return [0.0 for _ in numbers]
                return [value / norm for value in numbers]
            '''
        ),
        summary="Normalize a finite numeric vector to unit Euclidean length.",
        keywords=("L2 normalization", "unit vector", "Euclidean norm", "data science"),
        use_cases=(
            "normalize one feature or embedding vector before cosine comparison",
            "convert a nonzero vector to unit Euclidean length",
            "handle an all-zero vector without division by zero",
        ),
        limitations=(
            "Does not center features or retain a fitted transformer.",
            "A zero vector remains a zero vector rather than becoming unit length.",
            "Processes one non-empty in-memory vector.",
        ),
        input_name="values",
        input_schema=NUMBER_ARRAY_SCHEMA,
        output_schema=NUMBER_ARRAY_SCHEMA,
        errors=(
            {"type": "TypeError", "when": "values is not a numeric list"},
            {"type": "ValueError", "when": "values is empty or non-finite"},
        ),
        examples=(
            _case("positive", [3, 4], expected=[0.6, 0.8]),
            _case("boundary", [0, 0], expected=[0.0, 0.0]),
            _case("negative", [], error="ValueError"),
        ),
        tests=(
            _case("positive", [-5], expected=[-1.0]),
            _case("boundary", [1, 0], expected=[1.0, 0.0]),
            _case("negative", [1, True], error="TypeError"),
        ),
        group_id="taedri.group.data_science_vector_normalization",
        group_labels=(
            "unit L2 vector normalization",
            "normalize vector Euclidean length",
            "prepare vector for cosine similarity",
        ),
        documentation=(
            "validates finite numeric values, computes the Euclidean norm with fsum, "
            "divides nonzero vectors by that norm, and preserves zero vectors."
        ),
        references=(
            "https://docs.python.org/3.12/library/math.html#math.fsum",
            "https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.normalize.html",
        ),
        allowed_imports=("math",),
    ),
)


SEARCH_QUERIES = {
    "collapse-whitespace": "collapse internal whitespace",
    "normalize-column-name": "normalize dataframe column header",
    "stable-deduplicate": "stable duplicate removal",
    "flatten-record": "flatten nested record",
    "chunk-sequence": "batch sequence chunks",
    "normalize-null-marker": "normalize null markers",
    "normalize-iso-datetime": "normalize ISO datetime to UTC",
    "numeric-mean": "arithmetic mean numeric vector",
    "numeric-median": "robust median numeric vector",
    "minmax-scale": "scale numeric vector zero one",
    "zscore-standardize": "z score standardize vector",
    "normalize-unicode-nfkc": "unicode NFKC compatibility normalization",
    "remove-control-characters": "remove C0 C1 control characters",
    "parse-json-object": "strict JSON object parser",
    "canonical-json-object": "canonical compact JSON object serializer",
    "drop-null-fields": "drop top level null object fields",
    "coerce-finite-number": "finite numeric string coercion",
    "wrap-flatten-request": "wrap object for flatten record",
    "format-compact-number": "compact finite number formatting",
    "numeric-sum": "accurate finite numeric sum",
    "l2-normalize": "unit L2 vector normalization",
}


def _record(
    spec: PrimitiveAuthoringSpec,
    path: Path,
    inspected: InspectedPrimitiveDirectory,
) -> dict[str, object]:
    return {
        "category": spec.category,
        "namespace": spec.namespace,
        "name": spec.name,
        "path": (
            path.relative_to(ROOT).as_posix()
            if path.is_relative_to(ROOT)
            else path.as_posix()
        ),
        "tree_id": inspected.tree_id,
        "source_digest": inspected.artifacts.source_digest,
        "executed_case_count": (
            inspected.artifacts.example_count
            + inspected.artifacts.test_case_count
        ),
        "edge_count": inspected.artifacts.interface_edge_count,
        "port_count": inspected.artifacts.interface_port_count,
        "group_count": inspected.artifacts.capability_group_count,
        "search_query": SEARCH_QUERIES[spec.name],
    }


def generate(destination: Path) -> tuple[dict[str, object], ...]:
    records: list[dict[str, object]] = []
    for spec in COHORT:
        path = destination / spec.category / spec.name
        inspected = render_primitive_directory(spec, path)
        records.append(_record(spec, path, inspected))
    return tuple(records)


def check(destination: Path) -> tuple[dict[str, object], ...]:
    """Verify checked-in capsules match their strict specifications byte-for-byte."""

    records: list[dict[str, object]] = []
    for spec in COHORT:
        path = destination / spec.category / spec.name
        expected = build_primitive_files(spec)
        if not path.is_dir() or path.is_symlink():
            raise PrimitiveAuthoringError(
                f"generated primitive directory is missing or unsafe: {path}"
            )
        actual_paths = {
            item.relative_to(path).as_posix()
            for item in path.rglob("*")
            if item.is_file() or item.is_symlink()
        }
        if actual_paths != set(expected):
            missing = sorted(set(expected) - actual_paths)
            unexpected = sorted(actual_paths - set(expected))
            raise PrimitiveAuthoringError(
                f"generated primitive tree drift for {spec.name}; "
                f"missing={missing!r}; unexpected={unexpected!r}"
            )
        for relative, content in expected.items():
            target = path / relative
            if target.is_symlink() or target.read_bytes() != content:
                raise PrimitiveAuthoringError(
                    f"generated primitive content drift: {spec.name}/{relative}"
                )
        records.append(_record(spec, path, inspect_primitive_directory(path)))
    return tuple(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--destination",
        type=Path,
        default=ROOT / "examples/primitives",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify generated capsules exactly without rewriting them",
    )
    arguments = parser.parse_args()
    destination = arguments.destination.resolve()
    records = check(destination) if arguments.check else generate(destination)
    print(
        json.dumps(
            {
                "status": (
                    "checked-exact" if arguments.check else "generated-and-validated"
                ),
                "primitive_count": len(records),
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
