from awscrt import checksums
import base64

def calculate_aws_crc32_streaming(file_path, chunk_size=8 * 1024 * 1024):
    crc = 0  # initial value for AWS CRC32

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            crc = checksums.crc32(chunk, crc)  # incremental update

    # Convert to Base64 (AWS format)
    crc_bytes = crc.to_bytes(4, byteorder='big')
    crc_base64 = base64.b64encode(crc_bytes).decode('utf-8')

    print(f"File: {file_path}")
    print(f"AWS CRC32 (Decimal): {crc}")
    print(f"AWS CRC32 (Hex): {crc:08X}")
    print(f"AWS CRC32 (Base64): {crc_base64}")

    return crc, crc_base64


# Usage
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python crc32.py <file_path>")
        sys.exit(1)

    file_path = sys.argv[1]
    calculate_aws_crc32_streaming(file_path)

