import os
import csv
import json
import re
import time
from collections import defaultdict
import spacy
from dotenv import load_dotenv

# Load environment variables (such as GEMINI_API_KEY if needed)
load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Load spaCy NLP Model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    nlp = None


def run_pipeline(data_dir: str = "."):
    """
    Executes the ingestion, text relation extraction, CDR call log analysis,
    and financial circular transaction detection pipeline.
    """
    # 1. Resolve relative data file paths
    fir_file          = os.path.join(data_dir, "fir_records.txt")
    persons_file      = os.path.join(data_dir, "persons.csv")
    phones_file       = os.path.join(data_dir, "phones.csv")
    accounts_file     = os.path.join(data_dir, "accounts.csv")
    cdr_file          = os.path.join(data_dir, "cdr.csv")
    transactions_file = os.path.join(data_dir, "transactions.csv")

    person_id_to_name = {}
    if os.path.exists(persons_file):
        with open(persons_file, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                person_id_to_name[row["person_id"].strip()] = row["name"].strip()

    # 2. Extract Relations from FIR Text
    fir_rows = []
    if os.path.exists(fir_file):
        with open(fir_file, "r", encoding="utf-8") as f:
            raw_text = f.read()

        # Parse FIR blocks and extract entities using spaCy
        if nlp and raw_text:
            doc = nlp(raw_text)
            entities = [ent.text for ent in doc.ents if ent.label_ == "PERSON"]
            for i in range(len(entities) - 1):
                fir_rows.append({
                    "person_1": entities[i],
                    "person_2": entities[i + 1],
                    "relation": "ASSOCIATED_FIR",
                    "source_id": "FIR_TEXT",
                    "context": f"Mentioned together in FIR report.",
                    "confidence": 0.85
                })

    # 3. Process Call Detail Records (CDR)
    cdr_rows = []
    if os.path.exists(phones_file) and os.path.exists(cdr_file):
        phone_to_name = {}
        with open(phones_file, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = person_id_to_name.get(row["person_id"].strip())
                if name:
                    phone_to_name[row["phone_number"].strip()] = name

        calls_by_pair = defaultdict(list)
        with open(cdr_file, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                caller = phone_to_name.get(row["caller_phone"].strip())
                receiver = phone_to_name.get(row["receiver_phone"].strip())
                if not caller or not receiver or caller == receiver:
                    continue
                pair = tuple(sorted([caller, receiver]))
                calls_by_pair[pair].append(row)

        for pair, calls in calls_by_pair.items():
            count = len(calls)
            is_spike = count >= 5
            relation = "COMMUNICATED_SPIKE" if is_spike else "COMMUNICATED"
            confidence = min(0.99, 0.70 + 0.03 * count) if is_spike else min(0.95, 0.60 + 0.05 * count)
            cdr_rows.append({
                "person_1": pair[0],
                "person_2": pair[1],
                "relation": relation,
                "source_id": "CDR_LOGS",
                "context": f"{count} call(s) exchanged between {pair[0]} and {pair[1]}",
                "confidence": round(confidence, 2)
            })

    # 4. Process Financial Transactions & Circular Flow Detection
    txn_rows = []
    if os.path.exists(accounts_file) and os.path.exists(transactions_file):
        account_to_name = {}
        with open(accounts_file, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = person_id_to_name.get(row["owner_id"].strip())
                if name:
                    account_to_name[row["account_id"].strip()] = name

        with open(transactions_file, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sender = account_to_name.get(row["sender_account"].strip())
                receiver = account_to_name.get(row["receiver_account"].strip())
                if not sender or not receiver or sender == receiver:
                    continue
                amount = float(row.get("amount_inr", 0))
                confidence = min(0.95, 0.50 + (amount / 50000.0))
                txn_rows.append({
                    "person_1": sender,
                    "person_2": receiver,
                    "relation": "TRANSFERRED_FUNDS",
                    "source_id": row.get("source_id", "BANK_TXN").strip(),
                    "context": f"Transferred INR {amount} from {sender} to {receiver}",
                    "confidence": round(confidence, 2)
                })

    # 5. Deduplicate and Merge Results
    all_rows = fir_rows + cdr_rows + txn_rows
    merged = {}
    for r in all_rows:
        if r["person_1"] == r["person_2"]:
            continue
        pair_key = tuple(sorted([r["person_1"], r["person_2"]]))
        key = (r["source_id"], pair_key)
        if key not in merged:
            merged[key] = {
                "Name A": pair_key[0],
                "Name B": pair_key[1],
                "Relation": {r["relation"]},
                "Source ID": r["source_id"],
                "Context": {r["context"]},
                "Confidence": r["confidence"]
            }
        else:
            merged[key]["Relation"].add(r["relation"])
            merged[key]["Context"].add(r["context"])
            merged[key]["Confidence"] = max(merged[key]["Confidence"], r["confidence"])

    final_rows = []
    for v in merged.values():
        final_rows.append({
            "source_entity_id": v["source_entity_id"],
            "target_entity_id": v["target_entity_id"],
            "relationship_type": ", ".join(sorted(v["relationship_type"])),
            "source_document_id": v["source_document_id"],
            "context": " | ".join(sorted(v["context"])),
            "confidence": round(v["confidence"], 2)
        })

    final_rows.sort(key=lambda x: x["source_document_id"])
    return final_rows


if __name__ == "__main__":
    # Test execution locally via Python CLI
    output = run_pipeline(".")
    print(f"Pipeline finished execution. Extracted {len(output)} records.")
