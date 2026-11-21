"""
tests/test_services.py
Uji koneksi ke semua sumber — jalankan dengan: python tests/test_services.py
Tidak memerlukan server Flask berjalan, langsung panggil service functions.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import SOURCE_MAP
from app.services.openaccess import lookup_doi
from app.routes.classify import _fallback_classify, CATEGORIES
from app.routes.download import _resolve_by_doi, _resolve_by_isbn, _get_extension

QUERY    = "machine learning"
QUERY_ID = "hukum perdata"


def _status(result: dict) -> str:
    if result.get("error"):
        return f"FAIL: {result['error']}"
    count = len(result.get("results", []))
    total = result.get("total", "?")
    note  = f" | {result['note']}" if result.get("note") else ""
    return f"OK ({count}/{total} hasil){note}"


def run_service_tests():
    print("=" * 60)
    print("  LiterasiAI — Uji Koneksi Semua Sumber")
    print("=" * 60)

    for source_key, fn in SOURCE_MAP.items():
        query = QUERY_ID if source_key in ("garuda", "sinta", "neliti") else QUERY
        print(f"\n[{source_key.upper()}] query: '{query}'")
        try:
            result = fn(query=query, page=1, page_size=3)
            print(f"  {_status(result)}")
            if result.get("results"):
                first = result["results"][0]
                print(f"  Contoh: {first.get('title', '-')[:80]}")
                print(f"  Penulis: {', '.join(first.get('authors', [])[:2]) or '-'}")
                print(f"  Tahun: {first.get('year', '-')} | Tipe: {first.get('doc_type', '-')}")
                if first.get("pdf_url"):
                    print(f"  PDF: {first['pdf_url'][:80]}")
        except Exception as e:
            print(f"  FAIL: {e}")

    print("\n" + "=" * 60)
    print("  Uji DOI Lookup (Unpaywall)")
    print("=" * 60)
    doi = "10.1038/nature12373"
    print(f"\n[UNPAYWALL] doi: {doi}")
    try:
        oa = lookup_doi(doi)
        if oa.get("is_oa"):
            print(f"  OK - Open Access: {oa.get('best_url', '-')[:80]}")
        else:
            print(f"  WARN - Tidak OA: {oa.get('note', '-')}")
    except Exception as e:
        print(f"  FAIL: {e}")


def run_classify_tests():
    print("\n" + "=" * 60)
    print("  Uji Klasifikasi (Fallback)")
    print("=" * 60)

    test_docs = [
        {
            "title": "Deep Learning for Image Recognition",
            "abstract": "This paper presents a novel convolutional neural network architecture for image classification and object detection.",
            "subjects": ["deep learning", "computer vision", "neural network"],
        },
        {
            "title": "Climate Change Impact on Agriculture",
            "abstract": "Study of how rising temperatures affect crop yields and farming practices in tropical regions.",
            "subjects": ["climate", "agriculture", "environment"],
        },
        {
            "title": "Smart Contracts in Blockchain Technology",
            "abstract": "Analysis of automated contract execution using distributed ledger technology and cryptocurrency systems.",
            "subjects": ["blockchain", "smart contract", "ethereum"],
        },
    ]

    for i, doc in enumerate(test_docs, 1):
        result = _fallback_classify(
            title=doc["title"],
            abstract=doc["abstract"],
            subjects=doc["subjects"],
        )
        print(f"\n[{i}] {doc['title'][:50]}")
        print(f"    Category: {result['category']}")
        print(f"    Confidence: {result['confidence']}")
        print(f"    Keywords: {', '.join(result['keywords'][:3])}")
        print(f"    Provider: {result['provider']}")

    print(f"\n  Total kategori: {len(CATEGORIES)}")


def run_download_tests():
    print("\n" + "=" * 60)
    print("  Uji Download Helpers")
    print("=" * 60)

    print("\n[_get_extension]")
    test_urls = [
        "https://example.com/paper.pdf",
        "https://example.com/book.epub",
        "https://example.com/text.txt",
        "https://example.com/noextension",
    ]
    for url in test_urls:
        ext = _get_extension(url)
        print(f"  {url} -> .{ext}")

    print("\n[_resolve_by_doi] sample DOI lookup")
    doi = "10.1038/nature12373"
    from app.routes.download import _get_settings, _get_enabled_methods
    settings = _get_settings()
    methods = _get_enabled_methods()
    url, doc = _resolve_by_doi(doi, methods, settings)
    print(f"  DOI: {doi}")
    print(f"  Resolved URL: {url[:80] if url else 'None'}")
    print(f"  Doc title: {doc.get('title', '-')[:60] if doc else '-'}")


def run_all():
    run_service_tests()
    run_classify_tests()
    run_download_tests()
    print("\n" + "=" * 60)
    print("  Selesai")
    print("=" * 60)


if __name__ == "__main__":
    run_all()