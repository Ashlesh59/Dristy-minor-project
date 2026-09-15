"""
services/importer/zip_reader.py
--------------------------------------------------------------------------
Secure, in-memory ZIP and CSV reader for exchange archive feeds.
--------------------------------------------------------------------------
"""

import csv
import hashlib
import io
import os
import zipfile


class ZipArchiveError(Exception):
    """Raised when a ZIP archive is corrupt, missing, or insecure."""
    pass


def compute_file_sha256(file_path: str) -> str:
    """
    Computes the SHA-256 checksum of a file without loading the entire
    file into memory at once.
    """
    if not os.path.exists(file_path):
        raise ZipArchiveError(f"Archive file not found: {file_path}")

    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest().upper()


def read_bhavcopy_zip(file_path: str):
    """
    Safely inspects and streams the single CSV contents from a Bhavcopy ZIP archive.
    
    Returns:
        tuple: (file_sha256: str, csv_reader: csv.DictReader, total_uncompressed_bytes: int)
    
    Raises:
        ZipArchiveError: On invalid, corrupt, ambiguous, or malicious ZIP archives.
    """
    if not os.path.exists(file_path):
        raise ZipArchiveError(f"File does not exist: {file_path}")

    if not zipfile.is_zipfile(file_path):
        raise ZipArchiveError(f"Specified file is not a valid ZIP archive: {file_path}")

    file_sha256 = compute_file_sha256(file_path)

    try:
        zf = zipfile.ZipFile(file_path, "r")
    except Exception as e:
        raise ZipArchiveError(f"Could not open ZIP archive: {e}")

    # Test archive integrity
    bad_file = zf.testzip()
    if bad_file:
        raise ZipArchiveError(f"Corrupt file detected in ZIP archive: {bad_file}")

    # Inspect members for security and data CSV location
    csv_members = []
    for info in zf.infolist():
        name = info.filename
        # Check for path-traversal or absolute path attempts
        if ".." in name or name.startswith("/") or name.startswith("\\") or (len(name) > 1 and name[1] == ":"):
            raise ZipArchiveError(f"Malicious path-traversal detected in ZIP archive entry: {name}")

        # Ignore directory entries or hidden files (e.g. __MACOSX)
        if info.is_dir() or name.startswith("__MACOSX") or name.startswith("."):
            continue

        if name.lower().endswith(".csv"):
            csv_members.append(info)

    if not csv_members:
        raise ZipArchiveError("No CSV data file found in the ZIP archive.")

    if len(csv_members) > 1:
        raise ZipArchiveError(
            f"Ambiguous archive: multiple CSV files found ({len(csv_members)} CSVs: "
            f"{', '.join(m.filename for m in csv_members)})."
        )

    target_info = csv_members[0]

    # Open target CSV in memory using streaming text wrapper with utf-8-sig
    try:
        raw_stream = zf.open(target_info, "r")
        # TextIOWrapper decodes bytes to strings on the fly with UTF-8 BOM handling
        text_stream = io.TextIOWrapper(raw_stream, encoding="utf-8-sig", newline="")
    except Exception as e:
        raise ZipArchiveError(f"Failed to read CSV stream from archive entry {target_info.filename}: {e}")

    # Create CSV DictReader with stripped fieldnames
    csv_reader = csv.DictReader(text_stream)
    if csv_reader.fieldnames:
        csv_reader.fieldnames = [
            fn.strip() if fn is not None else "" for fn in csv_reader.fieldnames
        ]

    return file_sha256, csv_reader, zf
