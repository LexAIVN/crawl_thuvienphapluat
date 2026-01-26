"""Extract URLs from text file."""

import re
from pathlib import Path
from typing import List

from ..models import LawDocument, extract_id_from_url


def extract_hyperlinks_from_txt(txt_path: str | Path) -> List[LawDocument]:
    """Extract all thuvienphapluat.vn URLs from a text file.

    Expected format per line:
        1. https://thuvienphapluat.vn/...
        2. https://thuvienphapluat.vn/...

    Args:
        txt_path: Path to the .txt file

    Returns:
        List of LawDocument objects with sequential order preserved
    """
    txt_path = Path(txt_path)
    if not txt_path.exists():
        raise FileNotFoundError(f"File not found: {txt_path}")

    documents = []

    with open(txt_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Parse line format: "1. https://..."
            match = re.match(r"^(\d+)\.\s*(https?://[^\s]+)", line)
            if not match:
                continue

            order_num = int(match.group(1))
            url = match.group(2)

            if "thuvienphapluat.vn" not in url:
                continue

            # Extract display text from URL
            display_text = _url_to_display_text(url)
            doc_id = extract_id_from_url(url)

            documents.append(
                LawDocument(
                    url=url,
                    display_text=display_text,
                    document_id=doc_id,
                    # Store order number in document_id prefix for sorting
                    # We'll use a custom field approach
                )
            )

    return documents


def _url_to_display_text(url: str) -> str:
    """Generate display text from URL.

    Example:
        /van-ban/Thue-Phi-Le-Phi/Luat-Thue-gia-tri-gia-tang-sua-doi-2025-679698.aspx
        -> Luat Thue gia tri gia tang sua doi 2025
    """
    # Extract the law name from URL path
    path = url.split("/")[-1]  # Get filename
    name = path.replace(".aspx", "")  # Remove extension

    # Remove trailing ID (numbers at end)
    parts = name.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit():
        name = parts[0]

    # Replace hyphens with spaces
    return name.replace("-", " ")


if __name__ == "__main__":
    import sys

    txt_file = sys.argv[1] if len(sys.argv) > 1 else "src/data.txt"
    documents = extract_hyperlinks_from_txt(txt_file)

    print(f"Extracted {len(documents)} URLs from {txt_file}")
    print("\nFirst 5 documents:")
    for i, doc in enumerate(documents[:5], 1):
        print(f"  {i}. [{doc.document_id}] {doc.display_text[:60]}...")
        print(f"     URL: {doc.url}")
