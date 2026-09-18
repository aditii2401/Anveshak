"""
Handle file uploads (FIR text, CDR CSV, transaction CSV) with validation, 
and wire ingestion -> extraction -> resolution -> storage -> graph
-> detection -> evidence into one runnable pipeline.
"""

import os
import pandas as pd

from Graph2_analysis import GraphAnalyzer
from evidence_engine import build_alerts_from_detection_results
from resolution import run_resolution, convert_seed_to_raw_format, combine_extraction_sources


# ==========================================================================
#  FILE UPLOAD VALIDATION
# ==========================================================================
class ValidationError(Exception):
    pass


def validate_fir_upload(file_path):
    
    if not os.path.exists(file_path):
        raise ValidationError(f"FIR file not found: {file_path}")
    if not file_path.lower().endswith(".txt"):
        raise ValidationError("FIR file must be a .txt file.")
    if os.path.getsize(file_path) == 0:
        raise ValidationError("FIR file is empty.")
    return True


def validate_csv_upload(file_path, required_columns):

    if not os.path.exists(file_path):
        raise ValidationError(f"CSV file not found: {file_path}")
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        raise ValidationError(f"Could not read CSV file: {e}")

    if df.empty:
        raise ValidationError(f"CSV file is empty: {file_path}")

    missing = set(required_columns) - set(df.columns)
    if missing:
        raise ValidationError(f"CSV is missing required columns {missing}: {file_path}")

    return df


# ==========================================================================
# PLACEHOLDERS 
# ==========================================================================
def run_extraction(extraction_output_path):
   
    df = pd.read_csv(extraction_output_path)
    required = {"Name A", "Name B", "Relation", "Source ID", "Context", "Confidence"}
    missing = required - set(df.columns)
    if missing:
        raise ValidationError(f"Extraction output missing expected columns: {missing}")
    return df


def run_resolution_stage(raw_extraction_df, threshold=80):
    
    return run_resolution(raw_extraction_df, threshold=threshold)


def store_to_database(resolved_df, entity_name_lookup, db_config):
  
    try:
        import psycopg2
    except ImportError:
        raise ImportError("psycopg2 is not installed. Run: pip install psycopg2-binary")

    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()

    try:
        # Insert canonical entities first (relationships reference these)
        for entity_id, display_name in entity_name_lookup.items():
            cur.execute(
                """
                INSERT INTO persons (id, name) VALUES (%s, %s)
                ON CONFLICT (id) DO NOTHING;
                """,
                (entity_id, display_name)
            )

        # Insert relationships
        for _, row in resolved_df.iterrows():
            cur.execute(
                """
                INSERT INTO relationships
                    (source_entity_id, target_entity_id, relationship_type,
                     confidence, source_document_id, context)
                VALUES (%s, %s, %s, %s, %s, %s);
                """,
                (row["source_entity_id"], row["target_entity_id"], row["type"],
                 row["confidence"], row["source_document_id"], row["context"])
            )

        conn.commit()
        print(f"  Stored {len(entity_name_lookup)} entities and {len(resolved_df)} relationships to DB.")
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Database write failed, rolled back: {e}")
    finally:
        cur.close()
        conn.close()


# ==========================================================================
#  GRAPH -> DETECTION -> EVIDENCE 
# ==========================================================================
def run_graph_and_detection(db_config=None, csv_path=None, resolved_df=None, entity_name_lookup=None):
    
    analyzer = GraphAnalyzer(db_config=db_config, csv_path=csv_path)
    if resolved_df is not None:
        analyzer.load_from_dataframe(resolved_df)
    else:
        analyzer.build_graph()
    detection_results = analyzer.run_all_detections()
    alerts = build_alerts_from_detection_results(detection_results, entity_name_lookup)
    return alerts, analyzer


# ==========================================================================
# FULL PIPELINE ENTRY POINT
# ==========================================================================
def run_full_pipeline(fir_path, cdr_path, transactions_path, extraction_output_path,
                       seed_relationships_path=None, persons_path=None, db_config=None):
    
    print("Stage 0: Validating uploads...")
    validate_fir_upload(fir_path)
    validate_csv_upload(cdr_path, required_columns=["caller_phone", "receiver_phone", "timestamp"])
    validate_csv_upload(transactions_path, required_columns=["sender_account", "receiver_account", "amount_inr"])
    print("  All uploads valid.")

    print("Stage 1: Loading extraction output...")
    raw_extraction_df = run_extraction(extraction_output_path)
    print(f"  {len(raw_extraction_df)} social relationship rows loaded (FIR text).")

    if seed_relationships_path is not None and persons_path is not None:
        print("Stage 1b: Merging in financial/communication relationships...")
        seed_df = pd.read_csv(seed_relationships_path)
        persons_df = pd.read_csv(persons_path)
        seed_as_raw = convert_seed_to_raw_format(seed_df, persons_df)
        raw_extraction_df = combine_extraction_sources(raw_extraction_df, seed_as_raw)
        print(f"  Combined total: {len(raw_extraction_df)} relationship rows "
              f"(now includes TRANSFERRED/CONTACTED).")

    print("Stage 2: Resolving entities...")
    resolved_df, entity_name_lookup = run_resolution_stage(raw_extraction_df)
    print(f"  Resolved to {len(entity_name_lookup)} canonical entities, "
          f"{len(resolved_df)} relationships after removing self-loops.")

    print("Stage 3: Storage")
    if db_config is not None:
        try:
            store_to_database(resolved_df, entity_name_lookup, db_config)
        except Exception as e:
            print(f"  DB storage failed ({e}) - continuing with in-memory data for graph stage.")
    else:
        print("  No db_config provided - feeding resolved data directly into graph.")

    print("Stage 4-6: Graph -> Detection -> Evidence")
    alerts, analyzer = run_graph_and_detection(resolved_df=resolved_df, entity_name_lookup=entity_name_lookup)
    print(f"  {len(alerts)} alerts generated.")

    return alerts, entity_name_lookup


if __name__ == "__main__":
    
    fir_path = r"E:\SIH26\data\fir_records.txt"
    cdr_path = r"E:\SIH26\data\cdr.csv"
    txn_path = r"E:\SIH26\data\transactions.csv"
    extraction_output_path = r"E:\SIH26\data\relationships_output_1.csv"
    seed_relationships_path = r"E:\SIH26\data\relationships_seed.csv"
    persons_path = r"E:\SIH26\data\persons.csv"

    alerts, name_lookup = run_full_pipeline(
        fir_path=fir_path,
        cdr_path=cdr_path,
        transactions_path=txn_path,
        extraction_output_path=extraction_output_path,
        seed_relationships_path=seed_relationships_path,
        persons_path=persons_path,
    )

    print()
    print("=== Final alerts ===")
    for a in alerts:
        print(" -", a["reason_text"])
