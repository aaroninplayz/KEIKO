import re
import random
import logging
from typing import Dict, Any, List, Optional
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

QUESTION_TEMPLATES = {
    'HR': {
        'Beginner': [
            'Tell me about yourself and what motivates you in your career.',
            'What are your greatest strengths as a team member?',
            'Why are you interested in this role?',
            'Describe your ideal work environment.',
            'What are your career goals for the next 2-3 years?',
            'How do you handle constructive criticism?',
        ],
        'Intermediate': [
            'Can you describe a conflict with a coworker and how you resolved it?',
            'Tell me about a time when you had to give difficult feedback to a colleague.',
            'How do you handle competing priorities under tight deadlines?',
            'Describe a situation where you had to adapt to a major organizational change.',
            'What strategies do you use to maintain work-life balance while delivering results?',
            'How do you approach building relationships across different teams?',
        ],
        'Advanced': [
            'Describe how you have influenced company culture or team dynamics in a leadership role.',
            'Tell me about a strategic decision you made that had significant business impact.',
            'How do you approach talent development and mentoring within your team?',
            'Describe a time you navigated organizational politics to achieve a critical objective.',
            'How do you balance short-term deliverables with long-term vision?',
            'Tell me about a time you had to champion a significant change initiative.',
        ],
    },
    'Tech': {
        'Beginner': [
            'What programming languages are you most comfortable with and why?',
            'Can you explain the difference between a list and a dictionary in Python?',
            'How do you approach debugging a simple bug in your code?',
            'What is version control, and how have you used Git in your projects?',
            'Describe a small project you built and the technologies you chose.',
            'What do you understand about APIs and how they work?',
        ],
        'Intermediate': [
            'Walk me through how you would design a REST API for a user management system.',
            'Explain how you handle database migrations in a production environment.',
            'How do you ensure code quality through testing strategies?',
            'Describe your approach to optimizing a slow database query.',
            'How do you handle authentication and authorization in web applications?',
            'Explain the trade-offs between SQL and NoSQL databases for different use cases.',
        ],
        'Advanced': [
            'How would you architect a distributed system that handles millions of concurrent requests?',
            'Explain your approach to designing a fault-tolerant microservices architecture.',
            'How do you handle consistency vs availability tradeoffs in distributed databases?',
            'Describe your strategy for zero-downtime deployments in a large-scale production system.',
            'How would you design a real-time event processing pipeline?',
            'Explain how you would implement observability and monitoring across a complex system.',
        ],
    },
    'Situational': {
        'Beginner': [
            'Tell me about a time you had to learn something new quickly for a project.',
            'Describe a situation where you made a mistake at work and how you handled it.',
            'Can you share an experience where you received constructive criticism?',
            'Tell me about a time you worked with someone whose style was different from yours.',
            'Describe a situation where you had to ask for help.',
            'Tell me about a time when you went above and beyond your responsibilities.',
        ],
        'Intermediate': [
            'Describe a time you led a project through unexpected challenges.',
            'Tell me about a situation where you had to make a critical decision with incomplete information.',
            'How did you handle a scenario where a key dependency or team member was unavailable?',
            'Describe a time when you identified and resolved a systemic issue in your workflow.',
            'Tell me about a project where requirements changed midway through development.',
            'Describe a time you had to convince a skeptical stakeholder to support your approach.',
        ],
        'Advanced': [
            'Describe a situation where you had to rescue a failing project and turn it around.',
            'Tell me about a time you had to make an unpopular decision for the greater good of the team.',
            'How did you handle a critical production incident that affected thousands of users?',
            'Describe how you managed stakeholder expectations during a high-risk delivery.',
            'Tell me about a time you had to balance technical debt with business deadlines.',
            'Describe a complex cross-team negotiation you led to achieve a shared goal.',
        ],
    },
}

CONCLUDING_TEMPLATES = [
    'Thank you for your detailed responses today. Before we wrap up, do you have any questions about the role or our team?',
    'I appreciate you sharing your experience with us. Is there anything else you would like to highlight or ask about this position?',
    'We are coming to the end of our conversation. Do you have any final questions for me about the role, the team, or the company?',
]

SIGNOFF_TEMPLATES = [
    'Thank you for your time today. We will review your responses and our team will be in touch regarding the next steps. We appreciate your interest and wish you all the best.',
    'It was a pleasure speaking with you. We will be evaluating all candidates and will reach out soon with an update. Thank you again for your interest.',
]

class QuestionGenerator:
    """
    Hybrid LLM/NLP Question Generator. Ingests full resume text, job description text,
    normalized Candidate Profile, skill gaps, interview history, and evaluator guidelines.
    Uses a small local instruct model if available, falling back to a deterministic NLP template engine.
    """

    def __init__(self):
        self._llm_client = LLMClient()
        self._generator = None
        self._load_local_llm()

    def _load_local_llm(self):
        try:
            from transformers import pipeline
            # Use Qwen2.5-0.5B-Instruct: tiny, lightweight instruct model (~950MB) running cleanly on CPU
            logger.info("Attempting to load local instruction LLM 'Qwen/Qwen2.5-0.5B-Instruct'...")
            self._generator = pipeline(
                "text-generation", 
                model="Qwen/Qwen2.5-0.5B-Instruct", 
                device=-1, # Force CPU execution
                max_new_tokens=100
            )
            logger.info("Local instruction LLM successfully loaded.")
        except Exception as e:
            logger.warning(f"Could not load local LLM, falling back to robust NLP template generator: {e}")
            self._generator = None

    def generate(
        self,
        resume_text: str,
        jd_text: str,
        candidate_profile: Dict[str, Any],
        skill_gaps: List[str],
        history: List[Dict[str, str]],
        evaluator_feedback: Optional[str] = None,
        interview_type: str = 'Tech',
        difficulty: str = 'Intermediate'
    ) -> str:
        """
        Generates the next question based on context and evaluator feedback.
        """
        # Tier 1: Try External LLM API
        active_provider = self._llm_client.detect_provider()
        if active_provider:
            try:
                logger.info(f"Generating question via external LLM client ({active_provider})...")
                system_message = (
                    "You are Keiko, a professional technical interviewer. Your goal is to ask the candidate a single, clear, "
                    "direct interview question based on their resume, job description, and previous evaluation feedback.\n"
                    f"Interview Type: {interview_type}\n"
                    f"Difficulty Level: {difficulty}\n"
                    "Follow these rules:\n"
                    "1. Ask ONLY one question.\n"
                    "2. Do not write introductory chatter, explanations, or salutations.\n"
                    "3. If evaluator feedback tells you to probe, ask a probing question about the target topic.\n"
                    "4. Keep the question under 30 words."
                )
                
                history_str = ""
                for h in history:
                    history_str += f"Interviewer: {h.get('question')}\nCandidate: {h.get('answer')}\n"

                user_message = (
                    f"Candidate Experience Level: {candidate_profile.get('career_level')}\n"
                    f"Job Description: {jd_text[:300]}\n"
                    f"Skill Gaps Identified: {', '.join(skill_gaps)}\n"
                    f"Interview History:\n{history_str}\n"
                    f"Evaluator Guidance: {evaluator_feedback or 'First question, ask a main job description question.'}\n\n"
                    "Generate the next question:"
                )

                messages = [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ]
                
                question = self._llm_client.complete(messages, provider=active_provider, temperature=0.7)
                if question:
                    question = re.sub(r'[\r\n]+', ' ', question).strip()
                    question = question.replace("<|im_end|>", "").replace("<|endoftext|>", "").strip()
                    if len(question) > 10:
                        return question
            except Exception as e:
                logger.error(f"External API question generation failed: {e}. Falling back to local/heuristics.")

        # Tier 2: If local LLM pipeline is loaded, generate using a custom prompt
        if self._generator:
            try:
                prompt = self._build_prompt(resume_text, jd_text, candidate_profile, skill_gaps, history, evaluator_feedback, interview_type, difficulty)
                result = self._generator(prompt, num_return_sequences=1)
                text = result[0]['generated_text']
                # Extract generated assistant response
                question = text.split("Assistant:")[-1].split("assistant\n")[-1].strip()
                # Clean up any trailing text
                question = re.sub(r'[\r\n]+', ' ', question)
                # Strip system tags
                question = question.replace("<|im_end|>", "").replace("<|endoftext|>", "").strip()
                if question and len(question) > 20:
                    return question
            except Exception as e:
                logger.error(f"Error generating question via LLM: {e}")

        # Tier 3: Fallback to high-fidelity NLP Template Generator
        return self._generate_nlp_fallback(candidate_profile, skill_gaps, history, evaluator_feedback, interview_type, difficulty)

    def _build_prompt(
        self,
        resume_text: str,
        jd_text: str,
        profile: Dict[str, Any],
        gaps: List[str],
        history: List[Dict[str, str]],
        feedback: Optional[str],
        interview_type: str = 'Tech',
        difficulty: str = 'Intermediate'
    ) -> str:
        history_str = ""
        for h in history:
            history_str += f"Interviewer: {h.get('question')}\nCandidate: {h.get('answer')}\n"

        prompt = (
            "<|im_start|>system\n"
            "You are Keiko, a professional technical interviewer. Your goal is to ask the candidate a single, clear, "
            "direct interview question based on their resume, job description, and previous evaluation feedback.\n"
            f"Interview Type: {interview_type}\n"
            f"Difficulty Level: {difficulty}\n"
            "Follow these rules:\n"
            "1. Ask ONLY one question.\n"
            "2. Do not write introductory chatter, explanations, or salutations.\n"
            "3. If evaluator feedback tells you to probe, ask a probing question about the target topic.\n"
            "4. Keep the question under 30 words.\n"
            "<|im_end|>\n"
            "<|im_start|>user\n"
            f"Candidate Experience Level: {profile.get('career_level')}\n"
            f"Job Description: {jd_text[:300]}\n"
            f"Skill Gaps Identified: {', '.join(gaps)}\n"
            f"Interview History:\n{history_str}\n"
            f"Evaluator Guidance: {feedback or 'First question, ask a main job description question.'}\n\n"
            "Generate the next question:\n"
            "<|im_end|>\n"
            "<|im_start|>assistant\n"
        )
        return prompt

    def _generate_nlp_fallback(
        self,
        profile: Dict[str, Any],
        gaps: List[str],
        history: List[Dict[str, str]],
        feedback: Optional[str],
        interview_type: str = 'Tech',
        difficulty: str = 'Intermediate'
    ) -> str:
        """
        High-fidelity template engine. Synthesizes contextual probing and main questions.
        Uses interview type and difficulty to select from comprehensive template banks.
        """
        # Determine current stage of the interview
        q_count = len(history)

        # 1. Handle Evaluator Feedback (Probing / Adjustments)
        if feedback:
            lower_fb = feedback.lower()
            # If evaluator instructs to probe a specific topic or skill
            for gap in gaps:
                if gap.lower() in lower_fb:
                    return f"I noticed a gap in {gap} on your resume. Could you describe your familiarity with {gap} or any experience learning similar technologies?"

            # If evaluator wants details on projects
            if "project" in lower_fb and profile.get("project_expertise"):
                proj = profile["project_expertise"][0]
                return f"You worked on the project: '{proj}'. Could you detail your specific engineering contributions and the technical stack you used?"

            # When probing is requested AND skill gaps exist, target the gaps first
            if "probe" in lower_fb and gaps:
                # Check which gaps have already been asked about
                asked_topics = set()
                for h in history:
                    q_lower = h.get('question', '').lower()
                    for gap in gaps:
                        if gap.lower() in q_lower:
                            asked_topics.add(gap)
                unasked_gaps = [g for g in gaps if g not in asked_topics]
                if unasked_gaps:
                    target_gap = unasked_gaps[0]
                    return f"Looking at the job requirements, I see {target_gap} is a key component. Can you walk me through your experience with {target_gap} or related tools?"

            # General probing fallback based on feedback (no gaps to target)
            if "probe" in lower_fb:
                cand_skills = []
                for cat, skills in profile.get("skills", {}).items():
                    for s in skills:
                        cand_skills.append(s["name"])
                if cand_skills:
                    return f"Can you explain a challenging problem you solved using {cand_skills[0]} and how you optimized your solution?"

        # 2. Skill Gap Targeting: If gaps exist and haven't been addressed yet, ask about them
        if gaps and q_count > 0:
            asked_topics = set()
            for h in history:
                q_lower = h.get('question', '').lower()
                for gap in gaps:
                    if gap.lower() in q_lower:
                        asked_topics.add(gap)
            unasked_gaps = [g for g in gaps if g not in asked_topics]
            if unasked_gaps:
                target_gap = unasked_gaps[0]
                return f"Looking at the job requirements, I see {target_gap} is a key component. Can you walk me through your experience with {target_gap} or related tools?"

        # 3. Template-based question selection using interview type and difficulty
        templates = QUESTION_TEMPLATES.get(interview_type, QUESTION_TEMPLATES['Tech'])
        questions = templates.get(difficulty, templates['Intermediate'])
        # Cycle through the template bank based on question index
        index = q_count % len(questions)
        return questions[index]

    def generate_concluding(self, interview_type: str = 'Tech') -> str:
        """Returns a random concluding question to wrap up the interview."""
        return random.choice(CONCLUDING_TEMPLATES)

    def generate_signoff(self) -> str:
        """Returns a random sign-off message to end the interview."""
        return random.choice(SIGNOFF_TEMPLATES)
