import io
import os
import shutil
import zipfile
import psycopg2
from graph_analysis import GraphAnalyzer
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, status, Depends

# Import the main pipeline execution function directly from sih_6_2.py
from sih_6_2 import run_pipeline

app = FastAPI(title="UNRAVEL Criminal Network Router")

load_dotenv()

# Get the Neon connection URL from .env
DATABASE_URL = os.getenv("DATABASE_URL")

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from lyzr_chat import call_lyzr_agent

app = FastAPI()

class ChatRequest(BaseModel):
    message: str
    user_id: str = "aniruddhasharma141104@gmail.com"
    session_id: str = "6aabf939be73873d04ecd627-950i7xmw"

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        response_data = await call_lyzr_agent(
            message=request.message,
            user_id=request.user_id,
            session_id=request.session_id
        )
        return response_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


# Ensure audit_ingestion_logs table exists in Neon on server startup
@app.on_event("startup")
def init_db():
    if not DATABASE_URL:
        print("WARNING: DATABASE_URL is not set in .env")
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_ingestion_logs (
                    id SERIAL PRIMARY KEY,
                    file_name VARCHAR(255) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    error_message TEXT,
                    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        conn.commit()
        conn.close()
        print("Successfully initialized audit table in Neon database.")
    except Exception as e:
        print(f"Error initializing Neon database: {e}")


def write_logbook(db_conn, filename: str, status_msg: str, error_msg: str = None):
    query = """
        INSERT INTO audit_ingestion_logs (file_name, status, error_message, ingested_at)
        VALUES (%s, %s, %s, NOW());
    """
    with db_conn.cursor() as cursor:
        cursor.execute(query, (filename, status_msg, error_msg))
    db_conn.commit()


# ---------------------------------------------------------------------------
# Filename normalization + validation
# ---------------------------------------------------------------------------
# Keyword -> exact filename that sih_6_2.run_pipeline() expects to find.
# The first keyword that matches (case-insensitive substring) inside an
# uploaded filename wins, so upload names don't have to be exact.
FILENAME_KEYWORDS = {
    "person": "persons.csv",
    "phone": "phones.csv",
    "account": "accounts.csv",
    "cdr": "cdr.csv",
    "call": "cdr.csv",
    "transaction": "transactions.csv",
    "txn": "transactions.csv",
    "fir": "fir_records.txt",
}

# Files the pipeline can genuinely run without (it just skips that section).
OPTIONAL_TARGETS = set()

# All possible target files the pipeline looks for.
ALL_TARGETS = set(FILENAME_KEYWORDS.values())


def normalize_filenames(extracted_files: list[str]) -> list[str]:
    """
    Given the list of filenames actually extracted from the upload,
    copy/rename each one (where possible) to the exact filename
    sih_6_2.run_pipeline() expects, based on keyword matching.
    Returns the list of target filenames that were successfully resolved.
    """
    resolved = set()
    for fname in extracted_files:
        lower = fname.lower()
        for keyword, target_name in FILENAME_KEYWORDS.items():
            if keyword in lower:
                if fname != target_name:
                    shutil.copy(fname, target_name)
                resolved.add(target_name)
                break
    return sorted(resolved)


def validate_required_files(resolved_targets: list[str]) -> list[str]:
    """
    Returns a list of required target filenames that are still missing
    after normalization. An empty list means everything needed is present.
    """
    required = ALL_TARGETS - OPTIONAL_TARGETS
    missing = sorted(required - set(resolved_targets))
    return missing


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/api/upload", status_code=status.HTTP_200_OK)
async def route_raw_files(
    file: UploadFile = File(...),
    db = Depends(get_db)
):
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    file_bytes = await file.read()

    extracted_files = []

    try:
        # 1. Save uploaded file/unzip contents into local workspace (Retained for testing)
        if ext == ".zip":
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                for member_name in z.namelist():
                    if not member_name.startswith("__MACOSX") and not member_name.endswith("/"):
                        clean_name = os.path.basename(member_name)
                        with open(clean_name, "wb") as f:
                            f.write(z.read(member_name))
                        extracted_files.append(clean_name)
        else:
            with open(filename, "wb") as f:
                f.write(file_bytes)
            extracted_files.append(filename)

        # 2. Normalize filenames so the pipeline can find them regardless of
        #    exactly how the user named the files inside the upload.
        resolved_targets = normalize_filenames(extracted_files)

        # 3. Fail loudly with a clear message if something required is
        #    genuinely missing, instead of letting run_pipeline() silently
        #    skip a section or crash with a cryptic KeyError.
        missing = validate_required_files(resolved_targets)
        if missing:
            raise ValueError(
                f"Missing required file(s) for: {', '.join(missing)}. "
                f"Uploaded files were: {', '.join(extracted_files)}"
            )

        # 4. Call pipeline function directly
        extracted_results = run_pipeline(data_dir=".")

        # 5. Log audit entry in Neon PostgreSQL
        write_logbook(db, filename, "PROCESSED_SUCCESSFULLY")

        return {
            "status": "SUCCESS",
            "message": f"Successfully unpacked and executed module for {filename}",
            "retained_test_files": extracted_files,
            "resolved_files": resolved_targets,
            "data_count": len(extracted_results),
            "data": extracted_results
        }

    except Exception as err:
        write_logbook(db, filename, "FAILED", str(err))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Pipeline execution error: {str(err)}"
        )
# ===================================================================
# Graph Analysis & Alert Generation Endpoint
# ===================================================================
@app.post("/api/analyze-graph", status_code=status.HTTP_200_OK)
async def run_graph_analysis():
    """
    Triggers NetworkX graph construction from the Neon PostgreSQL database
    and executes all four criminal network detection rules.
    """
    if not DATABASE_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DATABASE_URL is not configured in environment."
        )

    try:
        # Pass the Neon DATABASE_URL directly as a string to GraphAnalyzer
        analyzer = GraphAnalyzer(db_config=DATABASE_URL)

        # Build graph from 'relationships' table in Neon
        analyzer.build_graph()

        # Execute graph analysis rules
        detection_results = analyzer.run_all_detections()

        return {
            "status": "SUCCESS",
            "nodes_count": analyzer.G.number_of_nodes(),
            "edges_count": analyzer.G.number_of_edges(),
            "analysis_results": detection_results,
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Graph analysis failed: {str(e)}",
        )
   