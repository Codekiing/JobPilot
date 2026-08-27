"""Local JobPilot API facade."""

from .api import JobPilotAPIError, build_filler_request, build_profile_request, build_rank_request, build_resume_request, questionnaire_response

__all__ = ["JobPilotAPIError", "build_filler_request", "build_profile_request", "build_rank_request", "build_resume_request", "questionnaire_response"]
__version__ = "0.1.0"
