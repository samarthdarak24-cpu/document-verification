"""License and attribution notice for pdf-diff integration.

This module incorporates and adapts code from `pdf-diff` by Joshua Tauberer:
    Repository: https://github.com/JoshData/pdf-diff
    Author: Joshua Tauberer (jt@occams.info)
    License: Creative Commons Zero 1.0 Universal (CC0 1.0) Public Domain Dedication.

Statement of Purpose:
The person associating CC0 with a Work dedicates the work to the public domain
by waiving all of his or her rights to the work worldwide under copyright law,
including all related and neighboring rights, to the extent allowed by law.

You can copy, modify, distribute and perform the work, even for commercial purposes,
all without asking permission.
"""

PDF_DIFF_ATTRIBUTION = {
    "name": "pdf-diff",
    "author": "Joshua Tauberer",
    "repository": "https://github.com/JoshData/pdf-diff",
    "license": "CC0 1.0 Universal",
    "description": "Finds differences between two PDF documents and outputs bounding boxes / rendered diffs.",
    "docutrace_extensions": [
        "PyMuPDF-backed word bounding-box extractor (cross-platform, zero poppler dependency)",
        "PyMuPDF-backed high-resolution page rasterizer for image comparison",
        "OpenCV-based visual diagram, figure, chart, and stamp modification detection",
        "Research paper section classifier (Abstract, Intro, Methodology, Results, Conclusion)",
        "Semantic entity and value change classification (numbers, dates, names, registration IDs)",
        "Typographic / font family, font size, bold, italic, and color change detection",
        "Integration with DocuTrace DAA algorithms (LCS DP, Levenshtein edit distance, Inversion counting)",
    ],
}
