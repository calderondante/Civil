import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, JSON, Integer, Float, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from pathlib import Path

DATA = Path(os.getenv('STUDIO_DATA_DIR', './data')).resolve()
DATA.mkdir(parents=True, exist_ok=True)
url = os.getenv('DATABASE_URL', f'sqlite:///{DATA}/studio.sqlite3')
if url.startswith('postgresql://'):
    url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 30} if url.startswith('sqlite') else {}, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase): pass

class Episode(Base):
    __tablename__ = 'aas_episodes'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    data: Mapped[dict] = mapped_column(JSON)

class Revision(Base):
    __tablename__ = 'aas_revisions'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str] = mapped_column(String(36), index=True)
    data: Mapped[dict] = mapped_column(JSON)

class Job(Base):
    __tablename__ = 'aas_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    episode_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True, default='queued')
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    lease_token: Mapped[str] = mapped_column(String(36), default='')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(String(500), default='')

active_job_index = Index('uq_aas_jobs_active_episode', Job.episode_id, unique=True,
                         postgresql_where=Job.status.in_(['queued','running']),
                         sqlite_where=Job.status.in_(['queued','running']))

def init_db():
    Base.metadata.create_all(engine)
    active_job_index.create(engine, checkfirst=True)
