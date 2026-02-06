# Refactored Architecture Documentation

## Overview

The codebase has been refactored to follow a modular, service-oriented architecture that separates concerns and makes it easy to add new integrations.

## Architecture Layers

### 1. Base Handler (`agent_framework/base_handler.py`)

Abstract base class that all handlers must inherit from:

```python
class BaseHandler(ABC):
    @abstractmethod
    async def initialize(self, config: Optional[Dict] = None) -> bool:
        """Initialize handler with configuration"""
        
    @abstractmethod
    async def handle_action(self, action: str, params: Dict) -> Dict:
        """Execute action and return standardized response"""
        
    @abstractmethod
    async def cleanup(self) -> bool:
        """Cleanup resources"""
```

**Benefits:**
- Consistent interface across all handlers
- Standardized error handling and logging
- Easy to test and maintain

### 2. Handler Registry (`agent_framework/handler_registry.py`)

Centralized handler management:

```python
from agent_framework.handler_registry import register_handler, get_handler

# Register handlers at startup
register_handler("playwright", PlaywrightHandler)
register_handler("testrail", TestRailHandler)

# Use handlers
handler = await get_handler("playwright", config={"headless": True})
result = await handler.handle_action("navigate", {"url": "https://example.com"})
```

**Benefits:**
- Dynamic handler loading
- Configuration-driven initialization
- No code changes needed for new handlers

### 3. Service Layer (`testflow/services/`)

Business logic separated from HTTP routing:

#### TestExecutionService
- Orchestrates test execution workflow
- Fetches test cases from TestRail
- Interprets steps with AI
- Executes Playwright actions
- Validates results
- Records to database

#### ValidationService
- AI-powered validation
- Fallback to rule-based validation
- Consistent validation interface

#### ScreenshotService
- Screenshot capture and storage
- Database persistence
- File management

**Benefits:**
- Business logic independent of HTTP framework
- Testable in isolation
- Reusable across different interfaces (HTTP, CLI, etc.)

### 4. Handlers (`testflow/*/handler.py`)

Specific integration implementations:

- **PlaywrightHandler**: Web UI automation
- **TestRailHandler**: Test case management
- **GitLabHandler**: CI/CD integration
- **SiemensPLCHandler**: Industrial automation

All handlers inherit from `BaseHandler` and provide:
- Initialization with configuration
- Action execution
- Resource cleanup

## Project Structure

```
ai-automation-agent/
│
├── agent_framework/                # Core framework
│   ├── base_handler.py            # Abstract base handler
│   ├── handler_registry.py        # Handler registration
│   └── agent.py                   # Legacy agent (to be refactored)
│
├── testflow/                      # Test automation framework
│   ├── services/                  # Business logic services
│   │   ├── test_execution_service.py
│   │   ├── validation_service.py
│   │   └── screenshot_service.py
│   │
│   ├── playwright_app/            # Playwright integration
│   │   ├── handler.py            # Legacy handler
│   │   └── handler_refactored.py # New BaseHandler-based
│   │
│   ├── testrail_app/             # TestRail integration
│   ├── gitlab_app/               # GitLab integration
│   ├── siemens_plc_app/          # Siemens PLC integration
│   │
│   ├── ai_interpreter.py         # AI step interpretation
│   ├── database/                 # Database models and manager
│   └── backend/                  # HTTP server (FastAPI)
│
└── requirements.txt              # Dependencies
```

## Adding a New Integration

### Step 1: Create Handler Class

```python
from agent_framework.base_handler import BaseHandler

class MyNewHandler(BaseHandler):
    def __init__(self, name: str = "mynew"):
        super().__init__(name)
        self._client = None
    
    async def initialize(self, config: Optional[Dict] = None) -> bool:
        """Initialize your integration"""
        try:
            self._client = MyClient(config.get("api_key"))
            self.logger.info("MyNew handler initialized")
            return True
        except Exception as e:
            self.logger.error(f"Initialization failed: {e}")
            return False
    
    async def handle_action(self, action: str, params: Dict) -> Dict:
        """Handle actions"""
        action_map = {
            "fetch": self._action_fetch,
            "update": self._action_update
        }
        
        handler = action_map.get(action)
        if not handler:
            return self.create_response(
                success=False,
                action=action,
                error=f"Unknown action: {action}"
            )
        
        try:
            result = await handler(params)
            return self.create_response(
                success=True,
                action=action,
                data=result
            )
        except Exception as e:
            return self.create_response(
                success=False,
                action=action,
                error=str(e)
            )
    
    async def cleanup(self) -> bool:
        """Cleanup resources"""
        if self._client:
            await self._client.close()
        return True
    
    async def _action_fetch(self, params: Dict) -> Dict:
        """Fetch data"""
        validation_error = self.validate_params(params, ["id"])
        if validation_error:
            raise ValueError(validation_error)
        
        data = await self._client.fetch(params["id"])
        return {"data": data}
    
    async def _action_update(self, params: Dict) -> Dict:
        """Update data"""
        validation_error = self.validate_params(params, ["id", "data"])
        if validation_error:
            raise ValueError(validation_error)
        
        result = await self._client.update(params["id"], params["data"])
        return {"updated": result}
```

### Step 2: Register Handler

```python
from agent_framework.handler_registry import register_handler
from my_integration.handler import MyNewHandler

# At application startup
register_handler("mynew", MyNewHandler)
```

### Step 3: Use Handler

```python
from agent_framework.handler_registry import get_handler

# Get handler instance
handler = await get_handler("mynew", config={
    "api_key": "your_api_key"
})

# Execute actions
result = await handler.handle_action("fetch", {"id": 123})
print(result)
# {'success': True, 'action': 'fetch', 'data': {...}, 'timestamp': '2024-01-08T...'}
```

## Migration Guide

### From Old Handler to New Handler

**Old Style:**
```python
class OldHandler:
    @staticmethod
    async def handle_action(action_json):
        action = action_json.get("action")
        params = action_json.get("params", {})
        
        if action == "navigate":
            # Navigate logic
            return {"success": True}
```

**New Style:**
```python
class NewHandler(BaseHandler):
    def __init__(self):
        super().__init__("mynew")
    
    async def initialize(self, config=None):
        # Setup
        return True
    
    async def handle_action(self, action, params):
        if action == "navigate":
            result = await self._action_navigate(params)
            return self.create_response(True, action, data=result)
    
    async def cleanup(self):
        # Cleanup
        return True
    
    async def _action_navigate(self, params):
        validation_error = self.validate_params(params, ["url"])
        if validation_error:
            raise ValueError(validation_error)
        
        # Navigate logic
        return {"url": params["url"]}
```

### From Route Logic to Service Logic

**Old Style (server.py):**
```python
@app.post("/run-test/{test_case_id}")
async def run_test(test_case_id: int):
    # Fetch test case
    test_case = await agent.handle("testrail", {...})
    
    # Interpret steps
    steps = ai_interpreter.interpret_steps(...)
    
    # Execute steps
    for step in steps:
        result = await agent.handle("playwright", step)
        # Validate, save to DB, etc.
    
    return {"status": "complete"}
```

**New Style:**
```python
@app.post("/run-test/{test_case_id}")
async def run_test(test_case_id: int):
    # Use service
    result = await test_execution_service.execute_test_case(
        test_case_id=test_case_id,
        test_case_data=test_case,
        progress_callback=send_progress
    )
    
    return result
```

## Benefits of New Architecture

### 1. Modularity
- Clear separation of concerns
- Each component has single responsibility
- Easy to understand and maintain

### 2. Extensibility
- Add new handlers without modifying existing code
- Configuration-driven handler initialization
- Pluggable architecture

### 3. Testability
- Services testable in isolation
- Mock handlers for testing
- Clear interfaces

### 4. Maintainability
- Consistent patterns across handlers
- Centralized logging and error handling
- Reduced code duplication

### 5. Scalability
- Services can be extracted to microservices
- Handlers can run in separate processes
- Easy to add caching, queuing, etc.

## Next Steps

1. **Migrate Existing Handlers**
   - Update PlaywrightHandler to use refactored version
   - Update TestRailHandler, GitLabHandler
   - Remove legacy handler code

2. **Refactor Backend Routes**
   - Extract business logic to services
   - Make routes thin controllers
   - Add proper error handling

3. **Add Unit Tests**
   - Test services in isolation
   - Test handlers with mocked dependencies
   - Test handler registry

4. **Documentation**
   - API documentation for each handler
   - Configuration reference
   - Example usage patterns

5. **Performance Optimization**
   - Add caching where appropriate
   - Connection pooling for handlers
   - Async optimization

## Configuration Example

```yaml
# config.yaml
handlers:
  playwright:
    headless: true
    browser_type: chromium
    viewport:
      width: 1920
      height: 1080
    screenshot_dir: test_results
  
  testrail:
    api_url: https://your-testrail.com
    api_key: your_api_key
    project_id: 1
  
  gitlab:
    api_url: https://gitlab.com
    api_token: your_token
    project_id: 123
```

## Logging

All handlers use consistent logging:

```python
# Each handler has its own logger
handler.logger.info("Operation successful")
handler.logger.warning("Potential issue")
handler.logger.error("Operation failed")
handler.logger.debug("Detailed debug info")

# Logs are namespaced: testflow.playwright, testflow.testrail, etc.
```

## Error Handling

Standardized error responses:

```python
{
    "success": False,
    "action": "navigate",
    "error": "URL is required",
    "timestamp": "2024-01-08T17:30:00Z"
}
```

## Support

For questions or issues with the new architecture:
1. Check this documentation
2. Review example handlers
3. Contact the development team
