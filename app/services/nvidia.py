"""
app/services/nvidia.py
Klasifikasi dokumen akademik menggunakan NVIDIA Nemotron via NVIDIA NIM.

Endpoint OpenAI-compatible:
    POST https://integrate.api.nvidia.com/v1/chat/completions

Catatan penting:
- Gunakan `response_format` JSON Schema (bukan `nvext.guided_json`) karena
  endpoint hosted NVIDIA menolak field `nvext.guided_json`.
- Reasoning dimatikan lewat `chat_template_kwargs.enable_thinking = false`
  agar klasifikasi cepat dan tidak menghabiskan token.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import threading
import time

import requests
from cachetools import TTLCache

from config import Config
from app.utils.logging import get_logger

log = get_logger("nvidia")


CATEGORIES = [
    "Artificial Intelligence",
    "Machine Learning",
    "Data Science",
    "Computer Vision",
    "Natural Language Processing",
    "Robotics",
    "Cybersecurity",
    "Cloud Computing",
    "Internet of Things",
    "Blockchain",
    "Quantum Computing",
    "Bioinformatics",
    "Medical Imaging",
    "Health Informatics",
    "Medicine",
    "Agriculture",
    "Veterinary Medicine",
    "Dentistry",
    "Nursing",
    "Pharmacy",
    "Public Health",
    "Environmental Science",
    "Physics",
    "Chemistry",
    "Mathematics",
    "Statistics",
    "Engineering",
    "Architecture",
    "Urban Planning",
    "Economics",
    "Business",
    "Finance",
    "Accounting",
    "Marketing",
    "Management",
    "Social Science",
    "Political Science",
    "International Relations",
    "Public Administration",
    "Law",
    "Criminology",
    "Education",
    "Psychology",
    "Sociology",
    "Anthropology",
    "Geography",
    "Demography",
    "Social Work",
    "Communication Studies",
    "Journalism",
    "Media Studies",
    "Library Science",
    "Information Science",
    "Linguistics",
    "Literature",
    "History",
    "Philosophy",
    "Religion",
    "Arts",
    "Music",
    "Theater",
    "Sports Science",
    "Nutrition",
    "Gender Studies",
    "Cultural Studies",
    "Area Studies",
    "Ethnic Studies",
    "Other",
]


SUBJECT_PROMPT = """
Kamu adalah klasifikator dokumen akademik. Tugasmu memilih tepat satu kategori
yang paling menggambarkan topik/domain utama dokumen.

Dokumen:
- Judul: {title}
- Abstrak: {abstract}
- Penulis: {authors}
- Tahun: {year}
- Sumber: {source}
- Subjek: {subjects}

Kategori yang tersedia:
{categories}

Prinsip utama:
0. **PRIORITAS KATEGORI SPESIFIK**: Pilih kategori paling spesifik yang cocok.
   Jika dokumen cocok dengan kategori spesifik (contoh: "Political Science",
   "Medicine", "Agriculture", "Architecture", "Journalism", "Music", "Sports Science",
   "Nutrition", "Anthropology", "Public Administration", "International Relations",
   "Criminology", "Sociology", "Veterinary Medicine", "Dentistry", "Nursing",
   "Pharmacy", "Public Health", "Urban Planning", "Finance", "Accounting",
   "Marketing", "Management", "Communication Studies", "Media Studies",
   "Library Science", "Information Science", "Linguistics", "Literature",
   "History", "Philosophy", "Religion", "Music", "Theater", "Gender Studies",
   "Cultural Studies", "Area Studies", "Ethnic Studies", "Demography",
   "Social Work", "Statistics", "Bioinformatics", "Medical Imaging",
   "Health Informatics"), JANGAN pilih kategori induk yang lebih luas
   ("Social Science", "Engineering", "Arts", "Business", "Education", "Law",
   "Environmental Science", "Physics", "Chemistry", "Mathematics", "Economics",
   "Psychology", "Geography", "Communication Studies").

1. **POLITICAL SCIENCE**: Jika fokus utamanya teori politik, sistem politik,
   kebijakan publik, pemilu, partai politik, perilaku pemilih, atau ilmu politik—
   pilih "Political Science" (BUKAN "Social Science", "Public Administration",
   atau "International Relations").

2. **MEDICINE**: Jika fokus utamanya praktik klinis, diagnosis, terapi, penyakit,
   bedah, kardiologi, neurologi, onkologi, uji klinis, atau ilmu kedokteran umum—
   pilih "Medicine" (BUKAN "Health Informatics", "Medical Imaging", "Bioinformatics",
   "Pharmacy", "Public Health", atau "Nursing").

3. **AGRICULTURE**: Jika fokus utamanya agronomi, tanaman pangan, peternakan,
   pertanian berkelanjutan, agroekologi, irigasi, pemuliaan tanaman, atau ilmu
   pertanian—pilih "Agriculture" (BUKAN "Environmental Science", "Biology",
   atau "Engineering").

4. **ARCHITECTURE**: Jika fokus utamanya desain arsitektur, bangunan, tata ruang,
   lingkungan dibangun, desain interior, teknologi bangunan, atau arsitektur
   lanskap—pilih "Architecture" (BUKAN "Engineering", "Environmental Science",
   "Urban Planning", atau "Arts").

5. **JOURNALISM**: Jika fokus utamanya jurnalistik, pemberitaan, etika media,
   pers, investigasi jurnalistik, kebebasan pers, atau praktik redaksi—pilih
   "Journalism" (BUKAN "Communication Studies", "Media Studies", "Social Science",
   atau "Political Science").

6. **MUSIC**: Jika fokus utamanya musikologi, teori musik, komposisi,
   etnomusikologi, analisis musik, pendidikan musik, atau sejarah musik—pilih
   "Music" (BUKAN "Arts", "Cultural Studies", "Anthropology", atau "Theater").

7. **NUTRITION**: Jika fokus utamanya nutrisi, dietetika, ilmu makanan, asupan
   gizi, stunting, malnutrisi, suplementasi, atau metabolisme—pilih "Nutrition"
   (BUKAN "Public Health", "Medicine", "Health Informatics", atau "Biology").

8. **ANTHROPOLOGY**: Jika fokus utamanya antropologi budaya, fisik, linguistik,
   arkeologi, etnografi, kebudayaan masyarakat tradisional, atau warisan budaya—
   pilih "Anthropology" (BUKAN "Social Science", "Sociology", "Cultural Studies",
   "Area Studies", atau "History").

9. **PUBLIC ADMINISTRATION**: Jika fokus utamanya administrasi publik, birokrasi,
   manajemen pemerintahan, pelayanan publik, reformasi birokrasi, atau e-government—
   pilih "Public Administration" (BUKAN "Political Science", "Social Science",
   "Management", atau "Law").

10. **INTERNATIONAL RELATIONS**: Jika fokus utamanya hubungan internasional,
    diplomasi, keamanan global, organisasi internasional, hukum internasional,
    kebijakan luar negeri, atau geopolitik—pilih "International Relations"
    (BUKAN "Political Science", "Law", "Social Science", atau "History").

11. **CRIMINOLOGY**: Jika fokus utamanya kriminologi, hukum pidana, sistem
    keadilan pidana, pencegahan kejahatan, viktimologi, atau penologi—pilih
    "Criminology" (BUKAN "Law", "Sociology", "Social Science", atau "Psychology").

12. **SOCIOLOGY**: Jika fokus utamanya sosiologi, struktur sosial, stratifikasi,
    perubahan sosial, teori sosiologis, gerakan sosial, atau ketimpangan sosial—
    pilih "Sociology" (BUKAN "Social Science", "Anthropology", "Criminology",
    "Demography", atau "Social Work").

13. Pilih berdasarkan topik/domain penelitian, BUKAN hanya metode yang disebut.
   Machine learning, deep learning, statistik, IoT, atau blockchain adalah alat
   jika bukan kontribusi utama.
2. Jangan memilih "Machine Learning" hanya karena judul menyebut ML/DL. Pilih
   "Machine Learning" jika kontribusi utamanya memang algoritma/model pembelajaran,
   pelatihan, evaluasi, atau perbandingan model.
3. Jika fokus utamanya keamanan siber—serangan, pertahanan, phishing, malware,
   intrusion detection, privasi, kriptografi, atau kerentanan sistem—pilih
   "Cybersecurity" meskipun metode yang dipakai adalah machine learning.
4. "Artificial Intelligence" untuk penalaran, representasi pengetahuan,
   perencanaan, agen cerdas, atau teori AI. "Data Science" untuk pipeline data,
   big data, analitik, visualisasi, atau insight bisnis.
5. "Medical Imaging" untuk akuisisi/analisis citra medis (CT, MRI, X-ray,
   histopatologi), termasuk segmentasi/deteksi dengan deep learning.
   "Health Informatics" untuk EHR, telemedicine, alur kerja klinis, dan sistem
   data kesehatan. "Bioinformatics" untuk genomik, proteomik, sekuensing, dan
   biologi komputasional.
6. "Robotics" untuk robot fisik, manipulator, navigasi, kontrol, atau sistem
   otonom, termasuk jika memakai reinforcement learning/computer vision.
   "Computer Vision" untuk penglihatan komputer umum di luar medis/robotika.
   "Natural Language Processing" untuk teks, bahasa, ucapan, sentimen,
   terjemahan, dan LLM.
7. "Cloud Computing" untuk infrastruktur cloud, serverless, container,
   orkestrasi, dan biaya. "Internet of Things" untuk sensor/perangkat tertanam.
   "Blockchain" untuk ledger terdistribusi dan smart contract. "Quantum
   Computing" untuk perangkat/algoritma/error correction kuantum.
8. "Engineering" untuk desain/aplikasi struktur, mesin, sirkuit, atau material.
   "Physics", "Chemistry", dan "Mathematics" untuk sains dasar. "Environmental
   Science" untuk iklim, ekologi, dan keberlanjutan.
9. "Social Science" HANYA untuk sosiologi umum, antropologi umum, dan komunikasi umum
   yang TIDAK cocok kategori spesifik: "Sociology", "Anthropology", "Criminology",
   "Demography", "Social Work", "Gender Studies", "Cultural Studies", "Area Studies",
   "Ethnic Studies", "Communication Studies", "Journalism", "Media Studies",
   "Political Science", "International Relations", "Public Administration".
   "Economics" untuk pasar, keuangan, dan ekonometrika. "Law" untuk doktrin/
   regulasi hukum. "Education" untuk pedagogi/pembelajaran. "Psychology" untuk
   kognisi/perilaku/kesehatan mental. "Literature" untuk analisis sastra.
   "History" untuk analisis sejarah. "Philosophy" untuk filsafat. "Religion"
   untuk teologi/studi agama. "Arts" untuk seni/musik/desain/pertunjukan.
10. "Medicine" untuk praktik klinis, diagnosis, terapi, penyakit, bedah,
    kardiologi, neurologi, onkologi, dan ilmu kedokteran umum.
    "Agriculture" untuk agronomi, tanaman pangan, peternakan, pertanian berkelanjutan,
    agroekologi, dan ilmu pertanian.
    "Veterinary Medicine" untuk kesehatan hewan, penyakit zoonosis, peternakan,
    dan kedokteran hewan.
    "Dentistry" untuk kedokteran gigi, ortodonsia, periodonsia, bedah mulut.
    "Nursing" untuk keperawatan, perawatan pasien, manajemen keperawatan,
    dan praktik keperawatan berbasis bukti.
    "Pharmacy" untuk farmakologi, farmasetika, pengembangan obat, farmakokinetik,
    dan ilmu farmasi.
    "Public Health" untuk epidemiologi, promosi kesehatan, kebijakan kesehatan,
    kesehatan lingkungan, dan kesehatan masyarakat.
    "Statistics" untuk metodologi statistik, inferensia, desain eksperimen,
    analisis data, dan probabilitas.
    "Architecture" untuk desain arsitektur, bangunan, tata ruang, dan lingkungan dibangun.
    "Urban Planning" untuk perencanaan kota, transportasi, zonasi, pembangunan wilayah,
    dan tata guna lahan.
    "Business" untuk manajemen bisnis, strategi, kewirausahaan, dan organisasi.
    "Finance" untuk keuangan korporat, pasar modal, investasi, perbankan,
    dan manajemen risiko keuangan.
    "Accounting" untuk akuntansi keuangan, auditing, pajak, dan pelaporan keuangan.
    "Marketing" untuk pemasaran, perilaku konsumen, branding, dan riset pasar.
    "Management" untuk manajemen operasional, SDM, operasi, dan kepemimpinan.
    "Political Science" untuk teori politik, sistem politik, kebijakan publik,
    pemilu, dan ilmu politik.
    "International Relations" untuk hubungan internasional, diplomasi, keamanan global,
    organisasi internasional, dan hukum internasional.
    "Public Administration" untuk administrasi publik, birokrasi, kebijakan publik,
    dan manajemen pemerintahan.
    "Criminology" untuk kriminologi, hukum pidana, sistem keadilan, dan pencegahan kejahatan.
    "Sociology" untuk sosiologi, struktur sosial, stratifikasi, perubahan sosial,
    dan teori sosiologis.
    "Anthropology" untuk antropologi budaya, fisik, linguistik, dan arkeologi.
    "Geography" untuk geografi fisik, manusia, GIS, kartografi, dan studi lingkungan.
    "Demography" untuk demografi, populasi, fertilitas, mortalitas, dan migrasi.
    "Social Work" untuk kesejahteraan sosial, kerja sosial, layanan manusia,
    dan advokasi sosial.
    "Communication Studies" untuk komunikasi massa, interpersonal, organisasi,
    teori komunikasi, dan media.
    "Journalism" untuk jurnalistik, pemberitaan, etika media, dan pers.
    "Media Studies" untuk studi media, budaya populer, film, televisi,
    dan media digital.
    "Library Science" untuk ilmu perpustakaan, organisasi pengetahuan,
    layanan informasi, dan manajemen koleksi.
    "Information Science" untuk ilmu informasi, sistem informasi, pencarian informasi,
    dan manajemen pengetahuan.
    "Linguistics" untuk linguistik, fonologi, sintaksis, semantik, pragmatik,
    dan akuisisi bahasa.
    "Music" untuk musikologi, teori musik, komposisi, etnomusikologi,
    dan pendidikan musik.
    "Theater" untuk teater, drama, seni pertunjukan, akting, dan regia.
    "Sports Science" untuk ilmu olahraga, fisiologi olahraga, biomekanika,
    psikologi olahraga, dan manajemen olahraga.
    "Nutrition" untuk nutrisi, dietetika, ilmu makanan, kesehatan masyarakat,
    dan metabolisme.
    "Gender Studies" untuk studi gender, feminisme, kesetaraan gender,
    dan seksualitas.
    "Cultural Studies" untuk studi budaya, representasi, identitas,
    budaya populer, dan teori kritis.
    "Area Studies" untuk studi kawasan, studi regional, dan perbandingan antarwilayah.
    "Ethnic Studies" untuk studi etnis, ras, migrasi, diaspora,
    dan hubungan antar-etnik.
11. Gunakan "Other" hanya jika tidak ada kategori yang cocok.

Aturan output:
- Pilih tepat satu kategori dari daftar.
- confidence 0.0-1.0 sesuai keyakinan.
- keywords maksimal 8 istilah penting.
- summary maksimal 2 kalimat.
- Jawab hanya dengan JSON sesuai schema.
"""


class NvidiaClassifyError(Exception):
    """Error klasifikasi NVIDIA yang bisa ditangani route dengan fallback."""


class _ApiError(Exception):
    """Error internal request NVIDIA."""

    def __init__(self, message: str, *, status_code=None,
                 retryable: bool = False, next_key: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.next_key = next_key


def _as_list(value) -> list:
    """Normalisasi nilai author/subject yang bisa string atau list."""
    if value is None:
        return []
    if isinstance(value, str):
        value = value.strip()
        return [value] if value else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _get_api_keys() -> list:
    """Kumpulkan API key NVIDIA dari environment, lalu deduplikasi.

    Sumber yang didukung:
    - NVIDIA_API_KEY
    - NVIDIA_API_KEYS (banyak key dipisah koma)
    - NVIDIA_API_KEY_1 .. NVIDIA_API_KEY_3
    """
    keys = []

    key = os.getenv("NVIDIA_API_KEY", "").strip()
    if key:
        keys.append(key)

    multi = os.getenv("NVIDIA_API_KEYS", "")
    if multi:
        keys.extend(part.strip() for part in multi.split(",") if part.strip())

    for index in range(1, 4):
        key = os.getenv(f"NVIDIA_API_KEY_{index}", "").strip()
        if key:
            keys.append(key)

    key = str(getattr(Config, "NVIDIA_API_KEY", "") or "").strip()
    if key:
        keys.append(key)

    seen = set()
    return [key for key in keys if not (key in seen or seen.add(key))]


_CACHE_LOCK = threading.RLock()
_CACHE = TTLCache(
    maxsize=max(1, Config.NVIDIA_CACHE_SIZE),
    ttl=max(1, Config.NVIDIA_CACHE_TTL),
)


def clear_cache() -> None:
    """Kosongkan cache klasifikasi (dipakai test dan benchmark)."""
    with _CACHE_LOCK:
        _CACHE.clear()


def cache_info() -> dict:
    """Statistik ringkas cache untuk observability."""
    with _CACHE_LOCK:
        return {
            "enabled": bool(Config.NVIDIA_CACHE_ENABLED),
            "size": len(_CACHE),
            "maxsize": _CACHE.maxsize,
            "ttl": _CACHE.ttl,
        }


def _cache_key(title, abstract, authors, year, source, subjects) -> str:
    """Kunci cache stabil: model + prompt + isi dokumen."""
    payload = {
        "schema": 1,
        "model": Config.NVIDIA_MODEL,
        "prompt": hashlib.sha256(SUBJECT_PROMPT.encode("utf-8")).hexdigest()[:16],
        "title": str(title or "").strip(),
        "abstract": str(abstract or "").strip(),
        "authors": _as_list(authors),
        "year": str(year or ""),
        "source": str(source or ""),
        "subjects": _as_list(subjects),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str):
    if not Config.NVIDIA_CACHE_ENABLED:
        return None
    with _CACHE_LOCK:
        value = _CACHE.get(key)
    return copy.deepcopy(value) if value is not None else None


def _cache_set(key: str, value: dict) -> None:
    if not Config.NVIDIA_CACHE_ENABLED:
        return
    with _CACHE_LOCK:
        _CACHE[key] = copy.deepcopy(value)


def _build_schema() -> dict:
    """JSON Schema untuk respons klasifikasi."""
    return {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": CATEGORIES},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 8,
            },
            "summary": {"type": "string", "maxLength": 500},
        },
        "required": ["category", "confidence", "keywords", "summary"],
        "additionalProperties": False,
    }


def _build_prompt(title: str, abstract: str = None, authors: list = None,
                  year: str = "", source: str = "", subjects: list = None) -> str:
    """Bangun prompt klasifikasi dengan membatasi ukuran teks."""
    title_text = str(title or "Unknown").strip()[:300]
    abstract_text = str(abstract or "No abstract available").strip()[:2500]
    author_list = _as_list(authors)
    subject_list = _as_list(subjects)

    return SUBJECT_PROMPT.format(
        title=title_text,
        abstract=abstract_text,
        authors=", ".join(author_list) if author_list else "Unknown",
        year=str(year or "Unknown"),
        source=str(source or "Unknown"),
        subjects=", ".join(subject_list) if subject_list else "None",
        categories="\n".join(f"- {category}" for category in CATEGORIES),
    )


def _normalize_category(value: str) -> str:
    """Samakan kategori dari model dengan daftar kategori resmi."""
    if value in CATEGORIES:
        return value

    aliases = {
        "ai": "Artificial Intelligence",
        "ml": "Machine Learning",
        "nlp": "Natural Language Processing",
        "iot": "Internet of Things",
        "it": "Engineering",
        "computer science": "Data Science",
    }
    lowered = value.strip().lower()
    if lowered in aliases:
        return aliases[lowered]

    for category in CATEGORIES:
        if category.lower() == lowered:
            return category

    return "Other"


def _parse_classification(content: str) -> dict:
    """Parse dan validasi isi respons model."""
    if not isinstance(content, str) or not content.strip():
        raise NvidiaClassifyError("Respons NVIDIA kosong")

    text = content.strip()

    # Bersihkan pagar markdown ```json ... ``` bila model tetap menambahkannya.
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text).strip()

    # Ambil objek JSON pertama bila ada teks pembuka/penutup.
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NvidiaClassifyError(f"Respons NVIDIA bukan JSON valid: {exc}") from exc

    if not isinstance(data, dict):
        raise NvidiaClassifyError("Respons NVIDIA bukan objek JSON")

    raw_category = str(data.get("category", "Other")).strip()
    category = _normalize_category(raw_category)
    if category != raw_category:
        log.warning("Kategori NVIDIA tidak dikenal: %r -> %s", raw_category, category)

    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    keywords = _as_list(data.get("keywords"))
    seen = set()
    keywords = [
        keyword for keyword in keywords
        if not (keyword.lower() in seen or seen.add(keyword.lower()))
    ][:8]

    summary = str(data.get("summary", "")).strip()[:500]

    return {
        "category": category,
        "confidence": round(confidence, 2),
        "keywords": keywords,
        "summary": summary,
        "provider": "nvidia",
    }


def _request_once(api_key: str, prompt: str, timeout: int) -> dict:
    """Satu request ke NVIDIA NIM, lalu parse hasilnya."""
    url = f"{Config.NVIDIA_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": Config.NVIDIA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": Config.NVIDIA_MAX_TOKENS,
        "temperature": Config.NVIDIA_TEMPERATURE,
        "top_p": Config.NVIDIA_TOP_P,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "literasiai_classification",
                "schema": _build_schema(),
                "strict": True,
            },
        },
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    except requests.Timeout as exc:
        raise _ApiError(f"Timeout setelah {timeout} detik", retryable=True) from exc
    except requests.RequestException as exc:
        raise _ApiError(f"Koneksi ke NVIDIA gagal: {exc}", retryable=True) from exc

    if response.status_code != 200:
        body = (response.text or "")[:500]
        status = response.status_code

        if status in (401, 403):
            raise _ApiError(
                f"HTTP {status}: API key NVIDIA ditolak",
                status_code=status,
                next_key=True,
            )
        if status in (402, 429):
            raise _ApiError(
                f"HTTP {status}: rate limit/quota NVIDIA",
                status_code=status,
                next_key=True,
            )
        if status >= 500:
            raise _ApiError(
                f"HTTP {status}: {body}",
                status_code=status,
                retryable=True,
            )
        raise _ApiError(
            f"HTTP {status}: {body}",
            status_code=status,
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise _ApiError(
            f"Respons NVIDIA bukan JSON: {(response.text or '')[:300]}",
            retryable=True,
        ) from exc

    if not isinstance(data, dict):
        raise _ApiError("Respons NVIDIA bukan objek JSON", retryable=True)

    if data.get("error"):
        error = data["error"]
        if isinstance(error, dict):
            message = json.dumps(error)[:500]
            code = error.get("code")
        else:
            message = str(error)[:500]
            code = None

        try:
            code_int = int(code)
        except (TypeError, ValueError):
            code_int = None

        lowered = message.lower()
        if code_int in (401, 403) or "invalid api key" in lowered or "unauthorized" in lowered:
            raise _ApiError(
                f"API error: {message}",
                status_code=code_int,
                next_key=True,
            )
        if code_int in (402, 429) or "rate limit" in lowered or "quota" in lowered:
            raise _ApiError(
                f"API error: {message}",
                status_code=code_int,
                next_key=True,
            )
        if code_int is not None and code_int >= 500:
            raise _ApiError(
                f"API error: {message}",
                status_code=code_int,
                retryable=True,
            )
        raise _ApiError(f"API error: {message}", status_code=code_int)

    choices = data.get("choices") or []
    if not choices:
        message = data.get("message") or "Respons tidak berisi choices"
        raise _ApiError(str(message)[:500], retryable=True)

    message = choices[0].get("message") or {}
    content = message.get("content")

    try:
        return _parse_classification(content)
    except NvidiaClassifyError as exc:
        raise _ApiError(f"Output tidak valid: {exc}", retryable=True) from exc


def classify_document(title: str, abstract: str = None, authors: list = None,
                      year: str = "", source: str = "", subjects: list = None) -> dict:
    """
    Klasifikasi satu dokumen menggunakan NVIDIA Nemotron.

    Return dict: category, confidence, keywords, summary, provider.
    Raise NvidiaClassifyError bila semua key/percobaan gagal.
    """
    cache_key = _cache_key(title, abstract, authors, year, source, subjects)
    cached = _cache_get(cache_key)
    if cached is not None:
        log.debug("NVIDIA cache hit: %s", cache_key[:12])
        return cached

    keys = _get_api_keys()
    if not keys:
        raise NvidiaClassifyError("NVIDIA_API_KEY belum dikonfigurasi")

    prompt = _build_prompt(
        title=title,
        abstract=abstract,
        authors=authors,
        year=year,
        source=source,
        subjects=subjects,
    )

    last_error = None
    retries = max(0, Config.NVIDIA_MAX_RETRIES)

    for key_index, api_key in enumerate(keys, start=1):
        for attempt in range(retries + 1):
            try:
                result = _request_once(api_key, prompt, Config.NVIDIA_TIMEOUT)
                _cache_set(cache_key, result)
                return result

            except _ApiError as exc:
                last_error = exc

                if exc.next_key:
                    log.warning("NVIDIA key #%s gagal: %s", key_index, exc)
                    break

                if not exc.retryable:
                    raise NvidiaClassifyError(
                        f"Request NVIDIA ditolak: {exc}"
                    ) from exc

                if attempt >= retries:
                    break

                delay = min(2 ** attempt, 8)
                log.warning(
                    "NVIDIA request gagal (%s); retry %s/%s dalam %s detik",
                    exc, attempt + 1, retries, delay,
                )
                time.sleep(delay)

    raise NvidiaClassifyError(f"Semua percobaan NVIDIA gagal: {last_error}")
