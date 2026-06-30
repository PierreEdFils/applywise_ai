# ruff: noqa
import datetime
import json
import re
from typing import AsyncGenerator

from pydantic import BaseModel, Field
from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.agents.context import Context
from google.adk.agents.callback_context import CallbackContext
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.tools import AgentTool
from google.adk.workflow import Workflow, START
from google.genai import types

from app.config import config

# =====================================================================
# 1. Pydantic Schemas for Structured I/O
# =====================================================================

class ApplyWiseInput(BaseModel):
    candidate_profile: str = Field(
        description="The candidate's resume, experience, skills, and background details."
    )
    job_posting: str = Field(
        description="The target job posting description and requirements."
    )

class JobAnalysis(BaseModel):
    job_title: str = Field(description="The official title of the job.")
    company_name: str = Field(description="The name of the company posting the job.")
    responsibilities: list[str] = Field(description="Core duties and responsibilities.")
    required_skills: list[str] = Field(description="Essential technical and soft skills.")
    nice_to_have_skills: list[str] = Field(description="Preferred or secondary skills.")
    cultural_insights: str = Field(description="Insights into the company's culture and values.")

class CandidateFitAnalysis(BaseModel):
    match_score: int = Field(description="Overall match percentage from 0 to 100.")
    matching_skills: list[str] = Field(description="Skills the candidate has that match the job.")
    missing_skills: list[str] = Field(description="Key skills required by the job that the candidate lacks.")
    fit_summary: str = Field(description="A brief summary of why the candidate is or isn't a good fit.")
    tailoring_recommendations: list[str] = Field(description="Actionable advice to tailor the application.")

class ResumeTailorOutput(BaseModel):
    suggested_headline: str = Field(description="A strong, keyword-rich resume headline.")
    professional_summary: str = Field(description="A tailored professional summary paragraph.")
    tailored_bullet_points: list[str] = Field(description="3-5 customized accomplishment bullet points.")

class CoverLetterOutput(BaseModel):
    cover_letter_text: str = Field(description="The drafted cover letter text, tailored to the job.")
    language: str = Field(description="The language used for the cover letter (English or French).")

class InterviewPrepOutput(BaseModel):
    interview_questions: list[str] = Field(description="3-5 custom interview questions tailored to the candidate's gaps.")
    english_elevator_pitch: str = Field(description="A 30-second elevator pitch in English.")
    french_elevator_pitch: str = Field(description="A 30-second elevator pitch in French.")

class FinalApplicationPackage(BaseModel):
    job_title: str
    company_name: str
    match_score: int
    resume_headline: str
    professional_summary: str
    tailored_bullet_points: list[str]
    cover_letter: str
    interview_questions: list[str]
    english_elevator_pitch: str
    french_elevator_pitch: str

# =====================================================================
# 2. MCP Server Configuration & Initialization
# =====================================================================

import os
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

# Resolve absolute path to mcp_server.py
current_dir = os.path.dirname(os.path.abspath(__file__))
mcp_server_path = os.path.join(current_dir, "mcp_server.py")

mcp_tools = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="uv",
            args=["run", "python", mcp_server_path],
        ),
    ),
)

# =====================================================================
# 3. Specialized Sub-Agents
# =====================================================================

job_analyzer = LlmAgent(
    name="job_analyzer",
    model=config.model,
    instruction="""You are an expert Job Analyzer.
Analyze the provided job posting. Extract the job title, company name, key responsibilities, required skills, nice-to-have skills, and cultural insights.
You can use the `fetch_job_posting` tool if the user provides a URL instead of raw text.
Ensure your response strictly adheres to the requested output schema.""",
    tools=[mcp_tools],
    output_schema=JobAnalysis,
    output_key="job_analysis",
    description="Analyzes a job posting to extract key details and requirements."
)

candidate_fit_analyzer = LlmAgent(
    name="candidate_fit_analyzer",
    model=config.model,
    instruction="""You are a Candidate Fit Analyzer.
Compare the candidate's profile with the job analysis.
Calculate a match score (0 to 100), identify matching skills, critical missing skills/gaps, and provide recommendations on how the candidate can bridge those gaps.
Ensure your response strictly adheres to the requested output schema.""",
    output_schema=CandidateFitAnalysis,
    output_key="candidate_fit",
    description="Analyzes the fit between a candidate profile and a job analysis."
)

orchestrator = LlmAgent(
    name="orchestrator",
    model=config.model,
    instruction="""You are the Lead Career Concierge.
Your task is to coordinate the analysis of the job and the candidate's fit.
First, call the job_analyzer tool to analyze the job posting.
Then, call the candidate_fit_analyzer tool to analyze how the candidate's profile fits that job.
Finally, summarize the findings for the user (e.g., job title, company, and overall match).
You must use the tools provided to perform these analyses.""",
    tools=[AgentTool(job_analyzer), AgentTool(candidate_fit_analyzer)],
)

resume_tailorer = LlmAgent(
    name="resume_tailorer",
    model=config.model,
    instruction="""You are a Resume Tailoring Expert.
Using the candidate's profile, job analysis, and fit analysis, generate:
1. A strong, keyword-rich resume headline.
2. A tailored professional summary paragraph.
3. 3-5 customized accomplishment bullet points matching the job's key requirements.
You can search Canadian career resources using the `search_canadian_career_resources` tool to ensure standards are met.
Highlight the candidate's matching strengths and address any gaps professionally.""",
    tools=[mcp_tools],
    output_schema=ResumeTailorOutput,
    output_key="tailored_resume",
)

cover_letter_generator = LlmAgent(
    name="cover_letter_generator",
    model=config.model,
    instruction="""You are a Professional Cover Letter Writer.
Using the candidate's profile, job analysis, and tailored resume details, draft a compelling, professional cover letter.
The cover letter should be written in the primary language of the job posting (English or French).
Tailor it to the company's culture and show how the candidate's background directly solves the company's needs.""",
    output_schema=CoverLetterOutput,
    output_key="cover_letter",
)

interview_coach = LlmAgent(
    name="interview_coach",
    model=config.model,
    instruction="""You are an expert Interview Coach.
Based on the job analysis, candidate's profile, and any user feedback, generate:
1. 3-5 custom interview questions targeting potential gaps or key responsibilities.
2. A bilingual elevator pitch (one in English, one in French) that the candidate can use to introduce themselves.
Ensure the pitches are professional, engaging, and highlight key strengths.""",
    output_schema=InterviewPrepOutput,
    output_key="interview_prep",
)

# =====================================================================
# 4. Workflow Function Nodes
# =====================================================================

def prepare_orchestrator_input(ctx: Context, node_input: ApplyWiseInput) -> str:
    """Formats the input for the orchestrator agent."""
    ctx.state["candidate_profile"] = node_input.candidate_profile
    ctx.state["job_posting"] = node_input.job_posting
    return f"""Please analyze the following job and candidate profile:
    
### Job Posting:
{node_input.job_posting}

### Candidate Profile:
{node_input.candidate_profile}"""

def prepare_resume_tailorer_input(ctx: Context, node_input: str) -> str:
    """Formats the input for the resume tailorer using session state."""
    profile = ctx.state.get("candidate_profile", "")
    job_analysis = ctx.state.get("job_analysis", {})
    candidate_fit = ctx.state.get("candidate_fit", {})
    
    return f"""Please tailor the resume details for this candidate:
    
### Candidate Profile:
{profile}

### Job Analysis:
{json.dumps(job_analysis, indent=2)}

### Fit Analysis:
{json.dumps(candidate_fit, indent=2)}"""

def prepare_cover_letter_input(ctx: Context, node_input: ResumeTailorOutput) -> str:
    """Formats the input for the cover letter generator using session state."""
    profile = ctx.state.get("candidate_profile", "")
    job_analysis = ctx.state.get("job_analysis", {})
    
    return f"""Please draft a tailored cover letter:
    
### Candidate Profile:
{profile}

### Job Analysis:
{json.dumps(job_analysis, indent=2)}

### Tailored Resume Details:
- Suggested Headline: {node_input.suggested_headline}
- Professional Summary: {node_input.professional_summary}"""

async def review_application(ctx: Context, node_input: CoverLetterOutput):
    """Human-in-the-Loop review node."""
    tailored = ctx.state.get("tailored_resume", {})
    summary = tailored.get("professional_summary", "")
    headline = tailored.get("suggested_headline", "")
    bullets = "\n".join([f"- {b}" for b in tailored.get("tailored_bullet_points", [])])
    
    message_text = f"""### 📋 Please Review Your Tailored Application Assets
    
**Suggested Headline:** {headline}

**Professional Summary:**
{summary}

**Tailored Bullet Points:**
{bullets}

**Draft Cover Letter ({node_input.language}):**
{node_input.cover_letter_text}

---
Please approve these assets or provide feedback to refine them."""

    if not ctx.resume_inputs or "user_review" not in ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="user_review",
            message=message_text
        )
        return
    
    feedback = ctx.resume_inputs["user_review"]
    yield Event(
        output=feedback,
        state={"user_feedback": feedback},
        content=f"Feedback received: {feedback}"
    )

def prepare_interview_coach_input(ctx: Context, node_input: str) -> str:
    """Formats the input for the interview coach using session state."""
    profile = ctx.state.get("candidate_profile", "")
    job_analysis = ctx.state.get("job_analysis", {})
    
    return f"""Please generate the interview coaching package:
    
### Candidate Profile:
{profile}

### Job Analysis:
{json.dumps(job_analysis, indent=2)}

### User Feedback on Assets:
{node_input}"""

def generate_final_package(ctx: Context, node_input: InterviewPrepOutput):
    """Compiles all tailored assets into a final structured output and presentation."""
    job_analysis = ctx.state.get("job_analysis", {})
    candidate_fit = ctx.state.get("candidate_fit", {})
    tailored_resume = ctx.state.get("tailored_resume", {})
    cover_letter = ctx.state.get("cover_letter", {})
    
    package = FinalApplicationPackage(
        job_title=job_analysis.get("job_title", "N/A"),
        company_name=job_analysis.get("company_name", "N/A"),
        match_score=candidate_fit.get("match_score", 0),
        resume_headline=tailored_resume.get("suggested_headline", ""),
        professional_summary=tailored_resume.get("professional_summary", ""),
        tailored_bullet_points=tailored_resume.get("tailored_bullet_points", []),
        cover_letter=cover_letter.get("cover_letter_text", ""),
        interview_questions=node_input.interview_questions,
        english_elevator_pitch=node_input.english_elevator_pitch,
        french_elevator_pitch=node_input.french_elevator_pitch,
    )
    
    # Format a beautiful markdown display for the Web UI
    bullets_md = "\n".join([f"- {b}" for b in package.tailored_bullet_points])
    questions_md = "\n".join([f"- {q}" for q in package.interview_questions])
    
    ui_content = f"""# 🚀 ApplyWise AI — Final Application Package
    
## 📊 Match Overview
* **Job Title:** {package.job_title}
* **Company:** {package.company_name}
* **Match Score:** **{package.match_score}%**

---

## 📄 Tailored Resume Assets
### Suggested Headline
> {package.resume_headline}

### Professional Summary
{package.professional_summary}

### Tailored Bullet Points
{bullets_md}

---

## ✉️ Tailored Cover Letter
```markdown
{package.cover_letter}
```

---

## 🧑‍🏫 Interview Coaching
### Target Interview Questions
{questions_md}

### 🇬🇧 English Elevator Pitch
*{package.english_elevator_pitch}*

### 🇫🇷 French Elevator Pitch
*{package.french_elevator_pitch}*
"""

    yield Event(
        content=types.Content(role='model', parts=[types.Part.from_text(text=ui_content)]),
        output=package
    )

# =====================================================================
# 4. Workflow Definition (ADK 2.0 Graph without Security Node)
# =====================================================================

applywise_workflow = Workflow(
    name="applywise_workflow",
    description="Bilingual career application concierge matching candidates to Canadian tech jobs.",
    input_schema=ApplyWiseInput,
    output_schema=FinalApplicationPackage,
    edges=[
        # START routes directly to prepare_orchestrator_input
        (START, prepare_orchestrator_input),
        
        # Orchestrator Analysis (Job + Fit via AgentTools)
        (prepare_orchestrator_input, orchestrator),
        
        # Resume Tailoring
        (orchestrator, prepare_resume_tailorer_input),
        (prepare_resume_tailorer_input, resume_tailorer),
        
        # Cover Letter Generation
        (resume_tailorer, prepare_cover_letter_input),
        (prepare_cover_letter_input, cover_letter_generator),
        
        # Human-in-the-Loop Review
        (cover_letter_generator, review_application),
        
        # Interview Coaching
        (review_application, prepare_interview_coach_input),
        (prepare_interview_coach_input, interview_coach),
        
        # Compile Final Package
        (interview_coach, generate_final_package)
    ]
)

app = App(
    root_agent=applywise_workflow,
    name="app",
)
