from sentence_transformers import SentenceTransformer, util
import torch

class SemanticRanker:
    def __init__(self, model_path: str = '/app/models/all-MiniLM-L6-v2'):
        self.device = "cpu"
        print(f"Loading model from {model_path} onto {self.device}...")
        try:
            self.model = SentenceTransformer(model_path, device=self.device)
            print("Model loaded successfully.")
        except Exception as e:
            print(f"Error loading model: {e}")
            self.model = None

    def rank_sections(self, persona: str, job: str, sections: list[dict]) -> list[dict]:
        if not self.model or not sections:
            return []
        query = f"User profile: {persona}. Task to be completed: {job}"
        section_headings = [section['text'] for section in sections]
        print(f"Encoding {len(section_headings)} section headings for relevance ranking...")
        query_embedding = self.model.encode(query, convert_to_tensor=True, device=self.device)
        section_embeddings = self.model.encode(section_headings, convert_to_tensor=True, device=self.device)
        cosine_scores = util.cos_sim(query_embedding, section_embeddings)
        for i, section in enumerate(sections):
            section['relevance_score'] = cosine_scores[0][i].item()
        ranked_sections = sorted(sections, key=lambda x: x['relevance_score'], reverse=True)
        print("Ranking complete.")
        return ranked_sections
