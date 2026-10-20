from copy import deepcopy
from datetime import date
import unittest

from portal.baichuan_conditions import ConditionError, combine, compile_conditions, evaluate_conditions


def requirement(**changes):
    node = {"field": "qualification", "category": "itss", "op": "grade_exact", "value": "2", "holder": "bidder"}
    node.update(changes)
    return node


def tree(node=None, **changes):
    result = {"schema_version": 1, "revision": 1, "must": node or requirement()}
    result.update(changes)
    return compile_conditions(result, today=date(2026, 10, 17))


RULES = {"itss": {"enabled": True, "version": "test-itss-v1", "source": "fixture://fictional-rules",
                  "grades": ["1", "2", "3", "4"], "at_least": {"2": ["1", "2"]}},
         "cs": {"enabled": True, "version": "test-cs-v1", "source": "fixture://fictional-rules",
                "grades": ["1", "2", "3", "4", "5"], "at_least": {"2": ["2", "3", "4", "5"]}}}


def company():
    return {"id": "fictional-company", "province": "广东省",
            "field_verification": {"province": {"status": "verified", "evidence_ids": ["geo-source"]}},
            "certificates": [{"category": "itss", "grade": "2", "holder_type": "bidder",
                              "holder_company_id": "fictional-company", "verification_status": "verified",
                              "assertion_status": "PRESENT", "evidence_ids": ["certificate-source"],
                              "evidence_status": "verified", "valid_from": "2025-01-01", "valid_until": "2027-01-01",
                              "revocation_status": "clear"}]}


class ConditionTests(unittest.TestCase):
    def result(self, row=None, compiled=None, rules=None):
        return evaluate_conditions(compiled or tree(), row or company(), rules=RULES if rules is None else rules)

    def test_strict_bounded_language_rejects_instructions_and_orm_paths(self):
        invalid = [requirement(field="company.__dict__"), requirement(op="raw_sql"), requirement(sql="SELECT 1"),
                   requirement(holder="group"), requirement(value=2), requirement(value="2\x00"),
                   {"all": []}, {"all": [requirement()], "any": [requirement()]},
                   {"all": [requirement()] * 51}, {"not": {"not": {"not": {"not": {"not": {"not": {"not": {"not": {"not": requirement()}}}}}}}}}]
        for node in invalid:
            with self.subTest(node=node), self.assertRaises(ConditionError):
                tree(node)
        for changes in ({"revision": True}, {"schema_version": True}, {"output": {"fields": ["name"], "limit": True}},
                        {"output": {"fields": ["name", "name"], "limit": 2}}, {"unresolved": "x"},
                        {"as_of": {"date": "2026-02-30", "basis": "user_date"}}, {"tool": "execute"}):
            with self.subTest(changes=changes), self.assertRaises(ConditionError):
                tree(**changes)

    def test_all_four_values_and_boolean_short_circuit_rules(self):
        self.assertEqual(combine("all", ["failed", "conflict"]), "failed")
        self.assertEqual(combine("all", ["satisfied", "unknown"]), "unknown")
        self.assertEqual(combine("any", ["satisfied", "unknown"]), "satisfied")
        self.assertEqual(combine("any", ["failed", "conflict"]), "conflict")
        self.assertEqual(combine("not", ["unknown"]), "unknown")
        self.assertEqual(combine("not", ["conflict"]), "conflict")
        self.assertEqual(combine("not", ["failed"]), "satisfied")

    def test_confirmed_requires_subject_evidence_dates_and_active_status(self):
        self.assertEqual(self.result()["status"], "confirmed")
        for changes in ({"holder_company_id": "parent-company"}, {"holder_type": "manufacturer"},
                        {"verification_status": "unverified"}, {"evidence_ids": []}, {"evidence_status": "snippet"},
                        {"valid_from": None}, {"valid_until": None}, {"revocation_status": "unknown"},
                        {"assertion_status": "UNKNOWN"}):
            row = company()
            row["certificates"][0].update(changes)
            with self.subTest(changes=changes):
                self.assertEqual(self.result(row)["status"], "candidate")
        row = company()
        row["certificates"][0]["verification_status"] = "conflict"
        self.assertEqual(self.result(row)["verdict"], "conflict")
        row["certificates"].append(company()["certificates"][0])
        self.assertEqual(self.result(row)["status"], "candidate")

    def test_missing_or_failed_certificate_is_not_exhaustive_absence(self):
        for changes in ({"grade": "3"}, {"revocation_status": "revoked"},
                        {"valid_until": "2025-01-01"}, {"valid_from": "2027-01-01", "valid_until": "2028-01-01"}):
            row = company()
            row["certificates"][0].update(changes)
            self.assertEqual(self.result(row)["status"], "candidate")
            row["category_verification"] = {"itss": {"status": "verified", "exhaustive": True,
                "as_of": "2026-10-17", "holder": "bidder", "evidence_ids": ["complete-check"]}}
            self.assertEqual(self.result(row)["status"], "excluded")
        row = company()
        row["certificates"] = []
        self.assertEqual(self.result(row)["status"], "candidate")

    def test_exact_and_opposite_grade_directions_only_use_versioned_rules(self):
        row = company()
        row["certificates"][0]["grade"] = "1"
        self.assertEqual(self.result(row)["status"], "candidate")
        self.assertEqual(self.result(row, tree(requirement(op="grade_at_least")))["status"], "confirmed")
        row["certificates"][0].update(category="cs", grade="3")
        self.assertEqual(self.result(row, tree(requirement(category="cs", op="grade_at_least")))["status"], "confirmed")
        for rules, node in (({}, requirement()), ({"itss": {**RULES["itss"], "source": ""}}, requirement()),
                            (RULES, requirement(rule_version="wrong")), (RULES, requirement(category="unknown")),
                            ({"itss": {**RULES["itss"], "at_least": {}}}, requirement(op="grade_at_least"))):
            self.assertEqual(self.result(compiled=tree(node), rules=rules)["status"], "candidate")

    def test_related_dates_and_unknown_company_fields_never_confirm(self):
        node = {"field": "company.province", "op": "eq", "value": "广东省"}
        self.assertEqual(self.result(compiled=tree(node))["status"], "confirmed")
        row = company()
        row["field_verification"] = {}
        self.assertEqual(self.result(row, tree(node))["status"], "candidate")
        row = company()
        row["province"] = "江苏省"
        self.assertEqual(self.result(row, tree(node))["status"], "excluded")
        self.assertEqual(self.result(compiled=tree(as_of={"date": "2028-01-01", "basis": "tender_date"}))["status"], "candidate")

    def test_unresolved_hard_conditions_and_preferences_cannot_override_failure(self):
        self.assertEqual(self.result(compiled=tree(unresolved=["联合体条件待确认"]))["status"], "candidate")
        node = {"field": "company.province", "op": "eq", "value": "江苏省"}
        result = self.result(compiled=tree(node, should=[requirement()]))
        self.assertEqual(result["status"], "excluded")
        self.assertEqual(result["preferences"], ["satisfied"])

    def test_input_not_mutated_and_condition_ids_are_stable(self):
        original = {"schema_version": 1, "revision": 1, "must": {"all": [requirement(), {"any": [requirement(), requirement(grade="3")]}]}}
        # A misspelled model output is rejected rather than silently corrected.
        with self.assertRaises(ConditionError):
            compile_conditions(original)
        original["must"]["all"][1]["any"][1].pop("grade")
        saved = deepcopy(original)
        result = self.result(compiled=compile_conditions(original, today=date(2026, 10, 17)))
        self.assertEqual(original, saved)
        self.assertEqual([item["condition_id"] for item in result["conditions"]], ["must.0", "must.1.0", "must.1.1"])
