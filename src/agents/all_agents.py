from typing import Callable, Dict

from src.agents.risk_agent import run_risk_analysis
from src.agents.tech_agent import run_qw_analysis
from src.agents.News_Scout import run_news_scout

ANALYSTS: Dict[str, Callable[[], str]] = {
    "risk": run_risk_analysis,
    "tech": run_qw_analysis,
    "news": run_news_scout,
}

__all__ = ["ANALYSTS"]
