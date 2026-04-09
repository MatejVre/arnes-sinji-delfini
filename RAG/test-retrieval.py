from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
import os
from dotenv import load_dotenv

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = "sinji-delfini-test"
TOP_K = 5 #Tle se stima kok dokumentov nej vrne retrieval. Se zmer je pomembno upostevat score ker 3 dokumenti s scori 0.9, 0.2, 0.1, ne pomen da use 3 upostevamo!


def find_suitable_documents(index, model, query):

    response = index.query(
    vector=model.encode(query).tolist(),
    top_k=TOP_K,
    include_metadata=True
    )

    return response

# vprasanje = "Ne spomnim se koliko denarja smo porabili za Patrio"


if __name__ == "__main__":
    
    load_dotenv()
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(INDEX_NAME)

    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2") #Model za embedding stavkov - tentative change glede na to kaj se zmenmo

    r = find_suitable_documents(index, model, "koliko smo porabili za Catering za sestanek s strankami")
    print(r)