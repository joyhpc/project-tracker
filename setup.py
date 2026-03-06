from setuptools import setup, find_packages

setup(
    name="project-tracker",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "tracker": [
            "flows/*.yaml",
            "flows/subtasks/*.yaml",
            "flows/v1_backup/*.yaml",
        ]
    },
    install_requires=["pyyaml>=6.0"],
    entry_points={"console_scripts": ["pt=tracker.cli:main"]},
    python_requires=">=3.10",
)
