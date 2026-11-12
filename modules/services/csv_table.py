"""A small, strict CSV reader shared by the chart templates and the CSV import (docs/csv_import_design.md).

It knows nothing about accounting. It checks the header, trims text, skips blank lines and reports
every problem with its row number and column in plain language. A formula-looking value such as
"=1+1" stays plain text. No SQL, no files: the caller passes the text.
"""
import csv
import io
from collections import namedtuple

from modules.services.errors import ValidationError

DEFAULT_MAX_ROWS = 50000

RowError = namedtuple("RowError", "row column message")
Table = namedtuple("Table", "columns rows row_numbers")


class CsvError(ValidationError):
    """One or more problems in a CSV file; `errors` is the list of RowError."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self._describe(e) for e in self.errors[:20])
                         + (f"; and {len(self.errors) - 20} more" if len(self.errors) > 20 else ""))

    @staticmethod
    def _describe(error):
        where = f"Row {error.row}" if error.row else "The file"
        column = f", column '{error.column}'" if error.column else ""
        return f"{where}{column}: {error.message}"


def _key(name):
    return " ".join((name or "").strip().lower().split())


def parse_table(text, required, optional=(), max_rows=DEFAULT_MAX_ROWS):
    """Parse CSV text into a Table of dict rows keyed by the canonical column names.

    `required` and `optional` give the canonical (lowercase) names. Header matching ignores case and
    extra spaces. Unknown or repeated columns, ragged rows and too many rows are errors. Row numbers
    are file line numbers (the header is row 1).
    """
    text = (text or "").lstrip("﻿")
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration:
        raise CsvError([RowError(0, None, "The file is empty")]) from None
    allowed = {_key(c): c for c in list(required) + list(optional)}
    errors, positions = [], {}
    for index, raw in enumerate(header):
        canonical = allowed.get(_key(raw))
        if canonical is None:
            errors.append(RowError(1, raw.strip(), f"'{raw.strip()}' is not a column this file may have"))
        elif canonical in positions:
            errors.append(RowError(1, canonical, f"The column '{canonical}' appears more than once"))
        else:
            positions[canonical] = index
    for name in required:
        if name not in positions:
            errors.append(RowError(1, name, f"The column '{name}' is missing"))
    if errors:
        raise CsvError(errors)

    rows, numbers = [], []
    for values in reader:
        line = reader.line_num
        if not any(v.strip() for v in values):
            continue
        if len(rows) >= max_rows:
            raise CsvError([RowError(line, None, f"The file has more than {max_rows} rows")])
        if len(values) != len(header):
            errors.append(RowError(line, None, f"This row has {len(values)} values; the header has {len(header)}"))
            continue
        rows.append({name: values[pos].strip() for name, pos in positions.items()})
        numbers.append(line)
    if errors:
        raise CsvError(errors)
    for name in optional:
        for row in rows:
            row.setdefault(name, "")
    columns = [c for c in list(required) + list(optional) if c in positions or c in optional]
    return Table(columns, rows, numbers)
