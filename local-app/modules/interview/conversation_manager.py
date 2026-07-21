import uuid
import time
import logging
from typing import Dict, Any, Optional, List
from core.database import SessionLocal
from .models_db import InterviewSession, ConversationHistory
from .agents.question_generator import QuestionGenerator
from .agents.central_evaluator import CentralEvaluator
from .agents.report_generator import ReportGenerator
from .agents.context_analyzer import ContextAnalyzer

logger = logging.getLogger(__name__)


class ConversationManager:
    """
    Central state machine managing the interview conversation lifecycle.
    Handles session creation, answer submission, phase transitions,
    adaptive difficulty, and database persistence.
    """

    VALID_INTERVIEW_TYPES = {'HR', 'Tech', 'Situational'}
    VALID_DIFFICULTY_MODES = {'Beginner', 'Intermediate', 'Advanced', 'Adaptive'}
    VALID_DURATION_TYPES = {'questions', 'minutes'}
    DIFFICULTY_LEVELS = ['Beginner', 'Intermediate', 'Advanced']

    def __init__(self):
        self.question_generator = QuestionGenerator()
        self.central_evaluator = CentralEvaluator()
        self.report_generator = ReportGenerator()
        self.context_analyzer = ContextAnalyzer()

    def start_session(
        self,
        interview_type: str,
        difficulty_mode: str,
        duration_type: str,
        duration_value: int,
        session_id: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Creates a new interview session, generates the first question,
        and persists the session to the database.
        """
        # Validate inputs
        if interview_type not in self.VALID_INTERVIEW_TYPES:
            raise ValueError(f"Invalid interview_type: {interview_type}")
        if difficulty_mode not in self.VALID_DIFFICULTY_MODES:
            raise ValueError(f"Invalid difficulty_mode: {difficulty_mode}")
        if duration_type not in self.VALID_DURATION_TYPES:
            raise ValueError(f"Invalid duration_type: {duration_type}")
        if duration_value <= 0:
            raise ValueError(f"duration_value must be positive, got: {duration_value}")

        if not session_id:
            session_id = str(uuid.uuid4())

        # Determine effective difficulty for Adaptive mode
        effective_difficulty = 'Beginner' if difficulty_mode == 'Adaptive' else difficulty_mode

        # Try to load resume/JD context if available
        profile_info = {}
        candidate_profile = {}
        skill_gaps = []
        resume_text = ""
        jd_text = ""
        try:
            profile_info = self.context_analyzer.get_session_profile(session_id)
            candidate_profile = profile_info.get('candidate_profile') or {}
            match_results = profile_info.get('match_results') or {}
            skill_gaps = match_results.get('skill_gap', [])

            role_profile = profile_info.get('role_profile') or {}
            if role_profile:
                req_skills = ", ".join(role_profile.get('required_skills', []))
                domain = role_profile.get('industry_domain', '')
                exp = role_profile.get('required_experience_years', 0)
                jd_text = f"Domain: {domain}. Required Experience: {exp} years. Required Skills: {req_skills}."

            if candidate_profile:
                skills_list = []
                for cat, skills_in_cat in candidate_profile.get('skills', {}).items():
                    for s in skills_in_cat:
                        if isinstance(s, dict):
                            skills_list.append(s.get('name', ''))
                        else:
                            skills_list.append(str(s))
                skills_str = ", ".join(skills_list)
                exp = candidate_profile.get('experience', 0)
                resume_text = f"Experience: {exp} years. Skills: {skills_str}."
        except Exception as e:
            logger.warning(f"Could not load profile context for {session_id}: {e}")

        # Generate first question
        first_question = self.question_generator.generate(
            resume_text=resume_text,
            jd_text=jd_text,
            candidate_profile=candidate_profile,
            skill_gaps=skill_gaps,
            history=[],
            evaluator_feedback=None,
            interview_type=interview_type,
            difficulty=effective_difficulty
        )

        # Persist to database
        db = SessionLocal()
        try:
            # If session_id was explicitly provided, clean up any prior session with that ID
            existing = db.query(InterviewSession).filter(
                InterviewSession.session_id == session_id
            ).first()
            if existing:
                db.delete(existing)
                db.flush()

            session_obj = InterviewSession(
                session_id=session_id,
                interview_type=interview_type,
                difficulty_mode=difficulty_mode,
                duration_type=duration_type,
                duration_value=duration_value,
                phase='Warmup',
                status='active',
                current_index=0,
                current_question=first_question,
                resume_profile=profile_info.get('candidate_profile'),
                jd_profile=profile_info.get('role_profile'),
                match_results=profile_info.get('match_results'),
                candidate_profile=candidate_profile or None,
                user_id=user_id,
            )
            db.add(session_obj)
            db.commit()
            db.refresh(session_obj)

            return {
                'session_id': session_id,
                'interview_type': interview_type,
                'difficulty_mode': difficulty_mode,
                'duration_type': duration_type,
                'duration_value': duration_value,
                'phase': 'Warmup',
                'status': 'active',
                'current_question': first_question,
                'current_index': 0,
                'history': [],
            }
        finally:
            db.close()

    def submit_answer(self, session_id: str, answer: str, current_metrics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Processes a candidate answer: evaluates it, persists history,
        manages phase transitions, and generates the next question.
        """
        db = SessionLocal()
        try:
            session = db.query(InterviewSession).filter(
                InterviewSession.session_id == session_id
            ).first()

            if not session:
                raise LookupError(f"Session not found: {session_id}")

            if session.phase == 'Completed':
                raise ValueError(f"Session {session_id} is already completed.")

            current_question = session.current_question or ''

            # Evaluate the answer
            eval_result = self.central_evaluator.evaluate_answer(
                session_id=session_id,
                question=current_question,
                answer=answer,
                current_metrics=current_metrics or {'posture': 50.0, 'eye_contact': 50.0, 'emotions': ['neutral']}
            )

            score = eval_result.get('evaluation_score', 70.0)
            quality = eval_result.get('quality_tier', 'Medium')
            feedback = eval_result.get('next_question_feedback', '')
            matched_keywords = eval_result.get('matched_keywords', [])

            # Compile comprehensive metrics for storage
            raw_metrics = {
                **(current_metrics or {}),
                "technical_competency": score,
                "communication_quality": eval_result.get("communication_quality", score),
                "behavioral_assessment": eval_result.get("behavioral_assessment", score),
                "learning_potential": eval_result.get("learning_potential", score),
                "cultural_fit": eval_result.get("cultural_fit", score)
            }

            def extract_score(metrics, key, default=70.0):
                if not metrics:
                    return default
                val = metrics.get(key, default)
                if isinstance(val, dict):
                    return val.get("score", default)
                return val

            # Persist ConversationHistory row
            history_entry = ConversationHistory(
                session_id=session_id,
                question=current_question,
                answer=answer,
                evaluation_score=score,
                feedback=feedback,
                quality_tier=quality,
                word_count=len(answer.split()),
                matched_keywords=matched_keywords,
                posture_score=extract_score(current_metrics, 'posture', 70.0),
                eye_contact_score=extract_score(current_metrics, 'eye_contact', 70.0),
                emotions=current_metrics.get('emotions', ['neutral']) if current_metrics else ['neutral'],
                metrics_raw=raw_metrics,
                timestamp=time.time()
            )
            db.add(history_entry)

            # Update session index
            session.current_index += 1
            session.next_question_feedback = feedback

            # Load full history for question generation context
            # Flush to ensure the new entry is queryable
            db.flush()
            history_records = db.query(ConversationHistory).filter(
                ConversationHistory.session_id == session_id
            ).order_by(ConversationHistory.timestamp).all()
            history_dicts = [
                {
                    'question': h.question,
                    'answer': h.answer,
                    'accuracy_score': h.evaluation_score,
                    'words': h.word_count,
                    'quality_tier': h.quality_tier,
                    'technical_competency': h.metrics_raw.get('technical_competency', h.evaluation_score) if (h.metrics_raw and isinstance(h.metrics_raw, dict)) else h.evaluation_score,
                    'communication_quality': h.metrics_raw.get('communication_quality', h.evaluation_score) if (h.metrics_raw and isinstance(h.metrics_raw, dict)) else h.evaluation_score,
                    'behavioral_assessment': h.metrics_raw.get('behavioral_assessment', h.evaluation_score) if (h.metrics_raw and isinstance(h.metrics_raw, dict)) else h.evaluation_score,
                    'learning_potential': h.metrics_raw.get('learning_potential', 70.0) if (h.metrics_raw and isinstance(h.metrics_raw, dict)) else 70.0,
                    'cultural_fit': h.metrics_raw.get('cultural_fit', 70.0) if (h.metrics_raw and isinstance(h.metrics_raw, dict)) else 70.0,
                    'metrics': h.metrics_raw if (h.metrics_raw and isinstance(h.metrics_raw, dict)) else {
                        'posture': h.posture_score if h.posture_score is not None else 70.0,
                        'eye_contact': h.eye_contact_score if h.eye_contact_score is not None else 70.0,
                        'emotions': h.emotions if h.emotions is not None else ['neutral'],
                        'body_language': 70.0,
                        'attire': 70.0,
                        'confidence': 70.0,
                        'facial_expression': 70.0,
                        'voice': 70.0,
                        'engagement': 70.0,
                        'professional_presence': 70.0
                    }
                }
                for h in history_records
            ]

            # Determine effective difficulty (for Adaptive mode)
            effective_difficulty = self._get_effective_difficulty(session, history_dicts)

            # Phase transition logic
            next_question = None
            final_report = None
            resume_text, jd_text = self._get_profile_summaries(session)

            if session.phase == 'Concluding':
                # The candidate answered the concluding question -> Complete
                session.phase = 'Completed'
                session.status = 'completed'
                next_question = None

                # Generate final report
                try:
                    final_report = self._generate_final_report(session_id, session, history_dicts)
                    session.final_report = final_report
                except Exception as e:
                    logger.error(f"Failed to generate final report: {e}")
                    final_report = {'error': str(e)}

            elif session.duration_type == 'questions' and session.current_index >= session.duration_value:
                # Reached question limit -> transition to Concluding
                session.phase = 'Concluding'
                next_question = self.question_generator.generate_concluding(session.interview_type)

            elif session.duration_type == 'minutes':
                # Check elapsed time against duration limit
                elapsed_minutes = (time.time() - session.created_at.timestamp()) / 60.0 if session.created_at else 0
                if elapsed_minutes >= session.duration_value:
                    session.phase = 'Concluding'
                    next_question = self.question_generator.generate_concluding(session.interview_type)
                else:
                    # Normal progression within time limit
                    if session.phase == 'Warmup':
                        session.phase = 'Main'

                    candidate_profile = session.candidate_profile or {}
                    match_results = session.match_results or {}
                    skill_gaps = match_results.get('skill_gap', [])

                    next_question = self.question_generator.generate(
                        resume_text=resume_text,
                        jd_text=jd_text,
                        candidate_profile=candidate_profile,
                        skill_gaps=skill_gaps,
                        history=history_dicts,
                        evaluator_feedback=feedback,
                        interview_type=session.interview_type,
                        difficulty=effective_difficulty
                    )

            else:
                # Normal progression (fallback)
                if session.phase == 'Warmup':
                    session.phase = 'Main'

                # Load profile context
                candidate_profile = session.candidate_profile or {}
                match_results = session.match_results or {}
                skill_gaps = match_results.get('skill_gap', [])

                next_question = self.question_generator.generate(
                    resume_text=resume_text,
                    jd_text=jd_text,
                    candidate_profile=candidate_profile,
                    skill_gaps=skill_gaps,
                    history=history_dicts,
                    evaluator_feedback=feedback,
                    interview_type=session.interview_type,
                    difficulty=effective_difficulty
                )

            session.current_question = next_question
            db.commit()

            return {
                'session_id': session_id,
                'phase': session.phase,
                'status': session.status,
                'current_index': session.current_index,
                'next_question': next_question,
                'evaluation': {
                    'score': score,
                    'quality': quality,
                    'feedback': feedback,
                },
                'next_question_feedback': feedback,
                'final_report': final_report,
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the full session state including history from the database.
        Returns None if session not found.
        """
        db = SessionLocal()
        try:
            session = db.query(InterviewSession).filter(
                InterviewSession.session_id == session_id
            ).first()

            if not session:
                return None

            history_records = db.query(ConversationHistory).filter(
                ConversationHistory.session_id == session_id
            ).order_by(ConversationHistory.timestamp).all()

            history = [
                {
                    'question': h.question,
                    'answer': h.answer,
                    'evaluation_score': h.evaluation_score,
                    'quality_tier': h.quality_tier,
                    'feedback': h.feedback,
                    'word_count': h.word_count,
                    'matched_keywords': h.matched_keywords,
                    'technical_competency': h.metrics_raw.get('technical_competency', h.evaluation_score) if (h.metrics_raw and isinstance(h.metrics_raw, dict)) else h.evaluation_score,
                    'communication_quality': h.metrics_raw.get('communication_quality', h.evaluation_score) if (h.metrics_raw and isinstance(h.metrics_raw, dict)) else h.evaluation_score,
                    'behavioral_assessment': h.metrics_raw.get('behavioral_assessment', h.evaluation_score) if (h.metrics_raw and isinstance(h.metrics_raw, dict)) else h.evaluation_score,
                    'metrics': h.metrics_raw if (h.metrics_raw and isinstance(h.metrics_raw, dict)) else {
                        'posture': h.posture_score if h.posture_score is not None else 70.0,
                        'eye_contact': h.eye_contact_score if h.eye_contact_score is not None else 70.0,
                        'emotions': h.emotions if h.emotions is not None else ['neutral'],
                        'body_language': 70.0,
                        'attire': 70.0,
                        'confidence': 70.0,
                        'facial_expression': 70.0,
                        'voice': 70.0,
                        'engagement': 70.0,
                        'professional_presence': 70.0
                    }
                }
                for h in history_records
            ]

            return {
                'session_id': session.session_id,
                'interview_type': session.interview_type,
                'difficulty_mode': session.difficulty_mode,
                'duration_type': session.duration_type,
                'duration_value': session.duration_value,
                'phase': session.phase,
                'status': session.status,
                'current_index': session.current_index,
                'current_question': session.current_question,
                'next_question_feedback': session.next_question_feedback,
                'history': history,
                'final_report': session.final_report,
            }
        finally:
            db.close()

    def _get_profile_summaries(self, session) -> tuple:
        resume_text = ""
        jd_text = ""
        try:
            role_profile = session.jd_profile or {}
            if role_profile:
                req_skills = ", ".join(role_profile.get('required_skills', []))
                domain = role_profile.get('industry_domain', '')
                exp = role_profile.get('required_experience_years', 0)
                jd_text = f"Domain: {domain}. Required Experience: {exp} years. Required Skills: {req_skills}."
            
            candidate_profile = session.candidate_profile or {}
            if candidate_profile:
                skills_list = []
                for cat, skills_in_cat in candidate_profile.get('skills', {}).items():
                    for s in skills_in_cat:
                        if isinstance(s, dict):
                            skills_list.append(s.get('name', ''))
                        else:
                            skills_list.append(str(s))
                skills_str = ", ".join(skills_list)
                exp = candidate_profile.get('experience', 0)
                resume_text = f"Experience: {exp} years. Skills: {skills_str}."
        except Exception as e:
            logger.warning(f"Error building profile summaries: {e}")
        return resume_text, jd_text

    def _get_effective_difficulty(self, session, history_dicts: List[Dict]) -> str:
        """
        For Adaptive mode, compute difficulty based on running average score.
        For fixed modes, return the configured difficulty.
        """
        if session.difficulty_mode != 'Adaptive':
            return session.difficulty_mode

        if not history_dicts:
            return 'Beginner'

        scores = [h.get('accuracy_score', 70.0) for h in history_dicts if h.get('accuracy_score') is not None]
        if not scores:
            return 'Beginner'

        avg_score = sum(scores) / len(scores)

        if avg_score >= 80.0:
            return 'Advanced'
        elif avg_score >= 55.0:
            return 'Intermediate'
        else:
            return 'Beginner'

    def _generate_final_report(
        self,
        session_id: str,
        session,
        history_dicts: List[Dict],
    ) -> Dict[str, Any]:
        """
        Generates the final recruiter report from DB history.
        """
        candidate_profile = session.candidate_profile or {}
        match_results = session.match_results or {}
        
        return self.report_generator.generate_report(
            session_id=session_id,
            cand_profile=candidate_profile,
            match_results=match_results,
            db_history=history_dicts
        )
