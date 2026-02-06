"""
SQLite database manager for test execution tracking
"""
import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path
from .models import TestRun, TestStep, Screenshot, ExecutionMetrics


class DatabaseManager:
    """Manages SQLite database operations for test tracking"""

    def __init__(self, db_path: str = "data/testflow.db"):
        self.db_path = db_path
        self._ensure_directory()
        self._init_database()

    def _ensure_directory(self):
        """Create data directory if it doesn't exist"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        return conn

    def _init_database(self):
        """Initialize database schema"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Test Runs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_case_id TEXT NOT NULL,
                test_name TEXT,
                status TEXT CHECK(status IN ('PASSED', 'FAILED', 'RUNNING', 'SKIPPED')),
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                duration_seconds REAL,
                total_steps INTEGER,
                passed_steps INTEGER,
                failed_steps INTEGER,
                screenshots_path TEXT,
                testrail_run_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Test Steps table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_run_id INTEGER,
                step_number INTEGER,
                description TEXT,
                action_type TEXT,
                action_params TEXT,
                status TEXT CHECK(status IN ('PASSED', 'FAILED', 'SKIPPED')),
                error_message TEXT,
                screenshot_path TEXT,
                execution_time_ms INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (test_run_id) REFERENCES test_runs(id)
            )
        """)

        # Screenshots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_run_id INTEGER,
                test_step_id INTEGER,
                file_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_size_bytes INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (test_run_id) REFERENCES test_runs(id),
                FOREIGN KEY (test_step_id) REFERENCES test_steps(id)
            )
        """)

        # Execution Metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS execution_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE DEFAULT (date('now')),
                total_tests INTEGER DEFAULT 0,
                passed_tests INTEGER DEFAULT 0,
                failed_tests INTEGER DEFAULT 0,
                total_duration_seconds REAL DEFAULT 0,
                avg_duration_seconds REAL DEFAULT 0,
                ai_calls_made INTEGER DEFAULT 0,
                cache_hits INTEGER DEFAULT 0,
                cache_miss INTEGER DEFAULT 0,
                UNIQUE(date)
            )
        """)

        # Vector Cache table (for AI response caching)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vector_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_text TEXT NOT NULL,
                response_text TEXT NOT NULL,
                embedding_id TEXT,
                usage_count INTEGER DEFAULT 1,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    # ========== Test Runs ==========

    def create_test_run(self, test_run: TestRun) -> int:
        """Create new test run and return ID"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO test_runs (
                test_case_id, test_name, status, start_time,
                total_steps, passed_steps, failed_steps, screenshots_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            test_run.test_case_id,
            test_run.test_name,
            test_run.status,
            test_run.start_time or datetime.now(),
            test_run.total_steps,
            test_run.passed_steps,
            test_run.failed_steps,
            test_run.screenshots_path
        ))

        test_run_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return test_run_id

    def update_test_run(self, test_run_id: int, **kwargs):
        """Update test run fields"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Build dynamic UPDATE query
        set_clause = ", ".join([f"{key} = ?" for key in kwargs.keys()])
        query = f"UPDATE test_runs SET {set_clause} WHERE id = ?"
        values = list(kwargs.values()) + [test_run_id]

        cursor.execute(query, values)
        conn.commit()
        conn.close()

    def get_test_run(self, test_run_id: int) -> Optional[Dict]:
        """Get test run by ID"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM test_runs WHERE id = ?", (test_run_id,))
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    def get_test_runs(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict]:
        """Get test runs with filters"""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM test_runs WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status)

        if start_date:
            query += " AND date(start_time) >= ?"
            params.append(start_date)

        if end_date:
            query += " AND date(start_time) <= ?"
            params.append(end_date)

        query += " ORDER BY start_time DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    # ========== Test Steps ==========

    def create_test_step(self, test_step: TestStep) -> int:
        """Create test step and return ID"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO test_steps (
                test_run_id, step_number, description, action_type,
                action_params, status, error_message, screenshot_path,
                execution_time_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            test_step.test_run_id,
            test_step.step_number,
            test_step.description,
            test_step.action_type,
            test_step.action_params,
            test_step.status,
            test_step.error_message,
            test_step.screenshot_path,
            test_step.execution_time_ms
        ))

        step_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return step_id

    def get_test_steps(self, test_run_id: int) -> List[Dict]:
        """Get all steps for a test run"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM test_steps WHERE test_run_id = ? ORDER BY step_number",
            (test_run_id,)
        )
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    # ========== Screenshots ==========

    def create_screenshot(self, screenshot: Screenshot) -> int:
        """Record screenshot metadata"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO screenshots (
                test_run_id, test_step_id, file_path, file_name, file_size_bytes
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            screenshot.test_run_id,
            screenshot.test_step_id,
            screenshot.file_path,
            screenshot.file_name,
            screenshot.file_size_bytes
        ))

        screenshot_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return screenshot_id

    def get_screenshots(self, test_run_id: int) -> List[Dict]:
        """Get all screenshots for a test run"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM screenshots WHERE test_run_id = ? ORDER BY timestamp",
            (test_run_id,)
        )
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    # ========== Metrics ==========

    def update_daily_metrics(
        self,
        tests_run: int = 0,
        tests_passed: int = 0,
        tests_failed: int = 0,
        duration: float = 0,
        ai_calls: int = 0,
        cache_hits: int = 0
    ):
        """Update metrics for today"""
        conn = self._get_connection()
        cursor = conn.cursor()

        today = datetime.now().date().isoformat()

        # Insert or update today's metrics
        cursor.execute("""
            INSERT INTO execution_metrics (
                date, total_tests, passed_tests, failed_tests,
                total_duration_seconds, ai_calls_made, cache_hits
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                total_tests = total_tests + excluded.total_tests,
                passed_tests = passed_tests + excluded.passed_tests,
                failed_tests = failed_tests + excluded.failed_tests,
                total_duration_seconds = total_duration_seconds + excluded.total_duration_seconds,
                ai_calls_made = ai_calls_made + excluded.ai_calls_made,
                cache_hits = cache_hits + excluded.cache_hits
        """, (today, tests_run, tests_passed, tests_failed, duration, ai_calls, cache_hits))

        # Update average duration
        cursor.execute("""
            UPDATE execution_metrics
            SET avg_duration_seconds = total_duration_seconds / total_tests
            WHERE date = ? AND total_tests > 0
        """, (today,))

        conn.commit()
        conn.close()

    def get_metrics_summary(self, days: int = 30) -> Dict[str, Any]:
        """Get metrics summary for last N days"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Overall stats
        cursor.execute("""
            SELECT
                SUM(total_tests) as total_tests,
                SUM(passed_tests) as passed_tests,
                SUM(failed_tests) as failed_tests,
                AVG(avg_duration_seconds) as avg_duration,
                SUM(ai_calls_made) as ai_calls,
                SUM(cache_hits) as cache_hits
            FROM execution_metrics
            WHERE date >= date('now', '-' || ? || ' days')
        """, (days,))

        row = cursor.fetchone()
        summary = dict(row) if row else {}

        # Success rate
        if summary.get('total_tests', 0) > 0:
            summary['success_rate'] = round(
                (summary['passed_tests'] / summary['total_tests']) * 100, 2
            )
        else:
            summary['success_rate'] = 0

        # Daily trend
        cursor.execute("""
            SELECT date, total_tests, passed_tests, failed_tests
            FROM execution_metrics
            WHERE date >= date('now', '-' || ? || ' days')
            ORDER BY date
        """, (days,))

        summary['daily_trend'] = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return summary

    # ========== Cache ==========

    def cache_ai_response(self, query: str, response: str, embedding_id: Optional[str] = None):
        """Cache AI response for future use"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO vector_cache (query_text, response_text, embedding_id)
            VALUES (?, ?, ?)
        """, (query, response, embedding_id))

        conn.commit()
        conn.close()

    def get_cached_response(self, query: str) -> Optional[str]:
        """Get cached AI response"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT response_text FROM vector_cache
            WHERE query_text = ?
            ORDER BY last_used DESC
            LIMIT 1
        """, (query,))

        row = cursor.fetchone()

        if row:
            # Update usage count and last used time
            cursor.execute("""
                UPDATE vector_cache
                SET usage_count = usage_count + 1, last_used = CURRENT_TIMESTAMP
                WHERE query_text = ?
            """, (query,))
            conn.commit()

        conn.close()
        return row['response_text'] if row else None
