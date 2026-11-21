"""
app/routes/classify.py
Endpoint klasifikasi AI menggunakan NVIDIA Nemotron untuk dokumen akademik.
"""
from flask import Blueprint, request, jsonify

from app.services.nvidia import (
    CATEGORIES,
    NvidiaClassifyError,
    classify_document as classify_with_nvidia,
)
from app.utils.logging import get_logger

log = get_logger("classify")
classify_bp = Blueprint("classify", __name__, url_prefix="/api/classify")


def _classify_document(title: str, abstract: str, authors: list, year: str,
                       source: str, subjects: list) -> dict:
    """
    Klasifikasi dokumen dengan NVIDIA Nemotron.
    Bila gagal, fallback ke keyword matching agar endpoint tetap merespons.
    """
    try:
        return classify_with_nvidia(
            title=title,
            abstract=abstract,
            authors=authors,
            year=year,
            source=source,
            subjects=subjects,
        )
    except NvidiaClassifyError as exc:
        log.warning("NVIDIA classification failed, using fallback: %s", exc)
    except Exception as exc:  # noqa: BLE001
        log.exception("Unexpected NVIDIA classification error: %s", exc)

    return _fallback_classify(title, abstract, subjects)


def _fallback_classify(title: str, abstract: str, subjects: list) -> dict:
    """
    Fallback classification berdasarkan keyword matching.
    Dijalankan jika NVIDIA API tidak tersedia.
    """
    if isinstance(subjects, str):
        subjects = [subjects]

    text = f"{title or ''} {abstract or ''} {' '.join(subjects or [])}".lower()

    keywords_map = {
        "Artificial Intelligence": ["artificial intelligence", "ai", "machine learning", "deep learning", "neural network"],
        "Machine Learning": ["machine learning", "ml model", "supervised", "unsupervised", "reinforcement", "classification"],
        "Data Science": ["data science", "data analysis", "big data", "analytics", "data mining"],
        "Computer Vision": ["computer vision", "image recognition", "object detection", "image segmentation", "cnn"],
        "Natural Language Processing": ["nlp", "natural language", "text mining", "sentiment", "language model"],
        "Robotics": ["robotics", "robot", "autonomous", "control system"],
        "Cybersecurity": ["cybersecurity", "security", "cryptography", "privacy", "vulnerability", "phishing", "phishing attack", "phishing attacks", "malware", "ransomware", "cyberattack", "intrusion detection"],
        "Cloud Computing": ["cloud", "saas", "paas", "iaas", "serverless", "container"],
        "Internet of Things": ["iot", "sensor", "embedded", "wearable"],
        "Blockchain": ["blockchain", "distributed ledger", "smart contract", "cryptocurrency"],
        "Quantum Computing": ["quantum", "qubit", "quantum computing"],
        "Bioinformatics": ["bioinformatics", "genomics", "proteomics", "biomedical"],
        "Medical Imaging": ["medical imaging", "mri", "ct scan", "x-ray", "diagnosis"],
        "Health Informatics": ["health informatics", "ehr", "telemedicine", "medical record"],
        "Environmental Science": ["climate", "environment", "sustainability", "pollution"],
        "Physics": ["physics", "quantum mechanics", "thermodynamics", "particle"],
        "Chemistry": ["chemistry", "molecule", "chemical reaction", "biochemistry"],
        "Mathematics": ["mathematics", "algebra", "geometry", "calculus", "statistics"],
        "Engineering": ["engineering", "mechanical", "electrical", "civil"],
        "Economics": ["economics", "econometrics", "finance", "market"],
        "Social Science": ["social science", "sociology", "anthropology"],
        "Law": ["law", "legal", "jurisprudence", "regulation"],
        "Education": ["education", "learning", "pedagogy", "e-learning"],
        "Psychology": ["psychology", "cognitive", "behavior", "mental"],
        "Literature": ["literature", "fiction", "poetry", "narrative"],
        "History": ["history", "historical", "archaeology"],
        "Philosophy": ["philosophy", "ethics", "metaphysics"],
        "Religion": ["religion", "theology", "faith"],
        "Arts": ["art", "music", "design", "creative"],
    }

    scores = {}
    for category, keywords in keywords_map.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[category] = score

    if not scores:
        return {
            "category": "Other",
            "confidence": 0.1,
            "keywords": [],
            "summary": "Tidak dapat diklasifikasikan secara otomatis.",
            "provider": "fallback",
        }

    top_cat = max(scores, key=scores.get)
    max_score = scores[top_cat]
    confidence = min(0.9, 0.3 + (max_score * 0.15))

    matched_keywords = [kw for kw in keywords_map[top_cat] if kw in text]

    return {
        "category": top_cat,
        "confidence": round(confidence, 2),
        "keywords": matched_keywords,
        "summary": f"Diklasifikasikan berdasarkan keyword matching: {', '.join(matched_keywords[:3])}",
        "provider": "fallback",
    }


@classify_bp.route("", methods=["POST"])
def classify_document():
    """
    Klasifikasi dokumen akademik menggunakan AI.

    POST /api/classify

    Body (JSON):
      title     : Judul dokumen (wajib)
      abstract  : Abstrak (opsional)
      authors   : List nama penulis (opsional)
      year      : Tahun publikasi (opsional)
      source    : Sumber dokumen (opsional)
      subjects  : List subjek/keyword (opsional)
      category_hint : Hint kategori (opsional)

    Response:
      {
        "category": "...",
        "confidence": 0.85,
        "keywords": [...],
        "summary": "...",
        "provider": "nvidia" | "fallback"
      }
    """
    data = request.get_json() or {}

    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Field 'title' wajib diisi."}), 400

    abstract = data.get("abstract")
    authors = data.get("authors", [])
    year = str(data.get("year", "") or "")
    source = data.get("source", "")
    subjects = data.get("subjects", [])
    category_hint = data.get("category_hint", "")

    log.info("Classifying document: %s", title[:60])

    result = _classify_document(
        title=title,
        abstract=abstract,
        authors=authors,
        year=year,
        source=source,
        subjects=subjects,
    )

    if category_hint and result.get("category") != category_hint:
        log.debug("Category mismatch: got %s, hint was %s", result["category"], category_hint)

    return jsonify({
        "title": title,
        "category": result["category"],
        "confidence": result["confidence"],
        "keywords": result["keywords"],
        "summary": result["summary"],
        "provider": result["provider"],
    })


@classify_bp.route("/batch", methods=["POST"])
def classify_batch():
    """
    Klasifikasi multiple dokumen sekaligus.

    POST /api/classify/batch

    Body (JSON):
      documents: [
        {"title": "...", "abstract": "...", ...},
        ...
      ]
    """
    data = request.get_json() or {}
    docs = data.get("documents", [])

    if not docs:
        return jsonify({"error": "Field 'documents' wajib berisi list."}), 400

    if len(docs) > 50:
        return jsonify({"error": "Maksimal 50 dokumen per batch."}), 400

    results = []
    for i, doc in enumerate(docs):
        title = (doc.get("title") or "").strip()
        if not title:
            results.append({"index": i, "error": "title required"})
            continue

        result = _classify_document(
            title=title,
            abstract=doc.get("abstract"),
            authors=doc.get("authors", []),
            year=str(doc.get("year", "") or ""),
            source=doc.get("source", ""),
            subjects=doc.get("subjects", []),
        )

        results.append({
            "index": i,
            "title": title,
            "category": result["category"],
            "confidence": result["confidence"],
            "keywords": result["keywords"],
            "provider": result["provider"],
        })

    return jsonify({
        "total": len(docs),
        "processed": len([r for r in results if "error" not in r]),
        "results": results,
    })


@classify_bp.route("/categories", methods=["GET"])
def list_categories():
    """Daftar semua kategori klasifikasi yang tersedia."""
    return jsonify({
        "total": len(CATEGORIES),
        "categories": CATEGORIES,
    })
