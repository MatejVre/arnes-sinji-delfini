from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer
import os
import json
import sys
import csv

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = "sinji-delfini-test"
BASE_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
PATH_TO_METADATA = os.path.join(BASE_DIRECTORY, "../documents/permissions.json")
PATH_TO_DOCUMENTS = os.path.join(BASE_DIRECTORY, "../documents")
CHUNK_SIZE = 200
CHUNK_OVERLAP = 20
ROWS_PER_CHUNK = 2


def match_documents_with_metadata(path_to_metadata, path_to_documents):

    with open(path_to_metadata, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    docs = []

    for entry in metadata:
        filepath = os.path.join(path_to_documents, entry["dokument"])
        try:
            text = read_document(filepath)
        except FileNotFoundError:
            print(f"Dokument {entry["dokument"]} ne obstaja v vaši zbirki dokumentov!")
            #Ce se ta error zgodi se ne bo noben fajl uploudou na pinecone. Razlog je ta da upserti stanejo, oz se stejejo
            #tko da je bols ce se samo usi enkrat naloudajo kokr da se popravla stokrat.

        docs.append({
            "text": text, #ta del je za zment se
            "dovoljene skupine": entry["dovoljene skupine"],
            "dokument": entry["dokument"]
        })

    return docs

def read_document(filepath):

    if filepath.endswith(".csv"):
        rows = []
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(", ".join(f"{k}: {v}" for k, v in row.items()))
        return "\n".join(rows)
    else:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

def chunk_text(doc, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP, rows_per_chunk=ROWS_PER_CHUNK):
    
    chunks = []

    if doc["dokument"].endswith(".csv"):
        rows = [row for row in doc["text"].split("\n") if row.strip()]  # remove empty lines
        chunks =  ["\n".join(rows[i:i+rows_per_chunk]) for i in range(0, len(rows), rows_per_chunk)]
        print(len(chunks))
    
    else:
        words = doc["text"].split()

        i = 0
        while i < len(words):
            chunk = " ".join(words[i:i+chunk_size])
            chunks.append(chunk)
            i += chunk_size - overlap
    return chunks

#rabmo chunke za dolge dokumente ker embedding daljsih rata ful slab. Je pa naceloma to odvisn od dokumenta. Ce so kratki se lahko chunking umakne,
#ce so pa dolge pogodbe ipd. je treba pa to nujno met.
def create_embedings(model, docs):

    for doc in docs:
        doc["chunks"] = chunk_text(doc)
        doc["embeddings"] = [model.encode(chunk).tolist() for chunk in doc["chunks"]]

    return docs


def upsert_to_index(docs, index):

    for doc in docs:
        vectors = []
        for i, (chunk, embedding) in enumerate(zip(doc["chunks"], doc["embeddings"])):
            vectors.append({
                "id": f"{doc["dokument"]}-chunk-{i}",
                "values": embedding,
                "metadata": {
                    "text": chunk,
                    "dovoljene skupine": doc["dovoljene skupine"]
                }
            })
        index.upsert(vectors=vectors)
        print(f"upserted {doc["dokument"]}")
#lahko se odlocimo ce bomo meli vsebino fajlou shranjeno v pinecone textu al bomo retrievali datoteke ko bodo vrnjene


#Program se zalaufa na mode 0 ce use stima in hocs probat dejanski upsert. 1 al pa karkol druzga pa za testiranje stvari ipd.
if __name__ == "__main__":
    mode = int(sys.argv[1])

    if mode == 0:
        pc = Pinecone(api_key=PINECONE_API_KEY)

        if not pc.has_index(INDEX_NAME):
            pc.create_index(
                name=INDEX_NAME,
                vector_type="dense",
                dimension=384,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                ),
                deletion_protection="disabled",
                tags={
                    "environment": "development"
                }
            )

        index = pc.Index(INDEX_NAME)

    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2") #Model za embedding stavkov - tentative change glede na to kaj se zmenmo

    docs = match_documents_with_metadata(PATH_TO_METADATA, PATH_TO_DOCUMENTS)

    if mode == 0:
        docs = create_embedings(model, docs)

        upsert_to_index(docs, index)