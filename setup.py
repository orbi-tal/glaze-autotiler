"""Setup configuration for Glaze Autotiler package."""

from setuptools import find_packages, setup

setup(
    name="glaze-autotiler",
    version="1.0.1",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    install_requires=[
        "websockets>=11.0.3",
        "Pillow>=10.0.0",
        "pystray>=0.19.4",
    ],
    package_data={
        "autotile": ["res/*"],
    },
    entry_points={
        "console_scripts": [
            "glaze-autotiler=autotile.main:main",
        ],
    },
    author="orbi-tal",
    description="An auto-tiling script for GlazeWM",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/glaze-autotiler",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
)
