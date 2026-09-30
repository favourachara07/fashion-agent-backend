from pydantic import BaseModel, Field
from typing import List

class DailyOutfit(BaseModel):
    day: str = Field(description="Day of the week")
    event_context: str = Field(description="Event driving the choice")
    top_id: str = Field(description="Exact item_id from the wardrobe database")
    bottom_id: str = Field(description="Exact item_id from database, or 'none'")
    reasoning: str = Field(description="Explanation based on weather/event")

class WeeklyWardrobePlan(BaseModel):
    plan: List[DailyOutfit] = Field(description="A 7-day array of daily outfit selections")
