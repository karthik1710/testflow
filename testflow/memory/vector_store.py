"""
Vector store using ChromaDB for semantic search and RAG
"""
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Optional, Any
from pathlib import Path


class VectorStore:
    """Manages vector embeddings for semantic search"""

    def __init__(self, persist_directory: str = "data/vector_db"):
        """Initialize ChromaDB vector store"""
        self.persist_directory = persist_directory
        Path(persist_directory).mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        # Create or get collections
        self.collections = {
            'webhmi': self._get_or_create_collection('webhmi_patterns'),
            'plc': self._get_or_create_collection('plc_commands'),
            'testrail': self._get_or_create_collection('testrail_usage'),
            'gitlab': self._get_or_create_collection('gitlab_operations'),
            'playwright': self._get_or_create_collection('playwright_actions')
        }

        # Initialize with default knowledge
        self._init_default_knowledge()

    def _get_or_create_collection(self, name: str):
        """Get or create a collection"""
        try:
            return self.client.get_collection(name)
        except:
            return self.client.create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"}  # Use cosine similarity
            )

    def _init_default_knowledge(self):
        """Initialize with default knowledge base"""

        # WebHMI patterns
        webhmi_docs = [
            {
                "text": "To navigate to joint geometry page, go to http://192.168.101.151/jointgeometry",
                "metadata": {"category": "navigation", "page": "jointgeometry"}
            },
            {
                "text": "To navigate to calibration page, go to http://192.168.101.151/calibration",
                "metadata": {"category": "navigation", "page": "calibration"}
            },
            {
                "text": "To click on Longitudinal Welding calibration, use selector with text 'Longitudinal Welding'",
                "metadata": {"category": "interaction", "element": "button"}
            },
            {
                "text": "To verify welding type, check for element with text 'longitudinal welding'",
                "metadata": {"category": "verification", "field": "welding_type"}
            }
        ]

        # Add to collection if empty
        if self.collections['webhmi'].count() == 0:
            self.add_documents('webhmi', webhmi_docs)

        # PLC patterns
        plc_docs = [
            {
                "text": "To read PLC data, use GET request to /api/plc/read with address parameter",
                "metadata": {"category": "read", "method": "GET"}
            },
            {
                "text": "To write PLC data, use POST request to /api/plc/write with address and value",
                "metadata": {"category": "write", "method": "POST"}
            }
        ]

        if self.collections['plc'].count() == 0:
            self.add_documents('plc', plc_docs)

        # TestRail patterns
        testrail_docs = [
            {
                "text": "To get test case details, use API endpoint /get_case/{case_id}",
                "metadata": {"category": "api", "endpoint": "get_case"}
            },
            {
                "text": "To add test result, use API endpoint /add_result/{test_id} with status and comment",
                "metadata": {"category": "api", "endpoint": "add_result"}
            }
        ]

        if self.collections['testrail'].count() == 0:
            self.add_documents('testrail', testrail_docs)

        # Playwright patterns
        playwright_docs = [
            {
                "text": "To click a button with text, use action: click with selector 'text=ButtonName'",
                "metadata": {"category": "action", "type": "click"}
            },
            {
                "text": "To navigate to URL, use action: navigate with url parameter",
                "metadata": {"category": "action", "type": "navigate"}
            },
            {
                "text": "To fill a form field, use action: fill with selector and value parameters",
                "metadata": {"category": "action", "type": "fill"}
            },
            {
                "text": "To verify element exists, use action: check_element_exists with selector",
                "metadata": {"category": "action", "type": "verify"}
            }
        ]

        if self.collections['playwright'].count() == 0:
            self.add_documents('playwright', playwright_docs)

    def add_documents(
        self,
        collection_name: str,
        documents: List[Dict[str, Any]],
        ids: Optional[List[str]] = None
    ):
        """Add documents to a collection"""
        if collection_name not in self.collections:
            raise ValueError(f"Unknown collection: {collection_name}")

        collection = self.collections[collection_name]

        texts = [doc['text'] for doc in documents]
        metadatas = [doc.get('metadata', {}) for doc in documents]

        # Generate IDs if not provided
        if ids is None:
            current_count = collection.count()
            ids = [f"{collection_name}_{current_count + i}" for i in range(len(documents))]

        collection.add(
            documents=texts,
            metadatas=metadatas,
            ids=ids
        )

    def search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 3,
        filter_metadata: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar documents"""
        if collection_name not in self.collections:
            raise ValueError(f"Unknown collection: {collection_name}")

        collection = self.collections[collection_name]

        # Perform similarity search
        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where=filter_metadata
        )

        # Format results
        formatted_results = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                formatted_results.append({
                    'text': doc,
                    'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                    'distance': results['distances'][0][i] if results['distances'] else None
                })

        return formatted_results

    def get_context(self, query: str, collections: Optional[List[str]] = None) -> str:
        """Get relevant context from multiple collections"""
        if collections is None:
            collections = list(self.collections.keys())

        context_parts = []

        for collection_name in collections:
            results = self.search(collection_name, query, top_k=2)
            if results:
                context_parts.append(f"\n## {collection_name.upper()} Knowledge:")
                for result in results:
                    context_parts.append(f"- {result['text']}")

        return "\n".join(context_parts)

    def add_execution_knowledge(
        self,
        action_description: str,
        playwright_actions: List[Dict],
        success: bool,
        metadata: Optional[Dict] = None
    ):
        """Learn from successful test executions"""
        if not success:
            return  # Only learn from successful executions

        # Create document from execution
        doc = {
            "text": f"{action_description} -> {len(playwright_actions)} Playwright actions",
            "metadata": {
                "success": success,
                "action_count": len(playwright_actions),
                **(metadata or {})
            }
        }

        # Add to playwright collection
        try:
            self.add_documents('playwright', [doc])
        except Exception as e:
            print(f"Failed to add execution knowledge: {e}")

    def get_similar_test_patterns(self, test_description: str, top_k: int = 5) -> List[Dict]:
        """Find similar test patterns from past executions"""
        results = []

        # Search across relevant collections
        for collection_name in ['webhmi', 'playwright']:
            collection_results = self.search(collection_name, test_description, top_k=top_k)
            results.extend(collection_results)

        # Sort by distance (most similar first)
        results.sort(key=lambda x: x.get('distance', float('inf')))

        return results[:top_k]

    def reset(self):
        """Reset all collections (for testing)"""
        for collection_name in list(self.collections.keys()):
            try:
                self.client.delete_collection(collection_name)
            except:
                pass

        # Recreate collections
        self.collections = {
            'webhmi': self._get_or_create_collection('webhmi_patterns'),
            'plc': self._get_or_create_collection('plc_commands'),
            'testrail': self._get_or_create_collection('testrail_usage'),
            'gitlab': self._get_or_create_collection('gitlab_operations'),
            'playwright': self._get_or_create_collection('playwright_actions')
        }

        self._init_default_knowledge()
