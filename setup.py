# Read the contents of README file
from pathlib import Path

from setuptools import find_packages, setup

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8")

setup(
    name="maketables",
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    author="Your Name",
    author_email="your.email@example.com",
    description="A Python package for creating publication-ready tables from statistical models and descriptive statistics",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/maketables",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=[
        "numpy>=1.20.0",
        "pandas>=1.3.0",
        "great-tables>=0.2.0",
        "tabulate>=0.9.0",
        "pyfixest>=0.13.0",
        "python-docx>=0.8.11",
        "ipython>=7.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "black>=22.0",
            "flake8>=5.0",
            "mypy>=1.0",
        ],
        "docs": [
            "sphinx>=5.0",
            "sphinx-rtd-theme>=1.0",
        ],
    },
)
