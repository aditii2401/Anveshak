import io
import os
import shutil
import zipfile
import psycopg2
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Pipeline & Module Imports
from pipeline import run_full_pipeline
from resolution import run_resolution
from Graph2_analysis import GraphAnalyzer
from evidence_engine import build_alerts_from_detection_results


app = FastAPI(title="UNRAVEL Criminal Network Router")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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





# --- API Routes ---
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

# Temporarily disabled — we are testing graph analysis first
        raise ValueError("Upload route temporarily disabled while testing graph analysis.")

        write_logbook(db, filename, "PROCESSED_SUCCESSFULLY")

    except Exception as err:
        write_logbook(db, filename, "FAILED", str(err))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Pipeline execution error: {str(err)}"
        )



@app.post("/api/analyze-graph", status_code=status.HTTP_200_OK)
async def run_graph_analysis():
    """
    Fetch relationships from PostgreSQL,
    perform entity resolution,
    build NetworkX graph,
    run detections,
    and return graph data for React.
    """

    if not DATABASE_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DATABASE_URL is not configured in environment."
        )

    try:

        # ============================================================
        # 1. Create GraphAnalyzer
        # ============================================================

        analyzer = GraphAnalyzer(db_config=DATABASE_URL)


        # ============================================================
        # 2. Fetch relationships from PostgreSQL
        # ============================================================

        raw_df = analyzer._fetch_relationships_from_db()


        # ============================================================
        # 3. Prepare data for Entity Resolution
        # ============================================================

        mapped_df = raw_df.rename(columns={
            "source_entity_id": "Name A",
            "target_entity_id": "Name B",
            "type": "Relation",
            "source_document_id": "Source ID",
            "context": "Context",
            "confidence": "Confidence"
        })


        # ============================================================
        # 4. Perform Entity Resolution
        # ============================================================

        resolved_df, name_lookup = run_resolution(mapped_df)


        # ============================================================
        # 5. Prepare resolved data for NetworkX
        # ============================================================

        graph_df = resolved_df.rename(columns={
            "Name A": "source_entity_id",
            "Name B": "target_entity_id",
            "Relation": "type",
            "Source ID": "source_document_id",
            "Context": "context",
            "Confidence": "confidence"
        })


        # ============================================================
        # 6. Build NetworkX graph
        # ============================================================

        analyzer.load_from_dataframe(graph_df)


        # ============================================================
        # 7. Run NetworkX detection rules
        # ============================================================

        detection_results = analyzer.run_all_detections()


        # ============================================================
        # 8. Generate evidence-based alerts
        # ============================================================

        alerts = build_alerts_from_detection_results(
            detection_results,
            entity_name_lookup=name_lookup
        )


        # ============================================================
        # 9. Convert NetworkX nodes into JSON
        # ============================================================

        nodes = []

        for node in analyzer.G.nodes():

            nodes.append({
                "id": str(node),
                "label": str(node)
            })


        # ============================================================
        # 10. Convert NetworkX edges into JSON
        # ============================================================

        edges = []

        for index, (source, target, data) in enumerate(
            analyzer.G.edges(data=True)
        ):

            edges.append({
                "id": f"edge-{index}",
                "source": str(source),
                "target": str(target),
                "relation": data.get("relation"),
                "confidence": data.get("confidence"),
                "source_doc": data.get("source_doc"),
                "context": data.get("context")
            })


        # ============================================================
        # 11. Send graph + alerts to React
        # ============================================================

        return {
            "status": "SUCCESS",

            "nodes_count": analyzer.G.number_of_nodes(),

            "edges_count": analyzer.G.number_of_edges(),

            "nodes": nodes,

            "edges": edges,

            "alerts_count": len(alerts),

            "alerts": alerts,

            "raw_analysis": detection_results
        }


    except Exception as e:

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Graph analysis failed: {str(e)}"
        )

    
   
    
