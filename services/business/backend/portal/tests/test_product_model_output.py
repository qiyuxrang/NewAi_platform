import json

from django.test import SimpleTestCase

from portal.product_worker import ExecutionError, _parse_model_output


class ProductModelOutputParserTests(SimpleTestCase):
    def test_accepts_object_json_formats(self):
        expected = {"title": "测试方案", "nested": {"note": "简体中文内容"}}
        obj = json.dumps(expected, ensure_ascii=False)
        inputs = (
            ("bare object", f" \t{obj} \n"),
            ("json fence LF", f"```json\n{obj}\n```"),
            ("json fence CRLF", f"```json\r\n{obj}\r\n```"),
            ("unlabeled fence LF", f"  ```\n{obj}\n```  "),
            ("unlabeled fence CRLF", f"```\r\n{obj}\r\n```\r\n"),
        )
        for label, raw in inputs:
            with self.subTest(format=label):
                self.assertEqual(_parse_model_output(raw), expected)

    def test_rejects_invalid_model_output(self):
        invalid = (
            ("leading explanation", "说明\n```json\n{}\n```"),
            ("trailing explanation", "```json\n{}\n```\n说明"),
            ("multiple fences", "```json\n{}\n```\n```json\n{}\n```"),
            ("missing opening fence", "{}\n```"),
            ("missing closing fence", "```json\n{}"),
            ("top-level array", "[]"),
            ("fenced array", "```json\n[]\n```"),
            ("duplicate top-level key", '{"key": 1, "key": 2}'),
            ("duplicate nested key", '{"outer": {"key": 1, "key": 2}}'),
            ("NaN", '{"value": NaN}'),
            ("Infinity", '{"value": Infinity}'),
            ("negative Infinity", '{"value": -Infinity}'),
            ("invalid escape", r'{"value": "\x"}'),
            ("invalid JSON", '{"value":}'),
        )
        for label, raw in invalid:
            with self.subTest(format=label):
                with self.assertRaises(ExecutionError) as error:
                    _parse_model_output(raw)
                self.assertEqual(error.exception.code, "invalid_model_output")
