import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


class IntentRecognizer:

    def __init__(
        self,
        dataset_path,
        similarity_threshold=0.60
    ):

        self.model = SentenceTransformer(
            "all-MiniLM-L6-v2"
        )

        self.data = pd.read_csv(dataset_path)

        self.sentences = self.data["sentence"].tolist()
        self.intents = self.data["intent"].tolist()

        self.intent_labels = sorted(
            self.data["intent"].unique()
        )

        self.similarity_threshold = (
            similarity_threshold
        )

        # Pre-compute reference embeddings
        self.embeddings = self.model.encode(
            self.sentences,
            normalize_embeddings=True
        )

    def predict(self, text, top_k=3):

        # Encode user input
        query_embedding = self.model.encode(
            [text],
            normalize_embeddings=True
        )

        # Compare against every reference sentence
        similarities = cosine_similarity(
            query_embedding,
            self.embeddings
        )[0]

        # Find maximum similarity for each intent
        intent_scores = {}

        for intent in self.intent_labels:

            indices = [
                i
                for i, label in enumerate(self.intents)
                if label == intent
            ]

            intent_scores[intent] = max(
                similarities[i]
                for i in indices
            )

        # Rank intents
        ranked = sorted(
            intent_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        top_results = ranked[:top_k]

        # Best intent
        best_intent, best_score = top_results[0]

        # Determine decision
        if best_score < self.similarity_threshold:

            decision = "UNKNOWN"
            predicted_intent = None

        else:

            decision = "PREDICTED"
            predicted_intent = best_intent

        # Find best matching reference sentence
        best_index = max(
            (
                i
                for i, label in enumerate(self.intents)
                if label == best_intent
            ),
            key=lambda i: similarities[i]
        )

        return {
            "decision": decision,
            "intent": predicted_intent,
            "similarity_score": float(best_score),
            "matched_sentence": self.sentences[best_index],
            "top_results": [
                {
                    "intent": intent,
                    "score": float(score)
                }
                for intent, score in top_results
            ]
        }