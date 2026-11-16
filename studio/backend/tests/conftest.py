import os
import tempfile
import pytest
os.environ['STUDIO_DATA_DIR'] = tempfile.mkdtemp(prefix='aas-tests-')
for name in ('DATABASE_URL','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','ASR_MODEL'):
    os.environ.pop(name, None)
from aas.db import init_db, Session, Episode, Job, Revision
from aas.api import app
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def clean():
    init_db()
    with Session.begin() as s:
        for model in (Job, Revision, Episode):
            s.query(model).delete()
    yield

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture
def body():
    return {'title':'Actos jurídicos', 'source':'# Unidad\n## Acto jurídico\nEl acto jurídico es el acto voluntario lícito que tiene por fin inmediato la adquisición, modificación o extinción de relaciones o situaciones jurídicas (Art. 259 CCCN).\n## Silencio\nEl silencio no es considerado como una manifestación de voluntad, excepto en los casos previstos por el artículo 263.\n', 'program':'- Acto jurídico\n- Silencio', 'target_minutes':10}
