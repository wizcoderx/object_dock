from setuptools import setup, find_packages

setup(
    name="object_dock",
    version="1.0.0",
    description="FastAPI-based Object Store Service (OSS) — accepts base64-encoded files, "
                "stores them on the local filesystem, and tracks them via SQLite.",
    author="Anamay",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "fastapi>=0.100.0",
        "uvicorn[standard]>=0.23.0",
        "filetype>=1.2.0",
    ],
    entry_points={
        "console_scripts": [
            "object-dock=uvicorn:main",
        ],
    },
)
