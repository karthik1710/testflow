"""
AI-powered step interpretation using OpenAI
Converts natural language test steps to Playwright actions
"""
import os
import json
import logging
from typing import Dict, List, Any, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

class AIInterpreter:
    """Uses OpenAI to interpret natural language test steps"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.client = None
        self.enabled = False

        if self.api_key:
            try:
                self.client = OpenAI(api_key=self.api_key)
                self.enabled = True
                logger.info("✅ OpenAI AI Interpreter enabled")
            except Exception as e:
                logger.warning(f"⚠️ OpenAI initialization failed: {e}")
                self.enabled = False
        else:
            logger.info("ℹ️ OpenAI API key not found, using rule-based parsing")

    def interpret_step(self, step_text: str, expected_result: str = "", context: Dict = None) -> Dict[str, Any]:
        """
        Use OpenAI to interpret a test step and convert to Playwright action

        Args:
            step_text: The test step description
            expected_result: Expected result for validation
            context: Additional context (previous steps, base_url, etc.)

        Returns:
            Dict with action, params, and expected result
        """
        if not self.enabled:
            return None

        try:
            context = context or {}
            base_url = context.get("base_url", "")
            previous_steps = context.get("previous_steps", [])

            system_prompt = """You are an expert test automation engineer. Convert natural language test steps into Playwright browser automation actions.

Return ONLY a valid JSON object with this structure:
{
  "action": "navigate|click|fill|type|select|wait|press_key|hover",
  "params": {
    // Action-specific parameters
  },
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}

Available actions:
- navigate: {"url": "https://..."} - Go to a URL (support relative paths)
- click: {"text": "Button Text"} or {"selector": "#id"} - Click element
- fill: {"selector": "#input", "value": "text"} - Fill input field
- type: {"selector": "#input", "text": "text", "delay": 100} - Type slowly
- select: {"selector": "#dropdown", "value": "option"} - Select dropdown
- wait: {"timeout": 1000} or {"selector": "#element"} - Wait for time/element
- press_key: {"key": "Enter|Tab|Escape|..."} - Press keyboard key
- hover: {"selector": "#element"} - Hover over element

Rules:
1. For navigation, construct full URL if relative path given and base_url available
2. For clicks, prefer text matching over selectors when possible
3. For waits, be intelligent about timing (page loads: 2-5s, animations: 500-1000ms)
4. Return confidence < 0.5 if step is ambiguous
5. Include reasoning for your interpretation
"""

            user_prompt = f"""Test Step: {step_text}
Expected Result: {expected_result}
Base URL: {base_url}
Previous Actions: {json.dumps(previous_steps[-3:] if len(previous_steps) > 3 else previous_steps, indent=2)}

Convert this test step to a Playwright action."""

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # Fast and cheap for step interpretation
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,  # Low temperature for consistent interpretation
                max_tokens=300,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)

            # Add expected result for validation
            result["expected"] = expected_result
            result["original_step"] = step_text

            logger.info(f"🤖 AI interpreted step: {result.get('action')} (confidence: {result.get('confidence', 0):.2f})")
            logger.debug(f"   Reasoning: {result.get('reasoning', 'N/A')}")

            return result

        except Exception as e:
            logger.error(f"❌ AI interpretation failed: {e}")
            return None

    def interpret_multiple_steps(self, steps: List[Dict], context: Dict = None) -> List[Dict[str, Any]]:
        """
        Interpret multiple test steps with context from previous steps

        Args:
            steps: List of step dicts with 'content' and 'expected' fields
            context: Shared context across all steps

        Returns:
            List of interpreted actions
        """
        if not self.enabled:
            return None

        interpreted_actions = []
        context = context or {}
        context["previous_steps"] = []

        for idx, step in enumerate(steps):
            step_text = step.get("content", "") or step.get("step", "") or str(step)
            expected = step.get("expected", "") or step.get("expected_result", "")

            # Interpret the step
            action = self.interpret_step(step_text, expected, context)

            if action:
                # Store base URL from first navigation
                if action.get("action") == "navigate" and not context.get("base_url"):
                    url = action.get("params", {}).get("url", "")
                    if url.startswith("http"):
                        # Extract protocol://domain
                        import re
                        match = re.match(r'(https?://[^/]+)', url)
                        if match:
                            context["base_url"] = match.group(1)
                            logger.info(f"📍 Base URL set to: {context['base_url']}")

                # Add to context for next steps
                context["previous_steps"].append({
                    "step": idx + 1,
                    "action": action.get("action"),
                    "description": step_text[:50]
                })

                interpreted_actions.append(action)
            else:
                # Fallback to wait action if AI fails
                logger.warning(f"⚠️ AI failed for step {idx+1}, using wait action")
                interpreted_actions.append({
                    "action": "wait",
                    "params": {"timeout": 1000},
                    "expected": expected,
                    "original_step": step_text,
                    "confidence": 0.0,
                    "reasoning": "AI interpretation failed, fallback action"
                })

        return interpreted_actions

    def validate_expected_result(self, expected_result: str, page_content: str, context: Dict = None) -> Dict[str, Any]:
        """
        Use AI to intelligently validate an expected result against page content

        Args:
            expected_result: The expected result text (e.g., "welding type should be `longitudinal welding` in that drop down")
            page_content: Current page content (text/HTML)
            context: Additional context (action performed, step description, etc.)

        Returns:
            Dict with validation result:
            {
                "passed": bool,
                "confidence": 0.0-1.0,
                "message": "explanation",
                "reasoning": "AI's reasoning"
            }
        """
        if not self.enabled:
            # Fallback to simple substring match
            expected_clean = expected_result.strip().lower()
            page_clean = page_content.strip().lower()
            passed = expected_clean in page_clean

            return {
                "passed": passed,
                "confidence": 0.5 if passed else 0.3,
                "message": "Expected result validated successfully" if passed else f"Expected result not found: {expected_result[:100]}",
                "reasoning": "Rule-based validation (simple substring match)"
            }

        try:
            context = context or {}
            action_performed = context.get("action_performed", "")
            step_description = context.get("step_description", "")

            system_prompt = """You are an expert test validation engineer. Your job is to determine if an expected result is present on a web page.

Given:
1. An expected result description (natural language)
2. The current page content (text from the page)
3. Context about what action was just performed

Determine if the expected result is satisfied by the current page state.

Think like a human tester:
- If expected says "field X should show value Y", check if field X exists and shows Y
- If expected says "dropdown should have option Z", check if that option is present
- Be intelligent about variations (e.g., "longitudinal welding" vs "Longitudinal Welding")
- Consider context - if we just filled a field, the value should be there
- Ignore minor formatting differences (spaces, case, punctuation)

Return ONLY a valid JSON object:
{
  "passed": true/false,
  "confidence": 0.0-1.0,
  "message": "Clear explanation of validation result",
  "reasoning": "Your step-by-step reasoning",
  "extracted_value": "What value/text you found (if applicable)"
}

Be strict but reasonable - the page must actually show what's expected."""

            user_prompt = f"""Expected Result: {expected_result}

Page Content:
{page_content[:4000]}  # Limit content to avoid token limits

Context:
- Last Action: {action_performed}
- Step Description: {step_description}

Does the page satisfy this expected result? Analyze carefully and respond."""

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,  # Low temperature for consistent validation
                max_tokens=500
            )

            result_text = response.choices[0].message.content.strip()

            # Parse JSON response
            if result_text.startswith("```json"):
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif result_text.startswith("```"):
                result_text = result_text.split("```")[1].split("```")[0].strip()

            validation_result = json.loads(result_text)

            logger.info(f"✅ AI Validation - Passed: {validation_result.get('passed')}, Confidence: {validation_result.get('confidence'):.2f}")
            logger.debug(f"AI Reasoning: {validation_result.get('reasoning', 'N/A')}")

            return validation_result

        except Exception as e:
            logger.error(f"❌ AI validation failed: {e}")
            # Fallback to simple substring match
            expected_clean = expected_result.strip().lower()
            page_clean = page_content.strip().lower()
            passed = expected_clean in page_clean

            return {
                "passed": passed,
                "confidence": 0.3,
                "message": f"AI validation error, used fallback: {str(e)}",
                "reasoning": "Fallback to substring match due to AI error"
            }
