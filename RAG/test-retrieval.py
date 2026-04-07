from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
import os
from dotenv import load_dotenv

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = "sinji-delfini-test"


def find_suitable_documents(index, model, query):

    response = index.query(
    vector=model.encode(query).tolist(),
    top_k=2,
    include_metadata=True
    )

    return response

# vprasanje = "Ne spomnim se koliko denarja smo porabili za Patrio"


if __name__ == "__main__":
    
    load_dotenv()
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(INDEX_NAME)

    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2") #Model za embedding stavkov - tentative change glede na to kaj se zmenmo

    r = find_suitable_documents(index, model, "Kdaj je bil odpuščen Tung Tung Tung Sahur?")
    print(r)