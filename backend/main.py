import io
import os
import shutil
import zipfile
import psycopg2
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, status, Depends
from pydantic import BaseModel

# Pipeline & Module Imports
from sih_6_2 import run_pipeline
from resolution import run_resolution
from graph_analysis import GraphAnalyzer
from evidence_engine import build_alerts_from_detection_results
from lyzr_chat import call_lyzr_agent

app = FastAPI(title="UNRAVEL Criminal Network Router")

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


# --- Database Connection Dependency ---
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


# --- Database Startup Initialization ---
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


# --- Filename Normalization Helpers ---
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

ALL_TARGETS = set(FILENAME_KEYWORDS.values())
OPTIONAL_TARGETS = set()


def normalize_filenames(extracted_files: list[str]) -> list[str]:
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
    required = ALL_TARGETS - OPTIONAL_TARGETS
    return sorted(required - set(resolved_targets))


# --- Pydantic Schema for Chat ---
class ChatRequest(BaseModel):
    message: str
    user_id: str = "aniruddhasharma141104@gmail.com"
    session_id: str = "6aabf939be73873d04ecd627-950i7xmw"


# --- API Routes ---
@app.get("/")
def health():
    return {"status": "ok"}


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

        resolved_targets = normalize_filenames(extracted_files)
        missing = validate_required_files(resolved_targets)
        if missing:
            raise ValueError(
                f"Missing required file(s) for: {', '.join(missing)}. "
                f"Uploaded files were: {', '.join(extracted_files)}"
            )

        extracted_results = run_pipeline(data_dir=".")
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


@app.post("/api/analyze-graph", status_code=status.HTTP_200_OK)
async def run_graph_analysis():
    """
    Fetches raw relationships from PostgreSQL, applies entity resolution 
    for name deduplication, builds NetworkX graph, executes detections, 
    and returns structured alerts with evidence snippets.
    """
    if not DATABASE_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DATABASE_URL is not configured in environment."
        )

    try:
        # 1. Fetch raw relationship rows from DB
        analyzer = GraphAnalyzer(db_config=DATABASE_URL)
        raw_df = analyzer._fetch_relationships_from_db()

        # 2. Map DB column headers to match Entity Resolution input expectations
        mapped_df = raw_df.rename(columns={
            "source_entity_id": "Name A",
            "target_entity_id": "Name B",
            "type": "Relation",
            "source_document_id": "Source ID",
            "context": "Context",
            "confidence": "Confidence"
        })

        # 3. Run Entity Resolution to canonicalize entity IDs & display names
        resolved_df, name_lookup = run_resolution(mapped_df)

        # 4. Map back to NetworkX schema before graph construction
        graph_df = resolved_df.rename(columns={
            "Name A": "source_entity_id",
            "Name B": "target_entity_id",
            "Relation": "type",
            "Source ID": "source_document_id",
            "Context": "context",
            "Confidence": "confidence"
        })

        # 5. Load resolved data into NetworkX & perform detections
        analyzer.load_from_dataframe(graph_df)
        detection_results = analyzer.run_all_detections()

        # 6. Generate structured alert cards using evidence engine
        alerts = build_alerts_from_detection_results(
            detection_results, 
            entity_name_lookup=name_lookup
        )

        return {
            "status": "SUCCESS",
            "nodes_count": analyzer.G.number_of_nodes(),
            "edges_count": analyzer.G.number_of_edges(),
            "alerts_count": len(alerts),
            "alerts": alerts,
            "raw_analysis": detection_results
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Graph analysis failed: {str(e)}",
        )