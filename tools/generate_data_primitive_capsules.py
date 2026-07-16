#!/usr/bin/env python3
"""Materialize a curated cohort of complete data utility primitives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from textwrap import dedent

from taedri_codegraph.primitives.authoring import (
    PrimitiveAuthoringSpec,
    render_primitive_directory,
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
        input_schema={
            "type": "object",
            "required": ["record"],
            "properties": {
                "record": {"type": "object"},
                "separator": {"type": "string"},
            },
            "additionalProperties": False,
        },
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
)


SEARCH_QUERIES = {
    "collapse-whitespace": "collapse internal whitespace",
    "normalize-column-name": "normalize dataframe column header",
    "stable-deduplicate": "stable duplicate removal",
    "flatten-record": "flatten nested record",
    "chunk-sequence": "batch sequence chunks",
    "numeric-mean": "arithmetic mean numeric vector",
    "numeric-median": "robust median numeric vector",
    "minmax-scale": "scale numeric vector zero one",
    "zscore-standardize": "z score standardize vector",
}


def generate(destination: Path) -> tuple[dict[str, object], ...]:
    records: list[dict[str, object]] = []
    for spec in COHORT:
        path = destination / spec.category / spec.name
        inspected = render_primitive_directory(spec, path)
        records.append(
            {
                "category": spec.category,
                "namespace": spec.namespace,
                "name": spec.name,
                "path": path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix(),
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
        )
    return tuple(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--destination",
        type=Path,
        default=ROOT / "examples/primitives",
    )
    arguments = parser.parse_args()
    destination = arguments.destination.resolve()
    records = generate(destination)
    print(
        json.dumps(
            {
                "status": "generated-and-validated",
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
