"""
Data models for test execution tracking
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


@dataclass
class TestRun:
    """Test execution run"""
    id: Optional[int] = None
    test_case_id: str = ""
    test_name: str = ""
    status: str = "RUNNING"  # PASSED, FAILED, RUNNING, SKIPPED
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    total_steps: int = 0
    passed_steps: int = 0
    failed_steps: int = 0
    screenshots_path: str = ""
    testrail_run_id: Optional[str] = None
    created_at: Optional[datetime] = None

    def to_dict(self):
        return {
            'id': self.id,
            'test_case_id': self.test_case_id,
            'test_name': self.test_name,
            'status': self.status,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration_seconds': self.duration_seconds,
            'total_steps': self.total_steps,
            'passed_steps': self.passed_steps,
            'failed_steps': self.failed_steps,
            'screenshots_path': self.screenshots_path,
            'testrail_run_id': self.testrail_run_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


@dataclass
class TestStep:
    """Individual test step"""
    id: Optional[int] = None
    test_run_id: int = 0
    step_number: int = 0
    description: str = ""
    action_type: str = ""
    action_params: str = ""
    status: str = "RUNNING"  # PASSED, FAILED, SKIPPED
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None
    execution_time_ms: int = 0
    timestamp: Optional[datetime] = None

    def to_dict(self):
        return {
            'id': self.id,
            'test_run_id': self.test_run_id,
            'step_number': self.step_number,
            'description': self.description,
            'action_type': self.action_type,
            'action_params': self.action_params,
            'status': self.status,
            'error_message': self.error_message,
            'screenshot_path': self.screenshot_path,
            'execution_time_ms': self.execution_time_ms,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


@dataclass
class Screenshot:
    """Screenshot metadata"""
    id: Optional[int] = None
    test_run_id: int = 0
    test_step_id: Optional[int] = None
    file_path: str = ""
    file_name: str = ""
    file_size_bytes: int = 0
    timestamp: Optional[datetime] = None

    def to_dict(self):
        return {
            'id': self.id,
            'test_run_id': self.test_run_id,
            'test_step_id': self.test_step_id,
            'file_path': self.file_path,
            'file_name': self.file_name,
            'file_size_bytes': self.file_size_bytes,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


@dataclass
class ExecutionMetrics:
    """Daily execution metrics"""
    id: Optional[int] = None
    date: str = ""
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    total_duration_seconds: float = 0.0
    avg_duration_seconds: float = 0.0
    ai_calls_made: int = 0
    cache_hits: int = 0
    cache_miss: int = 0

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date,
            'total_tests': self.total_tests,
            'passed_tests': self.passed_tests,
            'failed_tests': self.failed_tests,
            'total_duration_seconds': self.total_duration_seconds,
            'avg_duration_seconds': self.avg_duration_seconds,
            'ai_calls_made': self.ai_calls_made,
            'cache_hits': self.cache_hits,
            'cache_miss': self.cache_miss,
            'success_rate': round((self.passed_tests / self.total_tests * 100) if self.total_tests > 0 else 0, 2)
        }
