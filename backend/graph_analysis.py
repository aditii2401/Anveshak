"""
graph_analysis.py
Project: Anveshak

Module  - Database & Graph
Build the NetworkX graph from stored relationships (PostgreSQL),
run centrality/path/component/community analysis, and implement the four
detection rules (communication spike, circular money flow, bridge entity,
multi-source crossover).

"""

import pandas as pd
import networkx as nx
import numpy as np
from networkx.algorithms import community

try:
    import psycopg2
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


class GraphAnalyzer:
    """
    Builds and analyzes the criminal-network relationship graph.

    Two ways to load data:
      1. From PostgreSQL  -> GraphAnalyzer(db_config={...})
      2. From a local CSV -> GraphAnalyzer(csv_path="relationships_seed.csv")
         (useful for local dev/testing before the DB is wired up)
    """

    def __init__(self, db_config=None, csv_path=None):
        if db_config is None and csv_path is None:
            raise ValueError("Provide either db_config or csv_path.")
        self.db_config = db_config
        self.csv_path = csv_path
        self.G = None          # MultiDiGraph - full graph, all relation types
        self.G_simple = None   # simple undirected Graph - used for centrality/components

    # ------------------------------------------------------------------
    # DATA LOADING
    # ------------------------------------------------------------------
    def _fetch_relationships_from_db(self):
        """
        Pulls relationship rows from PostgreSQL.
        Expects a 'relationships' table with columns matching the project schema:
        source_entity_id, target_entity_id, relationship_type, confidence,
        source_document_id, context
        """
        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2 is not installed. Run: pip install psycopg2-binary")

        query = """
            SELECT source_entity_id, target_entity_id, relationship_type AS type,
                   confidence, source_document_id, context
            FROM relationships;
        """
        try:
            import os
            db_url = self.db_config if isinstance(self.db_config, str) else os.getenv("DATABASE_URL")
            conn = psycopg2.connect(db_url)
            df = pd.read_sql(query, conn)
            conn.close()
            return df
        except Exception as e:
            raise ConnectionError(f"Failed to fetch relationships from DB: {e}")

    def _fetch_relationships_from_csv(self):
        return pd.read_csv(self.csv_path)

    # ------------------------------------------------------------------
    # GRAPH CONSTRUCTION
    # ------------------------------------------------------------------
    def build_graph(self):
        """
        Builds a directed MultiDiGraph from relationship rows.
        Directed: TRANSFERRED / CONTACTED are directional relationships.
        Multi: the same pair of entities can have more than one relationship
               (e.g. both CONTACTED and TRANSFERRED), and we must not lose any.
        """
        if self.db_config is not None:
            rel_df = self._fetch_relationships_from_db()
        else:
            rel_df = self._fetch_relationships_from_csv()

        required_cols = {"source_entity_id", "target_entity_id", "type",
                          "confidence", "source_document_id", "context"}
        missing = required_cols - set(rel_df.columns)
        if missing:
            raise ValueError(f"Relationship data is missing required columns: {missing}")

        G = nx.MultiDiGraph()
        for _, row in rel_df.iterrows():
            if pd.isna(row["source_entity_id"]) or pd.isna(row["target_entity_id"]):
                continue  # skip malformed rows rather than crashing the whole build
            G.add_edge(
                row["source_entity_id"], row["target_entity_id"],
                relation=row["type"],
                confidence=row["confidence"],
                source_doc=row["source_document_id"],
                context=row["context"],
            )

        self.G = G
        self.G_simple = nx.Graph(G)  # collapsed undirected version for centrality/components
        return self.G

    def _check_graph_built(self):
        if self.G is None:
            raise RuntimeError("Graph not built yet. Call build_graph() first.")

    # ------------------------------------------------------------------
    # ANALYSIS: DEGREE 
    # ------------------------------------------------------------------
    def get_degree(self):
        """Returns (in_degree_dict, out_degree_dict, total_degree_dict)."""
        self._check_graph_built()
        return dict(self.G.in_degree()), dict(self.G.out_degree()), dict(self.G.degree())

    # ------------------------------------------------------------------
    # ANALYSIS: BETWEENNESS CENTRALITY
    # ------------------------------------------------------------------
    def get_betweenness(self):
        """Returns {node: betweenness_score}, computed on the undirected simple graph."""
        self._check_graph_built()
        return nx.betweenness_centrality(self.G_simple)

    # ------------------------------------------------------------------
    # ANALYSIS: SHORTEST PATH 
    # ------------------------------------------------------------------
    def get_shortest_path(self, source, target):
        """Returns (path_list, hop_count) or (None, None) if no path exists."""
        self._check_graph_built()
        if not nx.has_path(self.G, source, target):
            return None, None
        path = nx.shortest_path(self.G, source=source, target=target)
        length = nx.shortest_path_length(self.G, source=source, target=target)
        return path, length

    # ------------------------------------------------------------------
    # ANALYSIS: CONNECTED COMPONENTS
    # ------------------------------------------------------------------
    def get_connected_components(self):
        """Returns a list of sets - each set is one connected group of entities."""
        self._check_graph_built()
        return list(nx.connected_components(self.G_simple))

    # ------------------------------------------------------------------
    # ANALYSIS: COMMUNITY DETECTION 
    # ------------------------------------------------------------------
    def get_communities(self):
        """Returns a list of frozensets - tighter sub-clusters within components."""
        self._check_graph_built()
        return list(community.greedy_modularity_communities(self.G_simple))

    # ------------------------------------------------------------------
    # DETECTION RULE 1: CIRCULAR MONEY FLOW 
    # ------------------------------------------------------------------
    def detect_circular_flow(self):
        """
        Finds closed directed loops among TRANSFERRED (financial) edges only.
        Returns a list of cycles, each cycle a list of entity IDs.
        """
        self._check_graph_built()
        money_graph = nx.DiGraph()
        for u, v, data in self.G.edges(data=True):
            if data.get("relation") == "TRANSFERRED":
                money_graph.add_edge(u, v)
        return list(nx.simple_cycles(money_graph))

    # ------------------------------------------------------------------
    # DETECTION RULE 2: BRIDGE ENTITY 
    # ------------------------------------------------------------------
    def detect_bridges(self, percentile=75):
        """
        Flags entities in the top `percentile` of betweenness centrality
        (and score > 0, to exclude non-bridges even if threshold is near zero).
        Returns {entity_id: betweenness_score}.
        """
        self._check_graph_built()
        bc = self.get_betweenness()
        if not bc:
            return {}
        threshold = np.percentile(list(bc.values()), percentile)
        return {n: s for n, s in bc.items() if s >= threshold and s > 0}

    # ------------------------------------------------------------------
    # DETECTION RULE 3: COMMUNICATION SPIKE 
    # ------------------------------------------------------------------
    def detect_comm_spikes(self, spike_marker="SPIKE"):
        """
        Flags CONTACTED edges whose source document is marked as a spike case.
        NOTE: this is a placeholder rule for seed/demo data where spikes are
        pre-labeled in source_document_id. For real CDR data, replace this with
        a z-score/time-window calculation over raw call timestamps.
        Returns a list of (source, target, edge_data) tuples.
        """
        self._check_graph_built()
        flagged = []
        for u, v, data in self.G.edges(data=True):
            if data.get("relation") == "CONTACTED" and spike_marker in str(data.get("source_doc", "")):
                flagged.append((u, v, data))
        return flagged

    # ------------------------------------------------------------------
    # DETECTION RULE 4: MULTI-SOURCE CROSSOVER 
    # ------------------------------------------------------------------
    def detect_crossover(self):
        """
        Flags entities that appear in edges sourced from more than one
        distinct document type (e.g. both FIR and financial records).
        Returns {entity_id: set_of_source_prefixes}.
        """
        self._check_graph_built()
        node_sources = {}
        for u, v, data in self.G.edges(data=True):
            source_doc = str(data.get("source_doc", ""))
            prefix = source_doc.split("_")[0] if source_doc else "UNKNOWN"
            for node in (u, v):
                node_sources.setdefault(node, set()).add(prefix)
        return {n: s for n, s in node_sources.items() if len(s) > 1}

    # ------------------------------------------------------------------
    # RUN EVERYTHING AT ONCE - convenient for pipeline integration
    # ------------------------------------------------------------------
    def run_all_detections(self):
        """
        Runs all four detection rules and returns a single structured dict.
        This is the main entry point the orchestration layer should call.
        """
        self._check_graph_built()
        return {
            "circular_flow": self.detect_circular_flow(),
            "bridges": self.detect_bridges(),
            "comm_spikes": self.detect_comm_spikes(),
            "crossover": self.detect_crossover(),
        }


# ==========================================================================
# DEMO / LOCAL TEST - only runs if this file is executed directly,
# not when imported by a teammate's code
# ==========================================================================
if __name__ == "__main__":
    # For local testing, use the CSV. Once DB schema is live, swap to:
    # analyzer = GraphAnalyzer(db_config={
    #     "host": "localhost", "dbname": "database",
    #     "user": "postgres", "password": "your_password"
    # })
    analyzer = GraphAnalyzer(csv_path=r"E:\SIH26\data\relationships_seed.csv")
    analyzer.build_graph()

    print("Nodes:", analyzer.G.number_of_nodes())
    print("Edges:", analyzer.G.number_of_edges())
    print()

    in_deg, out_deg, total_deg = analyzer.get_degree()
    print("Top in-degree:", sorted(in_deg.items(), key=lambda x: x[1], reverse=True)[:3])
    print()

    print("Connected components:", len(analyzer.get_connected_components()))
    print("Communities found:", len(analyzer.get_communities()))
    print()

    results = analyzer.run_all_detections()
    for rule_name, output in results.items():
        print(f"{rule_name}: {output}")

# OUTPUT
# Nodes: 18
# Edges: 18

# Top in-degree: [('P-002', 3), ('P-001', 2), ('P-003', 2)]

# Connected components: 5
# Communities found: 6

# circular_flow: [['P-003', 'P-001']]
# bridges: {  'P-002': 0.06985294117647059, 
#             'P-007': 0.058823529411764705, 
#             'P-008': 0.03676470588235294, 
#             'P-010': 0.007352941176470588, 
#             'P-014': 0.007352941176470588, 
#             'P-017': 0.007352941176470588}
# comm_spikes: [('P-001', 'P-002', {'relation': 'CONTACTED', 'confidence': 0.97, 'source_doc': 'CDR_SPIKE_01', 'context': "Repeated calls from Rahul's phone to Amit's phone."})]
# crossover: {'P-001': {'FIR', 'FIN', 'CDR'}, 'P-002': {'FIR', 'FIN', 'CDR'}, 'P-003': {'FIR', 'FIN'}, 'P-004': {'FIR', 'FIN', 'CDR'}, 'P-007': {'FIR', 'FIN'}}
