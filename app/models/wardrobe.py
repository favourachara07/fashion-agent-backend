from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.core.database import Base, engine

class WardrobeItem(Base):
    __tablename__ = "wardrobe_items"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(String, unique=True, index=True) # E.g., the filename like "garment3.jpg"
    category = Column(String)
    style = Column(String)
    color = Column(String)
    description = Column(String)
    is_long = Column(Boolean, default=False)
    user_id = Column(Integer, ForeignKey("users.id"))

# Automatically create the tables when this file is imported
Base.metadata.create_all(bind=engine)