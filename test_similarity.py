from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

model = SentenceTransformer("all-MiniLM-L6-v2")

sentences = [
    "I want to sleep.",
    "I want to go to bed.",
    "I want to study."
]

embeddings = model.encode(sentences)

similarity = cosine_similarity(embeddings)

print("Similarity matrix:")
print(similarity)