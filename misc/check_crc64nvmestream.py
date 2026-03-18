#!/usr/bin/env python3
from awscrt import checksums
import base64
import os
import sys

def calculate_crc64nvme_stream(file_path: str, chunk_size: int = 16 * 1024 * 1024) -> str:
    """
    Calculate CRC64-NVME of a file by streaming in chunks.
    Returns the Base64-encoded checksum (8-byte big-endian), and also prints hex/decimal.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    crc = 0  # initial value
    total = 0

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            # Incremental update: pass previous CRC into the next call
            crc = checksums.crc64nvme(chunk, previous_crc64nvme=crc)  # incremental API
            total += len(chunk)

    # Convert final CRC (unsigned 64-bit int) to 8 bytes, big-endian, then Base64
    checksum_bytes = crc.to_bytes(8, byteorder="big", signed=False)
    checksum_base64 = base64.b64encode(checksum_bytes).decode("utf-8")

    # Hex form (zero-padded to 16 chars)
    checksum_hex = hex(crc)[2:].upper().zfill(16)

    print(f"File: {file_path}")
    print(f"Size: {total:,} bytes")
    print(f"CRC64NVME (Base64): {checksum_base64}")
    print(f"CRC64NVME (Hex): {checksum_hex}")
    print(f"CRC64NVME (Decimal): {crc}")

    return checksum_base64

if __name__ == "__main__":
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python crc64nvme_stream.py <file_path> [chunk_size_bytes]")
        sys.exit(1)

    path = sys.argv[1]
    chunk = int(sys.argv[2]) if len(sys.argv) == 3 else 16 * 1024 * 1024
    try:
        calculate_crc64nvme_stream(path, chunk)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
