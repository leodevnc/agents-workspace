import os
import tempfile
from pathlib import Path

os.environ['CHIEF_DB_PATH'] = str(Path(tempfile.mkdtemp()) / 'test.sqlite3')
os.environ.pop('OPENAI_API_KEY', None)
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_complete_review_workflow():
    assert client.get('/api/health').json()['mode'] == 'demo'
    response = client.post('/api/tasks', json={'title':'Release review','description':'Assess release risks','domain':'engineering','priority':1})
    assert response.status_code == 201
    task_id = response.json()['id']
    assert client.post(f'/api/tasks/{task_id}/decision', json={'action':'approve'}).status_code == 409
    result = client.post(f'/api/tasks/{task_id}/run')
    assert result.status_code == 200
    assert result.json()['status'] == 'pending_review'
    assert 'DEMO ONLY' in result.json()['chief_summary']
    assert client.post(f'/api/tasks/{task_id}/run').status_code == 409
    decision = client.post(f'/api/tasks/{task_id}/decision',json={'action':'approve','note':'Approved for planning'})
    assert decision.json()['status'] == 'approved'
    assert client.post(f'/api/tasks/{task_id}/decision',json={'action':'approve'}).status_code == 409
    assert any(d['task_id']==task_id for d in client.get('/api/decisions').json())


def test_rejection_and_revision():
    item = client.post('/api/tasks',json={'title':'Market scan','description':'Compare options','domain':'research'}).json()
    task_id = item['id']
    assert client.post(f'/api/tasks/{task_id}/run').status_code == 200
    assert client.post(f'/api/tasks/{task_id}/decision',json={'action':'reject','note':'Add alternatives'}).json()['status']=='rejected'
    assert client.post(f'/api/tasks/{task_id}/run').json()['status']=='pending_review'


def test_validation_and_unknown_task():
    assert client.post('/api/tasks',json={'title':'X','description':'Y','priority':5}).status_code==422
    assert client.post('/api/tasks/999999/run').status_code==404


def test_review_evidence_and_stale_decision():
    task = client.post('/api/tasks', json={
        'title': 'Review demo',
        'description': 'Check the screenshot and recording',
        'evidence': [
            {'kind': 'screenshot', 'url': 'https://example.com/demo.png'},
            {'kind': 'video', 'url': 'https://example.com/demo.mp4'},
        ],
    }).json()
    task_id = task['id']
    assert [item['kind'] for item in task['evidence']] == ['screenshot', 'video']
    review = client.post(f'/api/tasks/{task_id}/run').json()
    assert review['evidence'] == task['evidence']
    endpoint = f'/api/tasks/{task_id}/decision'
    assert client.post(endpoint, json={
        'action': 'approve', 'review_version': task['updated_at'],
    }).status_code == 409
    assert client.post(endpoint, json={
        'action': 'approve', 'review_version': review['updated_at'],
    }).status_code == 200


def test_reject_non_web_evidence_url():
    response = client.post('/api/tasks', json={
        'title': 'Unsafe evidence',
        'description': 'Reject non-web URLs',
        'evidence': [{'kind': 'link', 'url': 'javascript:alert(1)'}],
    })
    assert response.status_code == 422


def test_cross_origin_write_is_blocked():
    response = client.post('/api/tasks/1/run', headers={'Origin': 'https://example.com'})
    assert response.status_code == 403


def test_background_job_priority_approval_and_retry(monkeypatch):
    from app import worker

    monkeypatch.setenv('CHIEF_BACKGROUND_JOBS', '1')
    monkeypatch.setenv('CHIEF_GITHUB_REPO', 'example/workspace')

    def create(priority):
        return client.post('/api/tasks', json={
            'title': 'Review an engineering change',
            'description': 'Implement a small change',
            'priority': priority,
        }).json()['id']

    low = create(3)
    high = create(1)
    endpoint = f'/api/tasks/{high}/jobs/code'
    assert client.post(endpoint).status_code == 409
    assert client.post(f'/api/tasks/{high}/run').status_code == 409
    assert worker.process_one()
    listed = {task['id']: task for task in client.get('/api/tasks').json()}
    assert listed[high]['status'] == 'pending_review'
    assert listed[low]['job']['state'] == 'queued'
    assert client.post(f'/api/tasks/{high}/decision', json={'action': 'approve'}).status_code == 200
    job_id = client.post(endpoint).json()['id']
    assert client.post(endpoint).json()['id'] == job_id

    calls = []

    def publish(task, queued_id, target_repo, model_text):
        assert task['id'] == high
        assert target_repo == 'example/workspace'
        calls.append(queued_id)
        if len(calls) == 1:
            raise worker.code_changes.CodeJobError('Temporary test error')
        return 'https://github.com/example/workspace/pull/1'

    monkeypatch.setattr(worker.code_changes, 'publish', publish)
    assert worker.process_one()
    assert client.post(endpoint).json()['id'] == job_id
    assert worker.process_one()
    listed = {task['id']: task for task in client.get('/api/tasks').json()}
    assert listed[high]['job']['state'] == 'done'
    assert listed[high]['job']['result'].endswith('/pull/1')
    assert calls == [job_id, job_id]
    assert worker.process_one()


def test_code_edits_cannot_escape_configured_files():
    import pytest
    from app.code_changes import CodeJobError, parse_edits

    sources = {'app/main.py': ('100644', 'old')}
    assert parse_edits('{"app/main.py":"new"}', sources) == {'app/main.py': 'new'}
    with pytest.raises(CodeJobError):
        parse_edits('{"app/main.py":"new",".github/workflows/ci.yml":"modified"}', sources)
    with pytest.raises(CodeJobError):
        parse_edits('{"app/main.py":"old"}', sources)
