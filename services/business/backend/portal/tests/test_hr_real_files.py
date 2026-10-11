"""Real PDF extraction and API boundaries; these tests never claim LLM success."""
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from portal.hr_matching import match_matrix, requirements_for, score_matrix
from portal.hr_recruitment_models import RecruitmentRequest
from portal.hr_resume_extract import inspect_pdf
from portal.hr_screening_models import ResumeArtifact
from portal.hr_screening_worker import claim_one, finish_one, process_one
from .base import PortalTestCase, json_body


class RealHrFileApiTests(PortalTestCase):
    def setUp(self):
        self.hr = self.create_user('real-files-hr', 'hr')
        self.login(self.client, self.hr)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.enterContext(override_settings(HR_STORAGE_ROOT=Path(self.directory.name) / 'private'))
        self.root = '/api/hr/recruitment/'

    def real_pdf(self, *, scanned=False):
        runtime = Path(settings.PRODUCT_DOCUMENT_PYTHON)
        if not runtime.is_file():
            self.skipTest('isolated PDF document runtime unavailable')
        target = Path(self.directory.name) / ('scan.pdf' if scanned else 'text.pdf')
        # The document process creates genuine PDF bytes. Extraction is not mocked.
        script = (
            'import fitz,sys; d=fitz.open(); p=d.new_page(); '
            'lines=["合成测试材料", "岗位名称：数据工程师", "学历要求：本科", "技能要求：SQL、Python"]; '
            '[p.insert_text((72,72+i*24),line,fontname="china-s",fontsize=12) for i,line in enumerate(lines)]; '
            'd.save(sys.argv[1]); '
        )
        if scanned:
            script += (
                'image=p.get_pixmap().tobytes("jpeg"); s=fitz.open(); q=s.new_page(); '
                'q.insert_image(q.rect,stream=image); s.save(sys.argv[1]+".scan",deflate=True); '
                'd.close(); s.close(); from pathlib import Path; '
                'Path(sys.argv[1]).write_bytes(Path(sys.argv[1]+".scan").read_bytes())'
            )
        subprocess.run([str(runtime), '-c', script, str(target)], check=True, timeout=30,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return target.read_bytes()

    def local_jd(self, body):
        response = self.client.post(self.root + 'requests/intake/', json_body(text=body),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        confirmed = self.client.post(self.root + f"requests/{data['request']['id']}/jd-versions/{data['jd']['id']}/confirm/",
                                      json_body(expected_version=1), content_type='application/json')
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        batch = self.client.post(self.root + 'batches/', json_body(jd_version_id=data['jd']['id']),
                                content_type='application/json', HTTP_IDEMPOTENCY_KEY='real-file-batch')
        self.assertEqual(batch.status_code, 201, batch.content)
        return data, batch.json()

    def test_real_chinese_pdf_intake_and_worker_without_model_authorization(self):
        content = self.real_pdf()
        uploaded = self.client.post(self.root + 'requests/upload-jd/', {
            'file': SimpleUploadedFile('chinese-jd.pdf', content)})
        self.assertEqual(uploaded.status_code, 201, uploaded.content)
        data = uploaded.json()
        self.assertEqual(data['jd']['source'], 'upload')
        self.assertIn('本科', data['jd']['body'])
        self.assertEqual(data['jd']['requirements']['skill_requirements'], ['SQL', 'Python'])
        confirmed = self.client.post(self.root + f"requests/{data['request']['id']}/jd-versions/{data['jd']['id']}/confirm/",
                                      json_body(expected_version=1), content_type='application/json')
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        batch = self.client.post(self.root + 'batches/', json_body(jd_version_id=data['jd']['id']),
                                content_type='application/json', HTTP_IDEMPOTENCY_KEY='real-pdf-batch').json()
        base = self.root + f"batches/{batch['id']}/"
        uploaded = self.client.post(base + 'resumes/', {'expected_version': 1,
            'files': [SimpleUploadedFile('chinese-resume.pdf', content)]})
        self.assertEqual(uploaded.status_code, 201, uploaded.content)
        artifact = uploaded.json()['artifacts'][0]
        download = self.client.get(self.root + f"resumes/{artifact['id']}/download/")
        self.assertEqual(hashlib.sha256(b''.join(download.streaming_content)).hexdigest(), artifact['sha256'])
        self.assertEqual(self.client.post(base + 'run/', json_body(expected_version=2),
                                         content_type='application/json').status_code, 200)
        process_one(*claim_one())
        item = ResumeArtifact.objects.get(pk=artifact['id'])
        self.assertEqual((item.processing_status, item.error_code), ('failed', 'forbidden'))
        self.assertEqual(item.profile, {})
        self.assertEqual(item.match, {})
        self.assertEqual(self.client.get(base + 'progress/').json()['status'], 'partial_failed')

    def test_real_scan_is_rejected_for_jd_but_saved_for_explicit_vision_resume_stage(self):
        content = self.real_pdf(scanned=True)
        pages = inspect_pdf('scan.pdf', content)
        self.assertEqual(len(pages), 1)
        self.assertTrue(pages[0]['needs_vision'])
        self.assertEqual(pages[0]['text'].strip(), '')
        response = self.client.post(self.root + 'requests/upload-jd/', {
            'file': SimpleUploadedFile('scan.pdf', content)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'text_unavailable')
        self.assertEqual(RecruitmentRequest.objects.count(), 0)
        _, batch = self.local_jd('合成测试材料\n岗位名称：工程师\n技能要求：SQL')
        response = self.client.post(self.root + f"batches/{batch['id']}/resumes/", {
            'expected_version': 1, 'files': [SimpleUploadedFile('scan.pdf', content)]})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['batch']['prescreened'], 1)

    def test_real_csv_export_escapes_filename_and_marks_history_stale(self):
        data, batch = self.local_jd('合成测试材料\n岗位名称：工程师\n技能要求：SQL')
        base = self.root + f"batches/{batch['id']}/"
        content = '合成测试材料\n技能：SQL'.encode()
        response = self.client.post(base + 'resumes/', {'expected_version': 1,
            'files': [SimpleUploadedFile('=1+1.txt', content)]})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.client.post(base + 'run/', json_body(expected_version=2),
                                         content_type='application/json').status_code, 200)
        claimed = claim_one()
        text = content.decode()
        required = requirements_for(data['jd']['requirements'])
        # Protocol fixture supplies verdicts; the real validator/scorer checks source evidence.
        matrix = match_matrix(json.dumps({'requirements': [
            {'requirement_id': required[0]['id'], 'verdict': 'MATCH', 'evidence': [{'quote': 'SQL'}]}
        ]}), required, text)
        self.assertTrue(finish_one(*claimed, extraction={'text': text}, profile={},
                                  match={'matrix': matrix, 'score': score_matrix(matrix)}))
        response = self.client.get(base + 'export/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'\xef\xbb\xbf'))
        rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(rows[1][0], "'=1+1.txt")
        self.assertEqual(rows[1][2], '1')
        request_url = self.root + f"requests/{data['request']['id']}/"
        self.assertEqual(self.client.patch(request_url, json_body(expected_version=1, notes='合成测试需求更新'),
                                          content_type='application/json').status_code, 200)
        response = self.client.get(base + 'export/')
        rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(rows[1][5], 'True')
        self.assertEqual(rows[1][6], 'rule-v1-no-age-20260926')
