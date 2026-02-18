from setuptools import setup, find_packages

setup(
    name="project-tracker",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["pyyaml>=6.0"],
    entry_points={"console_scripts": ["pt=tracker.cli:main"]},
    python_requires=">=3.10",
)
