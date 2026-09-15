"""
services/importer/csv_reader.py
--------------------------------------------------------------------------
Robust, memory-efficient CSV file reader with BOM handling, whitespace
stripping on headers and cells, and SHA-256 calculation.
--------------------------------------------------------------------------
"""

import csv
import hashlib
import io
import os


class CSVReadResult:
    def __init__(self, file_sha256, headers, rows, total_raw_rows):
        self.file_sha256 = file_sha256
        self.headers = headers
        self.rows = rows
        self.total_raw_rows = total_raw_rows


def calculate_file_sha256(file_path: str) -> str:
    """Computes SHA-256 hex digest of a file in 64KB chunks."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest().upper()


def read_nse_csv(file_path: str) -> CSVReadResult:
    """
    Reads an NSE CSV file with UTF-8 / UTF-8-sig encoding.
    Strips whitespace from headers and cell values.
    Returns sanitized headers, raw row dictionaries, and SHA-256.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Source file not found: {file_path}")

    file_sha256 = calculate_file_sha256(file_path)

    # Read with utf-8-sig to automatically handle any UTF-8 BOM
    with open(file_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        try:
            raw_headers = next(reader)
        except StopIteration:
            return CSVReadResult(file_sha256=file_sha256, headers=[], rows=[], total_raw_rows=0)

        # Strip whitespace from each header string
        sanitized_headers = [h.strip() for h in raw_headers if h is not None]

        rows = []
        for line_num, row_values in enumerate(reader, start=2):
            # Skip empty lines
            if not row_values or all(not str(v).strip() for v in row_values):
                continue
            
            # Map header -> stripped cell value
            row_dict = {}
            for i, header in enumerate(sanitized_headers):
                val = row_values[i].strip() if i < len(row_values) else ""
                row_dict[header] = val

            rows.append(row_dict)

    return CSVReadResult(
        file_sha256=file_sha256,
        headers=sanitized_headers,
        rows=rows,
        total_raw_rows=len(rows),
    )
