import chromadb
from chromadb.utils import embedding_functions

class FashionRAG:
    def __init__(self, persist_directory="./chroma_data"):
        print("Initializing Local ChromaDB...")
        # Sets up a local database folder on your PC
        self.client = chromadb.PersistentClient(path=persist_directory)
        
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        self.collection = self.client.get_or_create_collection(
            name="fashion_trends",
            embedding_function=self.embedding_fn
        )

    def populate(self, trends_data: list[dict]):
        """Upserts mock data into the persistent DB."""
        if not trends_data:
            return
            
        documents = [item["description"] for item in trends_data]
        metadatas = [{"style": item["style"], "event": item["event"]} for item in trends_data]
        ids = [f"trend_{i}" for i in range(len(trends_data))]
        
        self.collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
        print(f"Populated DB with {len(trends_data)} items.")

    def retrieve(self, query: str, n_results: int = 2) -> list[str]:
        """Fetches the best context for the LangGraph agent."""
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results
        )
        return results['documents'][0] if results['documents'] else []

# Instantiate a single global instance to be imported by your LangGraph service
rag_db = FashionRAG()