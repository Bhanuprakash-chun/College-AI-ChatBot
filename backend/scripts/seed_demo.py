"""Seed a demo environment: users plus indexed sample documents.

Runs the same ingestion path the admin upload endpoint uses -- extraction,
chunking, embedding and ChromaDB insertion -- so the result is a genuinely
populated system, not fixtures.

    python scripts/seed_demo.py [--reset]
"""

import argparse
import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.database.session import create_all, db_state, session_scope  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.enums import DocumentStatus, DocumentType, UserRole  # noqa: E402
from app.models.user import User  # noqa: E402
from app.rag.vector_store import vector_store  # noqa: E402
from app.services.document_service import documents_dir, process_document  # noqa: E402
from app.utils.files import safe_filename, sha256_of  # noqa: E402

DEMO_USERS = [
    {
        "email": "admin@college.edu",
        "full_name": "College Administrator",
        "password": "Admin@12345",
        "role": UserRole.ADMIN,
        "department": "Administration",
    },
    {
        "email": "student@college.edu",
        "full_name": "Demo Student",
        "password": "Student@12345",
        "role": UserRole.STUDENT,
        "department": "Computer Science",
    },
]

# filename -> (department, document_type, academic_year)
DOC_METADATA = {
    "attendance_policy.pdf": ("Academics", DocumentType.POLICY, "2025-26"),
    "examinations_policy.pdf": ("Examinations", DocumentType.POLICY, "2025-26"),
    "admissions_policy.pdf": ("Admissions", DocumentType.POLICY, "2025-26"),
    "fees_structure.pdf": ("Accounts", DocumentType.CIRCULAR, "2025-26"),
    "certificates_services.pdf": ("Administration", DocumentType.HANDBOOK, "2025-26"),
    "courses_curriculum.pdf": ("Academics", DocumentType.SYLLABUS, "2025-26"),
    "placements_handbook.pdf": ("Placements", DocumentType.HANDBOOK, "2025-26"),
    "scholarships_policy.pdf": ("Scholarships", DocumentType.POLICY, "2025-26"),
    "hostel_rules.pdf": ("Hostel", DocumentType.HANDBOOK, "2025-26"),
    "college_general_info.pdf": ("General", DocumentType.HANDBOOK, "2025-26"),
}


def seed_users(db) -> None:
    print("\nUsers")
    for spec in DEMO_USERS:
        existing = db.execute(
            select(User).where(func.lower(User.email) == spec["email"])
        ).scalar_one_or_none()
        if existing is not None:
            print(f"  exists   {spec['email']} ({existing.role.value})")
            continue
        user = User(
            email=spec["email"],
            full_name=spec["full_name"],
            hashed_password=hash_password(spec["password"]),
            role=spec["role"],
            department=spec["department"],
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"  created  {spec['email']}  password: {spec['password']}  ({spec['role'].value})")


def seed_documents(db, source_dir: Path) -> None:
    print("\nDocuments")
    pdfs = sorted(source_dir.glob("*.pdf"))
    if not pdfs:
        print(f"  No PDFs found in {source_dir}.")
        print("  Run: python scripts/generate_sample_documents.py")
        return

    admin = db.execute(
        select(User).where(User.role == UserRole.ADMIN).order_by(User.id)
    ).scalars().first()

    for pdf in pdfs:
        content = pdf.read_bytes()
        checksum = sha256_of(content)

        existing = db.execute(
            select(Document).where(Document.checksum == checksum)
        ).scalar_one_or_none()
        if existing is not None:
            print(f"  exists   {pdf.name} (document #{existing.id}, {existing.status.value})")
            continue

        department, doc_type, year = DOC_METADATA.get(
            pdf.name, ("General", DocumentType.OTHER, "")
        )
        stored_name = safe_filename(pdf.name, ".pdf")
        destination = documents_dir() / stored_name
        shutil.copyfile(pdf, destination)

        document = Document(
            filename=stored_name,
            original_filename=pdf.name,
            file_path=str(destination),
            file_size=len(content),
            content_type="application/pdf",
            checksum=checksum,
            title=pdf.stem.replace("_", " ").title(),
            department=department,
            document_type=doc_type,
            academic_year=year,
            status=DocumentStatus.PROCESSING,
            uploaded_by_id=admin.id if admin else None,
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        print(f"  indexing {pdf.name} ...", end=" ", flush=True)
        process_document(document.id)
        db.expire_all()
        refreshed = db.get(Document, document.id)
        if refreshed.status == DocumentStatus.READY:
            print(f"ready ({refreshed.page_count} pages, {refreshed.chunk_count} chunks)")
        else:
            print(f"FAILED: {refreshed.error_message}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=str(BACKEND_DIR.parent / "documents" / "samples"),
        help="Directory of PDFs to ingest.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear the vector store before seeding.",
    )
    args = parser.parse_args()

    create_all()
    print(f"Database: {db_state.backend}")
    if db_state.fallback_reason:
        print(f"  (fallback: {db_state.fallback_reason})")

    if args.reset:
        print("Resetting vector store ...")
        vector_store.reset()

    db = session_scope()
    try:
        seed_users(db)
        seed_documents(db, Path(args.source))
    finally:
        db.close()

    print(f"\nVector store: {vector_store.count()} chunks indexed at {settings.CHROMA_PATH}")
    print("Done.")


if __name__ == "__main__":
    main()
