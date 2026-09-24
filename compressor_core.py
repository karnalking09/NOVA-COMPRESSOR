import zstandard as zstd
import hashlib
import time
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB


# ============================================================
# COMPRESSION PROFILES
# ============================================================

COMPRESSION_PROFILES = {
    "FAST": 1,
    "BALANCED": 5,
    "MAXIMUM": 19,
}


def get_compression_level(profile):
    """
    Convert a compression profile name into a Zstandard level.

    FAST      -> Level 1
    BALANCED  -> Level 5
    MAXIMUM   -> Level 19
    """

    if profile is None:
        return None

    profile = str(profile).upper().strip()

    if profile not in COMPRESSION_PROFILES:
        raise ValueError(
            f"Unknown compression profile: {profile}. "
            f"Available profiles: {', '.join(COMPRESSION_PROFILES.keys())}"
        )

    return COMPRESSION_PROFILES[profile]


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def format_size(size):
    units = ["B", "KB", "MB", "GB", "TB"]

    for unit in units:

        if size < 1024:
            return f"{size:.2f} {unit}"

        size /= 1024

    return f"{size:.2f} PB"


def sha256_file(path):

    sha = hashlib.sha256()

    with open(path, "rb"):

        # Re-open below to keep the code explicit and reliable
        pass

    with open(path, "rb") as f:

        while True:

            chunk = f.read(CHUNK_SIZE)

            if not chunk:
                break

            sha.update(chunk)

    return sha.hexdigest()


# ============================================================
# ADAPTIVE COMPRESSION ANALYSIS
# ============================================================

def analyze_file(path):

    SAMPLE_SIZE = 16 * 1024 * 1024

    with open(path, "rb") as f:
        sample = f.read(SAMPLE_SIZE)

    if not sample:
        return 1

    compressor = zstd.ZstdCompressor(level=1)

    compressed = compressor.compress(sample)

    ratio = len(compressed) / len(sample)

    if ratio < 0.10:
        return 3

    elif ratio < 0.30:
        return 5

    elif ratio < 0.60:
        return 9

    elif ratio < 0.90:
        return 3

    else:
        return 1


# ============================================================
# COMPRESSION
# ============================================================

def compress_file(
    input_path,
    output_path=None,
    profile=None
):

    source = Path(input_path)

    if not source.exists():
        raise FileNotFoundError(
            f"File not found: {source}"
        )

    if not source.is_file():
        raise ValueError(
            f"Not a file: {source}"
        )

    if output_path is None:

        output = Path(
            str(source) + ".zst"
        )

    else:

        output = Path(output_path)

    # --------------------------------------------------------
    # SELECT COMPRESSION LEVEL
    # --------------------------------------------------------

    if profile is not None:

        profile = str(profile).upper().strip()

        level = get_compression_level(profile)

        profile_name = profile

    else:

        # Keep existing adaptive behavior
        level = analyze_file(source)

        profile_name = "ADAPTIVE"

    # --------------------------------------------------------
    # BASIC INFORMATION
    # --------------------------------------------------------

    original_size = source.stat().st_size

    print("\n" + "=" * 70)
    print("NOVA COMPRESSOR")
    print("FILE COMPRESSION")
    print("=" * 70)

    print("Input       :", source)
    print("Original    :", format_size(original_size))
    print("Profile     :", profile_name)
    print("Zstd Level  :", level)

    # --------------------------------------------------------
    # ORIGINAL SHA-256
    # --------------------------------------------------------

    print("Calculating SHA-256...")

    original_hash = sha256_file(source)

    print("SHA-256     :", original_hash)

    # --------------------------------------------------------
    # COMPRESSION
    # --------------------------------------------------------

    compressor = zstd.ZstdCompressor(
        level=level
    )

    start = time.time()
    processed = 0

    with open(source, "rb") as fin:

        with open(output, "wb") as fout:

            with compressor.stream_writer(fout) as writer:

                while True:

                    chunk = fin.read(CHUNK_SIZE)

                    if not chunk:
                        break

                    writer.write(chunk)

                    processed += len(chunk)

                    elapsed = time.time() - start

                    speed = (
                        processed / elapsed
                        if elapsed > 0
                        else 0
                    )

                    if original_size > 0:

                        percent = (
                            processed /
                            original_size *
                            100
                        )

                    else:

                        percent = 100

                    remaining = (
                        original_size -
                        processed
                    )

                    eta = (
                        remaining / speed
                        if speed > 0
                        else 0
                    )

                    print(
                        f"\rProgress: {percent:6.2f}% | "
                        f"Speed: {format_size(speed)}/s | "
                        f"ETA: {eta:6.1f}s",
                        end=""
                    )

    elapsed = time.time() - start

    compressed_size = output.stat().st_size

    # --------------------------------------------------------
    # STATISTICS
    # --------------------------------------------------------

    if original_size > 0:

        reduction = (
            1 -
            compressed_size /
            original_size
        ) * 100

    else:

        reduction = 0

    if compressed_size > 0:

        ratio = (
            original_size /
            compressed_size
        )

    else:

        ratio = 0

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    print("\n")

    print("=" * 70)
    print("COMPRESSION COMPLETE")
    print("=" * 70)

    print(
        "Profile    :",
        profile_name
    )

    print(
        "Zstd Level :",
        level
    )

    print(
        "Original   :",
        format_size(original_size)
    )

    print(
        "Compressed :",
        format_size(compressed_size)
    )

    print(
        "Reduction  :",
        f"{reduction:.4f}%"
    )

    print(
        "Ratio      :",
        f"{ratio:.2f}:1"
    )

    print(
        "Time       :",
        f"{elapsed:.2f} sec"
    )

    print(
        "Output     :",
        output
    )

    print("=" * 70)

    return {
        "input": source,
        "output": output,
        "profile": profile_name,
        "level": level,
        "original_size": original_size,
        "compressed_size": compressed_size,
        "reduction": reduction,
        "ratio": ratio,
        "time": elapsed,
        "sha256": original_hash,
    }


# ============================================================
# DECOMPRESSION
# ============================================================

def decompress_file(
    input_path,
    output_path=None
):

    compressed = Path(input_path)

    if not compressed.exists():

        raise FileNotFoundError(
            f"Compressed file not found: {compressed}"
        )

    if output_path is None:

        if compressed.name.endswith(".zst"):

            output = Path(
                str(compressed)[:-4]
            )

        else:

            output = Path(
                str(compressed) + ".restored"
            )

    else:

        output = Path(output_path)

    print("\n" + "=" * 70)
    print("NOVA COMPRESSOR")
    print("FILE DECOMPRESSION")
    print("=" * 70)

    print("Input :", compressed)
    print("Output:", output)

    decompressor = zstd.ZstdDecompressor()

    start = time.time()
    restored_size = 0

    with open(compressed, "rb") as fin:

        with open(output, "wb") as fout:

            with decompressor.stream_reader(fin) as reader:

                while True:

                    chunk = reader.read(CHUNK_SIZE)

                    if not chunk:
                        break

                    fout.write(chunk)

                    restored_size += len(chunk)

    elapsed = time.time() - start

    speed = (
        restored_size / elapsed
        if elapsed > 0
        else 0
    )

    print("\n" + "=" * 70)
    print("DECOMPRESSION COMPLETE")
    print("=" * 70)

    print(
        "Restored size :",
        format_size(restored_size)
    )

    print(
        "Time          :",
        f"{elapsed:.2f} sec"
    )

    print(
        "Speed         :",
        f"{format_size(speed)}/s"
    )

    print(
        "Output        :",
        output
    )

    print("=" * 70)

    return {
        "output": output,
        "size": restored_size,
        "time": elapsed,
    }


# ============================================================
# SHA-256 VERIFICATION
# ============================================================

def verify_file(original, restored):

    print("\n" + "=" * 70)
    print("SHA-256 VERIFICATION")
    print("=" * 70)

    print("Calculating original SHA-256...")

    original_hash = sha256_file(original)

    print("Original SHA-256:")
    print(original_hash)

    print("\nCalculating restored SHA-256...")

    restored_hash = sha256_file(restored)

    print("Restored SHA-256:")
    print(restored_hash)

    print()

    if original_hash == restored_hash:

        print("VERIFICATION : PASS")
        print("RESULT       : 100% IDENTICAL")

        return True

    else:

        print("VERIFICATION : FAIL")
        print("RESULT       : FILES DIFFER")

        return False


# ============================================================
# PHASE 1 TEST
# ============================================================

if __name__ == "__main__":

    test_file = Path(
        r"D:\FileCompressor\test1GB.bin"
    )

    # --------------------------------------------------------
    # STEP 1 — COMPRESS
    # --------------------------------------------------------

    result = compress_file(
        test_file
    )

    compressed_file = result["output"]

    # --------------------------------------------------------
    # STEP 2 — DECOMPRESS
    # --------------------------------------------------------

    restored_file = Path(
        r"D:\FileCompressor\test1GB.restored.bin"
    )

    decompress_file(
        compressed_file,
        restored_file
    )

    # --------------------------------------------------------
    # STEP 3 — VERIFY
    # --------------------------------------------------------

    verified = verify_file(
        test_file,
        restored_file
    )

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    print("\n")
    print("#" * 70)
    print("PHASE 1 — STEP 2 RESULT")
    print("#" * 70)

    if verified:

        print("COMPRESSION      : PASS")
        print("DECOMPRESSION    : PASS")
        print("SHA-256          : PASS")
        print("DATA RECOVERY    : 100%")

    else:

        print("DATA VERIFICATION FAILED")

    print("#" * 70)