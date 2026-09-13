import io
import os
from dotenv import load_dotenv
import zipfile
import requests
from typing import List
from fastapi import FastAPI, UploadFile, File, HTTPException, status, Depends
import psycopg2

app = FastAPI(title="NCRB Module 3 - Raw File Router & Logger")

# Configuration
AI_NLP_ENDPOINT = "http://localhost:8001/api/nlp/extract"
load_dotenv()
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "ncrb_backend"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432")
}

# --- DATABASE CONNECTION & LOGBOOK ---
def get_db():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()
        
@app.get("/api/health")
def check_db_health():
    """Health check endpoint to test PostgreSQL connectivity from FastAPI."""
    try:
        # Attempt to establish connection
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            # Execute a lightweight ping query
            cursor.execute("SELECT 1;")
            result = cursor.fetchone()
        conn.close()
        
        return {
            "status": "ONLINE",
            "database_connected": True,
            "database_name": DB_CONFIG["dbname"],
            "query_result": result[0]
        }
    except Exception as err:
        return {
            "status": "ERROR",
            "database_connected": False,
            "error_detail": str(err)
        }
    
def write_logbook(db_conn, filename: str, status_msg: str, error_msg: str = None):
    """Writes an audit receipt directly into PostgreSQL."""
    query = """
        INSERT INTO audit_ingestion_logs (file_name, status, error_message, ingested_at)
        VALUES (%s, %s, %s, NOW());
    """
    with db_conn.cursor() as cursor:
        cursor.execute(query, (filename, status_msg, error_msg))
    db_conn.commit()


# --- API ROUTE & UNZIP ROUTER ---
@app.post("/api/upload", status_code=status.HTTP_200_OK)
async def route_raw_files(
    file: UploadFile = File(...),
    db = Depends(get_db)
):
    """
    1. Receives uploaded file from React frontend.
    2. Unzips in memory if it's a ZIP archive, or keeps the file as-is.
    3. Forwards raw file streams to AI/NLP endpoint.
    4. Writes execution receipt into PostgreSQL logbook.
    """
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    file_bytes = await file.read()
    
    files_to_send = []

    try:
        # Step 1: Unzip if ZIP archive
        if ext == ".zip":
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                for member_name in z.namelist():
                    # Ignore macOS system metadata files and directory entries
                    if not member_name.startswith("__MACOSX") and not member_name.endswith("/"):
                        member_bytes = z.read(member_name)
                        clean_name = os.path.basename(member_name)
                        files_to_send.append(
                            ("files", (clean_name, member_bytes, "application/octet-stream"))
                        )
        # Step 2: Single file handling (CSV, TXT, Excel)
        else:
            files_to_send.append(
                ("files", (filename, file_bytes, file.content_type or "application/octet-stream"))
            )

        # Step 3: Forward raw files directly to your friend's AI/NLP endpoint
        ai_response = requests.post(
            AI_NLP_ENDPOINT,
            files=files_to_send,
            timeout=60
        )

        # Step 4: Write receipt to logbook
        write_logbook(db, filename, f"SENT_TO_AI_{ai_response.status_code}")

        return {
            "status": "SUCCESS",
            "message": f"Forwarded {len(files_to_send)} file(s) to AI module.",
            "forwarded_files": [f[1][0] for f in files_to_send],
            "ai_response_status": ai_response.status_code
        }

    except Exception as err:
        write_logbook(db, filename, "FAILED", str(err))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to route file: {str(err)}"
        )