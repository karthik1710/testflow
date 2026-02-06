"""
RAG (Retrieval Augmented Generation) Engine
Combines vector search with AI to provide context-aware responses
"""
from typing import Dict, List, Optional, Any
from .vector_store import VectorStore
from ..database.db_manager import DatabaseManager


class RAGEngine:
    """RAG engine for context-aware AI responses"""

    def __init__(
        self,
        vector_store: VectorStore,
        db_manager: DatabaseManager,
        cache_threshold: float = 0.95
    ):
        """
        Initialize RAG engine

        Args:
            vector_store: Vector store for semantic search
            db_manager: Database manager for caching
            cache_threshold: Similarity threshold for using cached responses (0-1)
        """
        self.vector_store = vector_store
        self.db_manager = db_manager
        self.cache_threshold = cache_threshold
        self.cache_hits = 0
        self.cache_misses = 0

    def get_context_for_query(
        self,
        query: str,
        collections: Optional[List[str]] = None,
        top_k: int = 3
    ) -> str:
        """
        Get relevant context for a query from vector store

        Args:
            query: User query
            collections: Which collections to search (default: all)
            top_k: Number of results per collection

        Returns:
            Formatted context string
        """
        # Check cache first
        cached_response = self.db_manager.get_cached_response(query)
        if cached_response:
            self.cache_hits += 1
            return cached_response

        self.cache_misses += 1

        # Get context from vector store
        context = self.vector_store.get_context(query, collections)

        # Cache for future use
        self.db_manager.cache_ai_response(query, context)

        return context

    def enhance_prompt_with_context(
        self,
        user_prompt: str,
        collections: Optional[List[str]] = None
    ) -> str:
        """
        Enhance user prompt with relevant context from vector store

        Args:
            user_prompt: Original user prompt
            collections: Which collections to search

        Returns:
            Enhanced prompt with context
        """
        context = self.get_context_for_query(user_prompt, collections)

        enhanced_prompt = f"""
You have access to the following knowledge base:

{context}

User Request: {user_prompt}

Please use the knowledge base above to provide an accurate response. If the knowledge base contains relevant information, use it. Otherwise, use your general knowledge.
"""
        return enhanced_prompt

    def find_similar_test_executions(
        self,
        test_description: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Find similar test executions from history

        Args:
            test_description: Description of the test
            top_k: Number of similar tests to return

        Returns:
            List of similar test patterns
        """
        return self.vector_store.get_similar_test_patterns(test_description, top_k)

    def learn_from_execution(
        self,
        test_case_id: str,
        test_name: str,
        test_steps: str,
        playwright_actions: List[Dict],
        success: bool
    ):
        """
        Learn from test execution and store in vector database

        Args:
            test_case_id: TestRail test case ID
            test_name: Name of the test
            test_steps: Original test steps (natural language)
            playwright_actions: Generated Playwright actions
            success: Whether execution was successful
        """
        if not success:
            return  # Only learn from successful executions

        # Add to vector store
        self.vector_store.add_execution_knowledge(
            action_description=f"Test: {test_name}\nSteps: {test_steps}",
            playwright_actions=playwright_actions,
            success=success,
            metadata={
                'test_case_id': test_case_id,
                'test_name': test_name,
                'action_count': len(playwright_actions)
            }
        )

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total * 100) if total > 0 else 0

        return {
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'total_queries': total,
            'hit_rate_percent': round(hit_rate, 2)
        }

    def get_playwright_action_suggestions(
        self,
        test_step: str
    ) -> List[Dict[str, Any]]:
        """
        Get Playwright action suggestions based on test step description

        Args:
            test_step: Natural language test step

        Returns:
            List of suggested Playwright actions with confidence scores
        """
        # Search playwright collection for similar patterns
        results = self.vector_store.search(
            'playwright',
            test_step,
            top_k=5
        )

        suggestions = []
        for result in results:
            # Calculate confidence based on distance (lower distance = higher confidence)
            distance = result.get('distance', 1.0)
            confidence = max(0, min(1, 1 - distance))

            suggestions.append({
                'pattern': result['text'],
                'confidence': round(confidence, 2),
                'metadata': result.get('metadata', {})
            })

        return suggestions

    def should_call_ai(self, query: str, confidence_threshold: float = 0.8) -> bool:
        """
        Determine if we should call external AI or use cached knowledge

        Args:
            query: User query
            confidence_threshold: Minimum confidence to skip AI call

        Returns:
            True if should call AI, False if cached knowledge is sufficient
        """
        # Search for similar queries
        results = self.vector_store.search('playwright', query, top_k=1)

        if not results:
            return True  # No similar patterns, need AI

        # Check confidence
        distance = results[0].get('distance', 1.0)
        confidence = max(0, min(1, 1 - distance))

        return confidence < confidence_threshold
