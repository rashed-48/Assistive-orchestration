from sentence_transformers import SentenceTransformer

print("Loading model...")

model = SentenceTransformer("all-MiniLM-L6-v2")

sentences = [
    "I want to sleep.",
    "I want to go to bed.",
    "I want to study."
]

embeddings = model.encode(sentences)

print("Model loaded successfully.")
print("Embedding shape:", embeddings.shape)