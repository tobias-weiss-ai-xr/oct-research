"""Unit tests for the concept-graph text matching (tools/relate_concepts.py)
and graph metrics (tools/analyze_concept_graph.py).

Regression guard: phrase words that appear hyphen-attached to other words in a
title/abstract (e.g. "Neural network-based …") must still match the concept
"neural network" — the TOKEN regex otherwise folds the compound into a single
token and the subset check fails. Second guard: modularity must be genuine
Newman modularity (single community == 0 exactly).
"""

from tools.relate_concepts import paper_set
from tools.analyze_concept_graph import modularity


def _text_paper(title, abstract=""):
    return {"title": title, "abstract": abstract, "category": "method",
            "subcategory": "dl"}


def test_hyphenated_compound_still_matches_phrase_word():
    papers = [_text_paper("Neural network-based reconstruction for OCT images")]
    match = {"type": "text", "forms": ["neural network"]}
    assert paper_set(0, papers, match) == {0}


def test_hyphen_inside_phrase_matches_verbatim():
    papers = [_text_paper("Low-coherence interferometry for depth ranging")]
    match = {"type": "text", "forms": ["low-coherence interferometry"]}
    assert paper_set(0, papers, match) == {0}


def test_multiword_phrase_in_abstract_counts():
    papers = [_text_paper("OCT welding",
                          "Keyhole depth maps enable seam tracking in real time.")]
    match = {"type": "text", "forms": ["seam tracking"]}
    assert paper_set(0, papers, match) == {0}


def test_absent_term_does_not_match():
    papers = [_text_paper("Retinal layer segmentation with deep learning")]
    match = {"type": "text", "forms": ["glaucoma"]}
    assert paper_set(0, papers, match) == set()


def test_taxonomy_field_match_is_structural():
    papers = [_text_paper("Anything at all", "abstract with no keywords")]
    match = {"type": "field", "field": "category", "value": "method"}
    assert paper_set(0, papers, match) == {0}


def _adj_weighted(edges):
    """{u: {v: w}} undirected weighted adjacency from (u, v, w) triples."""
    adj = {}
    for u, v, w in edges:
        adj.setdefault(u, {})[v] = w
        adj.setdefault(v, {})[u] = w
    return {k: dict(v) for k, v in adj.items()}


def test_modularity_single_community_is_zero():
    # One edge, one community -> Newman Q must be exactly 0 (not >0).
    adj = _adj_weighted([(0, 1, 1)])
    assert modularity(adj, [[0, 1]]) == 0.0


def test_modularity_split_edge_is_negative():
    adj = _adj_weighted([(0, 1, 1)])
    assert modularity(adj, [[0], [1]]) == -0.5


def test_modularity_two_edges_one_community_is_zero():
    adj = _adj_weighted([(0, 1, 2), (1, 2, 3)])
    assert modularity(adj, [[0, 1, 2]]) == 0.0
