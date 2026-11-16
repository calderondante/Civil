"""Private artifacts: local for development; Supabase private bucket in production."""
import os
from pathlib import Path
import httpx
from .db import DATA

class Storage:
    def __init__(self):
        self.url = os.getenv('SUPABASE_URL', '').rstrip('/')
        self.key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
        self.bucket = os.getenv('SUPABASE_BUCKET', 'academic-audio')
        if bool(self.url) != bool(self.key):
            raise RuntimeError('Configurá SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY juntas.')

    def endpoint(self, key):
        from urllib.parse import quote
        return f'{self.url}/storage/v1/object/{quote(self.bucket)}/{quote(key, safe="/")}'

    def put(self, key, content, mime='application/octet-stream'):
        self.validate(key)
        if self.url:
            with httpx.Client(timeout=120) as c:
                r = c.post(self.endpoint(key), headers={'Authorization': f'Bearer {self.key}', 'apikey': self.key, 'x-upsert': 'true', 'Content-Type': mime}, content=content)
                r.raise_for_status()
        else:
            path = DATA / 'artifacts' / key
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(path.suffix+'.tmp')
            temp.write_bytes(content); temp.replace(path)

    def get(self, key):
        self.validate(key)
        if self.url:
            r = httpx.get(self.endpoint(key), headers={'Authorization': f'Bearer {self.key}', 'apikey': self.key}, timeout=120)
            r.raise_for_status(); return r.content
        return (DATA / 'artifacts' / key).read_bytes()

    @staticmethod
    def validate(key):
        if key.startswith('/') or '..' in key.split('/') or not key:
            raise ValueError('Clave de almacenamiento inválida.')
