"""csv_table.py: the generic CSV parser the chart templates and the CSV import share."""
import pytest

from modules.services import csv_table
from modules.services.csv_table import CsvError, parse_table
from modules.services.errors import ValidationError


def test_parses_rows_with_row_numbers():
    table = parse_table("a,b\n1,2\n3,4\n", required=["a", "b"])
    assert table.rows == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]
    assert table.row_numbers == [2, 3]


def test_bom_and_crlf_and_blank_lines():
    table = parse_table("﻿a,b\r\n1,2\r\n\r\n,\r\n3,4\r\n", required=["a", "b"])
    assert [r["a"] for r in table.rows] == ["1", "3"]
    assert table.row_numbers == [2, 5]          # row numbers are file lines, blank ones included


def test_header_is_case_and_space_insensitive_and_text_is_trimmed():
    table = parse_table(" Name , Code \n  Ann ,  A1  \n", required=["name", "code"])
    assert table.rows == [{"name": "Ann", "code": "A1"}]


def test_optional_columns_default_to_empty_text():
    table = parse_table("a\n1\n", required=["a"], optional=["b"])
    assert table.rows == [{"a": "1", "b": ""}]


def test_quoted_commas_and_newlines_are_kept():
    table = parse_table('a,b\n"x, y","line1\nline2"\n', required=["a", "b"])
    assert table.rows[0] == {"a": "x, y", "b": "line1\nline2"}


def test_missing_required_column_is_one_plain_error():
    with pytest.raises(CsvError) as caught:
        parse_table("a\n1\n", required=["a", "b"])
    assert [(e.row, e.column) for e in caught.value.errors] == [(1, "b")]
    assert "b" in str(caught.value) and "missing" in str(caught.value).lower()


def test_unknown_column_is_an_error():
    with pytest.raises(CsvError) as caught:
        parse_table("a,zzz\n1,2\n", required=["a"])
    assert caught.value.errors[0].column == "zzz"


def test_duplicate_column_is_an_error():
    with pytest.raises(CsvError):
        parse_table("a,a\n1,2\n", required=["a"])


def test_ragged_row_is_reported_with_its_row_number():
    with pytest.raises(CsvError) as caught:
        parse_table("a,b\n1,2\n3\n", required=["a", "b"])
    assert caught.value.errors[0].row == 3


def test_empty_file_and_header_only():
    with pytest.raises(CsvError):
        parse_table("", required=["a"])
    assert parse_table("a\n", required=["a"]).rows == []


def test_row_limit():
    text = "a\n" + "1\n" * 6
    assert len(parse_table(text, required=["a"], max_rows=6).rows) == 6
    with pytest.raises(CsvError) as caught:
        parse_table(text, required=["a"], max_rows=5)
    assert "5" in str(caught.value)


def test_errors_are_validation_errors_and_carry_everything():
    err = csv_table.RowError(7, "amount", "Enter a number")
    assert (err.row, err.column, err.message) == (7, "amount", "Enter a number")
    assert issubclass(CsvError, ValidationError)
    assert CsvError([err]).errors == [err]
    assert "Row 7" in str(CsvError([err])) and "amount" in str(CsvError([err]))


def test_leading_formula_characters_stay_plain_text():
    table = parse_table("a\n=1+1\n+5\n-3\n@x\n", required=["a"])
    assert [r["a"] for r in table.rows] == ["=1+1", "+5", "-3", "@x"]
