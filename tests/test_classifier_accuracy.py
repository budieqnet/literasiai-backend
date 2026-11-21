"""
tests/test_classifier_accuracy.py
Uji akurasi klasifikasi NVIDIA pada dataset kecil berlabel.

Script ini MEMANGGIL API NVIDIA ASLI (butuh NVIDIA_API_KEY di .env) dan
menghabiskan kuota free tier. Jalankan secara sequential dengan jeda agar
tidak kena rate limit.

Jalankan:
    python tests/test_classifier_accuracy.py
    python tests/test_classifier_accuracy.py --limit 10 --delay 1
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.nvidia import (  # noqa: E402
    NvidiaClassifyError,
    _get_api_keys,
    classify_document,
)


SAMPLES = [
    {
        "expected": "Medical Imaging",
        "title": "Deep Learning for Medical Image Segmentation: A Systematic Review",
        "abstract": "This review analyzes U-Net variants, transformers, and attention mechanisms for segmenting CT, MRI, and histopathology images.",
    },
    {
        "expected": "Natural Language Processing",
        "title": "Transformer-Based Sentiment Analysis of Indonesian Social Media Texts",
        "abstract": "Fine-tuned IndoBERT models classify customer reviews into positive, negative, and neutral sentiment using attention-based transformer architectures.",
    },
    {
        "expected": "Computer Vision",
        "title": "Real-Time Object Detection for Autonomous Vehicles Using YOLOv8",
        "abstract": "An improved YOLOv8 detector is evaluated on urban driving datasets for vehicle, pedestrian, and traffic-sign detection in real time.",
    },
    {
        "expected": "Machine Learning",
        "title": "A Comparative Study of Supervised and Unsupervised Learning Algorithms for Credit Scoring",
        "abstract": "Logistic regression, random forests, and k-means clustering are compared on loan applicant data to predict credit default.",
    },
    {
        "expected": "Artificial Intelligence",
        "title": "Knowledge Representation and Automated Reasoning for Intelligent Agents",
        "abstract": "The paper develops ontologies, rule-based inference, and planning algorithms for autonomous intelligent agents.",
    },
    {
        "expected": "Data Science",
        "title": "Big Data Analytics for Customer Churn Prediction in Telecommunications",
        "abstract": "Spark-based analytics and feature engineering are used to analyze large subscriber datasets and predict customer churn.",
    },
    {
        "expected": "Robotics",
        "title": "Reinforcement Learning for Robotic Manipulation in Unstructured Environments",
        "abstract": "A robot arm learns grasping and manipulation policies using deep reinforcement learning and visual feedback.",
    },
    {
        "expected": "Cybersecurity",
        "title": "Detecting Phishing Attacks Using Machine Learning and URL Features",
        "abstract": "Phishing URLs are classified using random forests and gradient boosting with lexical, host-based, and content features.",
    },
    {
        "expected": "Cloud Computing",
        "title": "Serverless Computing: Performance and Cost Optimization in Cloud Environments",
        "abstract": "The study benchmarks function-as-a-service platforms and proposes scheduling strategies to reduce latency and cloud costs.",
    },
    {
        "expected": "Internet of Things",
        "title": "IoT-Enabled Smart Agriculture Monitoring System with Wireless Sensor Networks",
        "abstract": "Wireless soil-moisture and temperature sensors transmit data to a cloud dashboard for automated irrigation decisions.",
    },
    {
        "expected": "Blockchain",
        "title": "Blockchain-Based Traceability in Agricultural Supply Chains",
        "abstract": "A permissioned blockchain and smart contracts record provenance and transactions across farmers, distributors, and retailers.",
    },
    {
        "expected": "Quantum Computing",
        "title": "Quantum Error Correction for Scalable Quantum Computers",
        "abstract": "Surface codes and fault-tolerant logical qubits are analyzed to suppress decoherence in large-scale quantum processors.",
    },
    {
        "expected": "Bioinformatics",
        "title": "Genome-Wide Association Studies and Bioinformatics Pipelines for Precision Medicine",
        "abstract": "Next-generation sequencing data are processed with variant-calling pipelines to identify genetic markers associated with disease.",
    },
    {
        "expected": "Health Informatics",
        "title": "Electronic Health Records and Telemedicine Adoption in Rural Clinics",
        "abstract": "The study evaluates EHR interoperability and telemedicine workflows in rural primary-care settings.",
    },
    {
        "expected": "Environmental Science",
        "title": "Impact of Climate Change on Coastal Ecosystems and Biodiversity",
        "abstract": "Rising sea levels, ocean warming, and acidification are assessed for their effects on coastal habitats and species diversity.",
    },
    {
        "expected": "Physics",
        "title": "Measurement of Neutrino Oscillations in Particle Physics Experiments",
        "abstract": "Detector data from accelerator and atmospheric neutrino experiments are analyzed to constrain oscillation parameters.",
    },
    {
        "expected": "Chemistry",
        "title": "Catalytic Conversion of Carbon Dioxide into Renewable Chemicals",
        "abstract": "Metal-organic frameworks and transition-metal catalysts are investigated for CO2 hydrogenation into methanol and formic acid.",
    },
    {
        "expected": "Mathematics",
        "title": "Graph Theory and Combinatorial Optimization Algorithms",
        "abstract": "The paper proves new bounds for graph coloring and develops approximation algorithms for combinatorial optimization problems.",
    },
    {
        "expected": "Economics",
        "title": "Financial Inclusion and Economic Growth in Developing Countries",
        "abstract": "Panel data from emerging economies are used to estimate the effect of financial inclusion on GDP growth and inequality.",
    },
    {
        "expected": "Law",
        "title": "Legal Regulation of Personal Data Protection in Indonesia",
        "abstract": "The study analyzes Indonesia's personal data protection law, consent requirements, and enforcement mechanisms.",
    },
    {
        "expected": "Engineering",
        "title": "Seismic Performance of Reinforced Concrete Bridge Structures",
        "abstract": "Finite-element models and shake-table tests are used to evaluate the seismic resilience of reinforced concrete bridges.",
    },
    {
        "expected": "Social Science",
        "title": "Social Capital and Community Resilience in Urban Slums",
        "abstract": "Ethnographic fieldwork examines how social networks and community organizations support resilience in informal urban settlements.",
    },
    {
        "expected": "Education",
        "title": "The Effectiveness of Blended Learning in Higher Education",
        "abstract": "A quasi-experimental study compares blended and face-to-face instruction on student achievement and engagement.",
    },
    {
        "expected": "Psychology",
        "title": "Cognitive Behavioral Therapy for Generalized Anxiety Disorder",
        "abstract": "A randomized controlled trial evaluates the efficacy of cognitive behavioral therapy on anxiety symptoms and worry.",
    },
    {
        "expected": "Literature",
        "title": "Narrative Structure and Identity in Contemporary Indonesian Poetry",
        "abstract": "The study analyzes narrative voice, metaphor, and identity construction in contemporary Indonesian poetry collections.",
    },
    {
        "expected": "History",
        "title": "Maritime Trade Routes in Southeast Asia, 1500-1800",
        "abstract": "Archival sources and port records are used to reconstruct maritime trade networks and commercial exchange in early modern Southeast Asia.",
    },
    {
        "expected": "Philosophy",
        "title": "Metaphysics of Causality in Hume and Kant",
        "abstract": "The paper compares Humean and Kantian accounts of causation, necessity, and the conditions of empirical knowledge.",
    },
    {
        "expected": "Religion",
        "title": "Interfaith Dialogue and Religious Pluralism in Indonesia",
        "abstract": "The study examines theological foundations and social practices of interfaith dialogue among religious communities in Indonesia.",
    },
    {
        "expected": "Arts",
        "title": "Digital Sound Design and Contemporary Music Composition",
        "abstract": "The paper explores synthesis techniques, spatial audio, and digital composition practices in contemporary electronic music.",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Uji akurasi klasifikasi NVIDIA")
    parser.add_argument("--limit", type=int, default=0, help="Batasi jumlah sampel (0 = semua)")
    parser.add_argument("--delay", type=float, default=0.5, help="Jeda antar request (detik)")
    parser.add_argument("--min-accuracy", type=float, default=0.0, help="Ambang akurasi minimum (0-1)")
    args = parser.parse_args()

    if not _get_api_keys():
        print("ERROR: NVIDIA_API_KEY belum dikonfigurasi di environment/.env")
        return 2

    samples = SAMPLES[:args.limit] if args.limit > 0 else SAMPLES

    print("=" * 98)
    print("  LiterasiAI — Uji Akurasi Klasifikasi NVIDIA Nemotron")
    print(f"  Sampel: {len(samples)} | Delay: {args.delay}s | Model: {os.getenv('NVIDIA_MODEL', 'default')}")
    print("=" * 98)
    print(f"{'No':<3} {'Expected':<28} {'Predicted':<28} {'Conf':>5} {'Detik':>6}  Status")
    print("-" * 98)

    correct = 0
    errors = 0
    latencies = []
    mismatches = []

    for index, sample in enumerate(samples, start=1):
        start = time.perf_counter()
        try:
            result = classify_document(
                title=sample["title"],
                abstract=sample.get("abstract", ""),
            )
            latency = time.perf_counter() - start
            latencies.append(latency)

            expected = sample["expected"]
            predicted = result["category"]
            is_correct = predicted == expected
            if is_correct:
                correct += 1
            else:
                mismatches.append((index, expected, predicted, result["confidence"]))

            status = "OK" if is_correct else "SALAH"
            print(
                f"{index:<3} {expected:<28} {predicted:<28} "
                f"{result['confidence']:>5.2f} {latency:>6.2f}  {status}"
            )
        except NvidiaClassifyError as exc:
            latency = time.perf_counter() - start
            errors += 1
            print(f"{index:<3} {sample['expected']:<28} {'ERROR':<28} {'-':>5} {latency:>6.2f}  {exc}")

        if index < len(samples) and args.delay > 0:
            time.sleep(args.delay)

    total = len(samples)
    evaluated = total - errors
    accuracy = (correct / evaluated) if evaluated else 0.0
    avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0

    print("-" * 98)
    print(f"Benar        : {correct}/{evaluated}")
    print(f"Akurasi      : {accuracy * 100:.1f}%")
    print(f"Error API    : {errors}")
    print(f"Rata-rata    : {avg_latency:.2f} detik/request")

    if mismatches:
        print("\nMismatch:")
        for index, expected, predicted, confidence in mismatches:
            print(f"  #{index}: expected={expected!r}, predicted={predicted!r}, confidence={confidence:.2f}")

    if errors and evaluated == 0:
        return 1
    if accuracy < args.min_accuracy:
        print(f"\nGAGAL: akurasi {accuracy * 100:.1f}% < minimum {args.min_accuracy * 100:.1f}%")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
