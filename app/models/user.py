from sqlalchemy import Column, Integer, String
from app.core.database import Base, engine

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

# Base.metadata.create_all is called in main.py or wardrobe.py usually, 
# but it's safe to call it here to ensure the table exists
Base.metadata.create_all(bind=engine)
