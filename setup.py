from setuptools import setup, find_packages

setup(
    name         = "nasal_monitor",
    version      = "0.3.0",
    packages     = find_packages(),
    install_requires = [
        "pyserial>=3.5",
        "matplotlib",
    ],
)
