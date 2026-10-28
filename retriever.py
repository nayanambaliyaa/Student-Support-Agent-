"""
Policy Document Chunker and Context Retriever (RAG).
Retrieves ONLY relevant chunks from the student handbook rather than dumping the whole document.
"""

import os
import re
import math
from typing import List, Dict, Any, Tuple

POLICY_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "student_handbook_policy.md")

class PolicyRetriever:
    """
    Splits policy document into semantic chunks and provides selective context retrieval.
    """

    def __init__(self, policy_path: str = POLICY_FILE_PATH):
        self.policy_path = policy_path
        self.chunks: List[Dict[str, Any]] = []
        self._load_and_chunk_policy()

    def _load_and_chunk_policy(self):
        if not os.path.exists(self.policy_path):
            self.chunks = []
            return

        with open(self.policy_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        # Split on markdown headings (### or ####)
        sections = re.split(r'\n(?=###+ )', raw_text)
        
        parsed_chunks = []
        chunk_idx = 1

        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue

            lines = sec.split("\n")
            header_line = lines[0].strip("# ").strip()
            body = "\n".join(lines[1:]).strip()

            if not body:
                continue

            # Create an informative chunk ID
            clean_id = re.sub(r'[^A-Za-z0-9_]', '_', header_line[:30]).upper()
            chunk_id = f"POLICY_CHK_{chunk_idx:02d}_{clean_id}"

            parsed_chunks.append({
                "chunk_id": chunk_id,
                "title": header_line,
                "content": body,
                "raw_section": sec,
                "tokens": self._tokenize(header_line + " " + body)
            })
            chunk_idx += 1

        self.chunks = parsed_chunks

    def _tokenize(self, text: str) -> List[str]:
        text = text.lower()
        # Keep alphanumeric words
        tokens = re.findall(r'[a-z0-9]+', text)
        stop_words = {
            "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
            "is", "are", "was", "were", "be", "been", "this", "that", "it", "can", "may",
            "will", "shall", "should", "i", "my", "you", "your", "we", "our", "does", "have",
            "has", "had", "do", "did", "student", "students", "campus", "institute", "college",
            "information", "details", "query", "question"
        }
        return [t for t in tokens if t not in stop_words]

    def _score_chunk(self, query_tokens: List[str], chunk: Dict[str, Any], query_str: str) -> float:
        chunk_tokens = chunk["tokens"]
        if not chunk_tokens or not query_tokens:
            return 0.0

        # Term frequency score
        score = 0.0
        chunk_token_set = set(chunk_tokens)
        query_token_set = set(query_tokens)

        # Keyword overlaps
        matches = query_token_set.intersection(chunk_token_set)
        score += len(matches) * 2.0

        # Title bonus
        title_tokens = set(self._tokenize(chunk["title"]))
        title_matches = query_token_set.intersection(title_tokens)
        score += len(title_matches) * 4.0

        # Exact phrase or bigram matches
        q_clean = query_str.lower()
        body_clean = chunk["content"].lower()

        key_phrases = [
            "payment portal failed", "portal fail", "next working day", "grace period",
            "late fee", "late fine", "installment", "installments", "refund policy",
            "scholarship retention", "merit award", "dean's excellence", "women in tech",
            "attendance minimums", "minimum attendance", "attendance required", "medical leave",
            "sit for exam", "sit in final exams", "below 65%",
            "course change", "elective change", "add drop", "add/drop", "credit limit", "over-crediting",
            "grading scale", "re-evaluation", "answer sheet verification", "backlogs", "supplementary exam",
            "hall ticket", "hall ticket blocked",
            "summer internship", "internship drive", "one offer policy", "dream offer", "placement drive",
            "hostel curfew", "night-out", "curfew timing", "wi-fi credentials", "library fine", "borrowing period",
            "bonafide certificate", "support ticket", "urgent sla"
        ]
        for phrase in key_phrases:
            if phrase in q_clean and phrase in body_clean:
                score += 8.0

        return score

    def retrieve(
        self,
        query: str,
        top_k: int = 1,
        min_threshold: float = 3.0
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Retrieves top_k relevant chunks.
        Returns (retrieved_chunks, has_sufficient_info_flag).
        If score is below min_threshold, has_sufficient_info_flag is False.
        """
        if not self.chunks:
            self._load_and_chunk_policy()

        q_tokens = self._tokenize(query)
        scored_chunks = []

        for chk in self.chunks:
            s = self._score_chunk(q_tokens, chk, query)
            if s > 0:
                scored_chunks.append((s, chk))

        scored_chunks.sort(key=lambda x: x[0], reverse=True)

        if not scored_chunks:
            return [], False

        top_score, best_chunk = scored_chunks[0]

        if top_score < min_threshold:
            # Not enough relevant information in policy
            return [], False

        selected = []
        for s, chk in scored_chunks[:top_k]:
            selected.append({
                "chunk_id": chk["chunk_id"],
                "title": chk["title"],
                "content": chk["content"],
                "score": round(s, 2)
            })

        return selected, True

    def get_all_chunks(self) -> List[Dict[str, Any]]:
        if not self.chunks:
            self._load_and_chunk_policy()
        return self.chunks
