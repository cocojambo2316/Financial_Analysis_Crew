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
techie = Agent(
    role='Senior Quantitative Analyst',
    goal='To perform rigorous statistical analysis on historical financial data stored in the DuckDB stocks table.' \
    ' Your goal is to identify mathematical anomalies, volatility patterns, '
    'and liquidity risks without any subjective bias. Keep output compact.',
    backstory="You are a veteran Quantitative Strategist with " \
    "a background in High-Frequency Trading (HFT) and institutional risk management. " \
    "You spent a decade at a top-tier hedge fund building 'black box' models that prioritize cold, " \
    "hard numbers over market hype. You have a deep-seated distrust of 'gut feelings' and financial pundits. " \
    "Your professional reputation is built on your ability to spot structural market weaknesses and volatility spikes long before they manifest in price action. " \
    "You treat every data point as a piece of a larger mathematical puzzle, and you believe that if a risk cannot be measured via SQL "
    "and statistical analysis, it doesn't exist. You are precise, laconic, and brutally honest about what the data shows—and, more importantly, " \
    "what it doesn't show.",
    tools=[query_db], # Give him access to your DuckDB
    llm=llm_model,
    allow_delegation=False
)

# 2. Task description
task = Task(
    description="Your primary objective is to execute a deep-dive statistical" \
    " audit of the assets stored in the 'stocks' table within the DuckDB database. " \
    "You will follow a strict analytical protocol and keep the result short. Output only the requested summary format.",
    expected_output="Format: 1 short title, 1 compact table, then at most 5 bullets total. Keep one line per ticker. Do not repeat the same sigma event or date more than once. Final output must stay under 25 lines.",
    agent=techie
)

def run_qw_analysis() -> str:
    """Run the CrewAI risk analysis workflow and return the final report."""
    crew = Crew(
        agents=[techie],
        tasks=[task],
        process=Process.sequential
    )
    result = crew.kickoff()
    return str(result)


# 3. Launch the crew
if __name__ == "__main__":
    result = run_qw_analysis()
    print("######################")
    print(result)