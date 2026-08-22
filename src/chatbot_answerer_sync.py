#!/usr/bin/env python3
"""
Chatbot Answerer for Naukri Job Application
Uses skill inventory from resume to intelligently answer chatbot questions.
Handles text inputs, radio buttons, and Continue button logic.
"""
import re
import time
from typing import Optional, Dict, List, Any
from playwright.sync_api import Page, ElementHandle

from src.llm_extractor import LLMSkillExtractor


# Try to import rapidfuzz
try:
    from rapidfuzz import fuzz, process
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False


class ChatbotAnswerer:
    def __init__(
        self,
        skill_inventory: Dict[str, str],
        profile_qa: Dict[str, str],
        profile: Dict[str, Any],
        api_key: Optional[str] = None,
        ui: Optional[Any] = None
    ):
        self.skill_inventory = {k.lower(): v for k, v in skill_inventory.items()}
        self.profile_qa = profile_qa
        self.profile = profile
        self.llm_extractor = LLMSkillExtractor(api_key=api_key)
        self.ui = ui

        # Default years for known skills
        self.default_years = "3 years"

        # Also include optimized skills from profile
        opt_skills = profile.get("optimized_skills", [])
        if isinstance(opt_skills, list):
            self.optimized_skills = {k.lower(): "3 years" for k in opt_skills}
        else:
            self.optimized_skills = {k.lower(): v for k, v in opt_skills.items()}

        # Common question patterns and their answers
        self.common_patterns = {
            "notice period": lambda: f"{profile.get('notice_period_months', 3)} months",
            "current ctc": lambda: f"{profile.get('current_ctc_lpa', 12)} LPA",
            "expected ctc": lambda: f"{profile.get('expected_ctc_lpa', 12)} LPA",
            "current salary": lambda: f"{profile.get('current_ctc_lpa', 12)} LPA",
            "expected salary": lambda: f"{profile.get('expected_ctc_lpa', 12)} LPA",
            "total experience": lambda: self.default_years,
            "years of experience": lambda: self.default_years,
            "current company": lambda: profile.get("current_company", ""),
            "current employer": lambda: profile.get("current_company", ""),
        }

    def _debug(self, msg: str) -> None:
        """Print debug message only when UI is not active (console mode)."""
        if self.ui is None:
            print(msg)

    def answer_question(
        self,
        question: str,
        chatbot_container: ElementHandle,
        page: Page,
        interactive: bool = True
    ) -> bool:
        """
        Main entry point to answer a chatbot question.
        Returns True if answered successfully.
        """
        self._debug(f"  [Chatbot] Question: {question[:100]}")
        # 1. Check profile Q&A first (exact match)
        if self._try_profile_qa(question, chatbot_container):
            return True

        # 2. DETECT YES/NO QUESTIONS - Check for Yes/No radio buttons FIRST
        # This avoids misclassifying text input questions that contain "yes"/"no" in text
        radios = chatbot_container.query_selector_all("input[type='radio']")
        is_yes_no = False
        yes_no_radios = []
        for radio in radios:
            if radio.is_visible():
                label = self._get_radio_label(radio, chatbot_container)
                if label and label.lower() in ['yes', 'no']:
                    yes_no_radios.append(radio)

        # Only classify as Yes/No question if we found actual Yes/No radio buttons
        # AND the question text suggests a Yes/No answer is expected
        q_lower = question.lower().strip()
        has_yes_no_keywords = any(kw in q_lower for kw in ['yes', 'no', 'true', 'false'])
        # Check if question is asking for a yes/no answer (not a text input)
        is_text_input_question = any(kw in q_lower for kw in [
            'write', 'enter', 'type', 'mention', 'specify', 'provide', 'fill', 'na', 'n/a',
            'how many', 'how much', 'what is', 'what are', 'which', 'when', 'where', 'who',
            'years', 'year', 'month', 'months', 'salary', 'ctc', 'salary', 'compensation',
            'experience', 'years', 'rate', 'score', 'percentage', 'percent', 'count', 'number'
        ])

        is_yes_no = len(yes_no_radios) > 0 and not is_text_input_question

        self._debug(f"  [Chatbot] Debug: yes_no_radios={len(yes_no_radios)}, is_text_input={is_text_input_question}, is_yes_no={is_yes_no}, q_lower={q_lower[:100]}")
        if is_yes_no:
            q_lower = question.lower().strip()
            # Determine answer based on question context
            if "counter offer" in q_lower:
                answer = "No"
            elif "relocate" in q_lower or "willing to relocate" in q_lower or "residing" in q_lower:
                answer = "Yes"
            elif "join within" in q_lower or "notice" in q_lower:
                answer = "No"  # Can't join within 30 days if 3 months notice
            elif "manual testing" in q_lower or "automation testing" in q_lower:
                answer = "No"  # Don't have manual testing experience
            else:
                answer = "No"  # Default to No

            self._debug(f"  [Chatbot] Yes/No question detected, answering: {answer}")
            return self._fill_answer(chatbot_container, answer, question, page)

        # 2b. HANDLE TEXT INPUT QUESTIONS
        # Questions asking to "write NA", "write NA if not", "enter NA", etc.
        q_lower = question.lower().strip()
        is_text_input_question = any(kw in q_lower for kw in [
            'write na', 'write n/a', 'enter na', 'enter n/a', 'type na', 'type n/a',
            'mention na', 'mention n/a', 'specify na', 'specify n/a',
            'provide na', 'provide n/a', 'fill na', 'fill n/a',
            'write "na"', 'write "n/a"', 'enter "na"', 'enter "n/a"'
        ]) or ('write' in q_lower and ('na' in q_lower or 'n/a' in q_lower))

        if is_text_input_question:
            # Default answer for "write NA" type questions is "NA"
            # Try different formats that might be accepted
            if "n/a" in q_lower or "n / a" in q_lower:
                answer = "N/A"
            else:
                answer = "NA"

            # Track answer attempts for this question
            question_key = self._clean_question_text(question)
            if not hasattr(self, '_text_answer_attempts'):
                self._text_answer_attempts = {}
            attempt = self._text_answer_attempts.get(question_key, 0) + 1
            self._text_answer_attempts[question_key] = attempt

            # Try different answer formats on subsequent attempts
            if attempt == 1:
                answer = "NA"
            elif attempt == 2:
                answer = "N/A"
            elif attempt == 3:
                answer = "Not Applicable"
            else:
                answer = "NA"

            self._debug(f"  [Chatbot] Text input question detected (write NA), attempt {attempt}, answering: {answer}")
            return self._fill_answer(chatbot_container, answer, question, page)

        # 3. Extract skill from question and lookup in inventory
        skill = self._extract_skill_from_question(question)
        if skill:
            if self._try_skill_answer(skill, question, chatbot_container):
                return True
            # Unknown skill -> answer "0 years"
            if self._fill_answer(chatbot_container, "0 years", question, page):
                self._debug(f"  [Chatbot] Unknown skill '{skill}', answered '0 years'")
                return True

        # 4. Try common patterns
        if self._try_common_patterns(question, chatbot_container):
            return True

        # 5. Interactive mode - wait for user to answer
        if interactive:
            return self._interactive_answer(question, chatbot_container, page)

        # 6. Could not answer
        self._debug(f"  [Chatbot] Could not answer: {question[:80]}")
        return False

    def _interactive_answer(self, question: str, chatbot_container: ElementHandle, page: Page) -> bool:
        """Pause and wait for user to manually answer the question."""
        print(f"\n  ═════════════")
        print(f"  ╸  MANUAL ANSWER REQUIRED")
        self._debug(f"  Question: {question}")
        print(f"  You have 8 seconds to type your answer in the browser...")
        # Wait for user to type answer (8 seconds)
        for i in range(8, 0, -1):
            print(f"  Waiting for your input... {i}s", end="\r")
            time.sleep(1)
        print()
        print()

        # Try to find the answer that was entered
        answer = self._get_entered_answer(chatbot_container, page)
        if answer:
            # Save to profile Q&A for future use
            self._save_answer_to_profile(question, answer)
            print(f"  [Chatbot] Saved answer: '{answer}' for future use")
            return True

        return False

    def _get_entered_answer(self, chatbot_container: ElementHandle, page: Page) -> Optional[str]:
        """Try to extract the answer that was manually entered."""
        try:
            # Try text input
            text_input = chatbot_container.query_selector("input[type='text'], textarea, input:not([type])")
            if text_input and text_input.is_visible():
                value = text_input.input_value()
                if value and value.strip():
                    return value.strip()

            # Try radio buttons
            radios = chatbot_container.query_selector_all("input[type='radio']")
            for radio in radios:
                if radio.is_visible() and radio.is_checked():
                    label = self._get_radio_label(radio, chatbot_container)
                    if label:
                        return label

            # Try dropdown
            select = chatbot_container.query_selector("select")
            if select and select.is_visible():
                value = select.input_value()
                if value:
                    return value

        except Exception as e:
            self._debug(f"  [Chatbot] Error getting entered answer: {e}")
        return None

    def _save_answer_to_profile(self, question: str, answer: str) -> None:
        """Save the answer to user_profile.yaml for future use."""
        clean_q = self._clean_question_text(question)

        # Check if already exists
        for item in self.profile.get("questions", []):
            if isinstance(item, dict) and self._clean_question_text(item.get("question", "")) == clean_q:
                item["answer"] = answer
                self._debug(f"  [Chatbot] Updated existing question answer")
                break
        else:
            # Add new question
            if "questions" not in self.profile:
                self.profile["questions"] = []
            self.profile["questions"].append({
                "question": question,
                "answer": answer
            })
            self._debug(f"  [Chatbot] Added new question to profile")
        # Write to file
        try:
            import yaml
            with open("user_profile.yaml", "w") as f:
                yaml.dump(self.profile, f, default_flow_style=False)
        except Exception as e:
            self._debug(f"  [Chatbot] Error saving to profile: {e}")

    def _try_profile_qa(self, question: str, chatbot_container: ElementHandle) -> bool:
        """Check if question matches stored profile Q&A."""
        q_lower = question.lower().strip()

        for stored_q, answer in self.profile_qa.items():
            stored_clean = stored_q.lower().strip()
            # Check if stored question is contained in current question
            if stored_clean in q_lower or q_lower in stored_clean:
                # Use fuzzy matching for better coverage
                if RAPIDFUZZ_AVAILABLE:
                    if fuzz.ratio(stored_clean, q_lower) > 80:
                        return self._fill_answer(chatbot_container, answer)

        return False

    def _extract_skill_from_question(self, question: str) -> Optional[str]:
        """Extract skill/technology from question using LLM or fallback."""
        return self.llm_extractor.extract_skill_from_question(question)

    def _try_skill_answer(
        self,
        skill: str,
        question: str,
        chatbot_container: ElementHandle
    ) -> bool:
        """Try to answer using skill inventory.

        Simple logic:
        - If skill found in skill_inventory/user_profile -> answer "3 years"
        - If skill NOT found -> answer "0 years"
        """
        skill_lower = skill.lower()

        # Check if skill exists in our inventory (exact or fuzzy match)
        skill_found = self._is_skill_known(skill_lower)

        if skill_found:
            answer = self.default_years  # "3 years"
            self._debug(f"  [Chatbot] Known skill '{skill}', answering '{answer}'")
        else:
            answer = "0 years"
            print(f"  [Chatbot] Unknown skill '{skill}', answering '{answer}'")
        return self._fill_answer(chatbot_container, answer, question, page)

    def _is_skill_known(self, skill_lower: str) -> bool:
        """Check if skill exists in our inventory (exact or fuzzy match)."""
        # Direct match
        if skill_lower in self.skill_inventory:
            return True

        # Also check optimized_skills from profile
        if skill_lower in self.optimized_skills:
            return True

        # Fuzzy match against known skills
        if RAPIDFUZZ_AVAILABLE:
            match = process.extractOne(skill_lower, self.skill_inventory.keys(), score_cutoff=85)
            if match:
                return True
            # Also check optimized_skills
            match = process.extractOne(skill_lower, self.optimized_skills.keys(), score_cutoff=85)
            if match:
                return True

        # Check aliases
        skill_aliases = {
            "azure cloud": "azure",
            "aws cloud": "aws",
            "google cloud": "gcp",
            "gcp": "google cloud",
            "k8s": "kubernetes",
            "ci cd": "ci/cd",
            "cicd": "ci/cd",
            "infra as code": "infrastructure as code",
            "iac": "infrastructure as code",
        }

        for alias, canonical in skill_aliases.items():
            if alias in skill_lower and canonical in self.skill_inventory:
                return True
            if alias in skill_lower and canonical in self.optimized_skills:
                return True

        return False

    def _try_common_patterns(self, question: str, chatbot_container: ElementHandle) -> bool:
        """Try to match common question patterns."""
        q_lower = question.lower().strip()
        for pattern, answer_func in self.common_patterns.items():
            if pattern in q_lower:
                answer = answer_func()
                self._debug(f"  [Chatbot] Common pattern '{pattern}', answering: {answer}")
                return self._fill_answer(chatbot_container, answer, question, None)
        return False

    def _fill_answer(self, chatbot_container: ElementHandle, answer: str, question: str, page: Page = None) -> bool:
        """Fill the answer in the chatbot form."""
        try:
            # Try text input first
            text_input = chatbot_container.query_selector("input[type='text'], textarea, input:not([type])")
            if text_input and text_input.is_visible():
                text_input.fill(answer)
                self._debug(f"  [Chatbot] Filled text input: {answer}")
                return True

            # Try radio buttons
            radios = chatbot_container.query_selector_all("input[type='radio']")
            for radio in radios:
                if radio.is_visible():
                    label = self._get_radio_label(radio, chatbot_container)
                    if label and label.lower() == answer.lower():
                        radio.click()
                        self._debug(f"  [Chatbot] Selected radio: {label}")
                        return True

            # Try dropdown
            select = chatbot_container.query_selector("select")
            if select and select.is_visible():
                # Try to select by visible text
                options = select.query_selector_all("option")
                for option in options:
                    if option.inner_text().strip().lower() == answer.lower():
                        select.select_option(value=option.get_attribute("value"))
                        self._debug(f"  [Chatbot] Selected dropdown: {answer}")
                        return True

        except Exception as e:
            self._debug(f"  [Chatbot] Error filling answer: {e}")
        return False

    def _get_radio_label(self, radio: ElementHandle, container: ElementHandle) -> Optional[str]:
        """Get the label text for a radio button."""
        try:
            # Try to find associated label
            radio_id = radio.get_attribute("id")
            if radio_id:
                label = container.query_selector(f"label[for='{radio_id}']")
                if label:
                    return label.inner_text().strip()

            # Try parent label
            parent = radio.evaluate_handle("el => el.closest('label')")
            if parent:
                return parent.inner_text().strip()

            # Try nearby text
            return radio.evaluate("el => el.nextElementSibling?.textContent || el.parentElement?.textContent || ''").strip()
        except Exception:
            pass
        return None

    def _clean_question_text(self, question: str) -> str:
        """Clean question text for comparison."""
        return re.sub(r'[^\w\s]', '', question.lower()).strip()


def create_chatbot_answerer(
    skill_inventory: Dict[str, str],
    profile_qa: Dict[str, str],
    profile: Dict[str, Any],
    api_key: Optional[str] = None,
    ui: Optional[Any] = None
) -> ChatbotAnswerer:
    """Factory function to create ChatbotAnswerer."""
    return ChatbotAnswerer(skill_inventory, profile_qa, profile, api_key, ui)