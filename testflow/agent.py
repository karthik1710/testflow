import importlib
import asyncio
import inspect

class Agent:
    def __init__(self):
        self.apps = {}

    def register_app(self, app_name, app_handler):
        self.apps[app_name] = app_handler

    async def handle(self, app_name, action_json, original_request=""):
        """Async handle method that supports both sync and async handlers"""
        if app_name in self.apps:
            handler = self.apps[app_name]

            # Check if handler has async method
            if hasattr(handler, 'handle_action_async'):
                return await handler.handle_action_async(action_json, original_request)
            else:
                # Call sync method in executor to not block event loop
                loop = asyncio.get_event_loop()
                try:
                    result = handler.handle_action(action_json, original_request)
                    # If it's a coroutine or task, await it
                    if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                        return await result
                    return result
                except TypeError:
                    # Fallback for handlers that don't support original_request
                    result = handler.handle_action(action_json)
                    if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                        return await result
                    return result
        else:
            raise ValueError(f"Unknown application: {app_name}")
