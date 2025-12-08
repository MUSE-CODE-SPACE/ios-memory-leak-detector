"""
iOS Memory Leak Detector - Setup Configuration
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

setup(
    name="ios-leak-detector",
    version="1.0.0",
    author="yoon-k",
    author_email="yoon-k@github.com",
    description="Static analysis tool to detect memory leaks and performance issues in iOS projects (Swift, SwiftUI, Objective-C)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yoon-k/ios-memory-leak-detector",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Software Development :: Testing",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Environment :: Console",
    ],
    python_requires=">=3.8",
    install_requires=[],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "black>=23.0",
            "flake8>=6.0",
            "mypy>=1.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "ios-leak-detector=ios_leak_detector.cli:main",
            "iosleaks=ios_leak_detector.cli:main",
        ],
    },
    keywords=[
        "ios",
        "swift",
        "swiftui",
        "objective-c",
        "memory-leak",
        "static-analysis",
        "code-quality",
        "xcode",
    ],
    project_urls={
        "Bug Reports": "https://github.com/yoon-k/ios-memory-leak-detector/issues",
        "Source": "https://github.com/yoon-k/ios-memory-leak-detector",
    },
)
