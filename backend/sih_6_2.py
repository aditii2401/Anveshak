"""
sih_6_2.py — Extraction pipeline.
 
Reads the uploaded FIR text / CDR / transaction files, extracts entities
and relationships, and writes them straight into the database through
db.py (per the pattern documented in README.md). This file must never
contain raw SQL - if a new kind of write is needed, add a function to
db.py instead.
"""
 
import os
import re

import csv
from collections import defaultdict
 
import spacy
from dotenv import load_dotenv
from rapidfuzz import fuzz
 
import db
 
load_dotenv()
 
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
 
# Load spaCy NLP Model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    nlp = None
 
FUZZY_MATCH_THRESHOLD = 80  # same threshold resolution.py used historically
 
 
def normalize_row_keys(row: dict) -> dict:
    """
    Normalizes CSV row keys to handle alternative column names cleanly.
    """
    normalized = {}
    mappings = {
        'person_id': 'person_id', 'id': 'person_id', 'owner_id': 'owner_id', 'owner': 'owner_id',
        'name': 'name', 'person_name': 'name', 'full_name': 'name',
        'phone_number': 'phone_number', 'phone': 'phone_number', 'mobile': 'phone_number',
        'caller_phone': 'caller_phone', 'caller': 'caller_phone', 'from_phone': 'caller_phone',
        'receiver_phone': 'receiver_phone', 'receiver': 'receiver_phone', 'to_phone': 'receiver_phone',
        'account_id': 'account_id', 'acc_id': 'account_id', 'account': 'account_id',
        'sender_account': 'sender_account', 'sender': 'sender_account', 'from_acc': 'sender_account',
        'receiver_account': 'receiver_account', 'receiver': 'receiver_account', 'to_acc': 'receiver_account',
        'amount_inr': 'amount_inr', 'amount': 'amount_inr', 'txn_amount': 'amount_inr'
    }
    for key, val in row.items():
        if key is None:
            continue
        clean_key = key.strip().lower()
        target_key = mappings.get(clean_key, clean_key)
        normalized[target_key] = val.strip() if isinstance(val, str) else val
    return normalized
 
 
def normalize_name(name: str) -> str:
    """Lowercase, alphanumeric-only form used for exact/fuzzy person matching."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())
 
 
def resolve_or_create_person(cur, raw_name, person_cache, source_document_id,
                              extraction_confidence=0.85, method="spacy_ner"):
    """
    Decides whether `raw_name` refers to a person already known in this run
    (exact or fuzzy normalized-name match) or a brand-new one, exactly as
    README.md describes: "decide using RapidFuzz ... then call
    get_or_create_person ... then log_extraction".
 
    person_cache: {normalized_name: person_id} - built up over the course of
    one run_pipeline() call so repeat mentions resolve without hitting the DB.
    Returns the resolved person_id.
    """
    norm = normalize_name(raw_name)
 
    if norm in person_cache:
        person_id = person_cache[norm]
        db.log_extraction(cur, source_document_id, "PERSON", raw_name, norm,
                           person_id, extraction_confidence, method)
        return person_id
 
    best_norm, best_score = None, 0
    for known_norm in person_cache:
        score = fuzz.token_set_ratio(norm, known_norm)
        if score > best_score:
            best_norm, best_score = known_norm, score
 
    if best_norm is not None and best_score >= FUZZY_MATCH_THRESHOLD:
        person_id = person_cache[best_norm]
        db.add_alias(cur, person_id, raw_name, norm, round(best_score / 100, 2), source_document_id)
        db.log_extraction(cur, source_document_id, "PERSON", raw_name, norm,
                           person_id, round(best_score / 100, 2), "rapidfuzz")
        return person_id
 
    # No good match - this is a new person
    person_id = db.get_or_create_person(cur, raw_name, norm)
    person_cache[norm] = person_id
    db.log_extraction(cur, source_document_id, "PERSON", raw_name, norm,
                       person_id, extraction_confidence, method)
    return person_id
 
 
def run_pipeline(cur, data_dir: str = "."):
    """
    Executes ingestion + extraction and writes everything directly into the
    database via db.py. Does NOT commit - the caller (main.py) controls
    when to commit, same as every other db.py consumer.
 
    Returns a summary dict of what was written (counts), for the API
    response - not the raw rows themselves, since those now live in the DB.
    """
    fir_file          = os.path.join(data_dir, "fir_records.txt")
    persons_file      = os.path.join(data_dir, "persons.csv")
    phones_file       = os.path.join(data_dir, "phones.csv")
    accounts_file     = os.path.join(data_dir, "accounts.csv")
    cdr_file          = os.path.join(data_dir, "cdr.csv")
    transactions_file = os.path.join(data_dir, "transactions.csv")
    vehicles_file     = os.path.join(data_dir, "vehicles.csv") # <-- Yeh add karein
 
    person_cache = {}          # normalized_name -> person_id (this run's cache)
    csv_person_id_to_dbid = {} # persons.csv's own person_id -> our db person_id
    phone_to_dbperson = {}     # phone_number -> person_id
    phone_number_to_phone_id = {}
    account_to_dbperson = {}   # account_number -> person_id
    account_number_to_account_id = {}
 
    counts = {
        "persons_registered": 0,
        "phones_linked": 0,
        "accounts_linked": 0,
        "vehicles_linked": 0,
        "fir_relationships": 0,
        "call_relationships": 0,
        "transaction_relationships": 0,
        "documents_processed": 0,
    }
 
    # ------------------------------------------------------------------
    # 1. persons.csv - pre-register known canonical persons
    # ------------------------------------------------------------------
    if os.path.exists(persons_file):
        db.insert_document(cur, "PERSONS_CSV", "PERSONS", file_name="persons.csv")
        with open(persons_file, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                norm_row = normalize_row_keys(row)
                csv_id, name = norm_row.get("person_id"), norm_row.get("name")
                if not csv_id or not name:
                    continue
                person_id = resolve_or_create_person(cur, name, person_cache, "PERSONS_CSV",
                                                      extraction_confidence=1.0, method="persons_csv")
                csv_person_id_to_dbid[csv_id] = person_id
                counts["persons_registered"] += 1
        db.set_document_status(cur, "PERSONS_CSV", "done")
        counts["documents_processed"] += 1
 
    # ------------------------------------------------------------------
    # 2. FIR text - spaCy PERSON entities co-mentioned become relationships
    # ------------------------------------------------------------------
    if os.path.exists(fir_file):
        with open(fir_file, "r", encoding="utf-8") as f:
            raw_text = f.read()
        db.insert_document(cur, "FIR_TEXT", "FIR", file_name="fir_records.txt", raw_text=raw_text)
 
        if nlp and raw_text:
            doc = nlp(raw_text)
            entities = [ent.text for ent in doc.ents if ent.label_ == "PERSON"]
            for i in range(len(entities) - 1):
                p1 = resolve_or_create_person(cur, entities[i], person_cache, "FIR_TEXT")
                p2 = resolve_or_create_person(cur, entities[i + 1], person_cache, "FIR_TEXT")
                if p1 == p2:
                    continue
                db.insert_relationship(
                    cur, source_person_id=p1, target_person_id=p2,
                    rel_type="ASSOCIATED_FIR", confidence=0.85,
                    source_document_id="FIR_TEXT",
                    context="Mentioned together in FIR report."
                )
                counts["fir_relationships"] += 1
        db.set_document_status(cur, "FIR_TEXT", "done")
        counts["documents_processed"] += 1
 
    # ------------------------------------------------------------------
    # 3. phones.csv - link phone numbers to known persons
    # ------------------------------------------------------------------
    if os.path.exists(phones_file):
        db.insert_document(cur, "PHONES_CSV", "PHONES", file_name="phones.csv")
        with open(phones_file, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                norm_row = normalize_row_keys(row)
                csv_person_id = norm_row.get("person_id")
                phone_number = norm_row.get("phone_number")
                if not phone_number:
                    continue
                person_id = csv_person_id_to_dbid.get(csv_person_id)
                phone_id = f"PH-{phone_number}"
                db.get_or_create_phone(cur, phone_id, phone_number, person_id, "PHONES_CSV")
                phone_number_to_phone_id[phone_number] = phone_id
                if person_id is not None:
                    phone_to_dbperson[phone_number] = person_id
                counts["phones_linked"] += 1
        db.set_document_status(cur, "PHONES_CSV", "done")
        counts["documents_processed"] += 1
 
    # ------------------------------------------------------------------
    # 4. cdr.csv - call records + communication-volume relationships
    # ------------------------------------------------------------------
    if os.path.exists(cdr_file):
        db.insert_document(cur, "CDR_LOGS", "CDR", file_name="cdr.csv")
        calls_by_pair = defaultdict(list)
        with open(cdr_file, "r", encoding="utf-8") as f:
         for i, row in enumerate(csv.DictReader(f)):
            norm_row = normalize_row_keys(row)
            caller_phone = norm_row.get("caller_phone")
            receiver_phone = norm_row.get("receiver_phone")

            # Auto-register phones from CDR if not already in phones.csv
            for phone_number in [caller_phone, receiver_phone]:
                if phone_number and phone_number not in phone_number_to_phone_id:
                    phone_id = f"PH-{phone_number}"
                    db.get_or_create_phone(cur, phone_id, phone_number,
                                           person_id=None, source_id="CDR_LOGS")
                    phone_number_to_phone_id[phone_number] = phone_id

            caller = phone_to_dbperson.get(caller_phone)
            receiver = phone_to_dbperson.get(receiver_phone)

            caller_phone_id = phone_number_to_phone_id.get(caller_phone)
            receiver_phone_id = phone_number_to_phone_id.get(receiver_phone)
            if caller_phone_id and receiver_phone_id:
                db.insert_call_record(
                    cur, cdr_id=f"CDR-{i}", timestamp=norm_row.get("timestamp"),
                    caller_phone_id=caller_phone_id, receiver_phone_id=receiver_phone_id,
                    duration_minutes=norm_row.get("duration_minutes"),
                    location=norm_row.get("location"), source_id="CDR_LOGS"
                )

            if not caller or not receiver or caller == receiver:
                continue
            pair = tuple(sorted([caller, receiver]))
            calls_by_pair[pair].append(norm_row)
 
    # ------------------------------------------------------------------
    # 5. accounts.csv - link account numbers to known persons
    # ------------------------------------------------------------------
    if os.path.exists(accounts_file):
        db.insert_document(cur, "ACCOUNTS_CSV", "ACCOUNTS", file_name="accounts.csv")
        with open(accounts_file, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                norm_row = normalize_row_keys(row)
                csv_owner_id = norm_row.get("owner_id")
                account_number = norm_row.get("account_id")
                if not account_number:
                    continue
                owner_id = csv_person_id_to_dbid.get(csv_owner_id)
                account_id = f"ACC-{account_number}"
                db.get_or_create_account(cur, account_id, account_number, owner_id)
                account_number_to_account_id[account_number] = account_id
                if owner_id is not None:
                    account_to_dbperson[account_number] = owner_id
                counts["accounts_linked"] += 1
        db.set_document_status(cur, "ACCOUNTS_CSV", "done")
        counts["documents_processed"] += 1

     
    # ------------------------------------------------------------------
    # 6. transactions.csv - transaction records + circular-flow relationships
    # ------------------------------------------------------------------
    if os.path.exists(transactions_file):
        db.insert_document(cur, "BANK_TXN", "TRANSACTIONS", file_name="transactions.csv")
        with open(transactions_file, "r", encoding="utf-8") as f:
            for i, row in enumerate(csv.DictReader(f)):
                norm_row = normalize_row_keys(row)
                sender_acc = norm_row.get("sender_account")
                receiver_acc = norm_row.get("receiver_account")
                sender = account_to_dbperson.get(sender_acc)
                receiver = account_to_dbperson.get(receiver_acc)
 
                try:
                    amount = float(norm_row.get("amount_inr", 0))
                except (ValueError, TypeError):
                    amount = 0.0
 
                sender_account_id = account_number_to_account_id.get(sender_acc)
                receiver_account_id = account_number_to_account_id.get(receiver_acc)
                if sender_account_id and receiver_account_id:
                    db.insert_transaction(
                        cur, transaction_id=f"TXN-{i}", timestamp=norm_row.get("timestamp"),
                        sender_account_id=sender_account_id, receiver_account_id=receiver_account_id,
                        amount_inr=amount, reference=norm_row.get("reference"), source_id="BANK_TXN"
                    )
 
                if not sender or not receiver or sender == receiver:
                    continue
                confidence = min(0.95, 0.50 + (amount / 50000.0))
                db.insert_relationship(
                    cur, source_person_id=sender, target_person_id=receiver,
                    rel_type="TRANSFERRED", confidence=round(confidence, 2),
                    source_document_id="BANK_TXN",
                    context=f"Transferred INR {amount} between these two persons."
                )
                counts["transaction_relationships"] += 1
        db.set_document_status(cur, "BANK_TXN", "done")
        counts["documents_processed"] += 1

     # ------------------------------------------------------------------
    # 7. vehicles.csv - link vehicles to registered persons
    # ------------------------------------------------------------------
    if os.path.exists(vehicles_file):
        db.insert_document(cur, "VEHICLE_LOGS", "VEHICLE", file_name="vehicles.csv")
        with open(vehicles_file, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                norm_row = normalize_row_keys(row)
                vehicle_id = norm_row.get("vehicle_id")
                reg_number = norm_row.get("registration_number")
                
                # Database mein owner_id integer hai, isliye safe conversion zaroori hai
                csv_owner_id = norm_row.get("owner_id")
                owner_id = csv_person_id_to_dbid.get(csv_owner_id) if csv_owner_id else None
                
                if vehicle_id and reg_number:
                    db.get_or_create_vehicle(
                        cur, 
                        vehicle_id=vehicle_id, 
                        registration_number=reg_number, 
                        owner_id=owner_id
                    )
                    counts["vehicles_linked"] += 1
        db.set_document_status(cur, "VEHICLE_LOGS", "done")
        counts["documents_processed"] += 1
 
    return counts




if __name__ == "__main__":
    conn = db.get_connection()
    cur = conn.cursor()
    conn.commit()
    result = run_pipeline(cur, ".")
    conn.commit()
    cur.close()
    conn.close()
    print(f"Pipeline finished execution. {result}")
 