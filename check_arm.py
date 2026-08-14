import platform, sys
print(f"Python: {sys.version.split()[0]}")
print(f"Architecture: {platform.machine()}")
print(f"Platform: {platform.platform()}")
if platform.machine().lower() not in {"arm64", "aarch64"}:
    print("WARNING: This is not an ARM64 Python process.")
else:
    print("OK: Running as ARM64/native ARM Python.")
