"""Isolated company trial gateway using real production routers and SQLite.

This deliberately omits the production PostgreSQL/Docker startup. It provides
department API/browser testing, not infrastructure or model acceptance.
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.engine import engine
from app.db.models import Base
from app.routes import auth, admin, enterprise


@asynccontextmanager
async def lifespan(app):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title='Company department trial — isolated SQLite', lifespan=lifespan)
app.add_middleware(CORSMiddleware,
    allow_origins=['http://127.0.0.1:13180', 'http://127.0.0.1:13181'],
    allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
for router in (auth.router, admin.router, enterprise.router):
    app.include_router(router)


@app.get('/api/ping')
async def ping():
    return {'service': 'company-trial', 'infrastructure': 'isolated_sqlite',
            'real_model_verified': False, 'docker_verified': False}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=18080)
