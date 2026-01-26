"""Extract hyperlinks from Word documents."""

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict

from ..models import LawDocument, extract_id_from_url


def extract_hyperlinks_from_docx(docx_path: str | Path) -> List[LawDocument]:
    """Extract all thuvienphapluat.vn hyperlinks from a Word document.

    Args:
        docx_path: Path to the .docx file

    Returns:
        List of LawDocument objects with unique URLs
    """
    docx_path = Path(docx_path)
    if not docx_path.exists():
        raise FileNotFoundError(f"Document not found: {docx_path}")

    # Extract hyperlinks from document relationships
    urls = _extract_urls_from_rels(docx_path)

    # Extract display text for each URL
    url_to_text = _extract_display_text(docx_path)

    # Create LawDocument objects
    documents = []
    seen_urls = set()

    for url in urls:
        if url in seen_urls:
            continue
        if "thuvienphapluat.vn" not in url:
            continue

        seen_urls.add(url)
        display_text = url_to_text.get(url, _url_to_display_text(url))
        doc_id = extract_id_from_url(url)

        documents.append(
            LawDocument(
                url=url,
                display_text=display_text,
                document_id=doc_id,
            )
        )

    return documents


def _extract_urls_from_rels(docx_path: Path) -> List[str]:
    """Extract URLs from document.xml.rels file."""
    urls = []

    with zipfile.ZipFile(docx_path, "r") as zf:
        # Read the relationships file
        try:
            with zf.open("word/_rels/document.xml.rels") as f:
                content = f.read().decode("utf-8")
        except KeyError:
            return urls

    # Parse XML and extract Target attributes
    root = ET.fromstring(content)
    namespace = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}

    for rel in root.findall(".//r:Relationship", namespace):
        target = rel.get("Target", "")
        rel_type = rel.get("Type", "")

        # Only include external hyperlinks
        if "hyperlink" in rel_type.lower() and target.startswith("http"):
            urls.append(target)

    return urls


def _extract_display_text(docx_path: Path) -> Dict[str, str]:
    """Extract display text associated with hyperlinks."""
    url_to_text: Dict[str, str] = {}

    with zipfile.ZipFile(docx_path, "r") as zf:
        # Read relationships to map rId to URLs
        try:
            with zf.open("word/_rels/document.xml.rels") as f:
                rels_content = f.read().decode("utf-8")
        except KeyError:
            return url_to_text

        # Parse relationships
        rid_to_url: Dict[str, str] = {}
        rels_root = ET.fromstring(rels_content)
        namespace_rels = {
            "r": "http://schemas.openxmlformats.org/package/2006/relationships"
        }

        for rel in rels_root.findall(".//r:Relationship", namespace_rels):
            rid = rel.get("Id", "")
            target = rel.get("Target", "")
            if target.startswith("http"):
                rid_to_url[rid] = target

        # Read main document
        try:
            with zf.open("word/document.xml") as f:
                doc_content = f.read().decode("utf-8")
        except KeyError:
            return url_to_text

    # Parse document and extract text for each hyperlink
    doc_root = ET.fromstring(doc_content)
    namespaces = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }

    for hyperlink in doc_root.findall(".//w:hyperlink", namespaces):
        rid = hyperlink.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        if rid and rid in rid_to_url:
            # Extract all text within the hyperlink
            text_parts = []
            for text_elem in hyperlink.findall(".//w:t", namespaces):
                if text_elem.text:
                    text_parts.append(text_elem.text)
            if text_parts:
                url_to_text[rid_to_url[rid]] = "".join(text_parts)

    return url_to_text


def _url_to_display_text(url: str) -> str:
    """Generate display text from URL as fallback."""
    # Extract the law name from URL path
    # Example: /van-ban/Doanh-nghiep/Luat-Doanh-nghiep-2020-68-2020-QH14-375519.aspx
    # -> Luat-Doanh-nghiep-2020-68-2020-QH14
    path = url.split("/")[-1]  # Get filename
    name = path.replace(".aspx", "")  # Remove extension

    # Remove trailing ID
    parts = name.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit():
        name = parts[0]

    # Replace hyphens with spaces
    return name.replace("-", " ")


if __name__ == "__main__":
    # Test extraction
    import sys

    docx_file = sys.argv[1] if len(sys.argv) > 1 else "law.docx"
    documents = extract_hyperlinks_from_docx(docx_file)

    print(f"Extracted {len(documents)} unique URLs from {docx_file}")
    print("\nFirst 5 documents:")
    for doc in documents[:5]:
        print(f"  - [{doc.document_id}] {doc.display_text[:60]}...")
        print(f"    URL: {doc.url}")
