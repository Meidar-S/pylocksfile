import setuptools
from pylocksfile import __version__

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name = "pylocksfile", # Replace with your own username
    version = __version__,
    author = "Meidar Sharkansky",
    author_email="meidarsharkansky@gmail.com",
    description="Python library for linux file-based read/write locks for inter-process communication",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Meidar-S/pylocksfile",
    py_modules = ["pylocksfile"],
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)