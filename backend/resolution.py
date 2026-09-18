
import re
import pandas as pd
from rapidfuzz import fuzz


def normalize_name(name):
    name = str(name).lower().strip()
    name = re.sub(r"[.,]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name


def cluster_names(names, threshold=80):
    
    clusters = []  # list of {"representative": str, "members": [str, ...]}
    name_to_cluster_index = {}

    for name in names:
        norm = normalize_name(name)
        best_match_index = None
        best_score = 0

        for i, cluster in enumerate(clusters):
            score = fuzz.token_set_ratio(norm, cluster["representative"])
            if score > best_score:
                best_score = score
                best_match_index = i

        if best_match_index is not None and best_score >= threshold:
            clusters[best_match_index]["members"].append(name)
            name_to_cluster_index[name] = best_match_index
            # Keep the LONGEST member as the representative -
            # longer names usually carry more information (e.g. "Rahul K Sharma"
            # over "R. Sharma"), which gives a better display name later.
            if len(norm) > len(clusters[best_match_index]["representative"]):
                clusters[best_match_index]["representative"] = norm
        else:
            clusters.append({"representative": norm, "members": [name]})
            name_to_cluster_index[name] = len(clusters) - 1

    # Assign canonical IDs and pick a display name per cluster
    name_to_canonical_id = {}
    canonical_id_to_display_name = {}
    for i, cluster in enumerate(clusters):
        canonical_id = f"P-{i+1:03d}"
        # Display name = the longest raw member string (most complete spelling)
        display_name = max(cluster["members"], key=len)
        canonical_id_to_display_name[canonical_id] = display_name
        for member in cluster["members"]:
            name_to_canonical_id[member] = canonical_id

    return name_to_canonical_id, canonical_id_to_display_name


def convert_seed_to_raw_format(relationships_seed_df, persons_df):
    
    id_to_name = dict(zip(persons_df["synthetic_person_id"], persons_df["name"]))

    converted = pd.DataFrame({
        "Name A": relationships_seed_df["source_entity_id"].map(id_to_name),
        "Name B": relationships_seed_df["target_entity_id"].map(id_to_name),
        "Relation": relationships_seed_df["type"],
        "Source ID": relationships_seed_df["source_document_id"],
        "Context": relationships_seed_df["context"],
        "Confidence": relationships_seed_df["confidence"],
    })

    unmapped = converted[converted["Name A"].isna() | converted["Name B"].isna()]
    if len(unmapped) > 0:
        print(f"[warning] {len(unmapped)} seed relationship(s) had an ID not found in persons.csv - dropped.")
    return converted.dropna(subset=["Name A", "Name B"])


def combine_extraction_sources(*raw_dfs):
    
    return pd.concat(raw_dfs, ignore_index=True)


def run_resolution(raw_extraction_df, threshold=80):
    
    required = {"Name A", "Name B", "Relation", "Source ID", "Context", "Confidence"}
    missing = required - set(raw_extraction_df.columns)
    if missing:
        raise ValueError(f"Extraction output missing expected columns: {missing}")

    all_names = pd.concat([raw_extraction_df["Name A"], raw_extraction_df["Name B"]]).unique()
    name_to_id, id_to_display_name = cluster_names(all_names, threshold=threshold)

    resolved_rows = []
    self_loops_removed = 0
    for _, row in raw_extraction_df.iterrows():
        source_id = name_to_id[row["Name A"]]
        target_id = name_to_id[row["Name B"]]
        if source_id == target_id:
            # Both raw names resolved to the SAME person (e.g. "N. Khan" and
            # "Neeraj Khan" turned out to be the same entity) - this isn't a
            # real relationship, it's an artifact of resolution. Skip it.
            self_loops_removed += 1
            continue
        resolved_rows.append({
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "type": row["Relation"],
            "confidence": row["Confidence"],
            "source_document_id": row["Source ID"],
            "context": row["Context"],
        })

    if self_loops_removed > 0:
        print(f"[resolution] Removed {self_loops_removed} self-loop row(s) "
              f"where both names resolved to the same entity.")

    resolved_df = pd.DataFrame(resolved_rows)
    return resolved_df, id_to_display_name


if __name__ == "__main__":
    
    raw = pd.read_csv(r"E:\SIH26\data\relationships_output_1.csv")
    resolved_df, name_lookup = run_resolution(raw)

    print("=== Name -> Canonical ID mapping ===")
    for cid, display_name in name_lookup.items():
        print(f"  {cid}: {display_name}")

    print()
    print("=== Resolved relationships (first 5 rows) ===")
    print(resolved_df.head().to_string(index=False))
    print()
    print(f"Total unique canonical entities: {len(name_lookup)}")
    print(f"Total relationships: {len(resolved_df)}")
