import os
from pathlib import Path
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process

try:
    from .news_tool import search_news  # package/module execution
except ImportError:
    from news_tool import search_news  # direct script execution

# Always resolve .env from project root, independent of current working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

# CrewAI expects either a model string or its own BaseLLM-compatible config.
llm_model = "gemini/gemini-2.5-flash"

# 1. Agent configuration
NewsGuy = Agent(
    role='Senior Financial Investigative Journalist & Sentiment Analyst.',
    goal='Find the main catalyst behind each move and answer briefly.',
    backstory="You are a world-class financial correspondent who has worked for Bloomberg and Reuters." \
    " You believe that while numbers (quantitative data) show the 'what,' " \
    "only news and market sentiment show the 'why.' You specialize in connecting sudden price movements to real-world events," \
    " such as earnings calls, geopolitical shifts, regulatory changes, product launches, and major company announcements." \
    " Use live news results when explaining catalysts and keep the final answer short.",
    tools=[search_news],
    llm=llm_model,
    allow_delegation=False
)

# 2. Task description
def run_news_scout(volatility_summary: str = "") -> str:
    """Run the CrewAI risk analysis workflow and return the final report."""
    if volatility_summary:
        task = Task(
            description=(
                "Use the volatility summary below as the quantitative input. Do not ask for more stock metrics. "
                "Identify the main news catalyst for each volatile ticker and keep the answer short.\n\n"
                f"Volatility summary:\n{volatility_summary}"
            ),
            expected_output="Max 5 bullets total. For each ticker: 1 bullet with the catalyst and 1 short sentiment tag (Bullish/Bearish/Neutral). If no clear news exists, say 'technical/liquidity'. No long paragraphs.",
            agent=NewsGuy,
        )
    else:
        task = Task(
            description="Take the volatile tickers and identify the main news catalyst for each one. Use the news tool only for the most relevant headlines and avoid extra context. Return a short report only.",
            expected_output="Max 5 bullets total. For each ticker: 1 bullet with the catalyst and 1 short sentiment tag (Bullish/Bearish/Neutral). If no clear news exists, say 'technical/liquidity'. No long paragraphs.",
            agent=NewsGuy,
        )

    crew = Crew(
        agents=[NewsGuy],
        tasks=[task],
        process=Process.sequential
    )
    result = crew.kickoff()
    return str(result)


# 3. Launch the crew
if __name__ == "__main__":
    result = run_news_scout()
    print("######################")
    print(result)