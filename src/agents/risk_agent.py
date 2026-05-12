import os
from pathlib import Path
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process

try:
    from .db_tool import query_db  # package/module execution
except ImportError:
    from db_tool import query_db  # direct script execution

# Always resolve .env from project root, independent of current working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

# CrewAI expects either a model string or its own BaseLLM-compatible config.
llm_model = "gemini/gemini-2.5-flash"

# 1. Agent configuration
analyst = Agent(
    role='Senior Financial Risk Analyst',
    goal='Find the most volatile stock and summarize it briefly.',
    backstory="""You are a senior financial risk analyst with 20 years of experience. You analyze volatility 
    and help investors avoid losses. You only work with facts from the database. Keep the answer concise.""",
    tools=[query_db], # Give him access to your DuckDB
    llm=llm_model,
    allow_delegation=False
)

# 2. Task description
task = Task(
    description="""Analyze the 'stocks' table and identify the most volatile ticker using closing-price range or return volatility. Use SQL facts only. Return a short, decision-ready summary.""",
    expected_output="No more than 5 bullets. Include the most volatile ticker, the key metric used, and 1 short conclusion. Avoid long prose.",
    agent=analyst
)

def run_risk_analysis() -> str:
    """Run the CrewAI risk analysis workflow and return the final report."""
    crew = Crew(
        agents=[analyst],
        tasks=[task],
        process=Process.sequential
    )
    result = crew.kickoff()
    return str(result)


# 3. Launch the crew
if __name__ == "__main__":
    result = run_risk_analysis()
    print("######################")
    print(result)