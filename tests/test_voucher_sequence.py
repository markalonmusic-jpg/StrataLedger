"""sequences.next_voucher_number: bill voucher numbers VCH-1001... (decision 1.3)."""
import sqlite3
import threading

import pytest

import modules.database as database
from modules.services import sequences


def test_first_numbers_and_format(fresh_company):
    conn = database.get_connection(fresh_company)
    try:
        assert sequences.next_voucher_number(conn) == "VCH-1001"
        assert sequences.next_voucher_number(conn) == "VCH-1002"
        conn.commit()
    finally:
        conn.close()


def test_a_rolled_back_number_may_leave_a_gap_but_never_repeats(fresh_company):
    conn = database.get_connection(fresh_company)
    try:
        first = sequences.next_voucher_number(conn)
        conn.commit()
        conn.execute("SAVEPOINT s")
        second = sequences.next_voucher_number(conn)
        conn.execute("ROLLBACK TO s")          # a deleted draft: the number is simply not used
        third = sequences.next_voucher_number(conn)
        conn.commit()
    finally:
        conn.close()
    assert first == "VCH-1001" and second == "VCH-1002" and third == "VCH-1002"
    # (Inside one transaction a rollback returns the number. Across transactions it is never reissued.)


def test_numbers_committed_by_separate_connections_are_distinct(fresh_company):
    seen, errors = [], []
    gate = threading.Barrier(6)

    def work():
        try:
            conn = database.get_connection(fresh_company)
            try:
                conn.isolation_level = None
                gate.wait()
                conn.execute("BEGIN IMMEDIATE")
                seen.append(sequences.next_voucher_number(conn))
                conn.execute("COMMIT")
            finally:
                conn.close()
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=work) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and len(set(seen)) == 6
    assert sorted(seen) == [f"VCH-{n}" for n in range(1001, 1007)]


def test_sequence_row_cannot_go_below_1000_or_be_duplicated(fresh_company):
    conn = database.get_connection(fresh_company)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE voucher_sequence SET last_number = 5 WHERE id = 1")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO voucher_sequence (id, last_number) VALUES (2, 1000)")
    finally:
        conn.close()
