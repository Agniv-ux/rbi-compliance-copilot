"""Download RBI source documents into data/raw/.

Re-runnable: files that already exist are skipped.
Usage: .venv/Scripts/python.exe ingestion/download_docs.py
"""

import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

TIMEOUT = 60

# Direct PDF links.
DIRECT_PDFS = {
    "kyc_md_2016.pdf": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/MD18KYCF6E92C82E1E1419D87323E3869BC9F13.PDF",
    # RBI/2025-26/51 (June 12, 2025); the pdicai.org mirror now returns 404.
    "kyc_amendment_2025_06.pdf": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/NT517A41C334FB0A42BC9D58A37DE3793F4E.PDF",
    "kyc_amendment_2025_08.pdf": "https://www.fidcindia.org.in/wp-content/uploads/2025/08/RBI-KYC-14-08-25.pdf",
    # RBI/2025-26/160 (December 29, 2025); the pdicai.org mirror now returns 404.
    "nbfc_kyc_amendment_2025_12.pdf": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/NT160A366EA8052104F0ABD04B9DAD153E3F9.PDF",
    "nbfc_kyc_md_2025.pdf": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/361MD1E2F8EA063454AD5AFA1D02A1BA5ACA7.PDF",
    "nbfc_responsible_business_conduct_2025.pdf": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/362MD26CA543937BA439A97E1BCFC08CF5808.PDF",
    "nbfc_credit_facilities_2025.pdf": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/347MD5CC21D3597C04354B67A42A1A4CB439C.PDF",
    "nbfc_outsourcing_2025.pdf": "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/363MD40F22B0CDF734E3C884A9CBCE5DF9194.PDF",
}

# RBI pages containing a PDF link: (page url, title text to match or None for the first PDF).
PAGE_PDFS = {
    "digital_lending_directions_2025.pdf": (
        "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12848&Mode=0",
        None,
    ),
}

# Pages saved as HTML.
HTML_PAGES = {
    "kyc_faqs.html": "https://rbi.org.in/Scripts/FAQDisplay.aspx?Id=173",
}


def _normalize(text: str) -> str:
    """Lowercase, unify dashes and collapse whitespace for fuzzy title matching."""
    text = re.sub(r"[‒-―−-]", "-", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _is_pdf_link(href: str) -> bool:
    return href.lower().split("?")[0].endswith(".pdf")


def fetch(session: requests.Session, url: str) -> requests.Response:
    resp = session.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp


def save_pdf(session: requests.Session, url: str, dest: Path) -> None:
    resp = fetch(session, url)
    if not resp.content.startswith(b"%PDF"):
        raise ValueError(f"response from {url} is not a PDF (Content-Type: {resp.headers.get('Content-Type')})")
    dest.write_bytes(resp.content)


def find_pdf_link(session: requests.Session, page_url: str, title: str | None) -> str:
    soup = BeautifulSoup(fetch(session, page_url).text, "html.parser")
    pdf_links = [a for a in soup.find_all("a", href=True) if _is_pdf_link(a["href"])]
    if not pdf_links:
        raise ValueError(f"no PDF links found on {page_url}")

    if title is None:
        return urljoin(page_url, pdf_links[0]["href"])

    # Master directions page lists each title in a row alongside its PDF link.
    target = _normalize(title)
    for a in pdf_links:
        container = a.find_parent("tr") or a.parent
        if container and target in _normalize(container.get_text(" ")):
            return urljoin(page_url, a["href"])
    # Fallback: the title is a link to a detail page that holds the PDF.
    for a in soup.find_all("a", href=True):
        if target in _normalize(a.get_text(" ")):
            return find_pdf_link(session, urljoin(page_url, a["href"]), None)
    raise ValueError(f"could not find '{title}' on {page_url}")


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    failures = []

    def run(name, action):
        dest = RAW_DIR / name
        if dest.exists():
            print(f"skip     {name} (exists)")
            return
        try:
            action(dest)
            print(f"saved    {name} ({dest.stat().st_size:,} bytes)")
        except Exception as exc:  # keep going so one bad link doesn't block the rest
            if dest.exists():
                dest.unlink()
            failures.append(name)
            print(f"FAILED   {name}: {exc}")

    for name, url in DIRECT_PDFS.items():
        run(name, lambda dest, url=url: save_pdf(session, url, dest))

    for name, (page_url, title) in PAGE_PDFS.items():
        run(name, lambda dest, p=page_url, t=title: save_pdf(session, find_pdf_link(session, p, t), dest))

    for name, url in HTML_PAGES.items():
        run(name, lambda dest, url=url: dest.write_bytes(fetch(session, url).content))

    if failures:
        print(f"\n{len(failures)} failed: {', '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
