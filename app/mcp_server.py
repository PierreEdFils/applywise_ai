import os
import httpx
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("ApplyWise Career Concierge Server")

@mcp.tool()
async def fetch_job_posting(url: str) -> str:
    """Fetches the text content of a job posting from a given URL.
    
    Args:
        url: The URL of the job posting to fetch.
    """
    try:
        async with httpx.AsyncClient() as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code == 200:
                # Returns a snippet or full text of the response (converting HTML to text is simulated here)
                text = response.text
                # Clean up simple HTML tags to make it readable for the LLM
                import re
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
                return text[:4000]  # Limit to first 4000 chars to save tokens
            return f"Failed to fetch job posting. HTTP Status: {response.status_code}"
    except Exception as e:
        return f"Error fetching job posting from URL: {str(e)}"

@mcp.tool()
def search_canadian_career_resources(keyword: str) -> str:
    """Searches Canadian tech career resources, resume standards, and market insights.
    
    Args:
        keyword: The topic to search (e.g., 'resume', 'salary', 'interview', 'bilingual').
    """
    resources = {
        "resume": (
            "Canadian Resume Standards:\n"
            "- Length: Maximum 2 pages for tech professionals.\n"
            "- Personal Info: Do NOT include photo, age, gender, marital status, or SIN (Social Insurance Number) due to anti-discrimination laws.\n"
            "- Format: Reverse chronological, starting with the most recent role.\n"
            "- Style: Action-oriented bullet points using the STAR method (Situation, Task, Action, Result) with quantified achievements."
        ),
        "salary": (
            "Canadian Tech Salary Guidelines (approximate annual CAD):\n"
            "- Junior Software Engineer: $70,000 - $95,000\n"
            "- Intermediate Software Engineer: $95,000 - $130,000\n"
            "- Senior Software Engineer: $130,000 - $180,000+\n"
            "Note: Salaries are typically highest in Toronto, Vancouver, and Montreal, but cost of living is also high."
        ),
        "interview": (
            "Canadian Tech Interview Tips:\n"
            "- Structure: Typically consists of a recruiter screen, a technical assessment (live coding or system design), and a behavioral/cultural fit interview.\n"
            "- Behavioral: Heavy emphasis on 'cultural fit' and collaboration. Use the STAR method to answer behavioral questions.\n"
            "- Follow-up: Send a brief thank-you email to the interviewers within 24 hours."
        ),
        "bilingual": (
            "Bilingualism (English/French) in Canadian Tech:\n"
            "- Private Sector: Primarily English-speaking, especially in major hubs like Toronto and Vancouver. French is highly valued or required in Montreal/Quebec.\n"
            "- Public Sector / Government: Federal government roles and crown corporations often require bilingualism (Bilingual Imperial classification: e.g., BBB or CBC levels).\n"
            "- Remote Work: Bilingualism increases opportunities across Canada, particularly for client-facing or support roles."
        )
    }
    
    keyword_clean = keyword.lower().strip()
    # Simple substring matching
    for key, value in resources.items():
        if key in keyword_clean or keyword_clean in key:
            return value
            
    return (
        f"No specific resource found for '{keyword}'. General Canadian Tech Advice:\n"
        "Ensure your application highlights collaboration, adaptability, and clear communication. "
        "Tailor your resume keywords to match the job description exactly."
    )

@mcp.tool()
def read_local_resume(file_path: str) -> str:
    """Reads the contents of a local resume file (txt or md format).
    
    Args:
        file_path: The absolute path to the local resume file.
    """
    if not os.path.exists(file_path):
        return f"Error: File not found at '{file_path}'."
    
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ['.txt', '.md', '.markdown']:
        return "Error: Only plain text (.txt) and Markdown (.md) resume files are supported."
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading resume file: {str(e)}"

@mcp.tool()
def save_application_package(filename: str, content: str) -> str:
    """Saves the tailored application package (cover letter, resume edits, etc.) to a local file.
    
    Args:
        filename: The name of the file (e.g., 'tailored_application.md').
        content: The markdown content to write to the file.
    """
    # Restrict saving to the current directory or subfolders for security
    clean_filename = os.path.basename(filename)
    try:
        with open(clean_filename, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully saved application package to {os.path.abspath(clean_filename)}"
    except Exception as e:
        return f"Error saving application package: {str(e)}"

if __name__ == "__main__":
    mcp.run()
